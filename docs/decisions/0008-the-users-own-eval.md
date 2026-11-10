---
status: accepted
date: 2026-11-11
supersedes: 0003
---
# 0008 — The eval is the user's own: grades on their reports, fed back to the next runs

## Context
cro-lens shipped with one fixed eval set: 15 real pages and 4 seeded cases in
`eval/manifest.yaml`, frozen snapshots, hand labels, a single-prompt baseline
and `RESULTS.md` (ADR 0003). Every user got the same set, and its precision
waited on the maintainer's labels. The maintainer found that backwards
(2026-11-11): the eval should build up from each user's own use, and their
grades should make the tool better for them.

## Decision
- **Grades on real reports.** On a finished report the user marks each kept or
  flagged finding right or wrong, with an optional note. Grades go to
  `$CRO_LENS_HOME/grades.json` (eval@2). Each grade is self-contained (category,
  title, quote, host, verdict, note), so it outlives its run, and it never
  leaves the machine.
- **Feedback to the model, not a filter.** When a run starts it selects at most
  12 grades, the same site first and then the newest, and freezes them in the
  run folder as `feedback.json`. The `analyse` and `check` prompts show them as
  the user's earlier verdicts. A resume reuses the frozen file, so retried steps
  see what the first attempt saw. Users can turn it off per run
  (`--no-feedback`, or the start-page checkbox).
  - Rejected: a deterministic filter that drops a finding like one marked wrong.
    It would hide true findings that only look alike, and the user picked
    feedback to the model.
  - Rejected: fine-tuning. There is no API to fine-tune through Claude Code.
- **The measure is the user's.** Precision = graded right / graded, overall and
  per category. Evidence validity is computed from every finished run's quote
  check. Both are `null` → `pending …` until they have inputs.
- **The fixed set is gone.** That covers the manifest, snapshots, seeded cases,
  baseline, labels, `RESULTS.md`, `cro-lens eval snapshot|run|report` and the
  labeling screen. `cro-lens eval` now prints the user's own numbers.

## Consequences
- There is no shared benchmark any more. A prompt change can no longer be
  scored offline against the same pages before and after. Its effect shows up
  only in users' precision over time, so a change in quality is slower to see
  and cannot be compared across users.
- The README can no longer quote a precision figure for the tool; it can only
  explain how each user gets their own.
- Feedback is in-context learning. It shapes a run only as far as the model
  follows the examples. A user who grades little teaches little, and the
  12-example cap keeps prompts bounded. The fake provider ignores the examples,
  so tests check the wiring (`feedback.json`, `run.feedback`, the prompt text),
  not the effect.
- Grades are local. Two machines of the same user do not share them.
- Held-out scenarios H10–H11 (eval@1) are retired; FB-1…FB-5 get new ones.
