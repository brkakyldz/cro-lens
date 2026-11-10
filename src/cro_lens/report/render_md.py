"""report.md — sections and order fixed by contract report@1."""

from __future__ import annotations

from cro_lens.models import Experiment, Finding, Report

PERSONA_LABEL = {
    "skeptical_first_timer": "skeptical first-timer",
    "comparison_shopper": "comparison shopper",
    "ready_to_buy": "ready to buy",
    "mobile_skimmer": "mobile skimmer",
    "risk_averse_evaluator": "risk-averse evaluator",
}


def _cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def _exp_line(e: Experiment, f: Finding | None) -> list[str]:
    flag = " ⚑ flagged by self-check" if e.flagged else ""
    out = [
        f"**{e.id} · ICE {e.ice.score}** (I {e.ice.impact} · C {e.ice.confidence} · E {e.ice.ease}){flag}  ",
        f"{e.hypothesis}  ",
    ]
    if f:
        out.append(f"Finding {f.id}: {f.title}  ")
    out.append(f"Change: *{e.change.get('from', '')}* → *{e.change.get('to', '')}*  ")
    if e.suggested_copy:
        out.append(f"Suggested copy: “{e.suggested_copy}”  ")
    out.append(
        f"Primary metric: {e.primary_metric} · guardrail: {e.guardrail_metric} · "
        f"feasibility: `{e.feasibility}`  "
    )
    out.append(
        f"Why these scores — impact: {e.ice.rationale.get('impact', '')}; "
        f"confidence: {e.ice.rationale.get('confidence', '')}; ease: {e.ice.rationale.get('ease', '')}"
    )
    return out


def cost_text(r: Report) -> str:
    """The run's cost in words. On a subscription the figure is what the calls would cost at API
    list prices; with ANTHROPIC_API_KEY it is Claude Code's estimate of the bill (ADR 0007)."""
    usd = r.cost.total_usd_equivalent
    if r.run.billing == "api_key":
        return f"${usd:.3f} billed to your Anthropic API key (Claude Code's estimate)"
    return f"${usd:.3f} API-equivalent"


