"""The local web app — contract ui@2 (ADR 0004).

Runs started here use the same Pipeline, provider and run folder as the CLI.
Run state is read from the run folder (steps.jsonl + report.json), so runs made
by the CLI show up too; exit codes of runs started in this process are kept in
memory, and inferred from the failed step for any other run."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import threading
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from cro_lens import __version__, feedback
from cro_lens.config import STEPS, CroLensError, new_run_id, provider_name, runs_dir, validate_url
from cro_lens.models import CATEGORIES, Given, Report
from cro_lens.pipeline.state import (
    alive,
    heartbeat_fresh,
    last_status,
    read_events,
    read_spec,
    resume_point,
)

HERE = Path(__file__).parent
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,80}$")
FINDING_ID_RE = re.compile(r"^F[0-9]{1,4}$")
LLM_STEPS = {"understand", "analyse", "check", "hypotheses"}
NO_STORE = {"Cache-Control": "no-store"}


# ---------------------------------------------------------------- run state
@dataclass
class Active:
    url: str
    started_at: str
    thread: threading.Thread | None = None
    exit_code: int | None = None
    error: str | None = None


@dataclass
class Runs:
    """Runs started by this process; everything else is read from disk."""

    active: dict[str, Active] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def reserve(self, url: str) -> tuple[str, Path]:
        root = runs_dir()
        root.mkdir(parents=True, exist_ok=True)
        with self.lock:
            base = new_run_id(url)
            run_id, n = base, 1
            while (root / run_id).exists() or run_id in self.active:
                n += 1
                run_id = f"{base}-{n}"
            folder = root / run_id
            folder.mkdir()
            self.active[run_id] = Active(url=url, started_at=datetime.now().astimezone().isoformat())
            return run_id, folder


def inferred_exit_code(step: str, detail: str) -> int:
    if step == "robots":
        return 3 if "disallow" in detail.lower() or "robots" in detail.lower() else 4
    if step == "capture":
        return 5 if any(w in detail.lower() for w in ("block", "challenge", "captcha")) else 4
    if step in LLM_STEPS:
        return 6
    return 1


def run_status(runs: Runs, run_id: str) -> dict[str, Any] | None:
    """{status, exit_code?, error?, resume_from?, url, started_at, events} or None when unknown.

    A step's state is its latest event, so a resumed run's new events supersede the old
    failure. A run with no end event whose process is gone (stale heartbeat) is failed
    as interrupted, so it can be resumed or deleted instead of showing "running" forever."""
    folder = runs_dir() / run_id
    act = runs.active.get(run_id)
    if not folder.is_dir() and act is None:
        return None
    events = read_events(folder)
    latest = last_status(events)
    failed = next((e for e in latest.values() if e.get("status") == "failed"), None)
    done = (folder / "report.json").exists() and latest.get("report", {}).get("status") == "done"
    thread_alive = bool(act and act.thread and act.thread.is_alive())
    url, started = (act.url, act.started_at) if act else ("", "")
    if not url:
        url, started = disk_run_info(folder, events)
    res: dict[str, Any] = {"url": url, "started_at": started, "events": events}
    if done:
        res["status"] = "done"
    elif thread_alive or (folder.is_dir() and heartbeat_fresh(folder)):
        res["status"] = "running"  # this process, or a CLI run/resume in another one
    elif failed:
        step = str(failed.get("step"))
        detail = str(failed.get("detail") or f"{step} failed")
        res.update(
            status="failed",
            exit_code=act.exit_code if act and act.exit_code else inferred_exit_code(step, detail),
            error=f"{step}: {detail}" if not detail.startswith(step) else detail,
        )
    elif folder.is_dir() and not (folder / "heartbeat").exists() and alive(folder):
        res["status"] = "running"  # a run from before heartbeats, judged by steps.jsonl age
    elif act and act.error is not None:
        res.update(status="failed", exit_code=act.exit_code or 1, error=act.error)
    else:
        stuck = next((s for s, e in latest.items() if e.get("status") == "started"), None)
        res.update(
            status="failed",
            exit_code=1,
            error=f"{stuck}: interrupted — the process running this step stopped"
            if stuck
            else "interrupted — the process running this audit stopped",
        )
    if res["status"] == "failed" and folder.is_dir():
        res["resume_from"] = resume_point(folder)
    return res


def disk_run_info(folder: Path, events: list[dict]) -> tuple[str, str]:
    url, started = "", events[0].get("t", "") if events else ""
    rep = folder / "report.json"
    meta = folder / "capture" / "meta.json"
    try:
        if rep.exists():
            data = json.loads(rep.read_text(encoding="utf-8"))
            return data["run"]["url"], data["run"].get("started_at") or started
        spec = read_spec(folder)  # run.json: known even when the capture failed
        if spec is not None:
            return spec.url, spec.started_at or started
        if meta.exists():
            url = json.loads(meta.read_text(encoding="utf-8")).get("url", "")
    except (ValueError, KeyError, OSError):
        pass
    return url, started


def list_runs(runs: Runs) -> list[dict]:
    root = runs_dir()
    ids = {d.name for d in root.iterdir() if d.is_dir()} if root.exists() else set()
    ids |= set(runs.active)
    rows = []
    for rid in ids:
        if not RUN_ID_RE.match(rid):
            continue
        st = run_status(runs, rid)
        if st is None:
            continue
        folder = root / rid
        ctime = folder.stat().st_ctime if folder.exists() else 0.0
        rows.append(
            (
                (rid[:15], ctime),
                {
                    "run_id": rid,
                    "url": st["url"],
                    "status": st["status"],
                    "started_at": st["started_at"],
                    "resume_from": st.get("resume_from"),
                },
            )
        )
    rows.sort(key=lambda r: r[0], reverse=True)
    return [r[1] for r in rows]


def load_report(run_id: str) -> dict | None:
    p = runs_dir() / run_id / "report.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- view helpers
def host_of(url: str) -> str:
    return urlparse(url).hostname or url


def fmt_ms(v: float | None) -> str:
    if v is None:
        return "–"
    return f"{v / 1000:.2f} s" if v >= 1000 else f"{v:.0f} ms"


def fmt_bytes(v: int | None) -> str:
    if v is None:
        return "–"
    return f"{v / 1_000_000:.2f} MB" if v >= 1_000_000 else f"{v / 1000:.0f} kB"


def fmt_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%d %b %Y, %H:%M")
    except (ValueError, TypeError):
        return iso or ""


def human(s: str) -> str:
    return str(s).replace("_", " ")


def report_view(rep: dict) -> dict:
    """Derived data the report template needs (no business logic, only layout)."""
    findings = rep.get("findings", [])
    by_id = {f["id"]: f for f in findings}
    exps = rep.get("experiments", [])
    exp_by_id = {e["id"]: e for e in exps}
    max_score = max([e["ice"]["score"] for e in exps] + [1])
    return {
        "live": [f for f in findings if f["check"]["verdict"] != "dropped"],
        "dropped": [f for f in findings if f["check"]["verdict"] == "dropped"],
        "finding": by_id,
        "exp": exp_by_id,
        "max_score": max_score,
        "exp_for_finding": {e["finding_id"]: e for e in exps},
        "host": host_of(rep["run"].get("final_url") or rep["run"]["url"]),
    }


# ---------------------------------------------------------------- app
def asset_version() -> str:
    """Cache key for /static links: changes whenever a CSS or JS file changes, not only on a release."""
    import hashlib

    h = hashlib.sha1()
    for f in sorted((HERE / "static").rglob("*")):
        if f.suffix in (".css", ".js"):
            h.update(f.read_bytes())
    return h.hexdigest()[:10]


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def create_app() -> FastAPI:
    app = FastAPI(title="cro-lens", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    env = Environment(
        loader=FileSystemLoader(HERE / "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(host=host_of, ms=fmt_ms, bytes=fmt_bytes, date=fmt_date, human=human, pct=feedback.pct)
    env.globals.update(STEPS=STEPS, CATEGORIES=CATEGORIES, version=__version__, asset_v=asset_version())
    runs = Runs()

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        """Refuse DNS-rebinding hosts on every request, and cross-site writes (CSRF from any page the
        owner visits while the app runs): non-GET calls need a JSON body and a same-host Origin."""
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if host not in LOCAL_HOSTS:
            return JSONResponse({"error": "host not allowed"}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
            origin = request.headers.get("origin")
            if request.method != "DELETE" and ctype != "application/json":
                return JSONResponse({"error": "application/json required"}, status_code=415)
            if origin and (urlparse(origin).hostname or "").lower() not in LOCAL_HOSTS:
                return JSONResponse({"error": "cross-origin request refused"}, status_code=403)
        return await call_next(request)

    def page(name: str, status: int = 200, **ctx: Any) -> HTMLResponse:
        return HTMLResponse(env.get_template(name).render(**ctx), status_code=status, headers=NO_STORE)

    def err(status: int, msg: str, **extra: Any) -> JSONResponse:
        return JSONResponse({"error": msg, **extra}, status_code=status)

    async def body_of(request: Request) -> dict:
        try:
            data = await request.json()
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------ runs API
    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.post("/api/runs")
    async def start_run(request: Request) -> JSONResponse:
        data = await body_of(request)
        url = str(data.get("url") or "").strip()
        try:
            validate_url(url)
        except CroLensError as e:
            return err(400, str(e))
        model = str(data.get("model") or "sonnet")
        if model not in ("sonnet", "opus"):
            return err(400, "model must be sonnet or opus")
        learn = data.get("feedback", True) is not False
        given = Given(
            **{
                k: (str(data[k]).strip() or None) if data.get(k) else None
                for k in ("audience", "traffic", "goal")
            }
        )
        from cro_lens.llm.provider import get_provider, preflight
        from cro_lens.pipeline.run import Options, Pipeline

        try:
            prov = get_provider(provider_name())
            await asyncio.to_thread(preflight, prov)  # may run claude for seconds
        except ValueError as e:
            return err(500, str(e))
        except CroLensError as e:  # Claude Code missing or not signed in: no folder, no visit
            return err(503, str(e))
        run_id, folder = runs.reserve(url)
        act = runs.active[run_id]

        def work() -> None:
            try:
                Pipeline(prov, Options(model=model, given=given, feedback=learn), folder.resolve()).run(
                    url, run_id
                )
            except CroLensError as e:
                act.exit_code, act.error = e.exit_code, str(e)
            except Exception as e:  # a crashed run must still end
                act.exit_code, act.error = 1, f"{type(e).__name__}: {e}"

        act.thread = threading.Thread(target=work, name=f"run-{run_id}", daemon=True)
        act.thread.start()
        return JSONResponse({"run_id": run_id}, status_code=202)

    @app.get("/api/runs")
    def get_runs() -> list[dict]:
        return list_runs(runs)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> Response:
        st = run_status(runs, run_id) if RUN_ID_RE.match(run_id) else None
        if st is None:
            return err(404, "unknown run")
        if st["status"] == "done":
            return Response(
                (runs_dir() / run_id / "report.json").read_bytes(),
                media_type="application/json",
                headers=NO_STORE,
            )
        if st["status"] == "failed":
            return JSONResponse(
                {
                    "status": "failed",
                    "exit_code": st["exit_code"],
                    "error": st["error"],
                    "resume_from": st.get("resume_from"),
                },
                status_code=409,
            )
        return JSONResponse({"status": "running"}, status_code=202)

    @app.post("/api/runs/{run_id}/resume")
    async def resume_run(run_id: str, request: Request) -> JSONResponse:
        from cro_lens.llm.provider import get_provider, preflight
        from cro_lens.pipeline.run import Pipeline

        st = run_status(runs, run_id) if RUN_ID_RE.match(run_id) else None
        if st is None or not (runs_dir() / run_id).is_dir():
            return err(404, "unknown run")
        if st["status"] != "failed":
            return err(409, f"the run is {st['status']}; only a stopped run can be resumed")
        data = await body_of(request)
        model = data.get("model") or None
        if model is not None and model not in ("sonnet", "opus"):
            return err(400, "model must be sonnet or opus")
        try:
            prov = get_provider(provider_name())
            await asyncio.to_thread(preflight, prov)  # may run claude for seconds
        except ValueError as e:
            return err(500, str(e))
        except CroLensError as e:
            return err(503, str(e))
        folder = (runs_dir() / run_id).resolve()
        with runs.lock:
            act = runs.active.get(run_id)
            if (act and act.thread and act.thread.is_alive()) or heartbeat_fresh(folder):
                return err(409, "the run is already running")
            try:
                pipe, spec, start = Pipeline.for_resume(prov, folder, model=model)
            except CroLensError as e:
                return err(409, str(e))
            act = runs.active[run_id] = Active(url=spec.url, started_at=spec.started_at)

            def work() -> None:
                try:
                    pipe.resume(spec, start)
                except CroLensError as e:
                    act.exit_code, act.error = e.exit_code, str(e)
                except Exception as e:  # a crashed run must still end
                    act.exit_code, act.error = 1, f"{type(e).__name__}: {e}"

            act.thread = threading.Thread(target=work, name=f"resume-{run_id}", daemon=True)
            act.thread.start()
        return JSONResponse({"run_id": run_id, "resume_from": start}, status_code=202)

    @app.delete("/api/runs/{run_id}")
    def delete_run(run_id: str) -> Response:
        st = run_status(runs, run_id) if RUN_ID_RE.match(run_id) else None
        if st is None:
            return err(404, "unknown run")
        if st["status"] == "running":
            return err(409, "the run is still running; wait for it to stop")
        root = runs_dir().resolve()
        folder = (root / run_id).resolve()
        if folder.parent != root:
            return err(404, "unknown run")
        with runs.lock:  # re-check: a resume may have started since the status above
            act = runs.active.get(run_id)
            if (act and act.thread and act.thread.is_alive()) or (
                folder.is_dir() and heartbeat_fresh(folder)
            ):
                return err(409, "the run is still running; wait for it to stop")
            runs.active.pop(run_id, None)
            if folder.is_dir():
                try:
                    shutil.rmtree(folder)
                except OSError as e:
                    return err(500, f"could not delete the run folder: {e}")
        return Response(status_code=204)

    provider_cache: dict[str, tuple[float, dict]] = {}

    @app.get("/api/provider")
    def provider_status() -> dict:
        """Is the model provider ready? The start page warns before a run is wasted."""
        from cro_lens.llm.provider import billing, get_provider, notices, preflight

        name = provider_name()
        hit = provider_cache.get(name)
        if hit and time.time() - hit[0] < (
            300 if hit[1]["ready"] else 20
        ):  # a ready check may cost a probe call
            return hit[1]
        try:
            prov = get_provider(name)
            preflight(prov)
            res: dict[str, Any] = {
                "provider": name,
                "ready": True,
                "billing": billing(prov),
                "notices": [
                    n.to_dict() if hasattr(n, "to_dict") else {"text": str(n)} for n in notices(prov)
                ],
            }
        except (CroLensError, ValueError) as e:
            res = {"provider": name, "ready": False, "error": str(e)}
        provider_cache[name] = (time.time(), res)
        return res

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: str) -> Response:
        if not RUN_ID_RE.match(run_id) or run_status(runs, run_id) is None:
            return err(404, "unknown run")

        async def stream() -> AsyncIterator[str]:
            sent, idle = 0, 0.0
            yield "retry: 2000\n\n"
            while True:
                st = run_status(runs, run_id)
                if st is None:
                    return
                events = st["events"]
                for ev in events[sent:]:
                    data = {k: ev[k] for k in ("step", "status", "seconds", "detail") if k in ev}
                    yield f"event: step\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    idle = 0.0
                sent = len(events)
                if st["status"] != "running":
                    end: dict[str, Any] = {"status": st["status"], "exit_code": st.get("exit_code", 0)}
                    if st["status"] == "done":
                        end.update(exit_code=0, report_url=f"/runs/{run_id}")
                    else:
                        end["error"] = st.get("error")
                    yield f"event: end\ndata: {json.dumps(end, ensure_ascii=False)}\n\n"
                    return
                await asyncio.sleep(0.25)
                idle += 0.25
                if idle >= 15:
                    idle = 0.0
                    yield ": keep-alive\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/runs/{run_id}/files/{path:path}")
    def run_file(run_id: str, path: str) -> Response:
        if not RUN_ID_RE.match(run_id):
            return err(404, "not found")
        base = (runs_dir() / run_id).resolve()
        target = (base / path).resolve()
        if not target.is_relative_to(base) or not target.is_file():
            return err(404, "not found")
        return FileResponse(target)

    # ------------------------------------------------------------ grades API (eval@2)
    def finished_report(run_id: str) -> tuple[Report | None, JSONResponse | None]:
        st = run_status(runs, run_id) if RUN_ID_RE.match(run_id) else None
        if st is None:
            return None, err(404, f"no run called {run_id}")
        if st["status"] != "done":
            return None, err(409, "only a finished run can be graded")
        raw = load_report(run_id)
        if raw is None:
            return None, err(404, f"no report for {run_id}")
        return Report.model_validate(raw), None

    def grade_json(g: feedback.Grade) -> dict:
        return {"finding_id": g.finding_id, "verdict": g.verdict, "note": g.note, "graded_at": g.graded_at}

    @app.get("/api/runs/{run_id}/grades")
    def get_grades(run_id: str) -> Response:
        if not RUN_ID_RE.match(run_id) or run_status(runs, run_id) is None:
            return err(404, f"no run called {run_id}")
        return JSONResponse(
            {
                fid: {k: v for k, v in grade_json(g).items() if k != "finding_id"}
                for fid, g in feedback.grades_of_run(run_id).items()
            },
            headers=NO_STORE,
        )

    @app.put("/api/runs/{run_id}/grades/{finding_id}")
    async def put_grade(run_id: str, finding_id: str, request: Request) -> JSONResponse:
        rep, bad = finished_report(run_id)
        if bad is not None:
            return bad
        assert rep is not None
        f = feedback.gradable(rep, finding_id) if FINDING_ID_RE.match(finding_id) else None
        if f is None:
            return err(404, f"no gradable finding {finding_id} in this report")
        data = await body_of(request)
        try:
            g = await asyncio.to_thread(
                feedback.set_grade, rep, f, str(data.get("verdict") or ""), str(data.get("note") or "")
            )
        except ValueError as e:
            return err(400, str(e))
        return JSONResponse(grade_json(g))

    @app.delete("/api/runs/{run_id}/grades/{finding_id}")
    def delete_grade(run_id: str, finding_id: str) -> Response:
        if not RUN_ID_RE.match(run_id) or not FINDING_ID_RE.match(finding_id):
            return err(404, "not graded")
        if not feedback.clear_grade(run_id, finding_id):
            return err(404, "not graded")
        return Response(status_code=204)

    @app.get("/api/eval")
    def get_eval() -> JSONResponse:
        st = feedback.stats()
        st.pop("evidence_runs", None)
        return JSONResponse(st, headers=NO_STORE)

    # ------------------------------------------------------------ pages
    @app.get("/", response_class=HTMLResponse)
    def start_page() -> HTMLResponse:
        return page("start.html", nav="start", runs=list_runs(runs))

    def run_context(run_id: str) -> dict | None:
        st = run_status(runs, run_id) if RUN_ID_RE.match(run_id) else None
        if st is None:
            return None
        steps = {s: {"status": "pending", "seconds": None, "detail": None} for s in STEPS}
        for ev in st["events"]:
            if ev.get("step") in steps:
                steps[ev["step"]].update(
                    status=ev["status"], seconds=ev.get("seconds"), detail=ev.get("detail")
                )
        rep = load_report(run_id) if st["status"] == "done" else None
        return {
            "run_id": run_id,
            "st": st,
            "steps": steps,
            "rep": rep,
            "v": report_view(rep) if rep else None,
            "grades": {fid: grade_json(g) for fid, g in feedback.grades_of_run(run_id).items()}
            if rep
            else {},
            "spec": read_spec(runs_dir() / run_id) if st["status"] == "failed" else None,
        }

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_page(run_id: str) -> HTMLResponse:
        ctx = run_context(run_id)
        if ctx is None:
            return page("missing.html", status=404, nav="", what=f"No run called {run_id}.")
        return page("run.html", nav="run", **ctx)

    @app.get("/runs/{run_id}/report-fragment", response_class=HTMLResponse)
    def run_fragment(run_id: str) -> HTMLResponse:
        ctx = run_context(run_id)
        if ctx is None or ctx["rep"] is None:
            return HTMLResponse("", status_code=404)
        return page("_report.html", **ctx)

    @app.get("/eval", response_class=HTMLResponse)
    def eval_page() -> HTMLResponse:
        return page("eval.html", nav="eval", st=feedback.stats(), max_examples=feedback.MAX_EXAMPLES)

    return app
