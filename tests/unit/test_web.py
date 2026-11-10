"""Web app (ui@2) against a synthetic capture: no browser, no network, fake provider."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from cro_lens.llm.fake import FakeProvider
from cro_lens.pipeline.run import Options, Pipeline
from cro_lens.web.app import create_app

URL = "http://127.0.0.1:9/saas.html"
BLOCKS = {
    "desktop": [
        {
            "id": "D1",
            "tag": "h1",
            "role": "heading",
            "text": "Ship invoices in 30 seconds",
            "bbox": [80, 120, 700, 60],
        },
        {"id": "D2", "tag": "a", "role": "cta", "text": "Start free trial", "bbox": [80, 220, 180, 44]},
        {
            "id": "D3",
            "tag": "p",
            "role": "text",
            "text": "Trusted by 2,000 freelancers",
            "bbox": [80, 300, 400, 24],
        },
    ],
    "mobile": [
        {
            "id": "M1",
            "tag": "h1",
            "role": "heading",
            "text": "Ship invoices in 30 seconds",
            "bbox": [16, 100, 350, 80],
        },
        {"id": "M2", "tag": "a", "role": "cta", "text": "Start free trial", "bbox": [16, 200, 160, 44]},
    ],
}


def make_capture(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    for name, size in {
        "desktop_full.png": (1440, 1200),
        "desktop_fold.png": (1440, 900),
        "mobile_full.png": (390, 1600),
        "mobile_fold.png": (390, 844),
    }.items():
        Image.new("RGB", size, "white").save(d / name)
    for vp, blocks in BLOCKS.items():
        (d / f"blocks_{vp}.json").write_text(json.dumps(blocks), encoding="utf-8")
    meta = {
        "url": URL,
        "final_url": URL,
        "status_code": 200,
        "title": "Invoices for freelancers",
        "captured_at": "2026-11-10T12:00:00+00:00",
        "viewports": {"desktop": {"height": 1200, "blocks": 3}, "mobile": {"height": 1600, "blocks": 2}},
    }
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (d / "page.html").write_text("<h1>Ship invoices in 30 seconds</h1>", encoding="utf-8")
    return d


def offline(monkeypatch: pytest.MonkeyPatch, cap: Path) -> None:
    """The pipeline's page visit replaced by a copy of the synthetic capture (no browser, no network)."""
    from cro_lens.capture.browser import load_capture

    def fake_capture(url: str, out: Path):
        shutil.copytree(cap, out, dirs_exist_ok=True)
        return load_capture(out)

    monkeypatch.setattr("cro_lens.pipeline.run.capture", fake_capture)
    monkeypatch.setattr("cro_lens.pipeline.run.check_robots", lambda url: "allowed")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    h = tmp_path / "home"
    monkeypatch.setenv("CRO_LENS_HOME", str(h))
    monkeypatch.setenv("CRO_LENS_PROVIDER", "fake")
    monkeypatch.delenv("CRO_LENS_FAKE_FAIL", raising=False)
    return h


@pytest.fixture
def done_run(home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, dict]:
    offline(monkeypatch, make_capture(tmp_path / "cap"))
    run_id = "20261110-120000-127-0-0-1"
    folder = home / "runs" / run_id
    rep = Pipeline(FakeProvider(), Options(), folder).run(URL, run_id)
    return run_id, json.loads(rep.model_dump_json(by_alias=True))


@pytest.fixture
def client(tmp_path: Path, home: Path) -> TestClient:
    return TestClient(create_app(), base_url="http://127.0.0.1")


def test_bad_url_is_refused_without_a_run(client: TestClient, home: Path) -> None:
    assert client.get("/healthz").json() == {"ok": True}
    r = client.post("/api/runs", json={"url": "ftp://example.invalid/x"})
    assert r.status_code == 400 and r.json()["error"]
    assert client.get("/api/runs").json() == []
    assert not (home / "runs").exists() or not any((home / "runs").iterdir())


