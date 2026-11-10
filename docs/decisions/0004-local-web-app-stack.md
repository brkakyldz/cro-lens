---
status: accepted
date: 2026-11-10
---
# 0004 — Local web app: FastAPI + Jinja2 + vanilla JS + SSE, no Node build

## Context
The owner asked for a simple, good-looking local web UI (start, live run, report, eval labeling). It must ship inside the Python package and start with `cro-lens ui`.

## Decision
FastAPI with uvicorn, server-rendered Jinja2 templates, one hand-written CSS file and small vanilla JS modules; live steps over Server-Sent Events read from the run's `steps.jsonl`. Runs started from the UI execute the same pipeline in a background thread. Fonts are self-hosted woff2 files in the package (no CDN at runtime). Design direction "Field Audit" from `reports/research/2026-11-10_ui-references.md`. Bound to 127.0.0.1 only.

## Consequences
- No npm, no bundler; the package stays `uv tool install`-able.
- Interactivity is deliberately small (forms, SSE, keyboard grading); anything SPA-like is out of scope.
