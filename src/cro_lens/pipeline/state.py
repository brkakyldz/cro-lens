"""What a run folder says about its run: the spec it was started with, the step checkpoints
that let a stopped run resume, and whether a run without an end event is still alive.

Resume never visits the page again: it needs a finished capture in the run folder and
re-runs only the steps after the last checkpoint (ADR 0006)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from cro_lens.models import Given

RUN_SPEC = "run.json"
STATE_DIR = "state"
HEARTBEAT = "heartbeat"
HEARTBEAT_S = 5.0
STALE_S = 30.0  # no heartbeat for this long → the process that ran the step is gone
LEGACY_STALE_S = 1800.0  # runs from before heartbeats: judged by the age of steps.jsonl
LLM_ORDER = ("understand", "analyse", "check", "hypotheses")
CAPTURE_FILES = (
    "meta.json",
    "blocks_desktop.json",
    "blocks_mobile.json",
    "desktop_full.png",
    "desktop_fold.png",
    "mobile_full.png",
    "mobile_fold.png",
)


class RunSpec(BaseModel):
    url: str
    run_id: str
    started_at: str = ""
    model: str = "sonnet"
    given: Given = Field(default_factory=Given)
    legacy: bool = False  # rebuilt from capture/meta.json; model and context were not recorded


def write_atomic(path: Path, text: str) -> None:
    """A run killed mid-write leaves the old file or none, never half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_events(folder: Path) -> list[dict]:
    p = folder / "steps.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue  # a line being written right now
    return out


def last_status(events: list[dict]) -> dict[str, dict]:
    """The latest event per step: a resumed run's new events supersede the old failure."""
    out: dict[str, dict] = {}
    for e in events:
        if "step" in e:
            out[e["step"]] = e
    return out


def read_spec(folder: Path) -> RunSpec | None:
    p = folder / RUN_SPEC
    if p.exists():
        try:
            return RunSpec.model_validate_json(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    meta = folder / "capture" / "meta.json"
    if not meta.exists():
        return None
    try:
        url = json.loads(meta.read_text(encoding="utf-8")).get("url") or ""
    except (ValueError, OSError):
        return None
    if not url:
        return None
    events = read_events(folder)
    return RunSpec(
        url=url, run_id=folder.name, started_at=events[0].get("t", "") if events else "", legacy=True
    )


def checkpoint_path(folder: Path, step: str) -> Path:
    return folder / STATE_DIR / f"{step}.json"


def save_checkpoint(folder: Path, step: str, result: Any, calls: list[dict]) -> None:
    write_atomic(
        checkpoint_path(folder, step),
        json.dumps({"step": step, "result": result, "calls": calls}, ensure_ascii=False, indent=1),
    )


def load_checkpoint(folder: Path, step: str) -> dict | None:
    p = checkpoint_path(folder, step)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return data if isinstance(data, dict) and "result" in data else None


def capture_dir(folder: Path) -> Path | None:
    """Where this run's finished capture is, or None. A capture checkpoint names it (a frozen
    folder); a run from before checkpoints needs its `capture done` event."""
    ckpt = load_checkpoint(folder, "capture")
    if ckpt is not None:
        res = str(ckpt.get("result") or "")
        return folder / res if res == "capture" else Path(res)
    st = last_status(read_events(folder)).get("capture")
    return folder / "capture" if st and st.get("status") == "done" else None


def capture_reusable(folder: Path) -> bool:
    """True only when the capture is there and loads: resume must never fall back to a visit."""
    from cro_lens.capture.browser import load_capture

    cap = capture_dir(folder)
    if cap is None or not all((cap / f).exists() for f in CAPTURE_FILES):
        return False
    try:
        load_capture(cap)
    except (ValueError, KeyError, TypeError, OSError):
        return False
    return True


def resume_point(folder: Path) -> str | None:
    """The first step a resume would run, or None when the run cannot be resumed
    (already finished, or its capture never completed — that needs a new visit)."""
    if (folder / "report.json").exists() or not capture_reusable(folder):
        return None
    for step in LLM_ORDER:
        if load_checkpoint(folder, step) is None:
            return step
    return "report"


def heartbeat_fresh(folder: Path, now: float | None = None) -> bool:
    """A process is working on this run right now (its heartbeat is recent)."""
    now = time.time() if now is None else now
    try:
        return now - (folder / HEARTBEAT).stat().st_mtime < STALE_S
    except OSError:
        return False


def alive(folder: Path, now: float | None = None) -> bool:
    """Is some process still working on this run? A live pipeline touches `heartbeat` every
    few seconds and removes it when it ends; a killed one leaves it behind, going stale."""
    now = time.time() if now is None else now
    hb = folder / HEARTBEAT
    try:
        if hb.exists():
            return now - hb.stat().st_mtime < STALE_S
        ref = folder / "steps.jsonl"
        ref = ref if ref.exists() else folder
        return now - ref.stat().st_mtime < (LEGACY_STALE_S if ref.name == "steps.jsonl" else STALE_S)
    except OSError:
        return False