def test_done_run_api_page_fragment_and_files(client: TestClient, done_run: tuple[str, dict]) -> None:
    run_id, rep = done_run
    r = client.get(f"/api/runs/{run_id}")
    assert r.status_code == 200 and r.json()["run"]["id"] == run_id
    listed = client.get("/api/runs").json()
    assert listed[0]["run_id"] == run_id and listed[0]["status"] == "done" and listed[0]["url"] == URL

    html = client.get(f"/runs/{run_id}").text
    live = [f for f in rep["findings"] if f["check"]["verdict"] != "dropped"]
    dropped = [f for f in rep["findings"] if f["check"]["verdict"] == "dropped"]
    assert html.count('data-testid="finding-card"') == len(live)
    assert html.count('data-testid="experiment-row"') == len(rep["experiments"])
    assert html.count('data-testid="top3-item"') == len(rep["top3"])
    assert html.count('data-testid="dropped-item"') == len(dropped)
    for s in ("robots", "capture", "understand", "analyse", "check", "hypotheses", "report"):
        assert f'data-testid="step-{s}" data-step="{s}" data-status="done"' in html
    for tid in ("report-summary", "understanding", "unverifiable-list", "speed-panel", "cost-total"):
        assert f'data-testid="{tid}"' in html
    assert "API-equivalent" in html
    frag = client.get(f"/runs/{run_id}/report-fragment")
    assert frag.status_code == 200 and 'data-testid="report-summary"' in frag.text

    crop = next(e["crop"] for f in rep["findings"] for e in f["evidence"] if e.get("crop"))
    assert client.get(f"/runs/{run_id}/files/{crop}").status_code == 200
    assert client.get(f"/runs/{run_id}/files/steps.jsonl").status_code == 200
    assert client.get(f"/runs/{run_id}/files/..%2F..%2Fsecret.txt").status_code == 404
    assert client.get("/api/runs/no-such-run").status_code == 404
    assert client.get("/runs/no-such-run").status_code == 404


def test_sse_replays_steps_and_ends(client: TestClient, done_run: tuple[str, dict]) -> None:
    run_id, _ = done_run
    with client.stream("GET", f"/api/runs/{run_id}/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    events = [
        (blk.split("\n")[0][len("event: ") :], json.loads(blk.split("\n")[1][len("data: ") :]))
        for blk in body.strip().split("\n\n")
        if blk.startswith("event: ")
    ]
    assert [d["step"] for e, d in events if e == "step" and d["status"] == "done"][0] == "robots"
    assert events[-1] == ("end", {"status": "done", "exit_code": 0, "report_url": f"/runs/{run_id}"})


