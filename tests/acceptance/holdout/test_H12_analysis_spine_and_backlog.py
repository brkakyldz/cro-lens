"""H12 — a CRO consultant audits how cro-lens reasoned about a SaaS page:
LIFT scores, persona walks, evidence on every finding, and an honest backlog."""
import re

from conftest import (FEASIBILITY, LIFT_FACTORS, PERSONAS, SAAS_H1, TAXONOMY, md_sections,
                      normalise, read_json, report_path_from)


def test_H12_findings_are_evidenced_and_experiments_are_honest(cli, site):
    """H12 [ANA-1, ANA-2, ANA-4, CAP-3, HYP-1, HYP-4, HYP-5, CHK-1]
    The report scores all six LIFT factors (1-5, reason), walks all five
    personas, gives every finding a taxonomy category, kind, severity,
    personas and evidence that resolves to a real block with a verbatim quote,
    and turns findings into If/then/because hypotheses with metrics, guardrail,
    feasibility and a computed confidence (3..6, within the HYP-4 rule). The
    report must NOT invent sample sizes or traffic numbers."""
    r = cli("analyze", site.url("/saas.html"))
    assert r.code == 0, r.dump()
    run_dir = report_path_from(r.out).parent
    rep = read_json(run_dir / "report.json")
    blocks = {"desktop": read_json(run_dir / "capture" / "blocks_desktop.json"),
              "mobile": read_json(run_dir / "capture" / "blocks_mobile.json")}
    text = {vp: {b["id"]: b for b in bl} for vp, bl in blocks.items()}
    all_ids = set(text["desktop"]) | set(text["mobile"])

    # CAP-3: role hints on the fixture's known elements
    desktop = blocks["desktop"]
    assert any(normalise(b["text"]) == normalise(SAAS_H1) and b["role"] == "heading" for b in desktop)
    assert any("start free trial" in normalise(b["text"]) and b["role"] == "cta" for b in desktop)
    assert any("$12" in b["text"] and b["role"] == "price" for b in desktop)

    # ANA-4: LIFT spine
    lift = {x["factor"]: x for x in rep["lift"]}
    assert set(lift) == LIFT_FACTORS
    for x in lift.values():
        assert isinstance(x["score"], int) and 1 <= x["score"] <= 5
        assert x["reason"].strip()
        assert set(x["evidence"]) <= all_ids

    # ANA-1: five persona walks
    walks = {p["persona"]: p for p in rep["personas"]}
    assert set(walks) == PERSONAS
    for p in walks.values():
        for stall in p["stalls"]:
            assert stall["block_id"] in all_ids and stall["why"].strip()
        for obj in p["objections"]:
            assert obj["status"] in {"answered", "partial", "absent"} and obj["objection"].strip()

    # ANA-2 / CHK-1: every finding carries its evidence
    findings = {f["id"]: f for f in rep["findings"]}
    for f in findings.values():
        assert f["category"] in TAXONOMY and f["kind"] in {"issue", "absence"}
        assert f["severity"] in {"high", "medium", "low"}
        assert f["title"].strip() and f["reasoning"].strip()
        assert set(f["personas"]) <= PERSONAS
        assert f["evidence"], f["id"]
        for e in f["evidence"]:
            assert e["viewport"] in {"desktop", "mobile"} and e["block_id"]
    for fid in ("F1", "F2"):
        e = findings[fid]["evidence"][0]
        block = text[e["viewport"]][e["block_id"]]
        assert normalise(e["quote"]) in normalise(block["text"]) and e["valid"] is True
    assert findings["F1"]["category"] == "value_prop_clarity"
    assert findings["F1"]["evidence"][0]["quote"] == SAAS_H1
    assert findings["F2"]["category"] == "cta"

    # HYP-1/4/5: experiments
    for x in rep["experiments"]:
        f = findings[x["finding_id"]]
        assert re.search(r"\bif\b.+\bthen\b.+\bbecause\b", x["hypothesis"], re.I | re.S), x["hypothesis"]
        assert x["primary_metric"].strip() and x["guardrail_metric"].strip()
        assert x["primary_metric"].strip() != x["guardrail_metric"].strip()
        assert x["feasibility"] in FEASIBILITY
        assert isinstance(x["change"]["from"], str) and isinstance(x["change"]["to"], str)
        ice = x["ice"]
        for k in ("impact", "confidence", "ease"):
            assert ice["rationale"][k].strip(), k
        kept = f["check"]["verdict"] == "kept"
        lo = 3 + int(kept) + int(len(f["personas"]) >= 2)
        hi = min(6, lo + 1 + int(f["check"]["verdict"] == "flagged"))
        assert min(lo, 6) <= ice["confidence"] <= hi, (x["id"], ice, f["check"], f["personas"])
    x1 = next(x for x in rep["experiments"] if x["id"] == "X1")
    assert x1["ice"]["confidence"] >= 4, "kept finding earned no evidence point"

    md = (run_dir / "report.md").read_text(encoding="utf-8")
    assert not re.search(r"sample size\s*(of|:|=|≈|~)?\s*\d", md, re.I), "invented sample size"
    assert not re.search(r"\b\d[\d,.]*\s*(visitors|sessions|users)\s*(per|/|a|each)\s*(day|week|month)", md, re.I)
    assert SAAS_H1 in md_sections(md)["Findings"], "finding quote missing from report.md"
