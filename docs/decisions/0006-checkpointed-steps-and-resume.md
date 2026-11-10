---
status: accepted
date: 2026-11-10
---
# 0006 — Steps checkpoint to the run folder; resume reuses the capture and never revisits

## Context
A run is seven steps and about 100 s. Before this change a failure anywhere (a model error, Claude Code signed out, Ctrl-C, the UI server closed) lost everything after the capture. The only way back was a new run, which meant a second visit to the page. A run killed without an end event also showed "running" forever in the UI. The owner's first live try hit exactly this: signed out of Claude Code, the run failed at `understand`, and nothing could continue it.

## Decision
- Every step writes its result to `state/<step>.json` (atomic replace) before its `done` event, together with the model calls it made, so a resumed run's cost still covers every call. `run.json` records the url, model and given context at the start.
- `resume` reuses checkpoints in step order and re-runs from the first step without one. A step that runs again ends the reuse, because later checkpoints were built on the old result.
- **Resume needs a finished capture and never calls `check_robots()` or `capture()`.** A run whose capture did not finish has nothing to resume; the UI offers "Run again" (a new run) instead. This keeps "one visit per viewport per run".
- Liveness comes from a `heartbeat` file touched every 5 s and removed at the end. A run with no end event and a heartbeat older than 30 s is failed as *interrupted*, so it can be resumed or deleted. Runs from before this change have no heartbeat; they are judged by the age of `steps.jsonl` (30 min).
- The sign-in is checked (`claude auth status`, under a second, no model call) before the run folder is created. A sign-in error from a model call is not retried.

## Rejected
- **Resume by re-running everything except the capture.** Simpler, but it throws away paid model calls, and the user asked to continue "from that step".
- **PID files for liveness.** On Windows, `os.kill(pid, 0)` terminates the process instead of probing it, and `psutil` would be a new dependency for a single check.
- **A new exit code for "not signed in".** Exit 6 already means "an LLM step cannot complete", and the held-out CLI scenarios fix the existing codes.

## Consequences
- Run folders gain `run.json`, `state/` and, while running, `heartbeat` (contract report.md § run folder).
- `steps.jsonl` can hold more than one event per step; a step's state is its latest event.
- (Eval runs on frozen snapshots were removed by ADR 0008.)
