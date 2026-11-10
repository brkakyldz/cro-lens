"""End-to-end offline run on the fixture site with the fake provider; asserts report@1 invariants."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cro_lens.config import Blocked, RobotsDisallowed
from cro_lens.llm.fake import FakeProvider
from cro_lens.models import Report
from cro_lens.pipeline.run import Options, Pipeline

pytestmark = pytest.mark.browser
FIXTURES = Path(__file__).parents[1] / "fixtures" / "pages"
REPORT_H2 = [
    "## Summary",
    "## Top 3 experiments",
    "## Experiment backlog",
    "## Findings",
    "## What this page is (understanding)",
    "## Assumptions and couldn't verify",
    "## Dropped by self-check",
    "## Page speed",
    "## Run",
]


@pytest.fixture(scope="module")
def site():
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    p = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(FIXTURES)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    import httpx

    for _ in range(100):
        try:
            httpx.get(f"http://127.0.0.1:{port}/robots.txt", timeout=0.5)
            break
        except httpx.HTTPError:
            import time

            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    p.terminate()


def test_saas_run_invariants(site: str, tmp_path: Path) -> None:
    rep = Pipeline(FakeProvider(), Options(), tmp_path).run(f"{site}/saas.html", "t1")
    data = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    Report.model_validate(data)
    for f in (
        "desktop_full.png",
        "desktop_fold.png",
        "mobile_full.png",
        "mobile_fold.png",
        "blocks_desktop.json",
        "blocks_mobile.json",
        "page.html",
        "meta.json",
    ):
        assert (tmp_path / "capture" / f).exists(), f
    verdicts = {f.id: (f.check.deterministic, f.check.verdict) for f in rep.findings}
    assert verdicts == {"F1": ("pass", "kept"), "F2": ("pass", "flagged"), "F3": ("fail", "dropped")}
    assert rep.findings[2].check.reason.startswith("evidence_not_found")
    live = {f.id for f in rep.findings if f.check.verdict != "dropped"}
    assert all(e.finding_id in live for e in rep.experiments)
    scores = [e.ice.score for e in rep.experiments]
    assert scores == sorted(scores, reverse=True)
    assert all(e.ice.confidence <= 6 for e in rep.experiments)
    assert len(rep.top3) == min(3, len(rep.experiments))
    assert rep.cost.total_usd_equivalent == 0
    for f in rep.findings:
        for e in f.evidence:
            if e.crop:
                assert (tmp_path / e.crop).exists()
    md = (tmp_path / "report.md").read_text(encoding="utf-8")
    positions = [md.index(h) for h in REPORT_H2]
    assert positions == sorted(positions)
    assert "API-equivalent" in md
    roles = {b["role"] for b in json.loads((tmp_path / "capture" / "blocks_desktop.json").read_text("utf-8"))}
    assert {"heading", "cta", "price", "form_field"} <= roles


def test_given_context_overrides(site: str, tmp_path: Path) -> None:
    from cro_lens.models import Given

    rep = Pipeline(FakeProvider(), Options(given=Given(traffic="paid social")), tmp_path).run(
        f"{site}/shop.html", "t2"
    )
    assert rep.understanding.traffic_source.value == "paid social"
    assert rep.understanding.traffic_source.source == "given"


def test_robots_and_challenge_stop_before_llm(site: str, tmp_path: Path) -> None:
    with pytest.raises(RobotsDisallowed):
        Pipeline(FakeProvider(), Options(), tmp_path / "a").run(f"{site}/private/page.html", "t3")
    with pytest.raises(Blocked):
        Pipeline(FakeProvider(), Options(), tmp_path / "b").run(f"{site}/challenge.html", "t4")
    assert not (tmp_path / "a" / "report.json").exists() and not (tmp_path / "b" / "llm").exists()


def test_cli_fake_fail_exit_6(site: str, tmp_path: Path) -> None:
    env = {
        **os.environ,
        "CRO_LENS_HOME": str(tmp_path),
        "CRO_LENS_PROVIDER": "fake",
        "CRO_LENS_FAKE_FAIL": "analyse",
        "PYTHONIOENCODING": "utf-8",
    }
    p = subprocess.run(
        [sys.executable, "-m", "cro_lens.cli", f"{site}/saas.html"],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert p.returncode == 6, p.stderr
    assert p.stderr.startswith("error:")
    assert not list(tmp_path.rglob("report.json"))
