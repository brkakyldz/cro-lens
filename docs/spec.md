# Spec — cro-lens v1

## 1. Users and the job

Growth marketers, founders and agencies point cro-lens at one public landing
page to learn, before or while they send traffic, who the page is really for,
where each kind of visitor stalls, and which experiments to run first — with
every claim tied to something they can see on the page.

**Promise:** one URL in, an evidence-backed experiment backlog out, and an
eval of the user's own that measures how often the tool is right for them and
teaches the next run from their grades.

## 2. Requirements

IDs are stable. `(assumption A-nn)` → run report; `(research: <file>)` → `reports/research/`.

### CLI — entry points
- **CLI-1** When the user runs `cro-lens analyze <url>`, the system shall run the full pipeline once and write the run folder (contract `cli@1`, `run-folder@1`), printing the report path. `cro-lens <url>` is an alias.
- **CLI-2** The system shall print one progress line per pipeline step with its outcome, and the run's equivalent cost at the end.
- **CLI-3** When the URL is not `http(s)`, robots.txt disallows it, the page returns ≥ 400, or a bot challenge / login wall is detected, the system shall stop before any LLM call, write no report, and exit with the code in `cli@1`.
- **CLI-4** The system shall accept `--model {sonnet,opus}`, `--audience <text>`, `--traffic <source>`, `--goal <text>` and `--out <dir>`; given context replaces the inferred value and is marked `given` in the report. (assumption A-04)
- **CLI-5** `cro-lens ui [--port N]` shall start the local web app on 127.0.0.1 only.

### CAP — capture (thin, deterministic, one visit)
- **CAP-1** The system shall fetch robots.txt once and honour `User-agent: *` and `cro-lens` rules for the page path; it shall identify itself with a `cro-lens/<version>` user-agent suffix.
- **CAP-2** The system shall load the page once per viewport — desktop 1440×900 and mobile (iPhone 13 emulation) — and take a full-page screenshot of each plus the first-screen (above-the-fold) crop.
- **CAP-3** The system shall extract visible text blocks per viewport with a stable id (`D12` desktop, `M7` mobile), tag, role hint (heading / cta / link / form-field / price / text), text and bbox, removing nested duplicates.
- **CAP-4** When a cookie/consent banner covers the first screen, the system shall try one decline/close action and record whether the banner was present and whether it was dismissed.
- **CAP-5** The system shall record lab timing in the same visit (TTFB, DCL, load, LCP, CLS, request count, transfer bytes as a lower bound); when `PAGESPEED_API_KEY` is set it shall add PageSpeed Insights scores. (assumption A-02)
- **CAP-6** Screenshots taller than the model's useful size shall be cut into viewport-height tiles, capped (desktop ≤ 6, mobile ≤ 4), and the report shall state when part of the page was not shown to the model.

