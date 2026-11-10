"""H01 — a growth marketer runs cro-lens on a SaaS landing page from the CLI
and reads the run folder it produced."""
import re

import pytest

from conftest import (FAKE_BAD_QUOTE, REPORT_H2, RUN_ID_RE, STEPS, h2_headings, md_sections,
                      png_size, read_json, read_jsonl, report_path_from, step_lines)


@pytest.mark.smoke
def test_H01_analyze_saas_page_writes_checked_report(cli, site, home):
    """H01 [CLI-1, CLI-2, LLM-3, LLM-4, CHK-1, CHK-2, CHK-3, HYP-2, HYP-3, REP-1, REP-2, CAP-4]
    `cro-lens analyze <url>` on the SaaS fixture: one progress line per step in
    order, the report path and the cost line; the run folder holds report.md
    with the contract sections, report.json whose self-check kept F1, flagged F2
    and dropped F3 (quote not on the page), a sorted backlog with top 3, and
    crops linked from report.md. F3 must NOT reach the backlog."""
    url = site.url("/saas.html")
    r = cli("analyze", url)
    assert r.code == 0, r.dump()

    # CLI-2: one line per step, in order, all done; check line counts verdicts
    steps = step_lines(r.out)
    assert [s.name for s in steps] == STEPS, r.dump()
    assert all(s.mark == "✓" for s in steps), r.dump()
    check_line = next(s.line for s in steps if s.name == "check")
    assert re.search(r"kept\s+1\s*·\s*flagged\s+1\s*·\s*dropped\s+1", check_line), check_line

    # final two lines: report path, then cost
    tail = [ln.strip() for ln in r.out.splitlines() if ln.strip()][-2:]
    assert tail[0].startswith("report: "), tail
    cost = re.fullmatch(r"cost: \$0\.000 API-equivalent \((\d+) model calls?\)", tail[1])
    assert cost, tail[1]

    # CLI-1 / run-folder@1: default location under $CRO_LENS_HOME/runs/<run_id>/
    report_md = report_path_from(r.out)
    run_dir = report_md.parent
    assert run_dir.parent == (home / "runs").resolve()
    assert RUN_ID_RE.match(run_dir.name), run_dir.name
    for rel in ("report.md", "report.json", "steps.jsonl", "capture/desktop_full.png",
                "capture/desktop_fold.png", "capture/mobile_full.png", "capture/mobile_fold.png",
                "capture/blocks_desktop.json", "capture/blocks_mobile.json",
                "capture/page.html", "capture/meta.json"):
        assert (run_dir / rel).is_file(), f"missing {rel}"

    rep = read_json(run_dir / "report.json")
    assert rep["schema_version"] == "report@1"
    assert rep["run"]["id"] == run_dir.name
    assert rep["run"]["url"] == url
    assert rep["run"]["provider"] == "fake"                       # LLM-4 via env
    assert rep["run"]["given"] == {"audience": None, "traffic": None, "goal": None}
    assert rep["capture"]["consent_banner"]["present"] is False   # CAP-4: no banner here
    assert isinstance(rep["summary"], str) and rep["summary"].strip()

    # CHK-1/2: verdicts per the fake provider
    findings = {f["id"]: f for f in rep["findings"]}
    assert set(findings) == {"F1", "F2", "F3"}
    assert findings["F1"]["check"]["deterministic"] == "pass"
    assert findings["F1"]["check"]["verdict"] == "kept"
    assert findings["F2"]["check"]["verdict"] == "flagged"
    f3 = findings["F3"]
    assert f3["category"] == "social_proof"
    assert f3["evidence"][0]["quote"] == FAKE_BAD_QUOTE
    assert f3["evidence"][0]["valid"] is False
    assert f3["check"]["deterministic"] == "fail"
    assert f3["check"]["verdict"] == "dropped"
    assert f3["check"]["reason"].startswith("evidence_not_found")

    # HYP-3: one experiment per kept/flagged finding, sorted, flags mirrored
    exps = rep["experiments"]
    assert {(x["id"], x["finding_id"]) for x in exps} == {("X1", "F1"), ("X2", "F2")}
    assert all(x["finding_id"] != "F3" for x in exps)              # NOT: dropped -> backlog
    by_id = {x["id"]: x for x in exps}
    assert by_id["X1"]["flagged"] is False and by_id["X2"]["flagged"] is True
    scores = [x["ice"]["score"] for x in exps]
    assert scores == sorted(scores, reverse=True)
    for x in exps:
        ice = x["ice"]
        assert (ice["impact"], ice["ease"]) == (6, 5)
        assert ice["confidence"] <= 6
        assert ice["score"] == pytest.approx(round((ice["impact"] + ice["confidence"] + ice["ease"]) / 3, 2))

    # HYP-2: top 3 = min(3, 2) entries, each explained
    assert len(rep["top3"]) == 2
    assert {t["experiment_id"] for t in rep["top3"]} <= set(by_id)
    assert all(t["why"].strip() for t in rep["top3"])

    # LLM-3: per-call records, zero cost with the fake, count matches stdout
    calls = rep["cost"]["calls"]
    assert calls and len(calls) == int(cost.group(1))
    for c in calls:
        assert {"step", "model", "seconds", "input_tokens", "output_tokens", "usd"} <= set(c)
        assert c["usd"] == 0
    assert rep["cost"]["total_usd_equivalent"] == 0

    # REP-2: crops exist, are PNGs, and report.md links them
    md = report_md.read_text(encoding="utf-8")
    crops = [e["crop"] for f in rep["findings"] for e in f["evidence"] if e.get("crop")]
    assert any(c.startswith("crops/F1-") for c in crops), crops
    for crop in crops:
        assert (run_dir / crop).is_file(), crop
        png_size(run_dir / crop)
    for crop in crops:
        if not crop.startswith("crops/F3-"):
            assert crop in md, f"report.md does not link {crop}"

    # REP-1: report.md sections in contract order
    headings = [h for h in h2_headings(md) if h in REPORT_H2]
    assert headings == REPORT_H2, h2_headings(md)
    sections = md_sections(md)
    assert re.search(r"evidence_not_found", sections["Dropped by self-check"])
    assert ("F3" in sections["Dropped by self-check"]
            or f3["title"] in sections["Dropped by self-check"])
    for name in ("Top 3 experiments", "Experiment backlog"):              # NOT: F3 leaks
        assert FAKE_BAD_QUOTE not in sections[name]
        assert f3["title"] not in sections[name]
    assert re.search(r"fake", sections["Run"])
    assert re.search(r"\$0(\.0+)? API-equivalent", sections["Run"])

    # steps.jsonl: every step started and finished, none failed
    events = read_jsonl(run_dir / "steps.jsonl")
    for step in STEPS:
        statuses = [e["status"] for e in events if e["step"] == step]
        assert "started" in statuses and "done" in statuses, (step, statuses)
    assert not [e for e in events if e["status"] == "failed"]
