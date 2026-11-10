"""The one place model calls go through (ADR 0001)."""

from __future__ import annotations

import base64
import copy
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel

from cro_lens.models import Call


@dataclass
class Image:
    data: bytes
    media_type: str = "image/jpeg"


@dataclass
class Request:
    step: str
    system: str
    parts: list[str | Image]
    schema: type[BaseModel]
    model: str = "sonnet"
    context: dict[str, Any] = field(default_factory=dict)  # for the fake provider only


class Provider(Protocol):
    name: str

    def complete(self, req: Request) -> tuple[BaseModel, Call]: ...


def content_blocks(parts: list[str | Image]) -> list[dict]:
    out: list[dict] = []
    for p in parts:
        if isinstance(p, Image):
            out.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": p.media_type,
                        "data": base64.b64encode(p.data).decode(),
                    },
                }
            )
        else:
            out.append({"type": "text", "text": p})
    return out


def inline_schema(model: type[BaseModel]) -> dict:
    """JSON schema with $refs inlined and no titles — the shape every structured-output route accepts."""
    schema = model.model_json_schema(by_alias=True)
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            return {k: walk(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


def preflight(p: Provider) -> None:
    """Raise a CroLensError when the provider cannot work at all (e.g. Claude Code not signed in).

    Called before a run creates its folder or visits the page, so a missing sign-in costs nothing."""
    check = getattr(p, "preflight", None)
    if callable(check):
        check()


def notices(p: Provider) -> list:
    """What the user should read before a run starts (set by preflight): an API key that bills
    every call, a rejected token cro-lens worked around."""
    return list(getattr(p, "notices", None) or [])


def billing(p: Provider) -> str | None:
    """Who pays for the calls: `subscription`, `api_key`, or None when not known (fake, old CLI)."""
    return getattr(p, "billing", None)


def get_provider(name: str) -> Provider:
    if name == "fake":
        from cro_lens.llm.fake import FakeProvider

        return FakeProvider()
    if name == "claude-code":
        from cro_lens.llm.claude_code import ClaudeCodeProvider

        return ClaudeCodeProvider()
    raise ValueError(f"unknown provider: {name} (available: claude-code, fake)")