def test_failed_run_is_409_with_exit_code(client: TestClient, home: Path) -> None:
    run_id = "20261110-120500-127-0-0-1"
    folder = home / "runs" / run_id
    folder.mkdir(parents=True)
    events = [
        {"step": "robots", "status": "done", "t": "2026-11-10T12:05:00+00:00"},
        {"step": "understand", "status": "done", "t": "2026-11-10T12:05:01+00:00"},
        {"step": "analyse", "status": "failed", "t": "2026-11-10T12:05:02+00:00", "detail": "analyse: boom"},
    ]
    (folder / "steps.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    r = client.get(f"/api/runs/{run_id}")
    assert r.status_code == 409
    assert r.json() == {"status": "failed", "exit_code": 6, "error": "analyse: boom", "resume_from": None}
    html = client.get(f"/runs/{run_id}").text
    assert 'data-testid="run-error"' in html and "analyse: boom" in html
    assert 'data-testid="step-check" data-step="check" data-status="pending"' in html
    assert 'data-testid="report-summary"' not in html


def test_grades_on_a_report_feed_your_eval_and_the_next_run(
    client: TestClient,
    home: Path,
    done_run: tuple[str, dict],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id, rep = done_run
    live = [f["id"] for f in rep["findings"] if f["check"]["verdict"] != "dropped"]
    dropped = [f["id"] for f in rep["findings"] if f["check"]["verdict"] == "dropped"]
    assert live == ["F1", "F2"] and dropped == ["F3"]

    st = client.get("/api/eval").json()
    assert st["graded"] == 0 and st["precision"] is None and st["evidence_validity"] is not None
    html = client.get("/eval").text
    assert 'data-testid="eval-empty"' in html and "pending grades" in html

    base = f"/api/runs/{run_id}/grades"
    assert client.put(f"{base}/F1", json={"verdict": "valid"}).status_code == 200
    r = client.put(f"{base}/F2", json={"verdict": "invalid", "note": "the CTA is fine"})
    assert r.status_code == 200 and r.json()["note"] == "the CTA is fine"
    assert client.put(f"{base}/F2", json={"verdict": "maybe"}).status_code == 400
    assert client.put(f"{base}/F3", json={"verdict": "valid"}).status_code == 404, "dropped: not gradable"
    assert client.put("/api/runs/no-such-run/grades/F1", json={"verdict": "valid"}).status_code == 404
    assert set(client.get(base).json()) == {"F1", "F2"}

    page = client.get(f"/runs/{run_id}").text
    assert 'data-grade="valid"' in page and 'data-grade="invalid"' in page and "2</span> of 2 graded" in page
    st = client.get("/api/eval").json()
    assert (st["graded"], st["valid"], st["invalid"], st["precision"]) == (2, 1, 1, 0.5)
    (row,) = st["runs"]
    assert (row["run_id"], row["findings"], row["graded"], row["valid"]) == (run_id, 2, 2, 1)
    assert 'data-testid="eval-run-row"' in client.get("/eval").text

    # the grade outlives the run, and the next run of the same site learns from it
    assert client.delete(f"/api/runs/{run_id}").status_code == 204
    assert client.get("/api/eval").json()["graded"] == 2
    folder = home / "runs" / "20261110-140000-127-0-0-1"
    rep2 = Pipeline(FakeProvider(), Options(), folder).run(URL, folder.name)
    fb = json.loads((folder / "feedback.json").read_text(encoding="utf-8"))
    assert fb["enabled"] is True and [e["verdict"] for e in fb["examples"]] == ["invalid", "valid"]
    assert all(e["same_site"] for e in fb["examples"]) and fb["examples"][0]["note"] == "the CTA is fine"
    assert rep2.run.feedback and rep2.run.feedback.examples == 2 and rep2.run.feedback.same_site == 2
    assert "Learned from 2 of your graded findings (2 from this site)." in (folder / "report.md").read_text(
        encoding="utf-8"
    )
    assert "learned from 2 graded findings" in client.get(f"/runs/{folder.name}").text

    # clearing a grade
    assert client.delete(f"/api/runs/{run_id}/grades/F1").status_code == 204
    assert client.delete(f"/api/runs/{run_id}/grades/F1").status_code == 404
    assert client.get("/api/eval").json()["graded"] == 1


def test_a_run_without_feedback_learns_nothing(
    client: TestClient, home: Path, done_run: tuple[str, dict]
) -> None:
    run_id, _ = done_run
    client.put(f"/api/runs/{run_id}/grades/F1", json={"verdict": "valid"})
    folder = home / "runs" / "20261110-150000-127-0-0-1"
    rep = Pipeline(FakeProvider(), Options(feedback=False), folder).run(URL, folder.name)
    assert json.loads((folder / "feedback.json").read_text(encoding="utf-8")) == {
        "enabled": False,
        "examples": [],
    }
    assert rep.run.feedback and rep.run.feedback.enabled is False
    assert "Feedback: off" in (folder / "report.md").read_text(encoding="utf-8")


def test_cross_site_writes_and_foreign_hosts_refused(tmp_path) -> None:
    from fastapi.testclient import TestClient

    from cro_lens.web.app import create_app

    c = TestClient(create_app(), base_url="http://127.0.0.1")
    r = c.post("/api/runs", content='{"url": "https://example.com"}', headers={"content-type": "text/plain"})
    assert r.status_code == 415
    r = c.post("/api/runs", json={"url": "https://example.com"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    rebound = TestClient(create_app(), base_url="http://attacker.example")
    assert rebound.get("/healthz").status_code == 403


# ---------------------------------------------------------------- resume, delete, sign-in
def wait_status(client: TestClient, run_id: str, want: int, timeout: float = 15.0) -> dict:
    import time

    end = time.time() + timeout
    while time.time() < end:
        r = client.get(f"/api/runs/{run_id}")
        if r.status_code == want:
            return r.json()
        time.sleep(0.05)
    raise AssertionError(f"{run_id} never reached HTTP {want}; last {r.status_code} {r.text[:200]}")


def test_not_signed_in_is_refused_before_any_run(
    client: TestClient, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CRO_LENS_FAKE_FAIL", "signin")
    r = client.post("/api/runs", json={"url": "https://example.com/"})
    assert r.status_code == 503 and "claude auth login" in r.json()["error"]
    assert client.get("/api/runs").json() == [], "a refused start must not leave a run folder"
    st = client.get("/api/provider").json()
    assert st["ready"] is False and "claude auth login" in st["error"]
    assert 'data-testid="provider-warning"' in client.get("/").text


def test_failed_run_resumes_from_ui_and_is_listed_with_actions(
    client: TestClient, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    offline(monkeypatch, make_capture(tmp_path / "cap"))
    run_id = "20261110-130000-127-0-0-1"
    folder = home / "runs" / run_id
    monkeypatch.setenv("CRO_LENS_FAKE_FAIL", "check")
    with pytest.raises(Exception, match="check"):
        Pipeline(FakeProvider(), Options(), folder).run(URL, run_id)
    body = wait_status(client, run_id, 409)
    assert body["exit_code"] == 6 and body["resume_from"] == "check"
    html = client.get(f"/runs/{run_id}").text
    assert 'data-testid="resume-button"' in html and "Continue from self-check" in html
    start = client.get("/").text
    assert 'data-testid="run-resume"' in start and 'data-testid="run-delete"' in start
    (row,) = client.get("/api/runs").json()
    assert row["status"] == "failed" and row["resume_from"] == "check"

    # still not signed in → 503, nothing changes
    monkeypatch.setenv("CRO_LENS_FAKE_FAIL", "signin")
    assert client.post(f"/api/runs/{run_id}/resume", json={}).status_code == 503
    monkeypatch.delenv("CRO_LENS_FAKE_FAIL")
    r = client.post(f"/api/runs/{run_id}/resume", json={})
    assert r.status_code == 202 and r.json() == {"run_id": run_id, "resume_from": "check"}
    rep = wait_status(client, run_id, 200)
    assert rep["run"]["id"] == run_id and rep["experiments"]
    assert client.post(f"/api/runs/{run_id}/resume", json={}).status_code == 409, "a done run cannot resume"
    assert client.post("/api/runs/no-such-run/resume", json={}).status_code == 404


def test_interrupted_run_is_failed_not_running_forever(
    client: TestClient, home: Path, tmp_path: Path
) -> None:
    import os
    import time

    run_id = "20261110-131000-127-0-0-1"
    folder = home / "runs" / run_id
    make_capture(folder / "capture")
    lines = [
        {"step": "robots", "status": "done"},
        {"step": "capture", "status": "done"},
        {"step": "understand", "status": "started"},
    ]
    (folder / "steps.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    hb = folder / "heartbeat"
    hb.write_text("x", encoding="utf-8")
    assert client.get(f"/api/runs/{run_id}").status_code == 202, "fresh heartbeat: still running"
    assert client.delete(f"/api/runs/{run_id}").status_code == 409, "a running audit cannot be deleted"
    old = time.time() - 120
    os.utime(hb, (old, old))
    body = client.get(f"/api/runs/{run_id}").json()
    assert (
        body["status"] == "failed" and "interrupted" in body["error"] and body["resume_from"] == "understand"
    )


def test_delete_run(client: TestClient, done_run: tuple[str, dict], home: Path) -> None:
    run_id, _ = done_run
    assert 'data-testid="run-delete"' in client.get(f"/runs/{run_id}").text
    r = client.delete(f"/api/runs/{run_id}", headers={"origin": "https://evil.example"})
    assert r.status_code == 403 and (home / "runs" / run_id).is_dir()
    assert client.delete(f"/api/runs/{run_id}").status_code == 204
    assert not (home / "runs" / run_id).exists()
    assert client.get(f"/api/runs/{run_id}").status_code == 404
    assert client.get("/api/runs").json() == []
    assert client.delete(f"/api/runs/{run_id}").status_code == 404
    assert client.delete("/api/runs/..").status_code == 404


def test_resume_in_another_process_shows_running_not_the_old_failure(client: TestClient, home: Path) -> None:
    run_id = "20261110-133000-127-0-0-1"
    folder = home / "runs" / run_id
    folder.mkdir(parents=True)
    ev = [
        {"step": "capture", "status": "done"},
        {"step": "understand", "status": "failed", "detail": "understand: Not logged in"},
        {"step": "resume", "status": "done", "detail": "resuming from understand"},
    ]
    (folder / "steps.jsonl").write_text("\n".join(json.dumps(x) for x in ev) + "\n", encoding="utf-8")
    (folder / "heartbeat").write_text("x", encoding="utf-8")
    assert client.get(f"/api/runs/{run_id}").status_code == 202
    assert client.post(f"/api/runs/{run_id}/resume", json={}).status_code == 409
    assert client.delete(f"/api/runs/{run_id}").status_code == 409 and folder.is_dir()


def test_capture_failure_offers_run_again_not_resume(client: TestClient, home: Path) -> None:
    from cro_lens.pipeline.state import RunSpec

    run_id = "20261110-132000-127-0-0-1"
    folder = home / "runs" / run_id
    folder.mkdir(parents=True)
    spec = RunSpec(url=URL, run_id=run_id, model="opus", given={"goal": "Trial sign-up"})
    (folder / "run.json").write_text(spec.model_dump_json(), encoding="utf-8")
    ev = {"step": "capture", "status": "failed", "detail": "capture: page returned HTTP 404"}
    (folder / "steps.jsonl").write_text(json.dumps(ev) + "\n", encoding="utf-8")
    body = client.get(f"/api/runs/{run_id}").json()
    assert body["exit_code"] == 4 and body["resume_from"] is None
    assert client.get("/api/runs").json()[0]["url"] == URL, "the URL comes from run.json"
    html = client.get(f"/runs/{run_id}").text
    assert 'data-testid="resume-button"' not in html
    assert 'data-testid="rerun-button"' in html and f'data-url="{URL}"' in html
    assert 'data-model="opus"' in html and 'data-goal="Trial sign-up"' in html
    assert client.post(f"/api/runs/{run_id}/resume", json={}).status_code == 409


# ---------------------------------------------------------------- who pays (ADR 0007)
def test_api_key_run_is_labelled_billed_not_api_equivalent(
    client: TestClient, done_run: tuple[str, dict], home: Path
) -> None:
    from cro_lens.models import Report
    from cro_lens.report.render_md import cost_text, render_markdown

    run_id, rep = done_run
    assert rep["run"]["billing"] is None, "the fake provider pays nobody"
    path = home / "runs" / run_id / "report.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["run"]["billing"] = "api_key"
    data["run"]["provider"] = "claude-code"
    path.write_text(json.dumps(data), encoding="utf-8")
    r = Report.model_validate(data)
    assert "billed to your Anthropic API key" in cost_text(r)
    md = render_markdown(r)
    assert "billed to your Anthropic API key" in md and "API-equivalent" not in md
    html = client.get(f"/runs/{run_id}").text
    assert "billed to your Anthropic API key" in html and "ANTHROPIC_API_KEY was set" in html

    data["run"]["billing"] = "subscription"
    assert "not billed per call" in render_markdown(Report.model_validate(data))
    del data["run"]["billing"]  # a report written before 0.3
    assert "API-equivalent" in cost_text(Report.model_validate(data))


def test_provider_status_carries_billing_and_notices(client: TestClient) -> None:
    st = client.get("/api/provider").json()
    assert st == {"provider": "fake", "ready": True, "billing": None, "notices": []}
    assert 'data-testid="provider-notice"' in client.get("/").text


def test_a_worked_around_token_explains_itself(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from cro_lens.llm.claude_code import TOKEN_FALLBACK
    from cro_lens.llm.fake import FakeProvider

    monkeypatch.setattr(FakeProvider, "notices", [TOKEN_FALLBACK], raising=False)
    (n,) = client.get("/api/provider").json()["notices"]
    assert n["code"] == "token_fallback" and n["title"].endswith("Audits still work.")
    assert n["steps"] and any(c["command"] == "claude auth status --json" for c in n["commands"])
