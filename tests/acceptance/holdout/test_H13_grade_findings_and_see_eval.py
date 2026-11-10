"""H13 — a marketer grades cro-lens's findings on a report and watches their own
eval fill in: on the /eval page, in the API and in `cro-lens eval`."""
import re

import pytest
from playwright.sync_api import expect

from conftest import (RUN_TIMEOUT, SAAS_H1, eval_lines, evidence_ratio, http, percent_of,
                      poll_until, read_grades)

T = RUN_TIMEOUT * 1000
NOTE_F1 = "Headline says exactly what it does - agree"
NOTE_F2 = "Our CTA is fine; trial sign-ups are not the problem"
SET = re.compile(r"\S")


def _card(page, fid):
    return page.locator(f'[data-testid="finding-card"][data-finding-id="{fid}"]')


def _expect_ungraded(card):
    expect(card).not_to_have_attribute("data-grade", SET)


def _wait_api_grades(srv, run_id, expected: dict[str, str]):
    """Wait until GET /api/runs/{id}/grades holds exactly `expected` ({finding_id: verdict})."""
    def holds():
        resp = http("GET", srv.url(f"/api/runs/{run_id}/grades"))
        assert resp.status == 200, resp.text
        got = {fid: g["verdict"] for fid, g in resp.json().items()}
        assert got == expected, got
        return resp.json()
    return poll_until(holds, 30, f"grades of {run_id} == {expected}")


def _pct_text(locator) -> float:
    expect(locator).to_contain_text(re.compile(r"\d\s*%"))
    return percent_of(locator.inner_text())


