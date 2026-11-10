"""H06 — an agency analyses a client page that greets visitors with a cookie
banner, then inspects what was captured."""
import re

from conftest import (BLOCK_ROLES, normalise, png_size, read_json, report_path_from)


def test_H06_consent_page_captured_once_per_viewport(cli, site, home):
    """H06 [CAP-1, CAP-2, CAP-3, CAP-4, CAP-5, CAP-6, SAFE-1, CLI-1]
    On /consent.html the banner is recorded as present and dismissed; capture/
    holds desktop (1440 wide, 1440x900 fold) and portrait mobile screenshots,
    per-viewport blocks with D/M ids, roles and bboxes and no nested
    duplicates, lab timing and tile counts within the caps. The site sees
    robots.txt once, the page at most once per viewport, every request
    identified as cro-lens/<version>, and NO other page fetched."""
    url = site.url("/consent.html")
    r = cli("analyze", url)
    assert r.code == 0, r.dump()
    run_dir = report_path_from(r.out).parent
    cap = run_dir / "capture"
    meta = read_json(cap / "meta.json")

    # CAP-4
    assert meta["consent_banner"]["present"] is True
    assert meta["consent_banner"]["dismissed"] is True
    assert meta["status_code"] == 200
    assert meta["url"] == url and meta["final_url"].endswith("/consent.html")

    # CAP-2: screenshot geometry
    assert png_size(cap / "desktop_fold.png") == (1440, 900)
    dw, dh = png_size(cap / "desktop_full.png")
    assert dw == 1440 and dh >= 900
    mw, mh = png_size(cap / "mobile_fold.png")
    fw, fh = png_size(cap / "mobile_full.png")
    assert mw < 1440 and mh > mw, "mobile fold is not a portrait phone screen"
    assert fw == mw and fh >= mh

    # CAP-3: blocks per viewport
    for name, prefix in (("blocks_desktop.json", "D"), ("blocks_mobile.json", "M")):
        blocks = read_json(cap / name)
        assert blocks, name
        ids = [b["id"] for b in blocks]
        assert len(ids) == len(set(ids)), f"duplicate ids in {name}"
        for b in blocks:
            assert re.fullmatch(rf"{prefix}\d+", b["id"]), b
            assert b["role"] in BLOCK_ROLES, b
            assert isinstance(b["tag"], str) and b["tag"]
            assert isinstance(b["text"], str) and b["text"].strip()
            assert len(b["bbox"]) == 4
        headings = [b for b in blocks if b["role"] == "heading"]
        assert headings, f"no heading block in {name}"
        first = normalise(headings[0]["text"])
        assert sum(normalise(b["text"]) == first for b in blocks) == 1, "nested duplicate block"

    # CAP-5: lab timing recorded in the same visit
    speed = meta["speed"]
    assert isinstance(speed, dict)
    numeric = [v for v in speed.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
    assert len(numeric) >= 3, speed
    rep = read_json(run_dir / "report.json")
    assert rep["capture"]["speed"] == speed

    # CAP-6: tiles within caps, truncation stated when it happens
    caps = {"desktop": 6, "mobile": 4}
    md = (run_dir / "report.md").read_text(encoding="utf-8")
    for vp, cap_n in caps.items():
        v = meta["viewports"][vp]
        assert isinstance(v["height"], int) and v["height"] > 0
        assert 1 <= v["tiles_sent"] <= cap_n, (vp, v)
        assert isinstance(v["truncated"], bool)
        if v["truncated"]:
            assert re.search(r"not (shown|sent)|truncat", md, re.I)

    # CAP-1 / SAFE-1: what the site saw
    assert site.count("/robots.txt") == 1
    assert 1 <= site.count("/consent.html") <= 2
    assert site.html_paths() == {"/consent.html"}, f"link following: {site.html_paths()}"
    agents = {x.user_agent for x in site.requests() if x.path in ("/robots.txt", "/consent.html")}
    versions = set()
    for ua in agents:
        m = re.search(r"cro-lens/(\S+)", ua)
        assert m, f"request not identified as cro-lens: {ua!r}"
        versions.add(m.group(1))
    v = cli("--version")
    assert v.code == 0, v.dump()
    for version in versions:
        assert version in v.out, (version, v.out)
