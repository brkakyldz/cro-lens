"""One visit per viewport: screenshots, id'd text blocks, consent handling, lab timing."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import httpx
from playwright.sync_api import Error as PWError
from playwright.sync_api import Page, sync_playwright

from cro_lens.config import USER_AGENT_SUFFIX, Blocked, PageLoadFailed, now_iso
from cro_lens.models import Block, CaptureMeta, ConsentBanner, Speed, ViewportMeta

BLOCKS_JS = files("cro_lens.capture").joinpath("blocks.js").read_text(encoding="utf-8")
TIMING_INIT = """window.__lcp=0;window.__cls=0;try{
new PerformanceObserver(l=>{for(const e of l.getEntries()) window.__lcp=e.startTime}).observe({type:'largest-contentful-paint',buffered:true});
new PerformanceObserver(l=>{for(const e of l.getEntries()) if(!e.hadRecentInput) window.__cls+=e.value}).observe({type:'layout-shift',buffered:true});
}catch(e){}"""
TIMING_JS = """()=>{const n=performance.getEntriesByType('navigation')[0]||{};
const res=performance.getEntriesByType('resource');
const bytes=res.reduce((a,r)=>a+(r.transferSize||0),n.transferSize||0);
return {ttfb:n.responseStart||null,dcl:n.domContentLoadedEventEnd||null,load:n.loadEventEnd||null,
lcp:window.__lcp||null,cls:window.__cls,bytes,requests:res.length+1}}"""
CHALLENGE = re.compile(
    r"verify you are human|are you a robot|captcha|just a moment\.\.\.|attention required|access denied"
    r"|checking your browser|enable javascript and cookies to continue",
    re.I,
)
CONSENT_SEL = (
    "[id*=cookie i],[class*=cookie i],[id*=consent i],[class*=consent i],[id*=gdpr i],"
    "[class*=gdpr i],[aria-label*=cookie i],#onetrust-banner-sdk,#CybotCookiebotDialog"
)
DECLINE = re.compile(
    r"^(reject( all)?|decline( all)?|deny|only (necessary|essential)|necessary only|"
    r"use necessary cookies only|refuse|close|dismiss|no,? thanks)$",
    re.I,
)


@dataclass
class CaptureResult:
    meta: CaptureMeta
    blocks: dict[str, list[Block]]
    dir: Path
    html: str


def _goto(page: Page, url: str):
    try:
        return page.goto(url, wait_until="networkidle", timeout=30000)
    except PWError as e:
        if "Timeout" not in str(e):
            raise
        return page.goto(url, wait_until="load", timeout=30000)


def _dismiss_consent(page: Page) -> ConsentBanner:
    banners = [b for b in page.query_selector_all(CONSENT_SEL) if b.is_visible()]
    big = [b for b in banners if (bb := b.bounding_box()) and bb["width"] * bb["height"] > 20000]
    if not big:
        return ConsentBanner()
    for b in big:
        for btn in b.query_selector_all("button, a, [role=button], input[type=button]"):
            label = (btn.inner_text() or btn.get_attribute("aria-label") or "").strip()
            if label and DECLINE.match(label) and btn.is_visible():
                try:
                    btn.click(timeout=3000)
                    page.wait_for_timeout(600)
                    still = any(
                        x.is_visible()
                        for x in page.query_selector_all(CONSENT_SEL)
                        if (bb := x.bounding_box()) and bb["width"] * bb["height"] > 20000
                    )
                    return ConsentBanner(present=True, dismissed=not still)
                except PWError:
                    continue
    return ConsentBanner(present=True, dismissed=False)


def _settle_lazy(page: Page) -> None:
    """Scroll once through the page (same visit) so lazy content renders, then back to top."""
    h = page.evaluate("document.documentElement.scrollHeight")
    vh = page.viewport_size["height"] if page.viewport_size else 900
    y = 0
    while y < min(h, 20000):
        y += vh
        page.evaluate(f"window.scrollTo(0, {y})")
        page.wait_for_timeout(120)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(300)


def _psi(url: str) -> dict | None:
    key = os.environ.get("PAGESPEED_API_KEY")
    if not key:
        return None
    try:
        r = httpx.get(
            "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
            params={"url": url, "strategy": "mobile", "category": "performance", "key": key},
            timeout=90,
        )
        d = r.json()
        lh = d["lighthouseResult"]
        return {
            "performance": lh["categories"]["performance"]["score"],
            "lcp": lh["audits"]["largest-contentful-paint"]["displayValue"],
            "cls": lh["audits"]["cumulative-layout-shift"]["displayValue"],
        }
    except Exception as e:  # noqa: BLE001 — PSI is optional garnish
        return {"error": f"{type(e).__name__}"}


def capture(url: str, out: Path) -> CaptureResult:
    out.mkdir(parents=True, exist_ok=True)
    blocks: dict[str, list[Block]] = {}
    vmeta: dict[str, ViewportMeta] = {}
    consent = ConsentBanner()
    speed = Speed()
    status, final_url, title, html = 0, url, "", ""
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for vp in ("desktop", "mobile"):
                if vp == "desktop":
                    ua = None
                    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
                    ua = ctx.new_page().evaluate("navigator.userAgent")
                    ctx.close()
                    ctx = browser.new_context(
                        viewport={"width": 1440, "height": 900}, user_agent=f"{ua} {USER_AGENT_SUFFIX}"
                    )
                else:
                    dev = dict(pw.devices["iPhone 13"])
                    dev["user_agent"] = f"{dev['user_agent']} {USER_AGENT_SUFFIX}"
                    ctx = browser.new_context(**dev)
                    ctx.add_init_script(TIMING_INIT)
                page = ctx.new_page()
                try:
                    resp = _goto(page, url)
                except PWError as e:
                    raise PageLoadFailed(f"could not load page: {str(e).splitlines()[0]}") from e
                if resp is None or resp.status >= 400:
                    raise PageLoadFailed(f"page returned HTTP {resp.status if resp else 'no response'}")
                data = page.evaluate(BLOCKS_JS, "D" if vp == "desktop" else "M")
                if CHALLENGE.search(data["title"]) or CHALLENGE.search(data["bodyText"][:1500]):
                    raise Blocked("bot challenge detected — cro-lens does not bypass bot protection")
                if data["hasPassword"] and len(data["blocks"]) < 25:
                    raise Blocked("login wall detected — only public pages can be analysed")
                c = _dismiss_consent(page)
                if vp == "desktop":
                    consent = c
                    status, final_url, title = resp.status, page.url, data["title"]
                page.screenshot(path=str(out / f"{vp}_fold.png"))
                _settle_lazy(page)
                data = page.evaluate(BLOCKS_JS, "D" if vp == "desktop" else "M")
                page.screenshot(path=str(out / f"{vp}_full.png"), full_page=True)
                blocks[vp] = [Block(**b) for b in data["blocks"]]
                vmeta[vp] = ViewportMeta(height=data["height"], blocks=len(blocks[vp]))
                if vp == "desktop":
                    html = page.content()
                else:
                    t = page.evaluate(TIMING_JS)
                    speed = Speed(
                        ttfb_ms=t["ttfb"],
                        dcl_ms=t["dcl"],
                        load_ms=t["load"],
                        lcp_ms=t["lcp"],
                        cls=round(t["cls"] or 0, 4),
                        requests=t["requests"],
                        transfer_bytes_min=t["bytes"],
                    )
                ctx.close()
        finally:
            browser.close()
    speed.psi = _psi(url)
    meta = CaptureMeta(
        url=url,
        final_url=final_url,
        status_code=status,
        title=title,
        captured_at=now_iso(),
        consent_banner=consent,
        speed=speed,
        viewports=vmeta,
    )
    for vp, bl in blocks.items():
        (out / f"blocks_{vp}.json").write_text(
            json.dumps([b.model_dump() for b in bl], ensure_ascii=False, indent=1), encoding="utf-8"
        )
    (out / "page.html").write_text(html, encoding="utf-8")
    (out / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    return CaptureResult(meta=meta, blocks=blocks, dir=out, html=html)


def load_capture(cap_dir: Path) -> CaptureResult:
    meta = CaptureMeta.model_validate_json((cap_dir / "meta.json").read_text(encoding="utf-8"))
    blocks = {
        vp: [Block(**b) for b in json.loads((cap_dir / f"blocks_{vp}.json").read_text(encoding="utf-8"))]
        for vp in ("desktop", "mobile")
    }
    html = (cap_dir / "page.html").read_text(encoding="utf-8") if (cap_dir / "page.html").exists() else ""
    return CaptureResult(meta=meta, blocks=blocks, dir=cap_dir, html=html)
