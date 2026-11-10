---
status: accepted
date: 2026-11-10
---
# 0005 — Page speed from the visit itself; PageSpeed Insights optional

## Context
The brief names Google PageSpeed Insights. Spike V-4: keyless PSI returns 429 (shared daily quota). V-6: Navigation Timing plus buffered LCP/CLS observers in the same Playwright visit give TTFB, DCL, load, LCP, CLS and request count at no cost and no second request to the site.

## Decision
Lab timing on the mobile visit is always recorded; PSI is added when `PAGESPEED_API_KEY` is set. The report labels lab numbers as one local measurement, not field data, and transfer bytes as a lower bound.

## Consequences
One visit per viewport stays true. Speed is input for the model's `mobile_speed_access` judgement, not a score of its own.
