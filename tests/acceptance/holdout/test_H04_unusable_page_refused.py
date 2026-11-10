"""H04 — a user analyses a page that cannot be used: a bot-challenge wall, or
an address that no longer exists."""
import re

import pytest

from conftest import LLM_STEPS, files_named, llm_steps_logged, step_lines


@pytest.mark.parametrize(
    "path, code, cause",
    [
        ("/challenge.html", 5, r"bot|challenge|captcha|human|block"),
        ("/gone-page.html", 4, r"404|not found|status|load"),
    ],
    ids=["bot-challenge", "missing-page"],
)
def test_H04_unusable_page_is_refused_without_llm_or_bypass(cli, site, home, path, code, cause):
    """H04 [CLI-3, SAFE-1, CAP-1]
    A bot challenge ("Just a moment..." / "Verify you are human") exits 5; a
    404 exits 4. Either way stderr names the cause in one `error:` line, the
    page is not hammered (at most one load per viewport — no retry to get past
    the wall), no LLM step runs (fake armed to fail `understand`) and no
    report is written."""
    r = cli("analyze", site.url(path), env_extra={"CRO_LENS_FAKE_FAIL": "understand"})
    assert r.code == code, r.dump()

    errors = r.error_lines()
    assert len(errors) == 1, r.dump()
    assert re.search(cause, errors[0], re.I), errors[0]

    assert 1 <= site.count(path) <= 2, f"{path} requested {site.count(path)} times"
    assert site.html_paths() <= {path}, f"other pages fetched: {site.html_paths()}"

    assert not llm_steps_logged(home), "an LLM step ran for an unusable page"
    assert not [s for s in step_lines(r.out) if s.name in LLM_STEPS], r.dump()
    assert not files_named(home, "report.json") and not files_named(home, "report.md")
