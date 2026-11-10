# INTENT — cro-lens

The product intent the build started from (2026-11-10), distilled into English.
The requirement IDs in `docs/spec.md` map back to the clause checklist below. A
later intent is a new dated section, written by the maintainer.

## Product

cro-lens: give it one public landing page URL. It captures the page once, and a
model reasoning like a senior growth marketer infers the audience and intent,
judges the message, walks the page as several kinds of visitor, and returns a
prioritized backlog of testable A/B experiments. Every claim cites evidence on
the page.

The model's judgement is the product. Deterministic capture (screenshots, page
text, timing) is only its input and stays thin. A checklist ("is there a CTA
above the fold?") is not the product.

## Users and job

Growth marketers, founders and agencies who want to know, before or while
sending traffic, why a page may not convert and what to test first — with
evidence they can show someone else.

## Quality rules

1. Every finding cites evidence from the page: quoted copy, an element, or a
   screenshot region. No evidence, no claim.
2. The tool says what it could not verify, and what it assumed instead.
3. The output is an experiment backlog, not a critique list: a hypothesis, an
   ICE score with reasoning, and suggested copy or a change.
4. A self-check pass verifies that each finding's evidence exists and that the
   reasoning holds; unsupported findings are dropped or flagged.
5. Evaluated, not just demoed: 10–15 hand-labeled pages, with evidence validity
   and precision reported in the README.

## Constraints

- Runtime is Claude Code (`claude -p` on the user's own subscription), so no API
  key is needed. The provider layer stays swappable.
- Public pages only, one visit per run, robots.txt respected, no bulk scraping,
  no bypassing of bot protection.
- The cost of a run is shown in the report.
- A simple local web UI, designed from external references.
- Nothing is published without the maintainer's approval.

## Non-goals

Multi-page funnels, crawling, auto-rewriting pages, hosted SaaS, accounts,
social-media automation, a deterministic checklist product.

## 2026-11-11 — the eval is the user's own

The maintainer replaced the fixed eval set (quality rule 5, clauses 13–15)
with an eval each user builds from their own use. On a finished report the
user marks findings right or wrong; the tool measures its accuracy from those
grades, and every later run shows the model the user's graded findings, the
same site first, so it learns that user's bar. The shipped page set, its
hand labels, seeded cases and the single-prompt baseline are removed. Grades
stay on the user's machine. ADR 0008 records the decision.

## Clause checklist

1. URL in → analysis (CLI `cro-lens <url>`)
2. Infer audience, job-to-be-done, traffic source, awareness level
3. 5-second value-prop clarity, specific vs generic, objections, offer–audience fit
4. Persona walkthroughs: skeptical first-timer, comparison shopper, ready-to-buy
5. Prioritize top 3 with reasons
6. Capture thin: desktop + mobile screenshots, visible text/DOM, above-the-fold, page speed
7. Every finding cites evidence (quote / element / screenshot region)
8. Says what it couldn't verify
9. Experiment backlog: hypothesis, ICE with reasoning, suggested copy
10. Self-check step: evidence exists, reasoning holds; drop/flag
11. Structured (Pydantic) outputs between steps
12. Markdown report: summary, top 3, findings with evidence, assumptions, backlog
13. Eval: 10–15 pages, mix SaaS / e-commerce / apps, good and bad; hand labels; evidence validity + precision
14. Baseline comparison against a single prompt
15. README with demo GIF and eval results
16. Swappable provider; Claude Code runtime first
17. Cost per run in the report
18. Public pages, one visit, robots.txt
19. Local web UI: URL input, live steps, report view, labeling screen; reference-led
20. Nothing public without approval
