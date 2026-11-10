"""The pipeline: robots → capture → understand → analyse → check → hypotheses → report.

Every step writes started/done/failed events to steps.jsonl; the CLI and the web UI
both read progress from there (or from the on_event callback)."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any

from cro_lens.capture.browser import CaptureResult, capture, load_capture
from cro_lens.capture.robots import check_robots
from cro_lens.config import CroLensError, InvalidInput, now_iso, validate_url
from cro_lens.feedback import Feedback, load_feedback, prompt_block, save_feedback, select
from cro_lens.llm.provider import Image, Provider, Request, billing
from cro_lens.models import (
    ICE,
    AnalysisOut,
    Block,
    Call,
    Check,
    CheckOut,
    Cost,
    Experiment,
    FeedbackInfo,
    Finding,
    Given,
    HypothesesOut,
    Report,
    RunInfo,
    Top3,
    Understanding,
)
from cro_lens.pipeline.check import check_evidence, confidence
from cro_lens.pipeline.state import (
    HEARTBEAT,
    HEARTBEAT_S,
    LLM_ORDER,
    RUN_SPEC,
    RunSpec,
    capture_dir,
    capture_reusable,
    heartbeat_fresh,
    load_checkpoint,
    read_spec,
    resume_point,
    save_checkpoint,
    write_atomic,
)
from cro_lens.report import images
from cro_lens.report.render_md import render_markdown

Event = dict
_MISSING = object()
OnEvent = Callable[[Event], None]


def prompt(name: str) -> str:
    return files("cro_lens.prompts").joinpath(f"{name}.md").read_text(encoding="utf-8")


@dataclass
class Options:
    model: str = "sonnet"
    given: Given = field(default_factory=Given)
    feedback: bool = True  # learn from the user's graded findings (eval@2)


class StepLog:
    def __init__(self, path: Path, on_event: OnEvent | None) -> None:
        self.path, self.on_event = path, on_event
        path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, step: str, status: str, **extra) -> None:
        ev = {
            "step": step,
            "status": status,
            "t": now_iso(),
            **{k: v for k, v in extra.items() if v is not None},
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        if self.on_event:
            self.on_event(ev)


def blocks_text(blocks: list[Block], max_y: int | None = None, limit: int = 260) -> str:
    rows = []
    for b in blocks:
        if max_y is not None and b.bbox[1] > max_y:
            continue
        text = b.text if len(b.text) <= 240 else b.text[:240] + "…"
        rows.append(f'{b.id} [{b.role} {b.tag}] y={b.bbox[1]}: "{text}"')
        if len(rows) >= limit:
            rows.append(f"… ({len(blocks) - limit} more blocks not listed)")
            break
    return "\n".join(rows)


def given_text(g: Given) -> str:
    parts = [f"{k}: {v}" for k, v in g.model_dump().items() if v]
    return (
        "User-supplied context (use as given): " + "; ".join(parts) if parts else "No user-supplied context."
    )


class Pipeline:
    def __init__(self, provider: Provider, opts: Options, out: Path, on_event: OnEvent | None = None) -> None:
        self.p, self.opts, self.out = provider, opts, out
        self.log = StepLog(out / "steps.jsonl", on_event)
        self.calls: list[Call] = []
        self.resuming = False
        self.fb: Feedback | None = None  # what this run learns from; None for runs from before 0.3

    def _step(self, name: str, fn: Callable, detail: Callable | None = None):
        self.log.emit(name, "started")
        t = time.time()
        try:
            res = fn()
        except CroLensError as e:
            self.log.emit(name, "failed", seconds=round(time.time() - t, 2), detail=str(e))
            raise
        except Exception as e:
            self.log.emit(
                name, "failed", seconds=round(time.time() - t, 2), detail=f"{type(e).__name__}: {e}"
            )
            raise
        except BaseException as e:  # Ctrl-C or shutdown: leave a resumable trace, not a "running" ghost
            self.log.emit(
                name, "failed", seconds=round(time.time() - t, 2), detail=f"interrupted ({type(e).__name__})"
            )
            raise
        self.log.emit(name, "done", seconds=round(time.time() - t, 2), detail=detail(res) if detail else None)
        return res

    def _call(self, req: Request):
        out, call = self.p.complete(req)
        self.calls.append(call)
        raw = self.out / "llm"
        raw.mkdir(exist_ok=True)
        (raw / f"{req.step}.json").write_text(out.model_dump_json(indent=1, by_alias=True), encoding="utf-8")
        return out

    # ---------------- steps ----------------
    def understand(self, cap: CaptureResult) -> Understanding:
        d = cap.dir
        parts: list[str | Image] = [
            "First desktop screen:",
            images.fold(d / "desktop_fold.png", "desktop"),
            "First mobile screen:",
            images.fold(d / "mobile_fold.png", "mobile"),
            f"Page title: {cap.meta.title}\nURL: {cap.meta.final_url}\n{given_text(self.opts.given)}\n\n"
            "Desktop text blocks (first two screens):\n"
            + blocks_text(cap.blocks["desktop"], max_y=1800)
            + "\n\nMobile text blocks (first two screens):\n"
            + blocks_text(cap.blocks["mobile"], max_y=1700, limit=80),
        ]
        req = Request(
            "understand",
            prompt("understand"),
            parts,
            Understanding,
            self.opts.model,
            {"blocks": cap.blocks, "given": self.opts.given.model_dump()},
        )
        u: Understanding = self._call(req)  # type: ignore[assignment]
        g = self.opts.given
        if g.audience:
            u.audience.value, u.audience.source = g.audience, "given"
        if g.traffic:
            u.traffic_source.value, u.traffic_source.source = g.traffic, "given"
        return u

    def analyse(self, cap: CaptureResult, u: Understanding) -> AnalysisOut:
        d = cap.dir
        dt, dcov, dtr = images.tiles(d / "desktop_full.png", "desktop")
        mt, mcov, mtr = images.tiles(d / "mobile_full.png", "mobile")
        cap.meta.viewports["desktop"].tiles_sent = len(dt)
        cap.meta.viewports["desktop"].truncated = dtr
        cap.meta.viewports["mobile"].tiles_sent = len(mt)
        cap.meta.viewports["mobile"].truncated = mtr
        if cap.dir.resolve().is_relative_to(self.out.resolve()):  # only this run's own capture
            (cap.dir / "meta.json").write_text(cap.meta.model_dump_json(indent=2), encoding="utf-8")
        sp = cap.meta.speed
        speed = (
            f"Lab speed (one local visit, mobile emulation): TTFB {sp.ttfb_ms} ms, LCP {sp.lcp_ms} ms, "
            f"load {sp.load_ms} ms, CLS {sp.cls}, {sp.requests} requests."
        )
        trunc = []
        if dtr:
            trunc.append(
                f"desktop screenshots stop at y={dcov}px of {cap.meta.viewports['desktop'].height}px"
            )
        if mtr:
            trunc.append(f"mobile screenshots stop at y={mcov}px of {cap.meta.viewports['mobile'].height}px")
        parts: list[str | Image] = (
            [f"Desktop page, {len(dt)} tiles top to bottom:"]
            + list(dt)
            + [f"Mobile page, {len(mt)} tiles top to bottom:"]
            + list(mt)
            + [
                f"URL: {cap.meta.final_url}\n{given_text(self.opts.given)}\n"
                f"Consent banner: present={cap.meta.consent_banner.present}, "
                f"dismissed={cap.meta.consent_banner.dismissed}\n{speed}\n"
                + (f"Not shown to you: {'; '.join(trunc)}.\n" if trunc else "")
                + "\nPage understanding from the previous step:\n"
                + u.model_dump_json(indent=1)
                + "\n\nDesktop text blocks:\n"
                + blocks_text(cap.blocks["desktop"], max_y=dcov)
                + "\n\nMobile text blocks:\n"
                + blocks_text(cap.blocks["mobile"], max_y=mcov, limit=140)
            ]
        )
        learned = prompt_block(self.fb, "analyse")
        if learned:
            parts.append(learned)
        req = Request(
            "analyse",
            prompt("analyse"),
            parts,
            AnalysisOut,
            self.opts.model,
            {"blocks": cap.blocks, "given": self.opts.given.model_dump(), "feedback": self._fb_context()},
        )
        return self._call(req)  # type: ignore[return-value]

    def check(self, cap: CaptureResult, a: AnalysisOut) -> list[Finding]:
        findings: list[Finding] = []
        for i, f in enumerate(a.findings, 1):
            ev = check_evidence(f, cap.blocks)
            ok = any(e.valid for e in ev)
            fid = f"F{i}"
            n = 0
            for e in ev:
                if not e.valid:
                    continue
                b = next(x for x in cap.blocks[e.viewport] if x.id == e.block_id)
                n += 1
                dest = self.out / "crops" / f"{fid}-{n}.png"
                if images.crop_block(cap.dir / f"{e.viewport}_full.png", b, e.viewport, dest):
                    e.crop = f"crops/{fid}-{n}.png"
            findings.append(
                Finding(
                    id=fid,
                    category=f.category,
                    kind=f.kind,
                    title=f.title,
                    personas=f.personas,
                    severity=f.severity,
                    reasoning=f.reasoning,
                    evidence=ev,
                    check=Check(
                        deterministic="pass" if ok else "fail",
                        verdict="kept" if ok else "dropped",
                        reason="quotes verified against the cited blocks"
                        if ok
                        else "evidence_not_found: no quote matched its cited block",
                    ),
                )
            )
        live = [f for f in findings if f.check.deterministic == "pass"]
        if not live:
            return findings
        parts: list[str | Image] = [
            "First desktop screen:",
            images.fold(cap.dir / "desktop_fold.png", "desktop"),
            "First mobile screen:",
            images.fold(cap.dir / "mobile_fold.png", "mobile"),
            "Every visible text block on the desktop page (use it to verify claims that something is absent "
            "or present elsewhere on the page):\n" + blocks_text(cap.blocks["desktop"], limit=400),
        ]
        for f in live:
            parts.append(
                f"--- {f.id} [{f.category}, {f.kind}, {f.severity}] {f.title}\nReasoning: {f.reasoning}\n"
                + "\n".join(f'Evidence {e.block_id} ({e.viewport}): "{e.quote}"' for e in f.evidence)
            )
            for e in f.evidence:
                if e.crop:
                    parts.append(f"Crop of {e.block_id}:")
                    parts.append(images.image_of(self.out / e.crop))
        learned = prompt_block(self.fb, "check")
        if learned:
            parts.append(learned)
        req = Request(
            "check",
            prompt("check"),
            parts,
            CheckOut,
            self.opts.model,
            {"finding_ids": [f.id for f in live], "blocks": cap.blocks, "feedback": self._fb_context()},
        )
        out: CheckOut = self._call(req)  # type: ignore[assignment]
        verdicts = {v.finding_id: v for v in out.verdicts}
        for f in live:
            v = verdicts.get(f.id)
            if v:
                f.check.verdict, f.check.reason = v.verdict, v.reason
            else:
                f.check.verdict, f.check.reason = "flagged", "self-check returned no verdict"
        return findings

    def hypotheses(
        self, u: Understanding, a: AnalysisOut, findings: list[Finding]
    ) -> tuple[list[Experiment], list[Top3], str]:
        live = [f for f in findings if f.check.verdict in ("kept", "flagged")]
        if not live:
            return [], [], "No finding survived the self-check, so there is nothing to test yet."
        payload = {
            "understanding": u.model_dump(),
            "lift": [s.model_dump() for s in a.lift],
            "findings": [
                {
                    "id": f.id,
                    "category": f.category,
                    "kind": f.kind,
                    "title": f.title,
                    "personas": f.personas,
                    "severity": f.severity,
                    "reasoning": f.reasoning,
                    "verdict": f.check.verdict,
                    "check_reason": f.check.reason,
                    "evidence": [{"block_id": e.block_id, "quote": e.quote} for e in f.evidence if e.valid],
                }
                for f in live
            ],
            "user_goal": self.opts.given.goal,
        }
        req = Request(
            "hypotheses",
            prompt("hypotheses"),
            [json.dumps(payload, ensure_ascii=False, indent=1)],
            HypothesesOut,
            self.opts.model,
            {"finding_ids": [f.id for f in live]},
        )
        h: HypothesesOut = self._call(req)  # type: ignore[assignment]
        by_id = {f.id: f for f in live}
        exps: list[Experiment] = []
        for x in h.experiments:
            f = by_id.get(x.finding_id)
            if f is None:
                continue
            conf, conf_why = confidence(f.check.verdict, f.category, f.personas, a.lift)
            score = round((x.impact + conf + x.ease) / 3, 2)
            exps.append(
                Experiment(
                    id="",
                    finding_id=f.id,
                    hypothesis=x.hypothesis,
                    change={"from": x.change.from_, "to": x.change.to},
                    suggested_copy=x.suggested_copy,
                    primary_metric=x.primary_metric,
                    guardrail_metric=x.guardrail_metric,
                    feasibility=x.feasibility,
                    ice=ICE(
                        impact=x.impact,
                        confidence=conf,
                        ease=x.ease,
                        score=score,
                        rationale={
                            "impact": x.impact_rationale,
                            "confidence": conf_why,
                            "ease": x.ease_rationale,
                        },
                    ),
                    flagged=f.check.verdict == "flagged",
                )
            )
        exps.sort(key=lambda e: e.ice.score, reverse=True)
        for i, e in enumerate(exps, 1):
            e.id = f"X{i}"
        top: list[Top3] = []
        for t in h.top3:
            best = next((e for e in exps if e.finding_id == t.finding_id), None)
            if best and all(x.experiment_id != best.id for x in top):
                top.append(Top3(experiment_id=best.id, why=t.why))
        for e in exps:
            if len(top) >= min(3, len(exps)):
                break
            if all(x.experiment_id != e.id for x in top):
                top.append(Top3(experiment_id=e.id, why=f"next highest ICE score ({e.ice.score})"))
        return exps, top[:3], h.summary

    def _fb_context(self) -> list[dict]:
        return [e.model_dump() for e in self.fb.examples] if self.fb else []

    # ---------------- run ----------------
    def run(self, url: str, run_id: str) -> Report:
        validate_url(url)
        spec = RunSpec(
            url=url,
            run_id=run_id,
            started_at=now_iso(),
            model=self.opts.model,
            given=self.opts.given,
        )
        write_atomic(self.out / RUN_SPEC, spec.model_dump_json(indent=2))
        # frozen at the start: a resume learns from exactly what the first attempt did
        self.fb = select(url, run_id) if self.opts.feedback else Feedback(enabled=False)
        save_feedback(self.out, self.fb)
        return self._execute(spec)

    @classmethod
    def for_resume(
        cls, provider: Provider, folder: Path, on_event: OnEvent | None = None, model: str | None = None
    ) -> tuple[Pipeline, RunSpec, str]:
        """A pipeline set up to continue the stopped run in `folder`, its spec, and the step it
        will start from. Raises InvalidInput when there is nothing that can be resumed."""
        spec = read_spec(folder)
        if spec is None:
            raise InvalidInput(f"not a cro-lens run folder (no run.json or capture): {folder}")
        if (folder / "report.json").exists():
            raise InvalidInput(f"run {spec.run_id} already finished; nothing to resume")
        if heartbeat_fresh(folder):
            raise InvalidInput(f"run {spec.run_id} is still running in another process")
        start = resume_point(folder)
        if start is None:
            raise InvalidInput(
                f"run {spec.run_id} stopped before the page capture finished; start a new audit "
                "instead (resuming would have to visit the page again)"
            )
        if model and model != spec.model:
            done = [s for s in LLM_ORDER if load_checkpoint(folder, s) is not None]
            if done and not spec.legacy:
                raise InvalidInput(
                    f"run {spec.run_id} already has {', '.join(done)} from {spec.model}; resume it "
                    f"with the same model, or start a new audit with {model}"
                )
            spec.model = model
        fb = load_feedback(folder)
        pipe = cls(
            provider,
            Options(model=spec.model, given=spec.given, feedback=bool(fb and fb.enabled)),
            folder,
            on_event,
        )
        pipe.fb = fb
        pipe.resuming = True
        return pipe, spec, start

    def resume(self, spec: RunSpec, start: str) -> Report:
        self.log.emit("resume", "done", detail=f"resuming from {start}")
        write_atomic(self.out / RUN_SPEC, spec.model_copy(update={"legacy": False}).model_dump_json(indent=2))
        return self._execute(spec)

    @contextmanager
    def _heartbeat(self):
        stop = threading.Event()
        path = self.out / HEARTBEAT

        def beat() -> None:
            while not stop.is_set():
                try:
                    path.write_text(now_iso(), encoding="utf-8")
                except OSError:
                    pass
                stop.wait(HEARTBEAT_S)

        t = threading.Thread(target=beat, name="cro-lens-heartbeat", daemon=True)
        t.start()
        try:
            yield
        finally:
            stop.set()
            t.join(timeout=5)
            try:  # never let cleanup replace the run's own result or error
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def _reuse(self, name: str, load: Callable[[Any], Any]) -> Any:
        """The saved result of `name` from an earlier attempt, or _MISSING."""
        if name in ("robots", "capture"):
            cap = capture_dir(self.out)
            if cap is None or not capture_reusable(self.out):
                return _MISSING
            return "kept from the earlier attempt" if name == "robots" else load_capture(cap)
        data = load_checkpoint(self.out, name)
        if data is None:
            return _MISSING
        try:
            res = load(data["result"])
            calls = [Call.model_validate(c) for c in data.get("calls", [])]
        except (ValueError, KeyError, TypeError, OSError):
            return _MISSING
        self.calls.extend(calls)
        return res

    def _stage(
        self,
        name: str,
        fn: Callable[[], Any],
        save: Callable[[Any], Any],
        load: Callable[[Any], Any],
        detail: Callable | None = None,
    ):
        """Run a step and checkpoint its result; on resume, reuse the checkpoint instead.
        Reuse stops at the first step that has to run again: later checkpoints were built
        on the old result."""
        if self.resuming:
            got = self._reuse(name, load)
            if got is not _MISSING:
                # supersedes any older failed/started event of this step in steps.jsonl
                self.log.emit(name, "done", detail="reused from the earlier attempt")
                return got
            if name in ("robots", "capture"):  # a resume must never fall back to a page visit
                raise InvalidInput("the capture of this run is missing or damaged; start a new audit instead")
            self.resuming = False
        n = len(self.calls)

        def run_and_save():
            res = fn()
            save_checkpoint(self.out, name, save(res), [c.model_dump() for c in self.calls[n:]])
            return res

        return self._step(name, run_and_save, detail)

    def _execute(self, spec: RunSpec) -> Report:
        with self._heartbeat():
            return self._steps(spec)

    def _steps(self, spec: RunSpec) -> Report:
        url, run_id, started = spec.url, spec.run_id, spec.started_at or now_iso()

        def keep(x: Any) -> Any:
            return x

        self._stage("robots", lambda: check_robots(url), save=keep, load=keep, detail=keep)
        cap = self._stage(
            "capture",
            lambda: capture(url, self.out / "capture"),
            save=lambda c: "capture",
            load=lambda d: load_capture(self.out / d),
            detail=lambda c: (
                f"desktop {len(c.blocks['desktop'])} blocks · mobile {len(c.blocks['mobile'])} blocks"
            ),
        )
        u = self._stage(
            "understand",
            lambda: self.understand(cap),
            save=lambda u: u.model_dump(mode="json"),
            load=Understanding.model_validate,
            detail=lambda u: f"audience: {u.audience.value[:80]} ({u.audience.confidence})",
        )
        a = self._stage(
            "analyse",
            lambda: self.analyse(cap, u),
            save=lambda a: a.model_dump(mode="json", by_alias=True),
            load=AnalysisOut.model_validate,
            detail=lambda a: f"{len(a.findings)} findings",
        )
        findings = self._stage(
            "check",
            lambda: self.check(cap, a),
            save=lambda fs: [f.model_dump(mode="json", by_alias=True) for f in fs],
            load=lambda d: [Finding.model_validate(f) for f in d],
            detail=lambda fs: (
                f"kept {sum(f.check.verdict == 'kept' for f in fs)} · "
                f"flagged {sum(f.check.verdict == 'flagged' for f in fs)} · "
                f"dropped {sum(f.check.verdict == 'dropped' for f in fs)}"
            ),
        )
        exps, top, summary = self._stage(
            "hypotheses",
            lambda: self.hypotheses(u, a, findings),
            save=lambda r: {
                "experiments": [e.model_dump(mode="json", by_alias=True) for e in r[0]],
                "top3": [t.model_dump(mode="json") for t in r[1]],
                "summary": r[2],
            },
            load=lambda d: (
                [Experiment.model_validate(e) for e in d["experiments"]],
                [Top3.model_validate(t) for t in d["top3"]],
                d["summary"],
            ),
            detail=lambda r: f"{len(r[0])} experiments",
        )

        def write() -> Report:
            rep = Report(
                run=RunInfo(
                    id=run_id,
                    url=url,
                    final_url=cap.meta.final_url,
                    started_at=started,
                    finished_at=now_iso(),
                    provider=self.p.name,
                    model=self.opts.model,
                    billing=billing(self.p),  # type: ignore[arg-type]
                    given=self.opts.given,
                    feedback=FeedbackInfo(**self.fb.summary()) if self.fb else None,
                ),
                capture=cap.meta,
                understanding=u,
                lift=a.lift,
                personas=a.personas,
                findings=findings,
                unverifiable=a.unverifiable,
                experiments=exps,
                top3=top,
                summary=summary,
                cost=Cost(total_usd_equivalent=round(sum(c.usd for c in self.calls), 4), calls=self.calls),
            )
            # report.json marks a finished run, so it is written last and atomically
            (self.out / "report.md").write_text(render_markdown(rep), encoding="utf-8")
            write_atomic(self.out / "report.json", rep.model_dump_json(indent=2, by_alias=True))
            return rep

        return self._step("report", write, detail=lambda r: "report.md · report.json")
