# Contracts — the test surface

Everything a black-box test may rely on. Changing a contract after the
held-out scenarios exist means re-running `scenario-author` for the affected
requirement IDs.

| Contract | File |
|---|---|
| `cli@2` — commands, flags, exit codes, stdout | [cli.md](cli.md) |
| `run-folder@1`, `report@1` — files a run writes, `report.json` shape | [report.md](report.md) |
| `taxonomy@1` — finding / label categories | [taxonomy.md](taxonomy.md) |
| `eval@2` — the user's grades, what a run learns from them, the metrics | [eval.md](eval.md) |
| `ui@2` — routes, API, SSE events, test ids | [ui.md](ui.md) |
| `fake@1` — the offline provider and the fixture pages | [fake.md](fake.md) |

## Environment

| Variable | Meaning | Default |
|---|---|---|
| `CRO_LENS_HOME` | data root; runs go to `$CRO_LENS_HOME/runs/`, grades to `$CRO_LENS_HOME/grades.json` | `~/.cro-lens` |
| `CRO_LENS_PROVIDER` | `claude-code` or `fake` | `claude-code` |
| `CRO_LENS_FAKE_FAIL` | with `fake`: name of a step to fail (`understand`, `analyse`, `check`, `hypotheses`) | unset |
| `PAGESPEED_API_KEY` | enables PageSpeed Insights in capture | unset |

Install for tests: `uv sync` then `uv run playwright install chromium`. The
console entry point is `cro-lens` (`uv run cro-lens …`).