def render_markdown(r: Report) -> str:
    fby = {f.id: f for f in r.findings}
    eby = {e.id: e for e in r.experiments}
    L: list[str] = [
        f"# Landing page teardown — {r.capture.title or r.run.final_url}",
        "",
        f"`{r.run.final_url}` · {r.run.finished_at[:10]} · model `{r.run.model}`",
        "",
    ]

    L += ["## Summary", "", r.summary, ""]

    L += ["## Top 3 experiments", ""]
    if not r.top3:
        L.append("_No experiments — no finding survived the self-check._")
    for i, t in enumerate(r.top3, 1):
        e = eby[t.experiment_id]
        L += [f"### {i}. {fby[e.finding_id].title}", "", f"*Why first:* {t.why}", ""]
        L += _exp_line(e, None)
        L.append("")

    L += [
        "## Experiment backlog",
        "",
        "| # | Hypothesis | Metric | I | C | E | ICE | Feasibility | Flag |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for e in r.experiments:
        L.append(
            f"| {e.id} | {_cell(e.hypothesis)} | {_cell(e.primary_metric)} | {e.ice.impact} | "
            f"{e.ice.confidence} | {e.ice.ease} | **{e.ice.score}** | {e.feasibility} | "
            f"{'⚑' if e.flagged else ''} |"
        )
    L += [
        "",
        "Confidence is computed, not guessed: base 3, +1 evidence kept by the self-check, +1 matches a weak "
        "LIFT factor, +1 raised by two or more personas; capped at 6 because the tool has no traffic data.",
        "",
    ]
    for e in r.experiments:
        L += _exp_line(e, fby.get(e.finding_id))
        L.append("")

    L += ["## Findings", ""]
    for f in r.findings:
        if f.check.verdict == "dropped":
            continue
        personas = ", ".join(PERSONA_LABEL.get(p, p) for p in f.personas)
        flag = " · ⚑ flagged" if f.check.verdict == "flagged" else ""
        L += [
            f"### {f.id} · {f.title}",
            "",
            f"`{f.category}` · {f.kind} · severity **{f.severity}** · {personas}{flag}",
            "",
            f.reasoning,
            "",
        ]
        for e in f.evidence:
            mark = "" if e.valid else " _(quote not found — ignored)_"
            L.append(f"> “{e.quote}” — `{e.block_id}` {e.viewport}{mark}")
            L.append("")
            if e.crop:
                L += [f"![{f.id} evidence {e.block_id}]({e.crop})", ""]
        L += [f"*Self-check:* {f.check.verdict} — {f.check.reason}", ""]

    u = r.understanding
    L += [
        "## What this page is (understanding)",
        "",
        "| | Inferred | Confidence | Evidence |",
        "|---|---|---|---|",
        f"| Audience | {_cell(u.audience.value)} ({u.audience.source}) | {u.audience.confidence} | "
        f"{', '.join(u.audience.evidence)} |",
        f"| Job to be done | {_cell(u.job_to_be_done.value)} | {u.job_to_be_done.confidence} | "
        f"{', '.join(u.job_to_be_done.evidence)} |",
        f"| Traffic source | {_cell(u.traffic_source.value)} ({u.traffic_source.source}) | "
        f"{u.traffic_source.confidence} | {', '.join(u.traffic_source.evidence)} |",
        f"| Awareness level | {u.awareness_level.value} | {u.awareness_level.confidence} | "
        f"{', '.join(u.awareness_level.evidence)} |",
        f"| Promise | {_cell(u.promise.value)} | | {', '.join(u.promise.evidence)} |",
        f"| Offer | {_cell(u.offer.value)} | | {', '.join(u.offer.evidence)} |",
        "",
        f"**5-second test** — clear: {'yes' if u.five_second.clear else 'no'}, specific: "
        f"{'yes' if u.five_second.specific else 'no'}. Judged copy: “{u.five_second.quote}”. "
        f"A visitor takes away: {u.five_second.understood}",
        "",
        "**LIFT** (1 = serious problem, 5 = strong)",
        "",
        "| Factor | Score | Reason |",
        "|---|---|---|",
    ]
    L += [f"| {s.factor} | {s.score} | {_cell(s.reason)} |" for s in r.lift]
    L += ["", "**Persona walkthroughs**", ""]
    for p in r.personas:
        stalls = "; ".join(f"`{s.block_id}` {s.why}" for s in p.stalls) or "no stalls"
        objs = "; ".join(f"{o.objection} ({o.status})" for o in p.objections) or "none"
        L.append(f"- **{PERSONA_LABEL.get(p.persona, p.persona)}** — stalls: {stalls}. Objections: {objs}.")
    L.append("")

    L += ["## Assumptions and couldn't verify", ""]
    for x in r.unverifiable:
        L.append(f"- **{x.what}** — {x.why} Assumed: {x.assumption}")
    for vp, m in r.capture.viewports.items():
        if m.truncated:
            L.append(
                f"- **Bottom of the {vp} page** — only {m.tiles_sent} screenshot tiles were shown to the model."
            )
    if r.capture.consent_banner.present and not r.capture.consent_banner.dismissed:
        L.append(
            "- **Consent banner** — it covered the first screen and could not be declined automatically."
        )
    L.append("")

    L += ["## Dropped by self-check", ""]
    dropped = [f for f in r.findings if f.check.verdict == "dropped"]
    if not dropped:
        L.append("_Nothing was dropped._")
    for f in dropped:
        L.append(f"- **{f.id} · {f.title}** (`{f.category}`) — {f.check.reason}")
    L.append("")

    s = r.capture.speed
    L += [
        "## Page speed",
        "",
        f"{s.source}.",
        "",
        "| TTFB | DOMContentLoaded | Load | LCP | CLS | Requests | Transfer (≥) |",
        "|---|---|---|---|---|---|---|",
        f"| {_ms(s.ttfb_ms)} | {_ms(s.dcl_ms)} | {_ms(s.load_ms)} | {_ms(s.lcp_ms)} | {s.cls} | {s.requests} | "
        f"{_kb(s.transfer_bytes_min)} |",
        "",
    ]
    if s.psi:
        L += [f"PageSpeed Insights (mobile): {s.psi}", ""]

    secs = sum(c.seconds for c in r.cost.calls)
    L += [
        "## Run",
        "",
        f"- Run `{r.run.id}` · provider `{r.run.provider}` · model `{r.run.model}`",
        f"- {r.run.started_at} → {r.run.finished_at}; {len(r.cost.calls)} model calls, {secs:.0f} s of model time",
        f"- Cost: {cost_text(r)}"
        + (
            " (ANTHROPIC_API_KEY was set)"
            if r.run.billing == "api_key"
            else " (on your Claude subscription, not billed per call)"
            if r.run.provider == "claude-code"
            else ""
        ),
    ]
    fb = feedback_line(r)
    if fb:
        L.append(f"- {fb}")
    L.append("")
    return "\n".join(L)


def feedback_line(r: Report) -> str | None:
    """What the run learned from the user's grades (eval@2); None for reports from before 0.3."""
    fb = r.run.feedback
    if fb is None:
        return None
    if not fb.enabled:
        return "Feedback: off for this run (it learned from none of your grades)."
    if not fb.examples:
        return "Feedback: none of your findings were graded yet, so this run learned from none."
    return f"Learned from {fb.examples} of your graded findings ({fb.same_site} from this site)."


def _ms(v: float | None) -> str:
    return "–" if v is None else f"{v:.0f} ms"


def _kb(v: int | None) -> str:
    return "–" if v is None else f"{v / 1024:.0f} KB"
