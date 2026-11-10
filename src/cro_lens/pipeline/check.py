"""Deterministic evidence check (ADR 0002) and the computed ICE confidence (HYP-4)."""

from __future__ import annotations

import re
from collections.abc import Sequence

from rapidfuzz import fuzz

from cro_lens.models import Block, Evidence, FindingIn, LiftScore

QUOTE_MIN_RATIO = 90

CATEGORY_LIFT = {
    "value_prop_clarity": {"value_proposition", "clarity"},
    "specificity": {"value_proposition", "clarity"},
    "message_match": {"relevance"},
    "offer": {"value_proposition", "urgency"},
    "pricing_visibility": {"anxiety", "clarity"},
    "social_proof": {"anxiety"},
    "trust_risk": {"anxiety"},
    "objection_handling": {"anxiety"},
    "cta": {"clarity", "urgency"},
    "friction_forms": {"anxiety", "distraction"},
    "visual_hierarchy_distraction": {"distraction", "clarity"},
    "mobile_speed_access": {"clarity", "distraction"},
}


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip().lower().strip("\"'")


def quote_matches(quote: str, text: str, min_ratio: int = QUOTE_MIN_RATIO) -> bool:
    q, t = norm(quote), norm(text)
    if not q or not t:
        return False
    if q in t:
        return True
    if len(q) > len(t) + 10:
        return False
    return fuzz.partial_ratio(q, t) >= min_ratio


def check_evidence(f: FindingIn, blocks: dict[str, list[Block]]) -> list[Evidence]:
    index = {vp: {b.id: b for b in bl} for vp, bl in blocks.items()}
    out = []
    for e in f.evidence:
        b = index.get(e.viewport, {}).get(e.block_id)
        if b is None:  # id from the other viewport cited with the wrong label
            other = "mobile" if e.viewport == "desktop" else "desktop"
            b = index.get(other, {}).get(e.block_id)
            vp = other if b else e.viewport
        else:
            vp = e.viewport
        valid = b is not None and quote_matches(e.quote, b.text)
        out.append(Evidence(block_id=e.block_id, viewport=vp, quote=e.quote, valid=valid))  # type: ignore[arg-type]
    return out


def confidence(
    verdict: str, category: str, personas: Sequence[str], lift: list[LiftScore]
) -> tuple[int, str]:
    score, why = 3, ["base 3"]
    if verdict == "kept":
        score += 1
        why.append("+1 evidence verified and kept by self-check")
    weak = {s.factor for s in lift if s.score <= 2}
    hit = CATEGORY_LIFT.get(category, set()) & weak
    if hit:
        score += 1
        why.append(f"+1 matches weak LIFT factor ({', '.join(sorted(hit))})")
    if len(set(personas)) >= 2:
        score += 1
        why.append("+1 raised for 2+ personas")
    score = min(score, 6)
    why.append("capped at 6: no traffic data")
    return score, "; ".join(why)
