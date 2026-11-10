# Plan — cro-lens

## Verified assumptions

Spike scripts in a throwaway spike folder (not kept); results recorded as the system answered.

| ID | Assumption | How tested | Result |
|---|---|---|---|
| V-1 | `claude -p` on subscription auth accepts a base64 image via `--input-format stream-json`, returns schema-valid JSON in `structured_output` with `--json-schema`, with tools disabled (`--tools ""`) and a custom `--system-prompt` | `v1_claude_p_image_schema.py` | ✅ rc 0, 5.4 s, `structured_output` = `{"headline":"Boost your productivity","cta_text":"Start free","evidence_ids":["E1","E2"]}`, `total_cost_usd` 0.047 (11.5k cache-creation tokens of fixed overhead) |
| V-1b | `--bare` cuts the fixed overhead on subscription auth | same script with `--bare` | ❌ `Not logged in · Please run /login` — bare skips subscription auth; not used |
| V-2 | On a real page (linear.app), 5 screenshot tiles + ~200 id'd text blocks → findings whose element id + verbatim quote check out deterministically | `v2_grounded_findings.py sonnet|opus` | ✅ Sonnet 6/6 grounded, 16.9 s, $0.094 eq.; Opus 6/6, 34–41 s, $0.20–0.22 eq. |
| V-3 | Playwright (Python) loads a real page desktop 1440×900 + iPhone 13 emulation, full-page screenshot, and extracts visible text blocks with id + tag + bbox via one `evaluate` | `v3_playwright_blocks.py https://linear.app` | ✅ desktop 200, 8.0 s, h 9960, 698 blocks; mobile 200, 3.7 s, h 5906, 224 blocks. Blocks include nested duplicates (li ⊃ button) → dedupe needed |
| V-4 | PageSpeed Insights v5 works without an API key | `curl runPagespeed?url=https://linear.app&strategy=mobile` | ❌ 429 "Quota exceeded … Queries per day" on the shared keyless quota — PSI only with `PAGESPEED_API_KEY`; default is local Playwright timing (A-02) |
| V-5 | Windows console encoding | V-2 printing a `→` | ❌ `UnicodeEncodeError` cp1254 — every subprocess and CLI print uses UTF-8 explicitly (`encoding="utf-8"`, `PYTHONIOENCODING`, `sys.stdout.reconfigure`) |
| V-6 | Lab timing in the same visit: Navigation Timing + buffered LCP/CLS observers injected with `add_init_script` | `v6_lab_timing.py https://linear.app` (iPhone 13) | ✅ `{"ttfb":798,"dcl":1164,"load":1441,"lcp":2140,"cls":0,"bytes":385579,"requests":251}` — `bytes` is a lower bound (cross-origin `transferSize` = 0 without Timing-Allow-Origin); reported as such |

## Shape

```
cro_lens/
  cli.py            Typer app: analyze, ui, eval {snapshot,run,report}
  config.py         paths, env (CRO_LENS_HOME, provider)
  models.py         Pydantic models = report@1, step outputs
  capture/          robots.py, browser.py (visit, blocks, consent, timing), tiles.py
  llm/              provider.py (interface, Usage), claude_code.py, fake.py, schema.py
  pipeline/         understand.py, analyse.py, check.py, hypotheses.py, run.py (orchestrates, steps.jsonl)
  prompts/          *.md — system + user templates per step
  report/           render_md.py, crops.py
  eval/             manifest.py, snapshot.py, baseline.py, match.py, metrics.py, results.py
  web/              app.py (FastAPI), templates/, static/ (css, js, fonts)
tests/
  unit/ …           builder's tests (offline)
  fixtures/pages/   fake@1 fixture site
eval/
  manifest.yaml  labels/  grades/  RESULTS.md   (pages/ and results/ gitignored)
```

## Milestones

### M1 — Offline vertical slice: CLI → capture → fake pipeline → report
Delivers CLI-1..4, CAP-1..4, CAP-6, LLM-1, LLM-2, LLM-4, CHK-1, CHK-3, HYP-1..5 (shape), REP-1, REP-2, SAFE-1. Relies on V-3, V-5, V-6.
- M1-A1 `uv run pytest tests/unit -q` green (models, check, ICE rule, robots, block dedupe, md render).
- M1-A2 `uv run cro-lens analyze http://127.0.0.1:<p>/saas.html --provider fake` exits 0 and writes every file of run-folder@1; `report.json` satisfies the report@1 invariants (`tests/unit/test_report_invariants.py`).
- M1-A3 robots / 404 / challenge fixtures exit 3 / 4 / 5 with no `report.json`.
- Gates wired: ruff check, ruff format --check, pyright (basic), pytest unit.
- **Product acceptance:** `uv run pytest tests/acceptance/holdout -k "not ui and not eval"` (from the pack until landed, A-10).

### M2 — Claude Code provider and real prompts
Delivers LLM-1..3, UND-1..2, ANA-1..4, CHK-2, CAP-5. Relies on V-1, V-2, V-6.
- M2-A1 unit tests for the provider's command line, stream parsing, retry, usage → USD (recorded stream fixtures, no live call).
- M2-A2 live: `cro-lens analyze https://linear.app` and one weak page complete, report evidence validity after check = 100 %, cost line present. Allowance: 6 live runs (subscription).
- **Product acceptance:** live run output reviewed against the brief's quality rules; shown to the owner in the run report.

### M3 — Local web app (start, live run, report)
Delivers CLI-5, UI-1..3, UI-5, SAFE-2. Relies on ADR 0004.
- M3-A1 `uv run pytest tests/unit/test_web.py` (API, SSE replay, file serving confinement).
- M3-A2 screenshots of the 3 screens at 1440 and 390 width reviewed against the UI research direction; no horizontal overflow (`visualViewport.width == innerWidth`).
- **Product acceptance:** holdout UI scenarios.

### M4 — Eval harness, seeded cases, baseline, labeling UI
Delivers EVAL-1..6, UI-4. Relies on ADR 0003.
- M4-A1 unit tests for match rule, fingerprint, metrics with nulls.
- M4-A2 `eval snapshot` on the manifest (15 real + 4 seeded) succeeds for ≥ 15 pages.
- **Product acceptance:** holdout eval scenarios.

### M5 — Live eval, prompt iteration, README, ship
- Live eval on all snapshots, both systems, Sonnet (allowance: 3 full rounds); one Opus round on the seeded + 5 pages.
- Prompt changes only with a before/after RESULTS row.
- README (what / why / how it works / eval table / limits), demo GIF (vhs or Playwright recording of the UI), LICENSE MIT, CHANGELOG, CI (ruff, pyright, unit, holdout with fake provider).
- **Product acceptance:** `verify-holdout.mjs` VERIFIED; fresh-clone install works; private GitHub repo with CI green.

## Live checks and allowances
All live model calls run on the owner's Claude subscription (not metered). Allowance for the run: ≤ 25 `analyze` runs and ≤ 4 full eval rounds. Real sites: one visit per viewport per run; eval pages captured once.

## Stops
- A holdout scenario contradicts the spec → Open gate `unreliable-oracle`, build to the spec.
- Subscription rate limit hit → pause live work, finish offline work, record.
- A seeded or real eval page blocks automation → drop it, do not bypass.

## Final gates
ruff + pyright + unit + holdout (fake) green; `verify-holdout.mjs` VERIFIED; fresh clone `uv sync && uv run cro-lens --version`; secret scan (`gitleaks` if present, else grep for key patterns); slice review on the full range.
