"""H02 — a founder who knows their audience and traffic source analyses a
product page, first pasting the address without a scheme."""
import json

from conftest import (AWARENESS, CONFIDENCE, SHOP_H1, files_named, normalise, read_json,
                      report_path_from)

AUDIENCE = "Trail runners who hike in cold, wet weather"
TRAFFIC = "Google Ads search: merino running socks"
GOAL = "add to cart"


def test_H02_alias_with_given_context_writes_to_out_dir(cli, site, home, tmp_path):
    """H02 [CLI-1, CLI-3, CLI-4, LLM-1, LLM-4, UND-1, UND-2, ANA-3, CAP-3]
    A URL without http(s) is refused (exit 2) and nothing is written; the alias
    `cro-lens <url>` with --model/--provider/--audience/--traffic/--goal/--out
    writes the run folder exactly to --out, marks the context `given` (replacing
    the inferred values) and grounds the promise in the h1 block. Nothing may be
    written under $CRO_LENS_HOME/runs."""
    out = tmp_path / "shop-run"
    url = site.url("/shop.html")

    bad = cli("analyze", url.split("://", 1)[1], "--out", out)
    assert bad.code == 2, bad.dump()
    assert any(ln.lower().lstrip().startswith("error:") for ln in bad.err.splitlines()), bad.dump()
    assert not (out / "report.json").exists() and not (out / "report.md").exists()

    r = cli(url, "--model", "opus", "--provider", "fake", "--audience", AUDIENCE,
            "--traffic", TRAFFIC, "--goal", GOAL, "--out", out)
    assert r.code == 0, r.dump()
    assert report_path_from(r.out) == (out / "report.md").resolve()
    assert (out / "report.json").is_file()
    assert not files_named(home / "runs", "report.json"), "run also written under CRO_LENS_HOME"

    rep = read_json(out / "report.json")
    run = rep["run"]
    assert run["provider"] == "fake"
    assert "opus" in run["model"].lower(), run["model"]
    assert run["given"] == {"audience": AUDIENCE, "traffic": TRAFFIC, "goal": GOAL}

    und = rep["understanding"]
    assert und["audience"]["value"] == AUDIENCE and und["audience"]["source"] == "given"
    assert und["traffic_source"]["value"] == TRAFFIC and und["traffic_source"]["source"] == "given"
    assert "fixture audience" not in json.dumps(und["audience"])     # NOT: inferred value kept

    # UND-1: promise grounded in the h1 block (fake@1), fields carry confidence
    blocks = read_json(out / "capture" / "blocks_desktop.json") + read_json(out / "capture" / "blocks_mobile.json")
    text_by_id = {b["id"]: b["text"] for b in blocks}
    assert und["promise"]["value"] == SHOP_H1
    assert und["promise"]["evidence"], "promise cites no block"
    assert all(bid in text_by_id for bid in und["promise"]["evidence"])
    assert any(normalise(text_by_id[bid]) == normalise(SHOP_H1) for bid in und["promise"]["evidence"])
    for key in ("audience", "job_to_be_done", "traffic_source", "awareness_level"):
        assert und[key]["confidence"] in CONFIDENCE, (key, und[key])
    assert und["awareness_level"]["value"] in AWARENESS

    # UND-2: five-second judgement quotes copy that is on the page
    five = und["five_second"]
    assert isinstance(five["understood"], str) and five["understood"].strip()
    assert isinstance(five["clear"], bool) and isinstance(five["specific"], bool)
    assert five["quote"].strip()
    page_text = normalise(" ".join(b["text"] for b in blocks))
    assert normalise(five["quote"]) in page_text, five["quote"]

    # ANA-3: what could not be verified, with why and the assumption made
    assert rep["unverifiable"]
    for item in rep["unverifiable"]:
        assert item["what"].strip() and item["why"].strip() and item["assumption"].strip()
