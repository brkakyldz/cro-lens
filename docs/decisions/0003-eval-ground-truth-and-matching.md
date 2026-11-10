---
status: superseded by 0008
date: 2026-11-10
---
# 0003 — Eval: seeded defects + owner labels, deterministic matching, frozen snapshots

## Context
The brief forbids claiming the tool works without a test. The builder must not write the labels (it would grade its own exam), and the autonomous run cannot wait for the owner's labels. No public labelled dataset of landing-page issues exists (research: 2026-11-10_cro-teardown-practice.md).

## Decision
- Ground truth A — **seeded defects**: real pages captured after a recorded DOM mutation removes or degrades something (CTA removed, headline made generic, pricing hidden). The defect is known by construction, so seeded recall is measurable now.
- Ground truth B — **owner labels** on 10–15 real pages (labels@1), plus owner grades of findings that match no label, giving label recall and precision.
- Matching is deterministic: same taxonomy category and evidence quote fuzzy-matching the label's anchor (or anchor null for absences). The owner can grade anything the rule misses.
- Eval runs only on frozen snapshots (`eval snapshot` once, then `eval run` offline). Snapshots are not committed (third-party captures, size); the manifest, labels and grades are.
- The baseline is one call, same model, same screenshots and page text, a plain critique prompt with a quote-only schema.

## Consequences
- RESULTS.md shows `pending owner labels` for recall/precision until the owner labels — never an invented number.
- Seeded cases measure detection of blatant defects, not judgement on subtle ones; RESULTS.md says so.
