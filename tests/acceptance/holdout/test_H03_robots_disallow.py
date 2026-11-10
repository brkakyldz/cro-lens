"""H03 — a user points cro-lens at a page the site's robots.txt disallows."""
import re

import pytest

from conftest import files_named, llm_steps_logged, step_lines


@pytest.mark.smoke
def test_H03_robots_disallow_stops_before_llm(cli, site, home):
    """H03 [CLI-3, CAP-1, SAFE-1]
    robots.txt (`User-agent: *` / `Disallow: /private/`) is fetched once with a
    `cro-lens/<version>` user-agent; the run exits 3 with an `error:` line naming
    robots.txt and the path. The page itself must NOT be fetched, no LLM step
    may run (the fake is armed to fail `understand`, which would turn this into
    exit 6), and no report is written."""
    r = cli("analyze", site.url("/private/page.html"), env_extra={"CRO_LENS_FAKE_FAIL": "understand"})
    assert r.code == 3, r.dump()

    errors = r.error_lines()
    assert len(errors) == 1, r.dump()
    assert re.search(r"robots", errors[0], re.I) and "/private/page.html" in errors[0], errors[0]

    robots = site.requests("/robots.txt")
    assert len(robots) == 1, [x.path for x in site.requests()]
    assert re.search(r"cro-lens/\S+", robots[0].user_agent), robots[0].user_agent
    assert site.count("/private/page.html") == 0, "disallowed page was fetched"

    assert not [s for s in step_lines(r.out) if s.name in {"understand", "analyse", "check", "hypotheses"}]
    assert not llm_steps_logged(home), "an LLM step ran after robots.txt refused"
    assert not files_named(home, "report.json") and not files_named(home, "report.md")
