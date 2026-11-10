# Retired — 2026-11-11

The owner removed the shipped eval set (INTENT.md, section 2026-11-11; ADR
0008): no manifest, snapshots, hand labels, seeded cases, single-prompt
baseline, RESULTS.md, labeling screen or `--eval-dir`. Each user's eval is now
built from their own grades (FB-1 … FB-5, contract eval@2).

## Scenarios

| Scenario | Was | Why retired | Surviving requirements now covered by |
|---|---|---|---|
| H10 | `eval snapshot` (seeded mutation, hashes) → offline `eval run` of cro-lens and the baseline → metrics → RESULTS.md | Every surface it drove is gone: manifest, snapshots, `eval run`/`eval report`, baseline@1, RESULTS.md, `--eval-dir` | Evidence validity → FB-4 (H13, H15). CHK-1 drop of unmatched evidence → H01, H12. SAFE-1 "eval does not visit the site" no longer applies (the eval reads finished runs only); SAFE-1 stays covered by H03, H04, H06, H15 |
| H11 | Labeling screen: grade by fingerprint, add / delete labels, hand-edited YAML, RESULTS.md recall and precision | The labeling screen (UI-4), labels/ and grades/ YAML and RESULTS.md are gone | Grading a finding right/wrong in the UI → FB-1 (H13); precision from the user's grades → FB-4 (H13, H15) |

## Requirements

| Requirement | Was | Successor |
|---|---|---|
| EVAL-1 | Manifest of 10–15 pages and frozen snapshots with hashes | none — no shipped page set |
| EVAL-2 | `eval run` on snapshots only, never the live site | none — the eval reads finished runs (FB-4, H13/H15) |
| EVAL-3 | Single-prompt baseline system | none |
| EVAL-4 | Evidence validity, seeded recall, label recall / precision | FB-4: evidence validity over finished runs, precision from the user's grades (H13, H15) |
| EVAL-5 | RESULTS.md with `pending owner labels` until labeled | FB-4: `/eval`, `GET /api/eval`, `cro-lens eval` with `pending grades` / `pending runs` (H13, H15) |
| EVAL-6 | Labels editable in the UI and by hand in YAML | FB-1: grades given on the report (H13); grades.json written only by a grade action (FB-5) |
| UI-4 | Labeling screen | FB-1 grade controls on the report screen (H13), `/eval` page (H13, H15) |

Helpers removed from `conftest.py` with them: `fingerprint`, `results_path_from`,
`load_yaml`, `dump_yaml`, `results_table`, `cell_for`, `ratio_of`,
`EVAL_TIMEOUT`, `EVAL_RUN_ID_RE`, and the `eval_dir` / `--eval-dir` argument of
the `ui()` fixture.
