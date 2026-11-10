"""H05 — the model keeps returning unusable output at the self-check step."""
import re

import pytest

from conftest import png_size, read_json, read_jsonl, step_lines


@pytest.mark.smoke
def test_H05_llm_step_failure_keeps_capture_but_writes_no_report(cli, site, tmp_path):
    """H05 [LLM-2, CLI-2, CLI-4]
    With the fake failing `check` every time, `analyze --out DIR` exits 6 with
    one `error:` line naming the step; progress shows the earlier steps done and
    `check` failed. DIR keeps steps.jsonl (check failed) and capture/, but must
    NOT contain report.md/report.json, and no later step may run."""
    out = tmp_path / "failed-run"
    r = cli("analyze", site.url("/saas.html"), "--out", out, env_extra={"CRO_LENS_FAKE_FAIL": "check"})
    assert r.code == 6, r.dump()

    errors = r.error_lines()
    assert len(errors) == 1 and re.search(r"check", errors[0], re.I), r.dump()

    marks = {s.name: s.mark for s in step_lines(r.out)}
    for done in ("robots", "capture", "understand", "analyse"):
        assert marks.get(done) == "✓", (done, r.dump())
    assert marks.get("check") == "✗", r.dump()
    assert "hypotheses" not in marks and "report" not in marks, r.dump()
    assert not re.search(r"^report:", r.out, re.M)

    events = read_jsonl(out / "steps.jsonl")
    assert any(e["step"] == "check" and e["status"] == "failed" for e in events), events
    assert any(e["step"] == "analyse" and e["status"] == "done" for e in events), events
    assert not [e for e in events if e["step"] in ("hypotheses", "report")], events

    cap = out / "capture"
    png_size(cap / "desktop_full.png")
    png_size(cap / "mobile_fold.png")
    assert read_json(cap / "blocks_desktop.json")
    assert (cap / "meta.json").is_file()

    assert not (out / "report.md").exists() and not (out / "report.json").exists()
