"""H14 — a growth marketer comes back to a site they graded before, with grades
carried over from their old laptop; the next run learns from their verdicts
(same site first, at most 12), and a run with feedback off learns from none."""
import json
import re
from datetime import datetime, timedelta, timezone

from playwright.sync_api import expect

from conftest import (FEEDBACK_OFF_RE, LEARNED_SOME_RE, MAX_EXAMPLES, RUN_TIMEOUT, STEPS, api_run,
                      http, learned_from_re, put_grade, read_grades, read_json, report_path_from,
                      run_section, step_lines)

T = RUN_TIMEOUT * 1000
SAME_HOST = "127.0.0.1"
NOTE = "Too generic for our buyers - they compare on price first"
COPIED = ("host", "category", "kind", "title", "quote", "verdict", "note")


def _at(value) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _stamp_like(sample: str, when: datetime) -> str:
    """ISO timestamp in the same style (naive, offset or Z) as the product's own graded_at."""
    if datetime.fromisoformat(str(sample).replace("Z", "+00:00")).tzinfo is None:
        return when.replace(tzinfo=None).isoformat(timespec="seconds")
    text = when.isoformat(timespec="seconds")
    return text.replace("+00:00", "Z") if str(sample).endswith("Z") else text


def _old_laptop_grades(sample: str) -> dict:
    """grades@1 entries from the user's previous machine: one grade of this site
    (5 Jan 2025) and 13 of other sites (1-13 Feb 2025, all newer than it)."""
    start = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
    grades = {}

    def add(day, host, category, verdict, note):
        run_id = f"{(start + timedelta(days=day)):%Y%m%d}-090000-{host.replace('.', '-')}"
        grades[f"{run_id}/F1"] = {
            "run_id": run_id, "finding_id": "F1", "url": f"http://{host}/landing", "host": host,
            "category": category, "kind": "issue", "title": f"Earlier finding on {host}, day {day}",
            "quote": f"Quoted copy from day {day}", "verdict": verdict, "note": note,
            "graded_at": _stamp_like(sample, start + timedelta(days=day)),
        }

    add(4, SAME_HOST, "pricing_visibility", "valid", "graded on my old laptop")
    others = ["shop.example.com", "example.org", "app.example.net"]
    for i in range(13):
        add(31 + i, others[i % 3], "cta" if i % 2 else "social_proof", "invalid" if i % 2 else "valid", "")
    return grades


