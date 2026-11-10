"""Paths, environment and errors with their CLI exit codes (contract cli@1)."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

USER_AGENT_SUFFIX = "cro-lens/0.2"
STEPS = ("robots", "capture", "understand", "analyse", "check", "hypotheses", "report")


def home() -> Path:
    return Path(os.environ.get("CRO_LENS_HOME") or Path.home() / ".cro-lens")


def runs_dir() -> Path:
    return home() / "runs"


def provider_name(explicit: str | None = None) -> str:
    return explicit or os.environ.get("CRO_LENS_PROVIDER") or "claude-code"


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_run_id(url: str) -> str:
    host = urlparse(url).hostname or "page"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{re.sub(r'[^a-z0-9]+', '-', host.lower()).strip('-')}"


class CroLensError(Exception):
    exit_code = 1


class InvalidInput(CroLensError):
    exit_code = 2


class RobotsDisallowed(CroLensError):
    exit_code = 3


class PageLoadFailed(CroLensError):
    exit_code = 4


class Blocked(CroLensError):
    exit_code = 5


class StepFailed(CroLensError):
    exit_code = 6


def validate_url(url: str) -> str:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise InvalidInput(f"not an http(s) URL: {url}")
    return url
