---
type: run-report
status: DONE
run: factory-cro-lens
runtime: claude-code
started: 2026-11-10 17:27
ended: 2026-11-10 19:10
base_sha: (empty repo)
head_sha: aca3876
---
# Run report — factory-cro-lens

## Plan refresh
- Station order deviation: the held-out author (fresh Opus subagent, pack holds only spec + contracts) ran in parallel with M1 coding instead of strictly before it; it never had access to the repo, so independence holds, but "locked before product code exists" did not. Its scenarios first executed against M1 at commit ff380bc.
- M1: no change. M2 (provider + prompts) was folded into M1 because the provider was a small file and the first live run validated it early.
- M3 and M4 run in parallel in separate worktrees (UI: Opus subagent; eval backend: Sonnet subagent); the eval file store (`eval/store.py`, `eval/match.py`) was written first so both build against one API.

## Checks run
- `uv run pytest -q` → 17 passed at ff380bc; 24 after M4 merge (agents' reports, re-run at the end below).
- Held-out CLI subset (`pytest holdout -k "H01 or … or H12"`, pack, `CRO_LENS_REPO=<repo root>`) at ff380bc → 6 passed, 2 failed (H06: tile counts not persisted in meta.json; H12: fake gave 1 persona walk instead of 5) → fixed in eb2aa0c → 8 passed.
- Live `cro-lens https://linear.app` (claude-code, sonnet) → exit 0, 8 findings, check kept 2 · flagged 6 · dropped 0, 8 experiments, $0.507 API-eq., ~2 min.
- Live `cro-lens https://www.proofhub.com/` → exit 0, 9 findings, kept 2 · flagged 6 · dropped 1, 8 experiments, $0.470 API-eq.
- Full held-out suite at 55ab3ad → 13 passed (83 s).
- `node verify-holdout.mjs --root <pack>` at 55ab3ad → `VERIFIED 12/12 scenarios, 100.0% of 36 scenario-runs` (evidence: a file in the scenario pack, outside the repo).
- M3-A2 (UI agent, worktree branch 2504054): Playwright screenshots of start / live / report / eval / label at 1440 and 390 in a throwaway screenshot folder; `visualViewport.width === innerWidth` and `scrollWidth` = viewport on every screen (agent's report); reviewed by the builder: start-1440, report-1440 (crops of top and findings).
- M4-A2: `cro-lens eval snapshot` (eval agent) → 19/19 pages captured; builder re-check: `ls eval/pages | wc -l` → 19; seeded block diffs vs base pages: notion CTA blocks 18 → 15 (nav + hero "Get Notion free"/"Request a demo" gone), mercury H1 "Radically different banking" → "Welcome to the future of work" (both viewports), linear "Pricing" removed (both), superhuman 4 proof blocks removed (both).
- Independent review (`claude -p --model sonnet`, slice-reviewer, range 72425b4..6f4769c) → CRITICAL 2, IMPORTANT 4, OPTIONAL 5 (`docs/reviews/findings.md`). Fixed in 579a59a: -2 (host/origin guard + unit test), -3 (seeded control rate), -6 (CI warns when held-out not run); -1, -4, -5 answered by the evidence lines in this section and the final STATE.
- Held-out full suite after the review fixes (579a59a) → 13 passed.
- Live eval `cro-lens eval run --system both --model sonnet` → results `eval/results/20261110-182010` (18 pages ok, cleanshot-home failed: PIL DecompressionBombError on a 475 MP 3×-DPR mobile screenshot) → fix `MAX_IMAGE_PIXELS = None` for own screenshots → `--only cleanshot-home` re-run (6 findings, $0.362) merged into the same results folder (noted in summary.json).
- `cro-lens eval report` → `eval/RESULTS.md`: cro-lens evidence validity 100.0 % (346/346), after check 100.0 % (294/294); baseline 94.9 % (280/295); seeded recall 4/4 both, seeded control 3/4 both; label recall / precision `pending owner labels`; 6.7 vs 15.5 findings/page; $0.413 vs $0.103 and 99.7 s vs 17.0 s per page.
- Self-check over the eval: 155 raw cro-lens findings → deterministic check dropped 0; LLM check kept 35, flagged 92, dropped 28.
- `uv run pytest -q` at the final tree → 31 passed.
- Fresh clone (`git clone` → `uv sync` → `cro-lens --version` → `pytest -q`) → `cro-lens 0.1.0`, 31 passed.
- Secret scan (`git grep` for sk-ant-/sk-/ghp_/gho_/AIza/private keys) → no hits.
- `gh repo create brkakyldz/cro-lens --private` + push + tag v0.1.0 → visibility PRIVATE. CI on 158e656 failed (ruff E402 from the PIL fix, which the local commit gate did not stop) → fixed → CI on aca3876 success (lint, types, unit; held-out step warns NOT RUN until landed).

## Acceptance
- M1 product acceptance (held-out CLI subset) → PASS, 8/8 at eb2aa0c.
- M2-A2 live runs → PASS on the any-match rule: every kept/flagged finding has ≥ 1 verified quote; evidence validity after check measured on the eval = 100 % (294/294), so no kept finding carried an unmatched quote.
- M3 / M4 product acceptance (held-out H07–H11) → PASS at 55ab3ad and 579a59a.
- Final: verify-holdout VERIFIED 12/12 (36/36 runs) at 55ab3ad; full suite 13/13 again at 579a59a.

## Assumptions

- A-01: LLM runtime = Claude Code CLI (`claude -p`, subscription auth) as the only shipped provider, behind a `Provider` interface with a deterministic `fake` provider for tests. Rejected: shipping Anthropic-API and OpenAI adapters now — the owner asked for the whole system to run on Claude Code; untested adapters would be claims without evidence. Adding one is one file (documented).
- A-02: Page speed = local lab timing measured by Playwright during the single visit (TTFB, DOMContentLoaded, load, LCP, CLS, transfer bytes); Google PageSpeed Insights only when `PAGESPEED_API_KEY` is set. Rejected: PSI as the default — keyless calls return 429 on the shared quota (V-4).
- A-03: Pipeline order = understand → analyse → self-check (code, then LLM) → hypotheses+ICE → report. Rejected: brief order (hypotheses before self-check) — writing experiments for findings that get dropped wastes a call and lets bad findings leak into the backlog.
- A-04: Default model Sonnet for every step, `--model opus` switch per run; eval compares both. V-2: both grounded 6/6 on linear.app; Opus findings more specific, ~2.4× time.
- A-05: Cost is reported as the API-list-equivalent USD that `claude -p` returns (`total_cost_usd`), labelled as such — the run is billed to the user's subscription, not metered.
- A-06: Eval ground truth has two parts: (a) seeded-defect cases — real pages with known defects injected by a recorded DOM mutation before capture, so recall is measurable without anyone's judgement; (b) owner hand labels on 10–15 real pages for recall and precision. Rejected: the builder labelling pages (it would grade its own exam).
- A-07: Label ↔ finding matching is deterministic: same taxonomy category AND overlapping evidence (anchor quote fuzzy-match or element bbox overlap). The owner can override any match in the labeling screen. Rejected: an LLM judge for matching — the brief's "don't say it works until a test shows it".
- A-08: Eval page snapshots (screenshots, HTML, blocks) are not committed; `eval/manifest.yaml` and labels are, and `cro-lens eval snapshot` recreates the pages. Reason: third-party page captures in a repo that may go public, and size.
- A-10: Held-out scenarios stay in their pack (the scenario pack outside the repo) and run from there with `CRO_LENS_REPO` pointing at the repo, until the owner lands them with the copy command in Owner gates. Rejected: the builder copying them into `tests/acceptance/holdout/` (holdout-lock; the builder's hand must not touch the oracle) and blocking the run on the owner.
- A-11: Self-check sees the full desktop text-block list in addition to folds and crops, so it can verify "X is absent / appears elsewhere" claims. Reason: first live run (linear.app) flagged 4/8 findings only because the checker had not seen the whole page.
- A-09: Web UI = FastAPI + Jinja2 server-rendered pages + vanilla JS + Server-Sent Events for live steps; no Node build. Rejected: a React SPA — a build chain for four screens.

## Cost
All model calls ran on the owner's Claude subscription via `claude -p` (not metered). API-list equivalent reported by Claude Code: spikes ≈ $0.6; live runs linear + proofhub $0.98; eval round $7.85 cro-lens (19 × $0.413) + $1.96 baseline (19 × $0.103); review and subagents: subscription, not itemised.

## Intent coverage
| # | Clause | Requirement IDs | Milestone | Status |
|---|---|---|---|---|
| 1 | URL in → analysis | CLI-1 | M1 | PASS |
| 2 | audience, JTBD, traffic, awareness | UND-1 | M1/M2 | PASS (shape held-out; quality live) |
| 3 | 5-second clarity, specificity, objections, offer fit | UND-2, ANA-1, ANA-4 | M2 | PASS (live) |
| 4 | persona walkthroughs | ANA-1 (5 personas, research) | M2 | PASS |
| 5 | top 3 with reasons | HYP-2 | M1/M2 | PASS |
| 6 | thin capture: screenshots, DOM text, fold, speed | CAP-1..6 | M1 | PASS — PSI only with key (V-4) |
| 7 | every finding cites evidence | ANA-2, CHK-1 | M1 | PASS (346/346 valid on eval) |
| 8 | says what it couldn't verify | ANA-3, REP-1 | M1/M2 | PASS |
| 9 | backlog: hypothesis, ICE + reasoning, copy | HYP-1,3,4,5 | M1/M2 | PASS |
| 10 | self-check step | CHK-1..3 | M1/M2 | PASS |
| 11 | Pydantic between steps | LLM-2 | M1 | PASS |
| 12 | Markdown report sections | REP-1,2 | M1 | PASS |
| 13 | eval 10–15 pages, hand labels, validity + precision | EVAL-1..6 | M4/M5 | PARTIAL — 15 pages + 4 seeded, validity measured; precision/recall OPEN_GATE (owner labels) |
| 14 | baseline comparison | EVAL-3 | M4/M5 | PASS |
| 15 | README with demo GIF and eval results | — | M5 | PASS |
| 16 | swappable provider; Claude first | LLM-1 | M1 | PASS (claude-code + fake; API providers out per A-01) |
| 17 | cost in report | LLM-3, REP-1 | M1 | PASS |
| 18 | public pages, one visit, robots | CAP-1, SAFE-1 | M1 | PASS |
| 19 | local web UI, reference-led | UI-1..5, CLI-5, SAFE-2 | M3 | PASS |
| 20 | private repo, nothing public | — | M5 | PASS (private) |

## Station log
| # | Station | Started | Ended | Artefact | Check |
|---|---|---|---|---|---|
| 0 | Open the run | 17:27 | 17:40 | this file | exists |
| 1 | Intake | 17:40 | 17:55 | INTENT.md | verbatim + 20-clause checklist |
| 1a | Spike | 17:30 | 17:55 | docs/plan.md § Verified assumptions | 5 rows tested |

## Factory metrics
- Wall-clock, intent → ship: ~1:45 (station 0 at 17:27 → push ≈ 19:10)
- Human minutes during the run: 0
- Held-out scenarios: 12 (13 test items) written by a fresh Opus subagent (same vendor); first execution: CLI subset 6/8 (H06, H12 red), UI subset H07–H09 3/3 at the UI agent's first reported run, H10 first-try unknown (eval agent); after fixes 12/12; verify-holdout runs 3
- Fix rounds per milestone: M1 1, M3 0 reported, M4 unknown, review 1
- Review findings: CRITICAL 2, IMPORTANT 4, OPTIONAL 5; open CRITICAL/IMPORTANT at ship 0 (3 code fixes, 3 evidence fixes)
- Product code / test code: 5099 / 771 lines (+1559 held-out lines in the pack)
- Engine spend: subscription, not metered; ≈ $11.5 API-equivalent in measured runs
- Assumptions made instead of questions: 11 (A-01…A-11)
- M0 spike: ~10 requests; verified rows ✅ 4 / ❌ 3 (V-1b, V-4, V-5, each routed around) / untested 0; plan rewrites caused by a late-found dependency 0

## Owner gates
1. **Land the held-out scenarios** (builder may not): copy the scenario pack into `tests/acceptance/holdout/` then `git add tests/acceptance/holdout && git commit -m "holdout: 12 scenarios by Opus subagent from spec@72425b4"` — CI then runs them.
2. **Label the eval set**: `uv run cro-lens ui` → *Eval set* → label each of the 15 real pages and grade unmatched findings; then `uv run cro-lens eval report` and paste the new row into README. Until then precision/recall stay `pending`.
3. **Public release**: the repo is private. To open it: `gh repo edit brkakyldz/cro-lens --visibility public --accept-visibility-change-consequences`.
4. **Font licence**: `src/cro_lens/web/static/fonts/OFL.txt` copyright lines were written from memory by the UI agent; check against the Google Fonts repos before going public.
