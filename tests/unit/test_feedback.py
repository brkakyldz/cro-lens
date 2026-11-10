"""The user's own eval (eval@2): grades, what a run learns from them, and the metrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_web import URL, make_capture, offline
from typer.testing import CliRunner

from cro_lens import feedback
from cro_lens.cli import app
from cro_lens.llm.fake import FakeProvider
from cro_lens.models import Report
from cro_lens.pipeline.run import Options, Pipeline


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    h = tmp_path / "home"
    monkeypatch.setenv("CRO_LENS_HOME", str(h))
    monkeypatch.setenv("CRO_LENS_PROVIDER", "fake")
    monkeypatch.delenv("CRO_LENS_FAKE_FAIL", raising=False)
    offline(monkeypatch, make_capture(tmp_path / "cap"))
    return h


class Recording(FakeProvider):
    """The fake provider, keeping every request so a test can read what the model was shown."""

    def __init__(self) -> None:
        self.requests = []

    def complete(self, req):
        self.requests.append(req)
        return super().complete(req)

    def text_of(self, step: str) -> str:
        req = next(r for r in self.requests if r.step == step)
        return "\n".join(p for p in req.parts if isinstance(p, str))


def run(home: Path, name: str, url: str = URL, provider=None, **opts) -> tuple[Report, Path]:
    folder = home / "runs" / name
    rep = Pipeline(provider or FakeProvider(), Options(**opts), folder).run(url, name)
    return rep, folder


def grade(rep: Report, fid: str, verdict: str, note: str = "") -> None:
    f = feedback.gradable(rep, fid)
    assert f is not None
    feedback.set_grade(rep, f, verdict, note)


def test_grades_reach_the_model_in_analyse_and_check(home: Path) -> None:
    first, _ = run(home, "20261111-100000-a")
    grade(first, "F2", "invalid", "the trial button is obvious")
    rec = Recording()
    run(home, "20261111-110000-a", provider=rec)
    for step in ("analyse", "check"):
        text = rec.text_of(step)
        assert "Primary action is easy to miss" in text and "WRONG" in text
        assert "the trial button is obvious" in text
    assert "WRONG" not in rec.text_of("understand"), "only analyse and check learn from grades"


def test_no_grades_or_feedback_off_shows_the_model_nothing(home: Path) -> None:
    rec = Recording()
    rep, folder = run(home, "20261111-100000-a", provider=rec)
    assert "earlier verdicts" not in rec.text_of("analyse")
    assert rep.run.feedback is not None and rep.run.feedback.examples == 0
    grade(rep, "F1", "valid")
    rec2 = Recording()
    run(home, "20261111-110000-a", provider=rec2, feedback=False)
    assert "verdicts" not in rec2.text_of("analyse") and "verdicts" not in rec2.text_of("check")


def test_same_site_first_newest_first_at_most_twelve(home: Path) -> None:
    other, _ = run(home, "20261111-090000-other", url="https://other.example/")
    for _ in range(7):
        grade(other, "F1", "valid")
        grade(other, "F2", "invalid")
    mine, _ = run(home, "20261111-100000-mine", url="https://www.Shop.example/landing")
    grade(mine, "F1", "valid")
    grade(mine, "F2", "invalid")
    # 2 grades on other.example (re-grading replaces) + 2 on shop.example
    fb = feedback.select("https://shop.example/other-page")
    assert [(e.host, e.finding_id, e.same_site) for e in fb.examples[:2]] == [
        ("shop.example", "F2", True),
        ("shop.example", "F1", True),
    ]
    assert [e.host for e in fb.examples[2:]] == ["other.example", "other.example"]
    assert len(feedback.select("https://shop.example/", limit=3).examples) == 3


def test_resume_learns_from_what_the_first_attempt_froze(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first, _ = run(home, "20261111-100000-a")
    grade(first, "F1", "valid")
    monkeypatch.setenv("CRO_LENS_FAKE_FAIL", "check")
    folder = home / "runs" / "20261111-110000-a"
    with pytest.raises(Exception, match="check"):
        Pipeline(FakeProvider(), Options(), folder).run(URL, folder.name)
    frozen = (folder / "feedback.json").read_text(encoding="utf-8")
    grade(first, "F2", "invalid")  # graded after the start: not part of this run
    monkeypatch.delenv("CRO_LENS_FAKE_FAIL")
    pipe, spec, start = Pipeline.for_resume(FakeProvider(), folder)
    rep = pipe.resume(spec, start)
    assert (folder / "feedback.json").read_text(encoding="utf-8") == frozen
    assert rep.run.feedback is not None and rep.run.feedback.examples == 1


def test_damaged_grades_file_is_survivable(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "grades.json").write_text("{not json", encoding="utf-8")
    assert feedback.load_grades() == {}
    data = {"schema_version": "grades@1", "grades": {"x/F1": {"run_id": "x"}}}
    (home / "grades.json").write_text(json.dumps(data), encoding="utf-8")
    assert feedback.load_grades() == {}
    rep, _ = run(home, "20261111-100000-a")
    assert rep.run.feedback is not None and rep.run.feedback.examples == 0


def test_cli_eval_pending_then_numbers(home: Path) -> None:
    cli = CliRunner()
    out = cli.invoke(app, ["eval"]).output.splitlines()
    assert out == [
        "graded: 0 findings (0 valid · 0 invalid)",
        "precision: pending grades",
        "evidence validity: pending runs",
        "next run learns from: 0 graded findings",
    ]
    rep, _ = run(home, "20261111-100000-a")
    grade(rep, "F1", "valid")
    grade(rep, "F2", "invalid")
    res = cli.invoke(app, ["eval"])
    assert res.exit_code == 0
    lines = res.output.splitlines()
    assert lines[0] == "graded: 2 findings (1 valid · 1 invalid)"
    assert lines[1] == "precision: 50%"
    # fake: F1 and F2 quotes are on the page, F3's is not → 2 of 3
    assert lines[2] == "evidence validity: 67% over 1 runs"
    assert lines[3] == "next run learns from: 2 graded findings"
