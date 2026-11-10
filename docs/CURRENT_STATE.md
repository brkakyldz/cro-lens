---
project_id: cro-lens
implementation_agent: claude-code
branch: main
as_of: v0.2.0
active_milestone: none
active_run: none
---
# Current state

## Milestones
| ID | Status | Evidence | Commit |
|---|---|---|---|
| M1 | PASS | held-out CLI subset 8/8 — run report § Checks | ff380bc, eb2aa0c |
| M2 | PASS | live runs linear.app, proofhub.com; eval validity after check 294/294 — run report § Checks | ff380bc, 852c7b6 |
| M3 | PASS | held-out H07–H09; screenshots 1440/390 — run report § Checks | 2504054 |
| M4 | PASS | held-out H10–H11; 19/19 snapshots, seeded diffs — run report § Checks | 7b32250 |
| M5 | PASS | live eval → eval/RESULTS.md; verify-holdout VERIFIED 12/12; review fixes 579a59a | 158e656 |
| 0.2 | PASS | checkpointed resume, interrupted-run detection, run delete in the UI, Claude Code sign-in check (ADR 0006); independent review of 6f08904 → 5 IMPORTANT + 3 OPTIONAL, all fixed in 808bbda; unit 55/55, held-out 13/13; 3 live example audits in `examples/` | 6f08904, 808bbda |
| publish prep | PASS | `.publish.json`, history clean-up (audit clean), README, NOTICE, CONTRIBUTING, font OFL lines checked against upstream | this release |
| personal eval | PASS | ADR 0008: grades on reports → `grades.json`, up to 12 fed to `analyse`/`check`, `/eval` + `cro-lens eval`; shipped eval set removed; unit 55/55 (offline). Held-out rewritten by a fresh Opus author (H10–H11 retired, H13–H15 new): 14/14 after two product fixes it caught (stat label run into its number on `/eval`; run-row link carried `#findings`); landed byte-identical, 14/14 in place | a799f8a, merged to main |

The hashes above are those of the published history. Review ids in
`docs/reviews/findings.md` and older commit subjects keep the hashes from before
the 2026-11-10 history clean-up (`55d5302` = 6f4769c).

## Open gates
- Held-out gaps the author listed (COVERAGE.md): what each step was shown is not observable (the fake ignores examples; `test_feedback.py` covers it), no egress check for FB-5, grading a failed run may answer 404 or 409.
- Live check 2026-11-11 (calendly.com, Sonnet, test home, $0.93 for both runs): A with no grades gave 8 findings (kept 1 · flagged 6 · dropped 1). Then 3 were graded right and 4 wrong, with notes. B learned from those 7 and gave 6 findings (kept 2 · flagged 4 · dropped 0). Three of the four wrong kinds did not come back (headline nitpick, claim in a secondary card, extraction artefact). The fourth came back as a related privacy finding, and the self-check flagged it, citing the user's verdict. All three right kinds came back, and the pricing one moved from flagged to kept. One pair with no control run, so model variance is not separated out. Watch item: the self-check now gives "the user marked it right" as a reason to keep, and kept raises the computed ICE confidence. Grades can lift scores, not only filter findings.
- OPEN_GATE owner: the repo is private; making it public needs the maintainer's approval. Social preview image to upload: `docs/media/readme/social-preview.png`.
- Resume, delete and the sign-in check have unit tests only; no held-out scenarios cover them yet (`scenario-author` for the ui@1/cli@1 additions). That now includes ADR 0007 (credential check, dead-token fallback, `run.billing`, `provider-notice`), which the fake provider cannot reach: a held-out scenario needs a `fake@1` switch for it first.

## Blockers

## Next
Decide whether a user's grade may move a finding from flagged to kept (see the live check).
