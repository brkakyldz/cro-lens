"""robots.txt check — one fetch, honours `*` and `cro-lens` groups."""

from __future__ import annotations

from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from cro_lens.config import USER_AGENT_SUFFIX, RobotsDisallowed


def check_robots(url: str, timeout: float = 10.0) -> str:
    """Return a short status line; raise RobotsDisallowed when the path is disallowed."""
    p = urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    try:
        r = httpx.get(
            robots_url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": f"Mozilla/5.0 {USER_AGENT_SUFFIX}"},
        )
    except httpx.HTTPError as e:
        return f"robots.txt unreachable ({type(e).__name__}), proceeding"
    if r.status_code >= 400:
        return f"no robots.txt ({r.status_code})"
    rp = RobotFileParser()
    rp.parse(r.text.splitlines())
    path = p.path or "/"
    if p.query:
        path += "?" + p.query
    target = f"{p.scheme}://{p.netloc}{path}"
    if not rp.can_fetch("cro-lens", target) or not rp.can_fetch("*", target):
        raise RobotsDisallowed(f"robots.txt disallows {p.path or '/'}")
    return "robots.txt allows this path"