@pytest.mark.smoke
def test_H13_grade_findings_in_report_and_eval_fills_in(page, ui, cli, site, home):
    """H13 [FB-1, FB-4, FB-5, UI-1, UI-3]
    With nothing graded and no run, /eval shows `eval-empty`, precision
    `pending grades` and validity `pending runs` (NOT 0 or 0%), and so do
    GET /api/eval (null) and `cro-lens eval`. The user starts a run from the
    start screen (feedback-toggle checked by default); its report shows 0 of 2
    graded. They grade F1 valid with a note, F2 valid then invalid (replaced),
    click invalid again (grade removed), invalid once more, then change F2's
    note by leaving the field; a reload keeps both grades. grades.json holds
    exactly the two self-contained grades; the dropped F3 has no grade
    controls and grading it is refused. /eval, the API and the CLI then show
    2 graded, 50% precision, one row per graded category and the run row.
    Finishing a run, viewing the report or reading the eval must NOT write
    any grade."""
    srv = ui()
    saas = site.url("/saas.html")

    # -- empty state: pending, never 0 -------------------------------------
    resp = http("GET", srv.url("/api/eval"))
    assert resp.status == 200, resp.text
    ev = resp.json()
    assert (ev["graded"], ev["valid"], ev["invalid"], ev["next_run_examples"]) == (0, 0, 0, 0), ev
    assert ev["precision"] is None and ev["evidence_validity"] is None, ev
    assert ev["by_category"] == [] and ev["runs"] == [], ev

    page.goto(srv.url("/eval"))
    expect(page.get_by_test_id("eval-empty")).to_be_visible()
    precision, validity = page.get_by_test_id("eval-precision"), page.get_by_test_id("eval-validity")
    expect(precision).to_contain_text(re.compile(r"pending grades", re.I))
    expect(validity).to_contain_text(re.compile(r"pending runs", re.I))
    expect(precision).not_to_contain_text(re.compile(r"\d"))
    expect(validity).not_to_contain_text(re.compile(r"\d"))
    expect(page.get_by_test_id("eval-graded")).to_contain_text(re.compile(r"\b0\b"))
    expect(page.get_by_test_id("eval-run-row")).to_have_count(0)

    r = cli("eval")
    assert r.code == 0, r.dump()
    lines = eval_lines(r.out)
    assert re.search(r"\b0 findings?\b", lines["graded"]), lines
    assert re.search(r"pending grades", lines["precision"], re.I), lines
    assert re.search(r"pending runs", lines["evidence validity"], re.I), lines
    assert not re.search(r"\d", lines["precision"] + lines["evidence validity"]), lines
    assert re.search(r"\b0\b", lines["next run learns from"]), lines

    # -- a run from the start screen, feedback on by default ---------------
    page.goto(srv.url("/"))
    expect(page.get_by_test_id("feedback-toggle")).to_be_checked()
    page.get_by_test_id("url-input").fill(saas)
    page.get_by_test_id("start-button").click()
    page.wait_for_url(re.compile(r"/runs/[^/?#]+/?$"), timeout=60_000)
    run_id = page.url.rstrip("/").rsplit("/", 1)[1]
    expect(page.get_by_test_id("report-summary")).to_be_visible(timeout=T)

    rep = http("GET", srv.url(f"/api/runs/{run_id}")).json()
    findings = {f["id"]: f for f in rep["findings"]}
    assert rep["run"]["feedback"] == {"enabled": True, "examples": 0, "same_site": 0}, rep["run"]
    expect(page.get_by_test_id("feedback-used")).to_contain_text(
        re.compile(r"learned from\s+(0|no)\s+graded findings", re.I))

    cards = page.get_by_test_id("finding-card")
    expect(cards).to_have_count(2)
    progress = page.get_by_test_id("grade-progress")
    expect(progress).to_contain_text(re.compile(r"\b0 of 2 graded"))
    f1, f2 = _card(page, "F1"), _card(page, "F2")
    _expect_ungraded(f1)
    _expect_ungraded(f2)

    # finished run counts for validity; precision still waits for grades
    ratio = evidence_ratio(rep)
    ev = http("GET", srv.url("/api/eval")).json()
    assert ev["precision"] is None and ev["evidence_validity"] == pytest.approx(ratio, abs=0.005), ev
    assert [(x["run_id"], x["findings"], x["graded"]) for x in ev["runs"]] == [(run_id, 2, 0)], ev["runs"]
    assert read_grades(home) == {}, "a grade was written without a grade action"

    # -- grade on the report ----------------------------------------------
    f1.get_by_test_id("grade-note").fill(NOTE_F1)
    f1.get_by_test_id("grade-valid").click()
    expect(f1).to_have_attribute("data-grade", "valid")
    _wait_api_grades(srv, run_id, {"F1": "valid"})

    f2.get_by_test_id("grade-valid").click()
    expect(f2).to_have_attribute("data-grade", "valid")
    _wait_api_grades(srv, run_id, {"F1": "valid", "F2": "valid"})
    f2.get_by_test_id("grade-invalid").click()                     # replaces the earlier verdict
    expect(f2).to_have_attribute("data-grade", "invalid")
    expect(progress).to_contain_text(re.compile(r"\b2 of 2 graded"))
    _wait_api_grades(srv, run_id, {"F1": "valid", "F2": "invalid"})

    f2.get_by_test_id("grade-invalid").click()                     # second click removes it
    _expect_ungraded(f2)
    expect(progress).to_contain_text(re.compile(r"\b1 of 2 graded"))
    _wait_api_grades(srv, run_id, {"F1": "valid"})
    assert f"{run_id}/F2" not in read_grades(home)

    f2.get_by_test_id("grade-invalid").click()
    expect(f2).to_have_attribute("data-grade", "invalid")
    _wait_api_grades(srv, run_id, {"F1": "valid", "F2": "invalid"})
    note = f2.get_by_test_id("grade-note")
    note.fill(NOTE_F2)
    note.press("Tab")                                              # leaving the field saves it

    def note_saved():
        got = http("GET", srv.url(f"/api/runs/{run_id}/grades")).json()
        assert got.get("F2", {}).get("note") == NOTE_F2, got
        assert got["F2"]["verdict"] == "invalid" and got["F1"]["verdict"] == "valid", got
        return True
    poll_until(note_saved, 30, "F2's changed note saved")

    # -- a reload keeps the grades; dropped findings cannot be graded ------
    page.reload()
    expect(page.get_by_test_id("report-summary")).to_be_visible(timeout=T)
    expect(_card(page, "F1")).to_have_attribute("data-grade", "valid")
    expect(_card(page, "F2")).to_have_attribute("data-grade", "invalid")
    expect(page.get_by_test_id("grade-progress")).to_contain_text(re.compile(r"\b2 of 2 graded"))
    expect(_card(page, "F3")).to_have_count(0)
    dropped = page.locator('[data-testid="dropped-item"][data-finding-id="F3"]')
    expect(dropped).to_have_count(1)
    expect(dropped.get_by_test_id("grade-valid")).to_have_count(0)
    expect(dropped.get_by_test_id("grade-invalid")).to_have_count(0)

    before = read_grades(home)
    refused = http("PUT", srv.url(f"/api/runs/{run_id}/grades/F3"), {"verdict": "valid"})
    assert refused.status == 404, refused.text
    assert read_grades(home) == before, "a dropped finding's grade was saved"

    # -- grades.json: two self-contained grades -----------------------------
    assert set(before) == {f"{run_id}/F1", f"{run_id}/F2"}, before
    g1, g2 = before[f"{run_id}/F1"], before[f"{run_id}/F2"]
    for g, fid in ((g1, "F1"), (g2, "F2")):
        f = findings[fid]
        assert g["run_id"] == run_id and g["finding_id"] == fid
        assert g["url"] == saas and g["host"] == "127.0.0.1"
        assert g["category"] == f["category"] and g["kind"] == f["kind"] and g["title"] == f["title"]
        assert g["quote"] == f["evidence"][0]["quote"]
        assert g["graded_at"]
    assert g1["category"] == "value_prop_clarity" and g1["quote"] == SAAS_H1
    assert (g1["verdict"], g1["note"]) == ("valid", NOTE_F1)
    assert g2["category"] == "cta" and (g2["verdict"], g2["note"]) == ("invalid", NOTE_F2)
    assert not [p for p in home.rglob("grades.json") if p.resolve() != (home / "grades.json").resolve()]

    # -- the eval now has real numbers: page, API, CLI ---------------------
    page.goto(srv.url("/eval"))
    expect(page.get_by_test_id("eval-category-row")).to_have_count(2)
    expect(page.get_by_test_id("eval-empty")).to_have_count(0)
    expect(page.get_by_test_id("eval-graded")).to_contain_text(re.compile(r"\b2\b"))
    expect(page.get_by_test_id("eval-examples")).to_contain_text(re.compile(r"\b2\b"))
    assert _pct_text(page.get_by_test_id("eval-precision")) == pytest.approx(0.5, abs=0.005)
    assert _pct_text(page.get_by_test_id("eval-validity")) == pytest.approx(ratio, abs=0.01)
    vpc = page.locator('[data-testid="eval-category-row"][data-category="value_prop_clarity"]')
    expect(vpc).to_have_attribute("data-graded", "1")
    expect(vpc).to_have_attribute("data-valid", "1")
    cta = page.locator('[data-testid="eval-category-row"][data-category="cta"]')
    expect(cta).to_have_attribute("data-graded", "1")
    expect(cta).to_have_attribute("data-valid", "0")
    expect(page.locator('[data-testid="eval-category-row"][data-category="social_proof"]')).to_have_count(0)
    row = page.locator(f'[data-testid="eval-run-row"][data-run-id="{run_id}"]')
    expect(page.get_by_test_id("eval-run-row")).to_have_count(1)
    expect(row).to_have_attribute("data-findings", "2")
    expect(row).to_have_attribute("data-graded", "2")
    hrefs = row.locator("a").evaluate_all("els => els.map(e => e.getAttribute('href'))")
    assert any(h and h.rstrip("/").endswith(f"/runs/{run_id}") for h in hrefs), hrefs

    ev = http("GET", srv.url("/api/eval")).json()
    assert (ev["graded"], ev["valid"], ev["invalid"], ev["next_run_examples"]) == (2, 1, 1, 2), ev
    assert ev["precision"] == pytest.approx(0.5)
    assert ev["evidence_validity"] == pytest.approx(ratio, abs=0.005)
    by_cat = {c["category"]: c for c in ev["by_category"]}
    assert set(by_cat) == {"value_prop_clarity", "cta"}, ev["by_category"]
    assert (by_cat["value_prop_clarity"]["graded"], by_cat["value_prop_clarity"]["valid"]) == (1, 1)
    assert by_cat["value_prop_clarity"]["precision"] == pytest.approx(1.0)
    assert (by_cat["cta"]["graded"], by_cat["cta"]["valid"]) == (1, 0)
    assert by_cat["cta"]["precision"] == pytest.approx(0.0)
    assert len(ev["runs"]) == 1, ev["runs"]
    run_row = ev["runs"][0]
    assert (run_row["run_id"], run_row["url"]) == (run_id, saas)
    assert (run_row["findings"], run_row["graded"], run_row["valid"]) == (2, 2, 1)

    r = cli("eval")
    assert r.code == 0, r.dump()
    lines = eval_lines(r.out)
    assert re.search(r"\b2 findings?\b.*\b1 valid\b.*\b1 invalid\b", lines["graded"]), lines
    assert percent_of(lines["precision"]) == pytest.approx(0.5, abs=0.005), lines
    assert percent_of(lines["evidence validity"]) == pytest.approx(ratio, abs=0.01), lines
    assert re.search(r"over\s+1\s+runs?\b", lines["evidence validity"]), lines
    assert re.search(r"\b2\b", lines["next run learns from"]), lines
