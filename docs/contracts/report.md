# run-folder@1 and report@1

## Run folder

`<run_id>` = `YYYYMMDD-HHMMSS-<host>` (host with dots → dashes, e.g. `20261110-181500-127-0-0-1`).

```
<run folder>/
  report.md            human report
  report.json          report@1 (below)
  steps.jsonl          one JSON object per step event: {"step","status":"started|done|failed","t":iso,"seconds"?, "detail"?}
                       a resumed run appends `{"step":"resume","status":"done","detail":"resuming from <step>"}`
                       and then the re-run steps' events; Ctrl-C/shutdown gives "failed" with detail "interrupted (…)"
  run.json             {url, run_id, started_at, model, given}: what resume needs
  feedback.json        the user's graded findings this run learns from (eval@2), written before robots
  state/<step>.json    checkpoint per finished step: {"step","result","calls"} (robots … hypotheses)
  heartbeat            touched every 5 s while a process works on the run; removed when it ends
  capture/
    desktop_full.png   full-page screenshot, 1440 wide
    desktop_fold.png   first screen, 1440×900
    mobile_full.png    full-page, iPhone 13 emulation
    mobile_fold.png    first screen
    blocks_desktop.json  [{"id":"D1","tag","role","text","bbox":[x,y,w,h]}]
    blocks_mobile.json   ids "M1"…
    page.html          DOM serialisation after load (desktop)
    meta.json          {url, final_url, status_code, title, captured_at, consent_banner:{present,dismissed}, speed:{…}, viewports:{desktop:{height,tiles_sent,truncated}, mobile:{…}}}
  crops/
    <finding_id>-<n>.png   one per evidence item that resolved to a block
```

`role` ∈ `heading`, `cta`, `link`, `form_field`, `price`, `text`.

## report.md sections, in this order (H2 headings, exact text)

`## Summary`, `## Top 3 experiments`, `## Experiment backlog`, `## Findings`,
`## What this page is (understanding)`, `## Assumptions and couldn't verify`,
`## Dropped by self-check`, `## Page speed`, `## Run`.
The `## Run` section says how many graded findings the run learned from
(`Learned from <n> of your graded findings (<k> from this site).`) or that
feedback was off.
The `## Run` section states the model, provider, duration and the cost line
`$<x> API-equivalent`, or `$<x> billed to your Anthropic API key` when
`run.billing` is `api_key` (ADR 0007).

## report.json (report@1)

```jsonc
{
  "schema_version": "report@1",
  "run": {"id": str, "url": str, "final_url": str, "started_at": iso, "finished_at": iso,
          "provider": "claude-code|fake", "model": str,
          "billing": "subscription|api_key|null",   // who paid (ADR 0007); null: fake, unknown, or written before 0.3
          "given": {"audience": str|null, "traffic": str|null, "goal": str|null},
          "feedback": {"enabled": bool, "examples": int, "same_site": int}|null},  // eval@2; null before 0.3
  "capture": { /* meta.json content */ },
  "understanding": {
    "audience":        {"value": str, "confidence": "low|medium|high", "source": "inferred|given", "evidence": [block_id]},
    "job_to_be_done":  {"value": str, "confidence": …, "evidence": [block_id]},
    "traffic_source":  {"value": str, "confidence": …, "source": "inferred|given", "evidence": [block_id]},
    "awareness_level": {"value": "unaware|problem_aware|solution_aware|product_aware|most_aware", "confidence": …, "evidence": [block_id]},
    "promise": {"value": str, "evidence": [block_id]},
    "offer":   {"value": str, "evidence": [block_id]},
    "five_second": {"understood": str, "clear": bool, "specific": bool, "quote": str, "evidence": [block_id]}
  },
  "lift": [{"factor": "value_proposition|relevance|clarity|anxiety|distraction|urgency", "score": 1-5, "reason": str, "evidence": [block_id]}],
  "personas": [{"persona": "skeptical_first_timer|comparison_shopper|ready_to_buy|mobile_skimmer|risk_averse_evaluator",
                "stalls": [{"block_id": str, "why": str}],
                "objections": [{"objection": str, "status": "answered|partial|absent"}]}],
  "findings": [{
    "id": "F1", "category": taxonomy@1, "kind": "issue|absence", "title": str,
    "personas": [persona], "severity": "high|medium|low", "reasoning": str,
    "evidence": [{"block_id": str, "viewport": "desktop|mobile", "quote": str, "crop": "crops/F1-1.png"|null, "valid": bool}],
    "check": {"deterministic": "pass|fail", "verdict": "kept|flagged|dropped", "reason": str}
  }],
  "unverifiable": [{"what": str, "why": str, "assumption": str}],
  "experiments": [{
    "id": "X1", "finding_id": "F1", "hypothesis": str,
    "change": {"from": str, "to": str}, "suggested_copy": str|null,
    "primary_metric": str, "guardrail_metric": str,
    "feasibility": "ab_ok|bold_change_only|qualitative_only",
    "ice": {"impact": 1-10, "confidence": 1-6, "ease": 1-10, "score": float,
            "rationale": {"impact": str, "confidence": str, "ease": str}},
    "flagged": bool
  }],
  "top3": [{"experiment_id": "X…", "why": str}],
  "summary": str,
  "cost": {"total_usd_equivalent": float, "calls": [{"step": str, "model": str, "seconds": float, "input_tokens": int, "output_tokens": int, "usd": float}]}
}
```

Invariants a test may assert:
- `findings` contains every finding, including dropped ones (`check.verdict == "dropped"`).
- A finding with `check.deterministic == "fail"` has `verdict == "dropped"` and `reason` starting `evidence_not_found`.
- Every experiment's `finding_id` refers to a finding whose verdict is `kept` or `flagged`; `flagged` on the experiment equals verdict `flagged`.
- `experiments` is sorted by `ice.score` descending; `ice.score` = round(mean(impact, confidence, ease), 2); `ice.confidence` ≤ 6.
- `top3` has min(3, len(experiments)) entries, all ids present in `experiments`.
- `cost.total_usd_equivalent` = sum of `calls[].usd` (rounded to 4 dp); with the `fake` provider every `usd` is 0.
- Every `evidence.crop` that is not null exists in the run folder.