def test_H14_next_run_learns_from_grades_same_site_first(page, ui, cli, site, home, workdir):
    """H14 [FB-2, FB-3, FB-1, FB-4, FB-5, CLI-1, REP-1, UI-1, UI-3]
    The user grades a run of the SaaS page in the app (F1 invalid with a note,
    F2 valid), closes it and merges 14 grades from their old laptop into
    grades.json (one older grade of this site, 13 of other sites). A second
    `cro-lens analyze` of the same site writes feedback.json with exactly 12
    examples: the 3 same-site grades first even though they are the oldest,
    then the 9 newest other-site grades, each carrying the user's verdict and
    note; the 4 oldest other-site grades are left out. report.json
    `run.feedback`, the `## Run` line and `feedback-used` say 12 (3 from this
    site); the new run's own findings start ungraded. A run started with
    `feedback-toggle` unchecked learns from none. A later grade must NOT
    change an earlier run's feedback.json, and no run writes a grade."""
    srv = ui()
    saas = site.url("/saas.html")

    # -- grades made in the app ---------------------------------------------
    run_a = api_run(srv, saas)
    put_grade(srv, run_a, "F1", "invalid", NOTE)
    saved = put_grade(srv, run_a, "F2", "valid")
    srv.stop()

    # -- the user merges the grades from their old laptop (app closed) ------
    grades_file = home / "grades.json"
    data = read_json(grades_file)
    data["grades"].update(_old_laptop_grades(saved["graded_at"]))
    grades_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    grades = read_grades(home)
    assert len(grades) == 16
    assert grades[f"{run_a}/F1"]["host"] == SAME_HOST

    # -- a second run of the same site, from the CLI ------------------------
    r = cli("analyze", saas)
    assert r.code == 0, r.dump()
    assert [s.name for s in step_lines(r.out)] == STEPS, r.dump()
    run_dir = report_path_from(r.out).parent
    run_c = run_dir.name
    fb_file = run_dir / "feedback.json"
    fb_bytes = fb_file.read_bytes()
    fb = json.loads(fb_bytes.decode("utf-8"))
    assert fb["enabled"] is True, fb
    examples = fb["examples"]

    def key(e):
        return f"{e['run_id']}/{e['finding_id']}"

    newest_first = sorted(grades, key=lambda k: _at(grades[k]["graded_at"]), reverse=True)
    same = [k for k in newest_first if grades[k]["host"] == SAME_HOST]
    other = [k for k in newest_first if grades[k]["host"] != SAME_HOST]
    assert len(same) == 3 and len(other) == 13
    picked = [key(e) for e in examples]

    assert len(examples) == MAX_EXAMPLES, picked
    assert [e["same_site"] for e in examples] == [True] * 3 + [False] * 9, examples
    assert set(picked) == set(same + other[:9]), picked
    assert not set(picked) & set(other[9:]), "older other-site grades took a place"
    for group in (examples[:3], examples[3:]):                       # newest graded_at first
        times = [_at(grades[key(e)]["graded_at"]) for e in group]
        assert times == sorted(times, reverse=True), [key(e) for e in group]
    assert picked[2] == same[-1], "the old same-site grade must precede newer other-site grades"
    for e in examples:
        g = grades[key(e)]
        assert {k: e[k] for k in COPIED} == {k: g[k] for k in COPIED}, (e, g)
    a_f1 = next(e for e in examples if key(e) == f"{run_a}/F1")
    assert (a_f1["verdict"], a_f1["note"]) == ("invalid", NOTE)

    rep = read_json(run_dir / "report.json")
    assert rep["run"]["feedback"] == {"enabled": True, "examples": 12, "same_site": 3}, rep["run"]
    assert learned_from_re(12, 3).search(run_section(run_dir)), run_section(run_dir)

    # FB-5: the run read the grades but wrote none, and only $CRO_LENS_HOME holds them
    assert read_grades(home) == grades, "a run changed grades.json"
    assert not list(workdir.rglob("grades.json")) and not list(run_dir.rglob("grades.json"))

    # -- the report in the app ----------------------------------------------
    srv = ui()
    page.goto(srv.url(f"/runs/{run_c}"))
    expect(page.get_by_test_id("report-summary")).to_be_visible(timeout=T)
    used = page.get_by_test_id("feedback-used")
    expect(used).to_contain_text(re.compile(r"learned from\s+12\s+graded findings", re.I))
    expect(used).to_contain_text(re.compile(r"\b3\s+from this site", re.I))
    cards = page.get_by_test_id("finding-card")
    expect(cards).to_have_count(2)
    expect(page.get_by_test_id("grade-progress")).to_contain_text(re.compile(r"\b0 of 2 graded"))
    for i in range(2):                                               # NOT: earlier verdicts copied over
        expect(cards.nth(i)).not_to_have_attribute("data-grade", re.compile(r"\S"))
    assert http("GET", srv.url(f"/api/runs/{run_c}/grades")).json() == {}

    ev = http("GET", srv.url("/api/eval")).json()
    assert (ev["graded"], ev["next_run_examples"]) == (16, 12), ev

    # -- a run with feedback off, from the start screen ---------------------
    page.goto(srv.url("/"))
    toggle = page.get_by_test_id("feedback-toggle")
    expect(toggle).to_be_checked()
    page.get_by_test_id("url-input").fill(saas)
    toggle.uncheck()
    expect(toggle).not_to_be_checked()
    page.get_by_test_id("start-button").click()
    page.wait_for_url(re.compile(r"/runs/[^/?#]+/?$"), timeout=60_000)
    run_d = page.url.rstrip("/").rsplit("/", 1)[1]
    expect(page.get_by_test_id("report-summary")).to_be_visible(timeout=T)
    used = page.get_by_test_id("feedback-used")
    expect(used).to_contain_text(FEEDBACK_OFF_RE)
    expect(used).not_to_contain_text(LEARNED_SOME_RE)

    d_dir = home / "runs" / run_d
    assert read_json(d_dir / "feedback.json") == {"enabled": False, "examples": []}
    rep_d = http("GET", srv.url(f"/api/runs/{run_d}")).json()
    fb_d = rep_d["run"]["feedback"]
    assert fb_d["enabled"] is False and fb_d["examples"] == 0 and fb_d["same_site"] == 0, fb_d
    assert FEEDBACK_OFF_RE.search(run_section(d_dir)), run_section(d_dir)
    assert not LEARNED_SOME_RE.search(run_section(d_dir)), run_section(d_dir)

    # -- a later grade leaves the earlier run's feedback as it was -----------
    put_grade(srv, run_c, "F1", "valid", "this time it is right")
    assert fb_file.read_bytes() == fb_bytes, "feedback.json changed after the run started"
    assert read_json(run_dir / "report.json")["run"]["feedback"]["examples"] == 12
    ev = http("GET", srv.url("/api/eval")).json()
    assert (ev["graded"], ev["next_run_examples"]) == (17, 12), ev
