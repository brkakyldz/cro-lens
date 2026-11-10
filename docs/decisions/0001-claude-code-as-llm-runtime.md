---
status: accepted
date: 2026-11-10
---
# 0001 — Claude Code CLI is the LLM runtime

## Context
The owner wants people to run cro-lens without paying for an API, while keeping the provider swappable. Spike V-1/V-2: `claude -p` on subscription auth takes base64 images over `--input-format stream-json`, returns schema-valid JSON with `--json-schema`, runs with tools off (`--tools ""`) and a custom system prompt, and reports `total_cost_usd` and token usage. `--bare` is unusable on subscription auth (V-1b).

## Decision
All model calls go through `Provider.complete(step, system, content_blocks, schema) -> (dict, Usage)`. Shipped implementations: `claude-code` (subprocess `claude -p`, stream-json in/out, UTF-8, one retry on invalid output) and `fake` (deterministic, contract `fake@1`). Anthropic-API and OpenAI providers are not shipped in v1; adding one is one module implementing the same method.

## Consequences
- Users need Claude Code installed and signed in; the README says so.
- Cost is shown as the API-list-equivalent figure `claude -p` reports, labelled as such; nothing is metered.
- Each call carries ~11.5k tokens of fixed CLI overhead (V-1); four calls per run is the budget, so steps are not split further.
- Tests and acceptance never call a model (fake provider).
