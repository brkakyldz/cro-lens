"""Screenshot tiles for the model and evidence crops for the report."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image as PILImage

from cro_lens.llm.provider import Image
from cro_lens.models import Block

# Our own full-page screenshots of long pages at 3x DPR exceed PIL's decompression-bomb guard.
PILImage.MAX_IMAGE_PIXELS = None

CSS_WIDTH = {"desktop": 1440, "mobile": 390}
TILE_CSS_HEIGHT = {"desktop": 1350, "mobile": 844}
TILE_OUT_WIDTH = {"desktop": 1000, "mobile": 560}
MAX_TILES = {"desktop": 6, "mobile": 4}


def _jpeg(im: PILImage.Image, quality: int = 80) -> bytes:
    b = io.BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=quality)
    return b.getvalue()


def scale_of(img: PILImage.Image, viewport: str) -> float:
    return img.width / CSS_WIDTH[viewport]


def tiles(path: Path, viewport: str) -> tuple[list[Image], int, bool]:
    """Return (tiles, css_height_covered, truncated)."""
    im = PILImage.open(path)
    s = scale_of(im, viewport)
    step = int(TILE_CSS_HEIGHT[viewport] * s)
    out: list[Image] = []
    y = 0
    while y < im.height and len(out) < MAX_TILES[viewport]:
        t = im.crop((0, y, im.width, min(y + step, im.height)))
        w = TILE_OUT_WIDTH[viewport]
        t = t.resize((w, max(1, int(t.height * w / t.width))))
        out.append(Image(_jpeg(t)))
        y += step
    covered = int(min(y, im.height) / s)
    return out, covered, y < im.height


def fold(path: Path, viewport: str) -> Image:
    im = PILImage.open(path)
    w = TILE_OUT_WIDTH[viewport]
    return Image(_jpeg(im.resize((w, max(1, int(im.height * w / im.width))))))


def crop_block(full: Path, block: Block, viewport: str, dest: Path, pad: int = 24) -> Path | None:
    im = PILImage.open(full)
    s = scale_of(im, viewport)
    x, y, w, h = block.bbox
    box = (
        max(0, int((x - pad) * s)),
        max(0, int((y - pad) * s)),
        min(im.width, int((x + w + pad) * s)),
        min(im.height, int((y + h + pad) * s)),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        return None
    c = im.crop(box)
    if c.width > 1200:
        c = c.resize((1200, int(c.height * 1200 / c.width)))
    if c.height > 900:
        c = c.crop((0, 0, c.width, 900))
    dest.parent.mkdir(parents=True, exist_ok=True)
    c.convert("RGB").save(dest, "PNG", optimize=True)
    return dest


def image_of(path: Path) -> Image:
    return Image(path.read_bytes(), "image/png")
