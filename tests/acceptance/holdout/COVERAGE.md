# Held-out coverage — cro-lens v1 (eval@2 revision, 2026-11-11)

Written from `spec.md` and `contracts/` only, without seeing product code.
13 scenario files (14 test items; H04 runs two journeys). Smoke: H01, H03,
H05, H07, H08, H13. H10 and H11 are retired with the shipped eval set — see
[RETIRED.md](RETIRED.md).

| Scenario | Journey |
|---|---|
| H01 | CLI analyze of the SaaS page; stdout, run folder, self-check, backlog, crops, report.md |
| H02 | Scheme-less URL refused (exit 2), then alias run with given context and `--out` |
| H03 | robots.txt disallows the path → exit 3, no page fetch, no LLM step |
| H04 | Bot challenge → exit 5 / missing page → exit 4, no bypass, no LLM step |
| H05 | Fake fails `check` → exit 6, capture and steps.jsonl kept, no report |
| H06 | Consent-banner page: capture geometry, blocks, timing, tiles, what the site saw |
| H07 | Web app: start a run, watch it finish without a reload, read the report, recent runs |
| H08 | JSON API + SSE: refusal, step stream, run files, path escape refused, list order, bind address |
| H09 | Web app: bad URL form error, then a run failing in `analyse` |
| H12 | Analysis spine: LIFT, personas, evidenced findings, honest hypotheses and confidence |
| H13 | Empty eval reads `pending …`; run from the start screen; grade on the report (note, replace, toggle off, note-on-leave, reload); dropped F3 not gradable; /eval, API and `cro-lens eval` show real numbers |
| H14 | Grades from the app plus grades merged from an old laptop; the next CLI run learns from 12 (same site first, newest first); `run.feedback`, `## Run`, `feedback-used`; a toggle-off run learns from none; feedback.json frozen |
| H15 | A run stopped in `check` is resumed after a grade is removed (keeps its feedback, no page visit); the graded run is deleted but its grade stays in the eval and teaches the next run; `--no-feedback` learns from none |

H01–H09 and H12 are unchanged by this revision: none used `--eval-dir` or an
eval@1 surface. Only conftest changed under them (retired helpers removed,
the `ui()` factory no longer takes `eval_dir`).

## Requirement → scenarios

| Requirement | Scenarios | Notes |
|---|---|---|
| CLI-1 | H01, H02, H06, H12, H14, H15 | default folder (H01), alias + `--out` (H02), `--no-feedback` (H15) |
| CLI-2 | H01, H05, H14 | step lines in order, check counts, cost line; failed step marked ✗ |
| CLI-3 | H02 (exit 2), H03 (3), H04 (4, 5), H08/H09 (UI/API refusal) | login wall: see gaps |
| CLI-4 | H02, H07, H05 | all five flags; `given` replaces inferred |
| CLI-5 | H07, H08 | served on 127.0.0.1:<port> |
| CAP-1 | H03, H04, H06 | robots once; `cro-lens/<version>` UA matches `--version` |
| CAP-2 | H06, H08, H05 | 1440 wide, 1440×900 fold, portrait mobile |
| CAP-3 | H06, H12, H02 | ids, roles, bbox, no nested duplicate of the first heading |
| CAP-4 | H06 (present + dismissed), H01 (absent) | |
| CAP-5 | H06 | shape only: numeric lab timing recorded; see gaps |
| CAP-6 | H06 | shape only: tile caps and `truncated` flag; see gaps |
| LLM-1 | H01, H02 | `provider: fake` recorded; `claude-code` default out of reach |
| LLM-2 | H05, H09, H15 | step failure → exit 6 / 409; retry-once not observable |
| LLM-3 | H01, H07 | per-call step/model/seconds/tokens/usd; total; count = stdout |
| LLM-4 | H01 (env), H02 (`--provider fake`) | |
| UND-1 | H02, H07 | shape + fake promise grounded in h1; reasoning quality out of reach |
| UND-2 | H02 | shape; quote found on the page |
| ANA-1 | H12 | five persona walks with stalls/objections (shape) |
| ANA-2 | H12, H01 | every field; evidence resolves to a block with verbatim quote |
| ANA-3 | H02, H07 | |
| ANA-4 | H12 | six LIFT factors, 1–5, reason, valid block ids |
| CHK-1 | H01, H12, H13 | F3 dropped `evidence_not_found`; evidence validity metric derived from it (H13, H15) |
| CHK-2 | H01, H07 | fake verdicts kept / flagged |
| CHK-3 | H01, H07, H13 | dropped listed in its section/list, never in backlog or cards, never gradable |
| HYP-1 | H12, H01 | If/then/because, metric, ICE rationales, change |
| HYP-2 | H01, H07 | top 3 = min(3, n) with reasons |
| HYP-3 | H01, H07 | mean, sorting, flagged mirrored in JSON and UI |
| HYP-4 | H12 | bounded check, see gaps |
| HYP-5 | H12 | guardrail, feasibility enum, no sample sizes / traffic numbers in report.md |
| REP-1 | H01, H02, H14, H15 | files, H2 order, sections' content; `run.feedback` and the `## Run` feedback line (H14, H15) |
| REP-2 | H01, H07, H08 | crops exist, linked, rendered, served |
| FB-1 | H13, H14, H15 | grade valid/invalid with note in the UI, replace, second click removes, note saved on leave, reload keeps; grades@1 entries self-contained; dropped (H13) and unfinished (H15) findings refused; grades survive run deletion (H15) |
| FB-2 | H14, H15, H13 | feedback.json: cap 12, same site first, newest first, verdict + note carried (H14); toggle off (H14) and `--no-feedback` (H15) → `{"enabled": false, "examples": []}`; resume reuses the file unchanged (H15); never changed after the run starts (H14) |
| FB-3 | H14, H15, H13 | `run.feedback` {enabled, examples, same_site}; `## Run` "Learned from n … (k from this site)" or feedback off; `feedback-used` in the UI |
| FB-4 | H13, H15, H14 | `pending grades` / `pending runs` and null, never 0; graded/valid/invalid, precision, per-category rows, evidence validity over finished runs only, next-run examples = min(12, graded), one row per finished run — on /eval, GET /api/eval and `cro-lens eval` |
| FB-5 | H13, H14, H15 | grades.json only under `$CRO_LENS_HOME`; runs, report views, eval reads and run deletion write no grade; "never leave the machine" only partly, see gaps |
| UI-1 | H07, H09, H13, H14 | `feedback-toggle` checked by default (H13, H14) |
| UI-2 | H08 (SSE), H07 (no reload), H09 (step statuses on failure) | |
| UI-3 | H07, H13, H14 | grade controls, `grade-progress`, `feedback-used` |
| UI-5 | — | not testable, see gaps |
| SAFE-1 | H03, H04, H06, H15 | site request log: one load per viewport, no link following, no retry past a wall; resume makes no request (H15) |
| SAFE-2 | H08 | non-loopback address refused; "nothing sent elsewhere" only partly, see gaps |

