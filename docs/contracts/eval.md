# eval@2 — the user's own eval, built from their grades

There is no shipped eval set. Every user builds their own: on a finished run's
report they mark findings right or wrong, the tool measures its accuracy from
those grades, and the next runs show the model the graded findings so it learns
that user's bar (ADR 0008). Everything stays on the user's machine, under
`$CRO_LENS_HOME`; nothing is sent anywhere.

## grades.json — `$CRO_LENS_HOME/grades.json` (grades@1)

Written only by a grade action (UI or API). Each grade is self-contained, so it
outlives the run it came from: deleting a run keeps its grades.

```jsonc
{
  "schema_version": "grades@1",
  "grades": {
    "<run_id>/<finding_id>": {
      "run_id": str, "finding_id": "F1", "url": str,
      "host": str,                 // lower-case hostname without a leading "www."
      "category": taxonomy@1, "kind": "issue|absence", "title": str,
      "quote": str,                // the finding's first valid evidence quote
      "verdict": "valid|invalid",
      "note": str,                 // the user's own words, may be ""
      "graded_at": iso
    }
  }
}
```

Only findings that reached the report (verdict `kept` or `flagged`) can be
graded; dropped findings cannot.

## What the next run learns — `<run folder>/feedback.json`

Written when a run starts, before the robots step, and never changed after; a
resumed run reuses it as it is.

```jsonc
{"enabled": bool,                  // false with --no-feedback / "feedback": false
 "examples": [{"run_id", "finding_id", "host", "same_site": bool, "category", "kind",
               "title", "quote", "verdict", "note"}]}
```

Selection: at most **12** grades. Grades on the same host as the new run come
first, newest `graded_at` first; the remaining places go to grades from other
hosts, newest first. With feedback off, or nothing graded yet, `examples` is `[]`.

The examples are shown to the model in the `analyse` and `check` steps as the
user's earlier verdicts. `report.json` records how many in `run.feedback`
(contract `report@1`).

## Metrics — `GET /api/eval`, the `/eval` page and `cro-lens eval`

| Metric | Definition | `null` when |
|---|---|---|
| `graded`, `valid`, `invalid` | counts over every grade in `grades.json` | never (0 is a count) |
| `precision` | `valid / graded`, 0–1 | nothing graded |
| `by_category[]` | `{category, graded, valid, precision}` per category with ≥ 1 grade | — |
| `evidence_validity` | evidence items with `valid: true` / all evidence items, over every finding (dropped included) of every finished run in `$CRO_LENS_HOME/runs/` | no finished run |
| `next_run_examples` | `min(12, graded)` | never |
| `runs[]` | finished runs, newest first: `{run_id, url, finished_at, findings, graded, valid}` — `findings` counts kept + flagged | — |

A metric without inputs is `null` and is shown as `pending grades` /
`pending runs` — never `0` or `0%`.
