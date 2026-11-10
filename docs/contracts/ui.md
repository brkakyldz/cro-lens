# ui@2

Start: `cro-lens ui --port <N>`; serves on `http://127.0.0.1:<N>`.
The server is ready when `GET /healthz` returns `200 {"ok": true}`.
Elements carry `data-testid` attributes named below; tests select by them only.

## JSON API

| Method & path | Body | Response |
|---|---|---|
| `GET /healthz` | – | `200 {"ok": true}` |
| `POST /api/runs` | `{"url", "model"?, "audience"?, "traffic"?, "goal"?, "feedback"?}` (`feedback` defaults to `true`; `false` = the run learns from no grades) | `202 {"run_id"}`; `400 {"error"}` when the URL is not http(s); `503 {"error"}` when the provider is not ready (Claude Code missing or not signed in) — no run is created |
| `GET /api/runs` | – | `200 [{"run_id","url","status":"running|done|failed","started_at","resume_from"}]`, newest first |
| `GET /api/runs/{id}` | – | `200` report@1 when done; `202 {"status":"running"}`; `409 {"status":"failed","exit_code","error","resume_from"}`; `404` unknown |
| `POST /api/runs/{id}/resume` | `{"model"?}` | `202 {"run_id","resume_from"}` and the run is running again; `409 {"error"}` when it is running, done, or cannot be resumed; `503` provider not ready; `404` unknown |
| `DELETE /api/runs/{id}` | – | `204`, run folder removed (its grades stay in `grades.json`); `409` while running; `404` unknown |
| `GET /api/provider` | – | `200 {"provider","ready":bool,"error"?}`; when ready also `"billing"` (`subscription`, `api_key` or null) and `"notices": [{"code","title","text","steps":[str],"commands":[{"label","command"}]}]` (`code` `api_key_billed`: an API key bills every call; `token_fallback`: a rejected token worked around; ADR 0007) |
| `GET /api/runs/{id}/events` | – | `text/event-stream`, see below |
| `GET /runs/{id}/files/{path}` | – | a file from the run folder (crops, screenshots); `404` outside it |
| `GET /api/runs/{id}/grades` | – | `200 {"<finding_id>": {"verdict","note","graded_at"}}` for this run's graded findings (`{}` when none); `404` unknown run |
| `PUT /api/runs/{id}/grades/{finding_id}` | `{"verdict":"valid|invalid","note"?}` | `200 {"finding_id","verdict","note","graded_at"}`, saved to `grades.json` (eval@2), replacing an earlier grade; `400` bad verdict; `404` unknown run or a finding that is not in the report or was dropped; `409` run not finished |
| `DELETE /api/runs/{id}/grades/{finding_id}` | – | `204` grade removed; `404` not graded |
| `GET /api/eval` | – | `200` the metrics of eval@2: `{"graded","valid","invalid","precision","by_category","evidence_validity","next_run_examples","runs"}` |

Runs started from the UI use the same pipeline, provider and run folder as the CLI.

`resume_from` is the step a resume would start from (`understand`, `analyse`,
`check`, `hypotheses`, `report`), or `null` when the run is not failed or has no
finished capture. A run with no end event whose process stopped (its
`heartbeat` file older than 30 s) is `failed` with exit code 1 and an error
containing `interrupted`. A step's state is its latest event in `steps.jsonl`.

## SSE `/api/runs/{id}/events`

Replays past events, then streams live ones:
- `event: step` · `data: {"step","status":"started|done|failed","seconds"?,"detail"?}`
- `event: end` · `data: {"status":"done|failed","exit_code","report_url"?}` — last event; `report_url` = `/runs/{id}`.

## Pages and test ids

**`GET /` — start**
`url-input`, `model-select` (options `sonnet`, `opus`), `audience-input`, `traffic-input`, `goal-input`, `feedback-toggle` (checkbox, checked by default: the run learns from the user's grades; unchecked sends `"feedback": false`), `start-button`; `recent-runs` containing every run as a `run-row` (`data-run-id`, `data-status`) with a `run-link` (anchor to `/runs/{id}`), a `run-delete` button unless running, and a `run-resume` button when `resume_from` is set. Submitting navigates to `/runs/{id}`. An invalid URL, or a `503`, shows `form-error` and does not navigate. `provider-warning` is shown when `GET /api/provider` says not ready; `provider-notice` lists its `notices` when it is ready and has any. Delete asks for confirmation first.

**`GET /runs/{id}` — live run and report**
While running: `step-<name>` for each step (`robots`, `capture`, `understand`, `analyse`, `check`, `hypotheses`, `report`), each with `data-status` = `pending|started|done|failed`. On `end` the page shows the report without a manual reload. A failed run shows `run-error` with the error line and, when `resume_from` is set, a `resume-button` ("Continue from …") that resumes it in place; with no finished capture it shows a `rerun-button` that starts a new run of the same URL instead. Action errors appear in `action-error`. `run-delete` (in the header, hidden while running) deletes the run and goes to `/`.
Report: `report-summary`, `top3` with 1–3 `top3-item`; `backlog` with one `experiment-row` per experiment carrying `data-experiment-id`, `data-ice` (score) and `data-flagged`; one `finding-card` per non-dropped finding with `data-finding-id`, `data-category`, `data-verdict` and `data-grade` (`valid`, `invalid`, or empty when ungraded), containing `finding-quote` (verbatim quote), `finding-crop` (`<img>`) when a crop exists, and the grade controls `grade-valid`, `grade-invalid` (buttons) and `grade-note` (text input); `grade-progress` above the findings says how many of them are graded (`<g> of <n> graded`); `understanding`; `unverifiable-list` with `unverifiable-item`s; `dropped-list` with `dropped-item`s (`data-finding-id`); `speed-panel`; `cost-total` (text contains `$` and `API-equivalent`, or `billed to your Anthropic API key` when `run.billing` is `api_key`); `feedback-used` says how many graded findings the run learned from (`learned from <n> graded findings`, `<k> from this site`) or that feedback was off.

**Grading.** Clicking `grade-valid` or `grade-invalid` saves that verdict with the text of `grade-note` and sets the card's `data-grade` without a reload; clicking the selected verdict again removes the grade (`data-grade` empty). Leaving a changed `grade-note` of a graded card saves the new note. Grades load with the page: a reload shows the same `data-grade` values. Dropped findings have no grade controls.

**`GET /eval` — your eval**
The metrics of eval@2 for this user: `eval-graded` (text contains the number of graded findings), `eval-precision` (a percentage, or `pending grades`), `eval-validity` (a percentage, or `pending runs`), `eval-examples` (text contains how many graded findings the next run learns from); one `eval-category-row` per graded category with `data-category`, `data-graded`, `data-valid`; one `eval-run-row` per finished run with `data-run-id`, `data-findings`, `data-graded` and a link to `/runs/{id}`. With nothing graded it shows `eval-empty` saying how to grade.
