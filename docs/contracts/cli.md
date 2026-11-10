# cli@2

## Commands

```
cro-lens analyze <url> [--model sonnet|opus] [--provider claude-code|fake]
                       [--audience TEXT] [--traffic TEXT] [--goal TEXT] [--out DIR]
                       [--no-feedback]
cro-lens <url> [same options]          # alias of analyze
cro-lens resume <run_id|DIR> [--model sonnet|opus] [--provider claude-code|fake]
cro-lens ui [--port 8765]
cro-lens eval
cro-lens --version
```

`--out DIR` writes the run folder to exactly
`DIR` instead of `$CRO_LENS_HOME/runs/<run_id>/`.

## Exit codes (`analyze`)

| Code | Meaning | Report written? |
|---|---|---|
| 0 | success | yes |
| 2 | invalid input (not an `http`/`https` URL, bad flag) | no |
| 3 | robots.txt disallows the path | no |
| 4 | page could not be loaded (network error, timeout, HTTP status ≥ 400) | no |
| 5 | blocked: bot challenge, captcha or login wall detected | no |
| 6 | an LLM step failed after one retry | no (`steps.jsonl` and `capture/` remain) |
| 1 | unexpected error | no |

For codes 2–6 stderr has one line starting `error:` that names the cause
(e.g. `error: robots.txt disallows /private/page.html`). No LLM call is made for
codes 2–5.

**Provider check first.** Before the run folder is created or the page is
visited, the provider is checked (`claude auth status`; a `CLAUDE_CODE_OAUTH_TOKEN`
or `ANTHROPIC_API_KEY` is tested with one tiny call, ADR 0007). Claude Code missing or
not signed in → exit 6, `error: Claude Code is not signed in. … claude auth login …`,
no run folder; a rejected variable is named in the message (`error: Claude Code
rejected the token in CLAUDE_CODE_OAUTH_TOKEN …` / `… the key in ANTHROPIC_API_KEY …`).
A rejected token with a working `claude auth login` underneath is not an error: the
run uses the login. A sign-in error returned by a model call mid-run is not retried
and gives the same message (exit 6).

**Notices.** When the check finds an API key (every call billed) or worked around
a rejected token, stderr gets, before the first step line, one block per notice:
a line starting `! ` with its title, then indented lines with what happened, the
numbered fix steps and the commands, and `More: README → Signing in`.

## `resume`

Continues a stopped run in its own folder: `<run_id>` under
`$CRO_LENS_HOME/runs/`, or a run folder path. Steps whose checkpoint exists in
`state/` are reused and print `✓ <step>  reused from the earlier attempt`; the
first step without one, and every step after it, runs again. The first line is
`✓ resume  resuming from <step>`, then the step lines and the two final lines.
`--model` may differ from the model in `run.json` only while no model step has
a checkpoint; the given context is always the original.

Resume never visits the page: it needs a finished capture that still loads.
Exit codes as for `analyze`, plus exit 2 with an `error:` line when there is
nothing to resume — unknown run, already finished, still running in another
process, a model switch after model steps were saved, or a capture that never
completed or is damaged (start a new run).

## Stdout of a successful `analyze`

One line per step, in order, each starting with `✓` (done) or `✗` (failed) and
the step name: `robots`, `capture`, `understand`, `analyse`, `check`,
`hypotheses`, `report`. Then the two final lines:

```
report: <absolute path to report.md>
cost: $<0.000> API-equivalent (<n> model calls)
```

When the run was billed to an API key (`run.billing == "api_key"`) the cost line
reads `cost: $<0.000> billed to your Anthropic API key (Claude Code's estimate) (<n> model calls)`.

The `check` line contains `kept <k> · flagged <f> · dropped <d>`.

## Feedback

By default a new run learns from the user's grades (contract eval@2): it
writes `feedback.json` in the run folder before the robots step and shows the
selected graded findings to the model. `--no-feedback` writes
`{"enabled": false, "examples": []}` and shows none. `resume` reuses the run's
own `feedback.json`.

## `eval`

Prints the user's eval (eval@2 metrics) and exits 0. Four lines, in order:

```
graded: <n> findings (<v> valid · <i> invalid)
precision: <p>%                       or  precision: pending grades
evidence validity: <x>% over <r> runs  or  evidence validity: pending runs
next run learns from: <k> graded findings
```

Grades are given in the web app (`cro-lens ui`, ui@2 § Grading); the CLI only reads them.