## Not tested, and why

Out of reach by design (real model / internet):
- **UND-1, UND-2, ANA-1, ANA-4 reasoning quality** — need a real model; only the contract shape is tested with the fake.
- **LLM-1 `claude-code` provider and default selection** — needs `claude -p` on a subscription.
- **CAP-5 PageSpeed Insights with `PAGESPEED_API_KEY`** — needs the internet.
- **Whether grades actually improve the model's judgement** — needs a real model over time; fake@1 ignores the examples by design.

Contract gaps (the requirement is testable in principle, the contracts do not give a test a handle):
- **FB-2 "shows them to the model in the `analyse` and `check` steps"** — no artefact records what a step's prompt contained (`state/<step>.json` holds the result and calls, not the input) and fake@1 says the examples do not change its output. A test can see what was *selected* (feedback.json, `run.feedback`), not that it reached those two steps and not the others. A fake-provider echo (e.g. the number of examples it saw per step in `state/<step>.json` or `cost.calls`) would close it.
- **FB-5 "grades never leave the user's machine"** — no network-egress observation is defined; tests check where grades are written and that the fixture site sees only robots.txt and page loads, not that nothing else is sent.
- **ui@2 delete confirmation** — "Delete asks for confirmation first" names no test id for the confirm step (native `confirm()` or an in-page control), so H15 deletes through `DELETE /api/runs/{id}`; the `run-delete` button path is not driven.
- **Refusal code for grading a failed run** — ui@2 lists both `404` (a finding not in the report) and `409` (run not finished) and a failed run matches both; H15 accepts either and asserts nothing was saved.
- **`feedback-used` with zero examples while feedback is on** — the template is `learned from <n> graded findings`; H13 accepts `0` or `no`.
- **Hand-merged grades.json** — eval@2 says grades.json is written only by a grade action and defines grades@1 fully, but does not say whether a grades@1 file restored by the user is honoured. H14 relies on it (one restored file, app closed while it is written) to reach the 12-grade cap without seven runs; if the owner rules that out, H14 needs seven graded runs instead.
- **UI-5 design** — no observable contract; it is a review judgement.
- **CAP-5 lab timing keys** — `meta.json` says `speed:{…}` without key names, so TTFB/DCL/LCP/CLS/requests/bytes cannot be checked individually; H06 checks only that numeric timings exist.
- **CAP-6 truncation** — no fixture page is taller than 6 desktop / 4 mobile tiles, and the report wording for "part of the page was not shown" is not fixed; H06 checks caps and the flag only.
- **CLI-3 login wall** — no fixture page shows a login wall; only the bot challenge (exit 5) is tested.
- **ANA-2 `absence` findings** — the fake never emits one, and `/no-cta.html` has no fake behaviour defined (no cta and no link for F2), so absence typing and "cites the region where it was expected" cannot be driven.
- **LLM-2 retry once / schema validation** — neither steps.jsonl nor `cost.calls` is specified to show attempts, so "retry once, then fail" is visible only as the final exit 6.
- **HYP-4 exact confidence** — the mapping from a finding category to a LIFT factor is not in a contract, and the fake's LIFT scores and personas are unspecified; H12 asserts the bounds the rule allows given the verdict and persona count (and +1 for the kept F1).
- **LLM-4 flag vs env precedence** — testing@1 requires `CRO_LENS_PROVIDER=fake` always, so `--provider fake` alone (env unset) is not exercised; H02 passes both.
- **SAFE-2 "nothing is sent anywhere except the page fetch and the model call"** — no network-egress observation is defined; tests see the fixture site's request log and the bind address only.
- **Unspecified details the tests avoid asserting:** run-id collision within one second; exact `data-flagged` values (H07 accepts `true`/`1`); the order of two grades with equal `graded_at` (H14 checks newest-first as non-increasing); whether the `## Run` / `feedback-used` "off" wording uses the word "off" (a regex on off / disabled / not learn is used).
