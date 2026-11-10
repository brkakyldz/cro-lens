"""Deterministic offline provider — contract fake@1. No network, zero cost."""

from __future__ import annotations

import os

from pydantic import BaseModel

from cro_lens.config import StepFailed
from cro_lens.llm.provider import Request
from cro_lens.models import PERSONAS, Block, Call

FAKE_BAD_QUOTE = "THIS TEXT IS NOT ON THE PAGE"


def _first(blocks: list[Block], *, tag: str | None = None, role: str | None = None) -> Block | None:
    for b in blocks:
        if (tag and b.tag == tag) or (role and b.role == role):
            return b
    return None


class FakeProvider:
    name = "fake"

    def preflight(self) -> None:
        """`CRO_LENS_FAKE_FAIL=signin` plays a provider with no sign-in (the claude-code message)."""
        if os.environ.get("CRO_LENS_FAKE_FAIL") == "signin":
            from cro_lens.llm.claude_code import LOGIN_HELP, NotSignedIn

            raise NotSignedIn(LOGIN_HELP)

    def complete(self, req: Request) -> tuple[BaseModel, Call]:
        if os.environ.get("CRO_LENS_FAKE_FAIL") == req.step:
            raise StepFailed(f"{req.step}: fake provider asked to fail (CRO_LENS_FAKE_FAIL)")
        data = getattr(self, f"_{req.step}")(req.context)
        call = Call(step=req.step, model="fake", seconds=0.0, input_tokens=0, output_tokens=0, usd=0.0)
        return req.schema.model_validate(data), call

    # -- steps --
    def _understand(self, ctx: dict) -> dict:
        blocks: list[Block] = ctx["blocks"]["desktop"]
        h1 = _first(blocks, tag="h1") or blocks[0]
        given = ctx.get("given") or {}
        aud = given.get("audience")
        trf = given.get("traffic")
        return {
            "audience": {
                "value": aud or "fixture audience",
                "confidence": "low",
                "source": "given" if aud else "inferred",
                "evidence": [h1.id],
            },
            "job_to_be_done": {"value": "fixture job", "confidence": "low", "evidence": [h1.id]},
            "traffic_source": {
                "value": trf or "unknown",
                "confidence": "low",
                "source": "given" if trf else "inferred",
                "evidence": [],
            },
            "awareness_level": {"value": "solution_aware", "confidence": "low", "evidence": [h1.id]},
            "promise": {"value": h1.text, "evidence": [h1.id]},
            "offer": {"value": "unknown", "evidence": []},
            "five_second": {
                "understood": h1.text,
                "clear": True,
                "specific": False,
                "quote": h1.text,
                "evidence": [h1.id],
            },
        }

    def _analyse(self, ctx: dict) -> dict:
        blocks: list[Block] = ctx["blocks"]["desktop"]
        h1 = _first(blocks, tag="h1") or blocks[0]
        cta = _first(blocks, role="cta") or _first(blocks, role="link") or h1

        def ev(b: Block, quote: str | None = None) -> dict:
            return {"block_id": b.id, "viewport": "desktop", "quote": quote if quote is not None else b.text}

        return {
            "lift": [
                {"factor": f, "score": 3, "reason": "fixture", "evidence": [h1.id]}
                for f in ("value_proposition", "relevance", "clarity", "anxiety", "distraction", "urgency")
            ],
            "personas": [
                {
                    "persona": p,
                    "stalls": [{"block_id": h1.id, "why": "fixture"}],
                    "objections": [{"objection": "Is this for me?", "status": "partial"}],
                }
                for p in PERSONAS
            ],
            "findings": [
                {
                    "category": "value_prop_clarity",
                    "kind": "issue",
                    "title": "Headline does not name the outcome",
                    "personas": ["skeptical_first_timer"],
                    "severity": "high",
                    "reasoning": "fixture",
                    "evidence": [ev(h1)],
                },
                {
                    "category": "cta",
                    "kind": "issue",
                    "title": "Primary action is easy to miss",
                    "personas": ["ready_to_buy"],
                    "severity": "medium",
                    "reasoning": "fixture",
                    "evidence": [ev(cta)],
                },
                {
                    "category": "social_proof",
                    "kind": "issue",
                    "title": "Proof is not attributed",
                    "personas": ["risk_averse_evaluator"],
                    "severity": "low",
                    "reasoning": "fixture",
                    "evidence": [ev(h1, FAKE_BAD_QUOTE)],
                },
            ],
            "unverifiable": [
                {
                    "what": "traffic source",
                    "why": "not visible on the page",
                    "assumption": "treated as unknown",
                }
            ],
        }

    def _check(self, ctx: dict) -> dict:
        verdicts = []
        for fid in ctx["finding_ids"]:
            v = {"F1": "kept", "F2": "flagged"}.get(fid, "kept")
            verdicts.append({"finding_id": fid, "verdict": v, "reason": f"fake verdict {v}"})
        return {"verdicts": verdicts}

    def _hypotheses(self, ctx: dict) -> dict:
        exps = [
            {
                "finding_id": fid,
                "hypothesis": f"If we fix {fid}, then sign-ups will rise for first-time visitors, because fixture.",
                "change": {"from": "current", "to": "proposed"},
                "suggested_copy": None,
                "primary_metric": "sign-up rate",
                "guardrail_metric": "bounce rate",
                "feasibility": "ab_ok",
                "impact": 6,
                "impact_rationale": "fixture",
                "ease": 5,
                "ease_rationale": "fixture",
            }
            for fid in ctx["finding_ids"]
        ]
        return {
            "experiments": exps,
            "top3": [{"finding_id": fid, "why": "fixture"} for fid in ctx["finding_ids"][:3]],
            "summary": "Fixture summary produced by the fake provider.",
        }
