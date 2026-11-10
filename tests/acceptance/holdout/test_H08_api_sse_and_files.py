"""H08 — a script drives the local web app's JSON API: start runs, follow the
event stream, fetch screenshots."""
import socket

import pytest

from conftest import STEPS, http, lan_ip, png_size, read_sse


def _run_to_end(srv, url):
    resp = http("POST", srv.url("/api/runs"), {"url": url})
    assert resp.status == 202, resp.text
    run_id = resp.json()["run_id"]
    return run_id, read_sse(srv.url(f"/api/runs/{run_id}/events"))


@pytest.mark.smoke
def test_H08_api_run_streams_steps_and_serves_run_files(ui, site, home):
    """H08 [UI-2, CLI-5, SAFE-2, CAP-2, REP-2, CLI-3]
    POST /api/runs refuses a non-http URL (400) without creating a run, then
    starts a valid one (202); its SSE stream replays/streams every step
    started->done in pipeline order and ends with `end` {done, 0, /runs/{id}}.
    The report, screenshots and crops are served from the run folder, but a
    path outside it is NOT; runs are listed newest first; unknown ids are 404.
    The server is NOT reachable on a non-loopback address."""
    srv = ui()

    bad = http("POST", srv.url("/api/runs"), {"url": "ftp://example.invalid/page"})
    assert bad.status == 400 and bad.json().get("error"), bad.text
    assert http("GET", srv.url("/api/runs")).json() == [], "a refused URL created a run"

    run_id, events = _run_to_end(srv, site.url("/saas.html"))
    steps = [(d["step"], d["status"]) for e, d in events if e == "step"]
    assert not [s for s in steps if s[1] == "failed"], steps
    done_order = [name for name, status in steps if status == "done"]
    assert done_order == STEPS, steps
    for name in STEPS:
        assert steps.index((name, "started")) < steps.index((name, "done")), name
    end_name, end = events[-1]
    assert end_name == "end"
    assert end["status"] == "done" and end["exit_code"] == 0
    assert end["report_url"] == f"/runs/{run_id}"

    resp = http("GET", srv.url(f"/api/runs/{run_id}"))
    assert resp.status == 200, resp.text
    rep = resp.json()
    assert rep["schema_version"] == "report@1" and rep["run"]["id"] == run_id
    assert (home / "runs" / run_id / "report.json").is_file()

    fold = http("GET", srv.url(f"/runs/{run_id}/files/capture/desktop_fold.png"))
    assert fold.status == 200
    assert png_size(fold.body[:32]) == (1440, 900)
    crops = [e["crop"] for f in rep["findings"] for e in f["evidence"] if e.get("crop")]
    assert crops
    crop = http("GET", srv.url(f"/runs/{run_id}/files/{crops[0]}"))
    assert crop.status == 200
    png_size(crop.body[:32])

    secret = home / "outside-secret.txt"
    secret.write_text("HOLDOUT-SECRET-7f3a", encoding="utf-8")
    leak = http("GET", srv.url(f"/runs/{run_id}/files/..%2F..%2Foutside-secret.txt"))
    assert leak.status != 200 and b"HOLDOUT-SECRET-7f3a" not in leak.body, leak.status

    assert http("GET", srv.url("/api/runs/no-such-run")).status == 404

    run2, events2 = _run_to_end(srv, site.url("/shop.html"))
    assert events2[-1][1]["status"] == "done"
    listed = http("GET", srv.url("/api/runs")).json()
    assert [x["run_id"] for x in listed[:2]] == [run2, run_id], listed
    assert all(x["status"] == "done" for x in listed[:2])
    assert listed[0]["url"] == site.url("/shop.html")

    ip = lan_ip()
    if ip:
        with pytest.raises(OSError):
            socket.create_connection((ip, srv.port), timeout=3).close()
