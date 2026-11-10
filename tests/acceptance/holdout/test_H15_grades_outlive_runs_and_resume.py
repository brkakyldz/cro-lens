"""H15 — a user tidies up: a run that stopped in the self-check is resumed after
they took back a grade, and the run they graded is deleted; its grades outlive
it, still count in their eval and still teach the next run."""
import json
import re

import pytest
from playwright.sync_api import expect

from conftest import (FEEDBACK_OFF_RE, LEARNED_SOME_RE, SAAS_H1, api_run, eval_lines,
                      evidence_ratio, http, learned_from_re, percent_of, put_grade, read_grades,
                      read_json, report_path_from, run_section)

NOTE = "Headline says exactly what the product does"


def test_H15_grades_outlive_their_run_and_resume_keeps_its_feedback(page, ui, cli, site, home):
    """H15 [FB-1, FB-2, FB-3, FB-4, FB-5, CLI-1, REP-1]
    After grading run A (F1 valid with a note, F2 invalid), a CLI run of the
    same site stops in `check` (exit 6) with feedback.json already naming
    both grades; it is NOT gradable and NOT in the eval's runs. The user
    removes the F2 grade and `cro-lens resume`s: the run finishes without
    visiting the page again and still reports the 2 grades it started with
    (feedback.json unchanged). Deleting run A removes its folder but NOT its
    grade: grades.json, GET /api/eval, /eval and `cro-lens eval` still count
    it (1 graded, 100%), while the eval's run rows and evidence validity
    cover only the remaining finished run. A `--no-feedback` run learns from
    nothing; the next default run learns from the deleted run's grade."""
    srv = ui()
    saas = site.url("/saas.html")
    runs = home / "runs"

    run_a = api_run(srv, saas)
    put_grade(srv, run_a, "F1", "valid", NOTE)
    put_grade(srv, run_a, "F2", "invalid")

    # -- a CLI run stops in the self-check, after choosing what to learn from --
    before = {p.name for p in runs.iterdir()}
    r = cli("analyze", saas, env_extra={"CRO_LENS_FAKE_FAIL": "check"})
    assert r.code == 6, r.dump()
    new = {p.name for p in runs.iterdir()} - before
    assert len(new) == 1, new
    run_c = new.pop()
    c_dir = runs / run_c
    assert not (c_dir / "report.json").exists()
    fb_bytes = (c_dir / "feedback.json").read_bytes()
    fb = json.loads(fb_bytes.decode("utf-8"))
    assert fb["enabled"] is True, fb
    assert sorted((e["run_id"], e["finding_id"], e["same_site"]) for e in fb["examples"]) == [
        (run_a, "F1", True), (run_a, "F2", True)], fb

    # an unfinished run cannot be graded and is not part of the eval
    grades_before = read_grades(home)
    refused = http("PUT", srv.url(f"/api/runs/{run_c}/grades/F1"), {"verdict": "valid"})
    assert refused.status in (404, 409), refused.text
    assert read_grades(home) == grades_before, "an unfinished run's finding was graded"
    ev = http("GET", srv.url("/api/eval")).json()
    assert [x["run_id"] for x in ev["runs"]] == [run_a], ev["runs"]

    # -- the user takes back one verdict, then resumes the stopped run -------
    assert http("DELETE", srv.url(f"/api/runs/{run_a}/grades/F2")).status == 204
    assert set(read_grades(home)) == {f"{run_a}/F1"}
    page_loads, robots = site.count("/saas.html"), site.count("/robots.txt")
    r = cli("resume", run_c)
    assert r.code == 0, r.dump()
    assert re.search(r"resuming from\s+check", r.out), r.dump()
    assert report_path_from(r.out).parent == c_dir.resolve()
    assert (site.count("/saas.html"), site.count("/robots.txt")) == (page_loads, robots), "resume visited the site"
    assert (c_dir / "feedback.json").read_bytes() == fb_bytes, "resume rewrote feedback.json"
    rep_c = read_json(c_dir / "report.json")
    assert rep_c["run"]["feedback"] == {"enabled": True, "examples": 2, "same_site": 2}, rep_c["run"]
    assert learned_from_re(2, 2).search(run_section(c_dir)), run_section(c_dir)

    # -- deleting run A keeps its grade --------------------------------------
    kept = read_grades(home)
    assert http("DELETE", srv.url(f"/api/runs/{run_a}")).status == 204
    assert not (runs / run_a).exists()
    assert http("GET", srv.url(f"/api/runs/{run_a}")).status == 404
    assert http("GET", srv.url(f"/api/runs/{run_a}/grades")).status == 404
    assert read_grades(home) == kept, "deleting a run changed grades.json"
    g = kept[f"{run_a}/F1"]
    assert (g["verdict"], g["note"], g["url"], g["category"], g["quote"]) == (
        "valid", NOTE, saas, "value_prop_clarity", SAAS_H1), g

    ratio = evidence_ratio(rep_c)
    ev = http("GET", srv.url("/api/eval")).json()
    assert (ev["graded"], ev["valid"], ev["invalid"], ev["next_run_examples"]) == (1, 1, 0, 1), ev
    assert ev["precision"] == pytest.approx(1.0)
    assert [(c["category"], c["graded"], c["valid"]) for c in ev["by_category"]] == [("value_prop_clarity", 1, 1)]
    assert [(x["run_id"], x["findings"], x["graded"], x["valid"]) for x in ev["runs"]] == [(run_c, 2, 0, 0)], ev["runs"]
    assert ev["evidence_validity"] == pytest.approx(ratio, abs=0.005)

    page.goto(srv.url("/eval"))
    expect(page.get_by_test_id("eval-run-row")).to_have_count(1)
    row = page.locator(f'[data-testid="eval-run-row"][data-run-id="{run_c}"]')
    expect(row).to_have_attribute("data-findings", "2")
    expect(row).to_have_attribute("data-graded", "0")
    expect(page.locator(f'[data-testid="eval-run-row"][data-run-id="{run_a}"]')).to_have_count(0)
    expect(page.get_by_test_id("eval-category-row")).to_have_count(1)
    expect(page.get_by_test_id("eval-category-row")).to_have_attribute("data-category", "value_prop_clarity")
    expect(page.get_by_test_id("eval-empty")).to_have_count(0)
    expect(page.get_by_test_id("eval-graded")).to_contain_text(re.compile(r"\b1\b"))
    expect(page.get_by_test_id("eval-examples")).to_contain_text(re.compile(r"\b1\b"))
    precision = page.get_by_test_id("eval-precision")
    expect(precision).to_contain_text(re.compile(r"\d\s*%"))
    assert percent_of(precision.inner_text()) == pytest.approx(1.0)

    r = cli("eval")
    assert r.code == 0, r.dump()
    lines = eval_lines(r.out)
    assert re.search(r"\b1 findings?\b.*\b1 valid\b.*\b0 invalid\b", lines["graded"]), lines
    assert percent_of(lines["precision"]) == pytest.approx(1.0), lines
    assert percent_of(lines["evidence validity"]) == pytest.approx(ratio, abs=0.01), lines
    assert re.search(r"over\s+1\s+runs?\b", lines["evidence validity"]), lines
    assert re.search(r"\b1\b", lines["next run learns from"]), lines

    # -- --no-feedback learns from nothing, even with a grade on file --------
    r = cli("analyze", saas, "--no-feedback")
    assert r.code == 0, r.dump()
    d_dir = report_path_from(r.out).parent
    assert read_json(d_dir / "feedback.json") == {"enabled": False, "examples": []}
    fb_d = read_json(d_dir / "report.json")["run"]["feedback"]
    assert fb_d["enabled"] is False and fb_d["examples"] == 0 and fb_d["same_site"] == 0, fb_d
    assert FEEDBACK_OFF_RE.search(run_section(d_dir)), run_section(d_dir)
    assert not LEARNED_SOME_RE.search(run_section(d_dir)), run_section(d_dir)

    # -- the next default run still learns from the deleted run's grade -------
    r = cli("analyze", saas)
    assert r.code == 0, r.dump()
    e_dir = report_path_from(r.out).parent
    fb_e = read_json(e_dir / "feedback.json")
    assert fb_e["enabled"] is True, fb_e
    assert [(e["run_id"], e["finding_id"], e["same_site"], e["verdict"], e["note"]) for e in fb_e["examples"]] == [
        (run_a, "F1", True, "valid", NOTE)], fb_e
    assert read_json(e_dir / "report.json")["run"]["feedback"] == {"enabled": True, "examples": 1, "same_site": 1}
    assert learned_from_re(1, 1).search(run_section(e_dir)), run_section(e_dir)
    assert read_grades(home) == kept, "a run changed grades.json"
