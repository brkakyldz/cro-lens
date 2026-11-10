# cro-lens — agent instructions

One public landing page URL in → an evidence-backed, self-checked A/B
experiment backlog out, plus a local web UI and an eval each user builds from
their own grades, which also teaches their next runs (ADR 0008). Intent: `INTENT.md` (frozen). Spec: `docs/spec.md`.
Contracts (the test surface): `docs/contracts/`. Plan: `docs/plan.md`.
Where we are: `docs/CURRENT_STATE.md`. Why: `docs/decisions/`.

## Rules

- The LLM's judgement is the product; capture stays thin and deterministic.
- Every finding carries `{block_id, viewport, quote}` evidence; the deterministic check runs before any LLM check (ADR 0002).
- All model calls go through `cro_lens.llm.provider` — never call `claude` or an SDK elsewhere (ADR 0001).
- Tests never call a model or the internet: `CRO_LENS_PROVIDER=fake`, fixture pages in `tests/fixtures/pages/`.
- One visit per viewport per run; honour robots.txt; never bypass bot protection.
- Windows: open files and subprocess pipes with `encoding="utf-8"`; CLI output reconfigures stdout to UTF-8.
- A user's grades are theirs: only their grade action writes `$CRO_LENS_HOME/grades.json`; tests use a temp `CRO_LENS_HOME`.
- `tests/acceptance/holdout/` is held out: read it, never edit it (holdout-lock).
- Prompt changes land with a before/after live run of the same page, named in the commit or run report (no shared benchmark, ADR 0008).
- Contract change after scenarios exist → re-run `scenario-author` for the affected IDs.
- Nothing public (visibility, posts, PyPI) without the owner's yes.

## Invariants that break silently

Each of these fails with a green suite unless someone checks it by name.

1. **Evidence check bypassed** — a finding reaches `experiments` without a quote that matched its cited block (`check.deterministic == "pass"`). Grep for any path that builds `Experiment` from findings not filtered by verdict.
2. **Feedback re-selected on resume** — a run learns from the `feedback.json` it wrote at its start; `resume` must load that file, never call `feedback.select()` again (grades made since would change a half-done run).
3. **Feedback reaches the wrong steps or none** — the examples belong in the `analyse` and `check` prompts only (`feedback.prompt_block`); a refactor that drops the `parts.append` passes every fake test except `test_feedback.py`.
4. **Missing metric shown as 0** — a metric without inputs is `null` and renders `pending …`, never `0` or `0%`.
5. **Fake provider in a live claim** — numbers in the README must come from `provider: claude-code` results; fake outputs are for tests only.
6. **Cost mislabeled** — the figure is `total_cost_usd` from `claude -p`: an API-list equivalent on a subscription, never billed spend; on `ANTHROPIC_API_KEY` (`run.billing == "api_key"`) it is billed, and must say so (ADR 0007).
7. **Report written after a failed step** — exit codes 2–6 leave no `report.json`.
8. **File serving escapes the run folder** — `/runs/{id}/files/{path}` must resolve inside the run folder.
9. **Windows encoding** — any `open()`/`subprocess` without `encoding="utf-8"` passes on CI (Linux) and breaks on the owner's machine (cp1254).
10. **Confidence asked of the model** — ICE confidence is computed (`pipeline/check.confidence`); a prompt or schema that lets the model set it breaks HYP-4 silently.
11. **Resume visits the page again** — `Pipeline.for_resume`/`resume` must never reach `capture()` or `check_robots()`; a run without a finished capture is not resumable (ADR 0006).

## Commands

| What | Command |
|---|---|
| install | `uv sync && uv run playwright install chromium` |
| unit (offline) | `uv run pytest -q` |
| lint | `uv run ruff check src tests && uv run ruff format --check src tests` |
| types | `uv run pyright` |
| held-out | `uv run pytest tests/acceptance/holdout` (env `CRO_LENS_REPO` = repo root) |
| run | `uv run cro-lens analyze <url>` · `uv run cro-lens resume <run_id>` · `uv run cro-lens ui` |
