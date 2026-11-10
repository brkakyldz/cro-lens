"""H09 — in the web app a user mistypes the address, fixes it, and the run
then fails in the model step."""
import re
from urllib.parse import urlsplit

from playwright.sync_api import expect

from conftest import RUN_TIMEOUT, http, read_jsonl

T = RUN_TIMEOUT * 1000


def test_H09_ui_rejects_bad_url_then_shows_failed_run(page, ui, site, home):
    """H09 [UI-1, UI-2, LLM-2, CLI-3]
    A non-http URL shows `form-error` and does NOT navigate or create a run.
    With the fake failing `analyse`, the corrected run navigates to /runs/{id}
    and shows `run-error`; the step list marks understand done, analyse failed
    and check NOT run; the API answers 409 with exit code 6, and no report is
    rendered or written."""
    srv = ui(env_extra={"CRO_LENS_FAKE_FAIL": "analyse"})
    page.goto(srv.url("/"))

    page.get_by_test_id("url-input").fill("ftp://example.invalid/landing")
    page.get_by_test_id("start-button").click()
    expect(page.get_by_test_id("form-error")).to_be_visible()
    assert urlsplit(page.url).path in ("", "/")
    assert http("GET", srv.url("/api/runs")).json() == []

    page.get_by_test_id("url-input").fill(site.url("/saas.html"))
    page.get_by_test_id("start-button").click()
    page.wait_for_url(re.compile(r"/runs/[^/?#]+/?$"), timeout=60_000)
    run_id = page.url.rstrip("/").rsplit("/", 1)[1]

    expect(page.get_by_test_id("run-error")).to_be_visible(timeout=T)
    expect(page.get_by_test_id("run-error")).to_contain_text(re.compile(r"\S"))
    expect(page.get_by_test_id("step-understand")).to_have_attribute("data-status", "done")
    expect(page.get_by_test_id("step-analyse")).to_have_attribute("data-status", "failed")
    expect(page.get_by_test_id("step-check")).to_have_attribute("data-status", "pending")
    expect(page.get_by_test_id("report-summary")).to_have_count(0)

    resp = http("GET", srv.url(f"/api/runs/{run_id}"))
    assert resp.status == 409, resp.text
    body = resp.json()
    assert body["status"] == "failed" and body["exit_code"] == 6 and body["error"]
    listed = {x["run_id"]: x for x in http("GET", srv.url("/api/runs")).json()}
    assert listed[run_id]["status"] == "failed"

    run_dir = home / "runs" / run_id
    events = read_jsonl(run_dir / "steps.jsonl")
    assert any(e["step"] == "analyse" and e["status"] == "failed" for e in events)
    assert not (run_dir / "report.json").exists() and not (run_dir / "report.md").exists()
