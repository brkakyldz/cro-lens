---
status: accepted
date: 2026-11-10
---
# 0002 — Evidence is a block id plus a verbatim quote, checked by code first

## Context
The brief's first rule: every finding cites evidence, and a self-check verifies it exists. If the verification is itself an LLM, "evidence validity" is one model grading another. Spike V-2 showed the model reliably cites ids from a provided block list (12/12 across Sonnet and Opus on linear.app).

## Decision
Capture gives every visible text block an id per viewport (`D12`, `M7`) with tag, role and bbox. The analysis schema requires `{block_id, viewport, quote}` per evidence item. Self-check runs in two parts: (1) code — the id exists and the quote fuzzy-matches the block text (rapidfuzz partial ratio ≥ 90 after normalisation), else the finding is dropped as `evidence_not_found`; (2) a skeptical LLM pass that sees the survivors with crops of their evidence regions and keeps, flags or drops them. Absence findings cite the region where the thing was expected. Experiments are written only after the self-check (A-03).

## Consequences
- Evidence validity is a deterministic metric, comparable with the baseline (which can only quote, not cite ids).
- Crops come for free from bboxes, which the report and UI show.
- Visual-only claims (an image, colour contrast) still need a block nearby to anchor to; pure-visual findings without text are out of reach in v1.