### LLM — provider
- **LLM-1** All model calls go through one `Provider` interface; the shipped providers are `claude-code` (default, `claude -p` with the user's Claude Code credential — normally their subscription; an `ANTHROPIC_API_KEY` run is labelled billed, ADR 0007 — tools disabled) and `fake` (deterministic, offline, for tests). (assumption A-01)
- **LLM-2** Every call shall request JSON-schema structured output generated from the step's Pydantic model and validate it; on invalid output the system shall retry once, then fail the step with a clear error.
- **LLM-3** The system shall record per call: step, model, duration, token usage and equivalent USD; the run total appears in the report. (assumption A-05)
- **LLM-4** `CRO_LENS_PROVIDER=fake` (or `--provider fake`) shall select the fake provider.

### UND — understand the page
- **UND-1** The system shall infer audience, the job the visitor hires the product for, likely traffic source, awareness level (Schwartz: unaware … most aware), the page's core promise and offer, each with a confidence and the block ids it rests on.
- **UND-2** The system shall judge 5-second clarity from the first screen only: what a visitor would understand, whether the value proposition is clear, and whether it is specific or generic, quoting the copy it judged.

### ANA — analysis and persona walkthroughs
- **ANA-1** The system shall walk the page as five personas — skeptical first-timer, comparison shopper, ready-to-buy, mobile skimmer, risk-averse evaluator — each producing a walk log (where they stall, which objections are answered / partial / absent). (research: 2026-11-10_cro-teardown-practice.md)
- **ANA-4** The system shall score the page on the LIFT factors (value proposition, relevance, clarity, anxiety, distraction, urgency; 1–5 each, with one-line reason and block ids) as the analysis spine. (research: 2026-11-10_cro-teardown-practice.md)
- **ANA-2** Every finding shall carry: id, taxonomy category (contract `taxonomy@1`), title, personas affected, severity, ≥ 1 evidence item (block id + verbatim quote, viewport) and reasoning. A finding about something absent ("no pricing") cites the region where it was expected and is typed `absence`.
- **ANA-3** The system shall list what it could not verify (`unverifiable`: what, why, the assumption it made instead) — e.g. pricing behind a link, traffic source unknown.

### CHK — self-check
- **CHK-1** Deterministic check: every evidence item's block id exists in that viewport and its quote fuzzy-matches the block text (partial ratio ≥ 90 after whitespace/case normalisation); findings with no surviving evidence are dropped with reason `evidence_not_found`.
- **CHK-2** LLM check: a second, skeptical call sees each surviving finding with crops of its evidence regions and returns `kept` / `flagged` / `dropped` with a reason.
- **CHK-3** Dropped findings shall appear in the report's "Dropped by self-check" section with their reason; they never reach the backlog.

### HYP — experiment backlog
- **HYP-1** Each kept or flagged finding becomes ≥ 1 experiment: hypothesis (*If we change X to Y, then <metric> will <direction> for <persona/segment>, because <evidence-based reason>*), primary metric, ICE (Impact, Confidence, Ease, 1–10 each, one-line rationale each), and suggested copy or change where relevant.
- **HYP-2** The system shall choose the top 3 experiments and state why those three.
- **HYP-3** ICE score = mean of the three; the backlog is sorted by it; flagged findings' experiments carry a visible flag.
- **HYP-4** Confidence is computed, not asked: base 3, +1 evidence visible on the page (kept by self-check), +1 matches a LIFT factor scored ≤ 2, +1 raised by ≥ 2 personas; capped at 6 because the tool has no traffic data. The rationale lists which conditions held. (research: 2026-11-10_cro-teardown-practice.md)
- **HYP-5** Each experiment carries a guardrail metric and a feasibility flag (`ab_ok` / `bold_change_only` / `qualitative_only`); the system never invents sample sizes or traffic numbers. (research: 2026-11-10_cro-teardown-practice.md)

### REP — report
- **REP-1** Each run writes `report.md` and `report.json` (contract `report@1`): summary, top 3, experiment backlog, findings with evidence and crop images, page understanding, assumptions / couldn't verify, dropped findings, page speed, run metadata and cost.
- **REP-2** Evidence crops are PNG files in the run folder, linked from `report.md`.

### FB — the user's own eval (ADR 0008; replaces EVAL-1…6 and UI-4, retired 2026-11-11)
- **FB-1** On a finished run's report the user marks each finding (kept or flagged) right or wrong, with an optional note; a second click on the same verdict removes it. Grades are saved to `$CRO_LENS_HOME/grades.json` (contract `eval@2`) and survive the run's deletion.
- **FB-2** When a run starts, the system selects at most 12 of the user's graded findings — the same site first, newest first — writes them to the run folder's `feedback.json`, and shows them to the model in the `analyse` and `check` steps as the user's earlier verdicts. A resumed run reuses that file; `--no-feedback` (UI: unchecked `feedback-toggle`) selects none.
- **FB-3** The report states how many graded findings the run learned from and how many came from the same site (`run.feedback`, `## Run`, `feedback-used`).
- **FB-4** The user's eval — graded, valid, invalid, precision (overall and per category), evidence validity over all finished runs, how many grades the next run learns from, and one row per finished run — is shown at `/eval`, returned by `GET /api/eval` and printed by `cro-lens eval`. A metric without inputs reads `pending grades` / `pending runs`, never 0.
- **FB-5** Grades never leave the user's machine and are written only by the user's grade action; tests use a temporary `CRO_LENS_HOME`.

### UI — local web app
- **UI-1** Start screen: URL input, model choice, optional audience/traffic/goal, recent runs list.
- **UI-2** Live run screen: the pipeline steps update as they happen (SSE), with per-step duration and errors.
- **UI-3** Report screen renders `report.json`: summary, top 3, backlog with ICE, findings with quote + crop + element id, assumptions, dropped, speed, cost.
- **UI-5** The design follows `reports/research/2026-11-10_ui-references.md`; no generic AI-template look (no gradient heroes, emoji icons, card soup).

### SAFE — conduct
- **SAFE-1** One visit per viewport per run, no link following, no crawling, no bypassing bot protection.
- **SAFE-2** The UI binds to 127.0.0.1; nothing is sent anywhere except the page fetch and the model call.

## 3. Out of scope (v1)

Multi-page funnels; crawling or bulk runs over arbitrary URLs; rewriting the page; hosted SaaS, accounts; LinkedIn automation; Anthropic-API / OpenAI providers (interface only, A-01); report-to-report diffing.

## 4. Acceptance

Product-level acceptance drives the real entry points: the `cro-lens` CLI and the web app on a chosen port, with `CRO_LENS_HOME` pointing at a temp dir, `CRO_LENS_PROVIDER=fake` in place of the paid/subscription model call, and pages served from local fixture HTML (`tests/fixtures/pages/`) by a local HTTP server, so acceptance never touches the internet. Live checks (real `claude -p`, real sites) are separate, listed in the plan with an allowance.
