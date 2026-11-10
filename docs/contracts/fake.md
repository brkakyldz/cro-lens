# fake@1 — offline provider and fixture pages

## The fake provider (`CRO_LENS_PROVIDER=fake` or `--provider fake`)

Deterministic, no network, zero cost (`usd: 0`, tokens 0). Given the captured
desktop blocks it returns:

- **understand**: promise = text of the first `h1` block (cited); audience
  `"fixture audience"`, confidence `low`, inferred unless given; traffic source
  `"unknown"` inferred unless `--traffic` given (then that value, `source: given`).
- **analyse**: exactly three findings —
  - `F1` category `value_prop_clarity`, evidence = the first `h1` block, quote = its full text;
  - `F2` category `cta`, evidence = the first block with role `cta` (or, if none, the first `link`), quote = its full text;
  - `F3` category `social_proof`, evidence = the first `h1` block id with quote `"THIS TEXT IS NOT ON THE PAGE"`.
  Plus one `unverifiable` item: what `"traffic source"`.
- **check (LLM part)**: `F1` → `kept`, `F2` → `flagged`. (`F3` never reaches it: the deterministic check drops it with `evidence_not_found`.)
- Grades shown to it (eval@2 feedback) do not change its output: what a run learned from is observable in `feedback.json` and `run.feedback`, not in the fake's findings.
- **hypotheses**: one experiment per kept/flagged finding (`X1` ← F1, `X2` ← F2) with impact 6, ease 5; confidence from the HYP-4 rule.

`CRO_LENS_FAKE_FAIL=<step>` makes that step's call fail every time → `analyze` exits 6.
`CRO_LENS_FAKE_FAIL=signin` makes the provider check fail with the Claude Code
"not signed in" message → `analyze` exits 6 before any visit; `POST /api/runs` answers 503.

## Fixture pages (`tests/fixtures/pages/`, served by any static HTTP server)

| Path | Content |
|---|---|
| `/robots.txt` | `User-agent: *` / `Disallow: /private/` |
| `/saas.html` | h1 "Ship invoices in 30 seconds", a subheading, a button "Start free trial", a pricing section "$12 / month", three testimonial paragraphs, a 5-field form |
| `/shop.html` | an e-commerce product page: h1 "Merino Trail Sock", price "$24", "Add to cart" button, reviews |
| `/no-cta.html` | h1 "Welcome to our platform", paragraphs only, no button and no link |
| `/challenge.html` | title "Just a moment...", body "Verify you are human" |
| `/private/page.html` | any content (disallowed by robots.txt) |
| `/consent.html` | saas-like page with a fixed cookie banner (`#cookie-banner`) and a "Reject all" button that removes it |

A missing path returns 404 (→ exit 4).
