"""H07 — a marketer starts a run from the local web app, watches it finish and
reads the report on screen."""
import re

import pytest
from playwright.sync_api import expect

from conftest import RUN_TIMEOUT, http

AUDIENCE = "Freelance designers who invoice monthly"
T = RUN_TIMEOUT * 1000


@pytest.mark.smoke
def test_H07_ui_start_run_and_read_report_without_reload(page, ui, site, home):
    """H07 [UI-1, UI-2, UI-3, CLI-4, CLI-5, LLM-3, CHK-3, HYP-2, HYP-3, REP-2, ANA-3]
    From the start screen the user enters the SaaS URL, picks `opus`, gives an
    audience and starts; the app navigates to /runs/{id} and shows the report
    when the run ends with NO manual reload: summary, top 3, backlog rows with
    ICE and flag, one card per non-dropped finding with its verbatim quote and
    crop, the dropped F3 in its own list (and NOT as a card), unverifiable
    items, speed and cost. The run then appears in the recent-runs list."""
    srv = ui()
    assert srv.base.startswith("http://127.0.0.1:")

    page.goto(srv.url("/"))
    model = page.get_by_test_id("model-select")
    options = model.locator("option").evaluate_all("els => els.map(e => e.value || e.textContent.trim())")
    assert {"sonnet", "opus"} <= set(options), options
    page.get_by_test_id("url-input").fill(site.url("/saas.html"))
    model.select_option("opus")
    page.get_by_test_id("audience-input").fill(AUDIENCE)
    page.get_by_test_id("start-button").click()

    page.wait_for_url(re.compile(r"/runs/[^/?#]+/?$"), timeout=60_000)
    run_id = page.url.rstrip("/").rsplit("/", 1)[1]
    page.evaluate("window.__holdoutMarker = 'same-document'")

    expect(page.get_by_test_id("report-summary")).to_be_visible(timeout=T)
    assert page.evaluate("window.__holdoutMarker") == "same-document", "page reloaded to show the report"

    resp = http("GET", srv.url(f"/api/runs/{run_id}"))
    assert resp.status == 200, resp.text
    rep = resp.json()
    assert rep["schema_version"] == "report@1"
    assert "opus" in rep["run"]["model"].lower()
    assert rep["understanding"]["audience"]["source"] == "given"
    assert rep["understanding"]["audience"]["value"] == AUDIENCE

    # top 3 and backlog
    expect(page.get_by_test_id("top3-item")).to_have_count(len(rep["top3"]))
    rows = page.get_by_test_id("experiment-row")
    expect(rows).to_have_count(len(rep["experiments"]))
    for i, exp in enumerate(rep["experiments"]):
        row = rows.nth(i)
        expect(row).to_have_attribute("data-experiment-id", exp["id"])
        assert float(row.get_attribute("data-ice")) == pytest.approx(exp["ice"]["score"], abs=0.01)
        flagged = (row.get_attribute("data-flagged") or "").lower() in ("true", "1")
        assert flagged == exp["flagged"], exp["id"]

    # findings: kept + flagged as cards, dropped only in the dropped list
    cards = page.get_by_test_id("finding-card")
    expect(cards).to_have_count(2)
    expect(page.locator('[data-testid="finding-card"][data-finding-id="F3"]')).to_have_count(0)
    findings = {f["id"]: f for f in rep["findings"]}
    for fid, verdict in (("F1", "kept"), ("F2", "flagged")):
        card = page.locator(f'[data-testid="finding-card"][data-finding-id="{fid}"]')
        expect(card).to_have_attribute("data-verdict", verdict)
        expect(card).to_have_attribute("data-category", findings[fid]["category"])
        expect(card.get_by_test_id("finding-quote").first).to_contain_text(findings[fid]["evidence"][0]["quote"])
        if findings[fid]["evidence"][0].get("crop"):
            img = card.get_by_test_id("finding-crop").first
            expect(img).to_be_visible()
            page.wait_for_function("img => img.complete && img.naturalWidth > 0", arg=img.element_handle(), timeout=30_000)
    expect(page.locator('[data-testid="dropped-item"][data-finding-id="F3"]')).to_have_count(1)

    expect(page.get_by_test_id("understanding")).to_contain_text(AUDIENCE)
    expect(page.get_by_test_id("unverifiable-item").first).to_be_visible()
    expect(page.get_by_test_id("speed-panel")).to_be_visible()
    expect(page.get_by_test_id("cost-total")).to_contain_text(re.compile(r"\$.*API-equivalent"))

    # the UI run used the same run folder as the CLI
    assert (home / "runs" / run_id / "report.json").is_file()

    # recent runs on the start screen
    page.goto(srv.url("/"))
    link = page.get_by_test_id("recent-runs").get_by_test_id("run-link")
    expect(link.first).to_be_visible()
    hrefs = link.evaluate_all("els => els.map(e => e.getAttribute('href'))")
    assert any(h and h.rstrip("/").endswith(f"/runs/{run_id}") for h in hrefs), hrefs
