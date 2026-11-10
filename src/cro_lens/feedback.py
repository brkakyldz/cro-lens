"""The user's own eval (contract eval@2, ADR 0008).

The user grades findings on finished reports; grades live in `$CRO_LENS_HOME/grades.json`,
outlive the run they came from, and never leave the machine. Each new run picks up to
`MAX_EXAMPLES` of them (the same site first, newest first), freezes the choice in its
run folder as `feedback.json`, and shows them to the model in `analyse` and `check`."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from cro_lens.config import home, now_iso
from cro_lens.models import Finding, Report

MAX_EXAMPLES = 12
GRADES_FILE = "grades.json"
FEEDBACK_FILE = "feedback.json"
_lock = threading.Lock()

Verdict = Literal["valid", "invalid"]


class Grade(BaseModel):
    run_id: str
    finding_id: str
    url: str
    host: str
    category: str
    kind: str
    title: str
    quote: str
    verdict: Verdict
    note: str = ""
    graded_at: str


class Example(BaseModel):
    run_id: str
    finding_id: str
    host: str
    same_site: bool
    category: str
    kind: str
    title: str
    quote: str
    verdict: Verdict
    note: str = ""


class Feedback(BaseModel):
    enabled: bool = True
    examples: list[Example] = Field(default_factory=list)

    @property
    def same_site(self) -> int:
        return sum(e.same_site for e in self.examples)

    def summary(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "examples": len(self.examples), "same_site": self.same_site}


def site_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def grades_path() -> Path:
    return home() / GRADES_FILE


# ---------------------------------------------------------------- grades.json
def load_grades() -> dict[str, Grade]:
    p = grades_path()
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8")).get("grades") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    out: dict[str, Grade] = {}
    for key, g in raw.items():
        try:
            out[key] = Grade.model_validate(g)
        except ValueError:
            continue  # a hand-damaged entry never breaks the rest
    return out


def _save(grades: dict[str, Grade]) -> None:
    from cro_lens.pipeline.state import write_atomic

    data = {"schema_version": "grades@1", "grades": {k: g.model_dump() for k, g in grades.items()}}
    write_atomic(grades_path(), json.dumps(data, ensure_ascii=False, indent=1))


def gradable(report: Report, finding_id: str) -> Finding | None:
    """The finding if the user may grade it: in the report and not dropped by the self-check."""
    f = next((x for x in report.findings if x.id == finding_id), None)
    return f if f is not None and f.check.verdict in ("kept", "flagged") else None


def set_grade(report: Report, finding: Finding, verdict: str, note: str = "") -> Grade:
    if verdict not in ("valid", "invalid"):
        raise ValueError("verdict must be valid or invalid")
    quote = next(
        (e.quote for e in finding.evidence if e.valid), finding.evidence[0].quote if finding.evidence else ""
    )
    g = Grade(
        run_id=report.run.id,
        finding_id=finding.id,
        url=report.run.url,
        host=site_of(report.run.url),
        category=finding.category,
        kind=finding.kind,
        title=finding.title,
        quote=quote,
        verdict=verdict,  # type: ignore[arg-type]
        note=(note or "").strip()[:500],
        graded_at=now_iso(),
    )
    with _lock:
        grades = load_grades()
        key = f"{g.run_id}/{g.finding_id}"
        grades.pop(key, None)  # re-insert: file order doubles as "newest last" within one second
        grades[key] = g
        _save(grades)
    return g


def clear_grade(run_id: str, finding_id: str) -> bool:
    with _lock:
        grades = load_grades()
        if grades.pop(f"{run_id}/{finding_id}", None) is None:
            return False
        _save(grades)
    return True


def grades_of_run(run_id: str) -> dict[str, Grade]:
    return {g.finding_id: g for g in load_grades().values() if g.run_id == run_id}


# ---------------------------------------------------------------- what a run learns
def select(url: str, run_id: str = "", limit: int = MAX_EXAMPLES) -> Feedback:
    """Up to `limit` grades: the same site first, then other sites, newest first in each."""
    site = site_of(url)
    ordered = [g for g in load_grades().values() if g.run_id != run_id]
    pool = [g for _, g in sorted(enumerate(ordered), key=lambda ig: (ig[1].graded_at, ig[0]), reverse=True)]
    chosen = [g for g in pool if g.host == site] + [g for g in pool if g.host != site]
    return Feedback(
        enabled=True,
        examples=[
            Example(**g.model_dump(exclude={"url", "graded_at"}), same_site=g.host == site)
            for g in chosen[:limit]
        ],
    )


def load_feedback(folder: Path) -> Feedback | None:
    p = folder / FEEDBACK_FILE
    if not p.exists():
        return None
    try:
        return Feedback.model_validate_json(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_feedback(folder: Path, fb: Feedback) -> None:
    from cro_lens.pipeline.state import write_atomic

    write_atomic(folder / FEEDBACK_FILE, fb.model_dump_json(indent=1))


def prompt_block(fb: Feedback | None, step: str) -> str | None:
    """The examples as the model sees them, or None when there are none."""
    if fb is None or not fb.examples:
        return None
    if step == "analyse":
        head = (
            "The user who ordered this audit graded findings from earlier audits. These are their verdicts. "
            "Learn their bar from them: avoid the kinds of finding they marked wrong, and aim for the kind "
            "they marked right. Never copy a finding from these examples; every finding must still rest on "
            "this page's own evidence."
        )
    else:
        head = (
            "The user's earlier verdicts on findings from past audits (they had read the real page). A "
            "finding here of the same kind as one they marked wrong should be flagged or dropped unless "
            "this page's evidence clearly sets it apart. Judge every finding on this page's evidence."
        )
    rows = []
    for e in fb.examples:
        where = "same site" if e.same_site else e.host
        note = f' — their note: "{e.note[:300]}"' if e.note else ""
        verdict = "RIGHT" if e.verdict == "valid" else "WRONG"
        rows.append(
            f'- [{where}] [{e.category}, {e.kind}] {e.title} — quote: "{e.quote[:200]}" → {verdict}{note}'
        )
    return head + "\n" + "\n".join(rows)


# ---------------------------------------------------------------- metrics
def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def stats(runs_root: Path | None = None) -> dict[str, Any]:
    """The eval@2 metrics. A metric without inputs is None, never 0."""
    from cro_lens.config import runs_dir

    grades = list(load_grades().values())
    valid = sum(g.verdict == "valid" for g in grades)
    cats: dict[str, list[Grade]] = {}
    for g in grades:
        cats.setdefault(g.category, []).append(g)
    by_category = [
        {
            "category": c,
            "graded": len(gs),
            "valid": sum(g.verdict == "valid" for g in gs),
            "precision": _ratio(sum(g.verdict == "valid" for g in gs), len(gs)),
        }
        for c, gs in sorted(cats.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    ]
    per_run: dict[str, list[Grade]] = {}
    for g in grades:
        per_run.setdefault(g.run_id, []).append(g)

    ev_ok = ev_all = 0
    runs = []
    root = runs_root or runs_dir()
    for d in sorted((x for x in root.iterdir() if x.is_dir()), reverse=True) if root.exists() else []:
        f = d / "report.json"
        if not f.exists():
            continue
        try:
            rep = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for fd in rep.get("findings") or []:
            for e in fd.get("evidence") or []:
                ev_all += 1
                ev_ok += bool(e.get("valid"))
        run_id = (rep.get("run") or {}).get("id") or d.name
        gs = per_run.get(run_id, [])
        runs.append(
            {
                "run_id": run_id,
                "url": (rep.get("run") or {}).get("url", ""),
                "finished_at": (rep.get("run") or {}).get("finished_at", ""),
                "findings": sum(
                    (x.get("check") or {}).get("verdict") in ("kept", "flagged")
                    for x in rep.get("findings") or []
                ),
                "graded": len(gs),
                "valid": sum(g.verdict == "valid" for g in gs),
            }
        )
    runs.sort(key=lambda r: r["finished_at"], reverse=True)
    return {
        "graded": len(grades),
        "valid": valid,
        "invalid": len(grades) - valid,
        "precision": _ratio(valid, len(grades)),
        "by_category": by_category,
        "evidence_validity": _ratio(ev_ok, ev_all) if runs else None,
        "evidence_runs": len(runs),
        "next_run_examples": min(MAX_EXAMPLES, len(grades)),
        "runs": runs,
    }


def pct(v: float | None, pending: str) -> str:
    return pending if v is None else f"{round(v * 100)}%"
