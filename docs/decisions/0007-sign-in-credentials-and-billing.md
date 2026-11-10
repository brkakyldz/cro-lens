---
status: accepted
date: 2026-11-11
---
# 0007 — cro-lens names the Claude Code credential, works around a dead token, labels API-key runs as billed

## Context
cro-lens has no sign-in of its own: every model call is `claude -p` (ADR 0001), and Claude Code picks the credential. A spike on Claude Code 2.1.318 (2026-11-11, clean environment) showed three things the 0.2 sign-in check got wrong or left unsaid:

- `ANTHROPIC_API_KEY` wins over `CLAUDE_CODE_OAUTH_TOKEN`, which wins over the `claude auth login` sign-in. `claude auth status --json` names the winner (`authMethod`: `api_key`, `oauth_token`, `claude.ai`; `apiKeySource`) but calls it `loggedIn: true` without testing it.
- A revoked or invalid token makes `claude -p` print `Failed to authenticate. API Error: 401 Invalid bearer token`, which the 0.2 error patterns did not recognise, so the run failed as a generic model error.
- With an API key every call is billed to that API account, while the README, the report and invariant 6 said a run is never billed.

The owner's own machine had a dead `CLAUDE_CODE_OAUTH_TOKEN` in the user environment and a working `claude auth login` underneath it; every audit stopped before it began.

## Decision
- Preflight reads `claude auth status --json` and records the credential. A variable's credential (token or API key) is tested with one tiny haiku call.
- A rejected `CLAUDE_CODE_OAUTH_TOKEN` falls back to the `claude auth login` sign-in when that one passes the same test: cro-lens runs `claude` without the variable for that run and shows a notice telling the user to remove or renew it. With no working login it stops (exit 6 / 503) and names both fixes.
- A rejected `ANTHROPIC_API_KEY` stops the run. It is not swapped for the subscription, because the user set it on purpose.
- A working API key runs, with a notice before the run that every call is billed. `report.json` records `run.billing` (`subscription`, `api_key`, or `null` when not known: fake provider, a CLI without `auth status`, a report from before 0.3), and the CLI, `report.md` and the report page say `billed to your Anthropic API key` instead of `API-equivalent` for such a run.
- The README's Signing in section is the one place that explains the three credentials to users; error messages point there.

## Consequences
- A dead token costs one failed probe and one working probe (a few seconds) at every run start until the user removes it; the notice says so each time.
- `total_cost_usd` is still the only cost figure. On an API key it is Claude Code's estimate of the bill, labelled as an estimate.
- Other credentials Claude Code supports (`ANTHROPIC_AUTH_TOKEN`, `apiKeyHelper`, Bedrock, Vertex) are not tested or labelled; a run on one of them has `billing: null`.
- The error patterns are tied to Claude Code's wording; a new wording falls through to the generic model-call failure until it is added.
