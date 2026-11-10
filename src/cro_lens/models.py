"""Data models. The report models are contract report@1; the *Out models are the
JSON schemas the model must fill at each LLM step."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal[
    "value_prop_clarity",
    "specificity",
    "message_match",
    "offer",
    "pricing_visibility",
    "social_proof",
    "trust_risk",
    "objection_handling",
    "cta",
    "friction_forms",
    "visual_hierarchy_distraction",
    "mobile_speed_access",
]
CATEGORIES: tuple[str, ...] = Category.__args__  # type: ignore[attr-defined]

Persona = Literal[
    "skeptical_first_timer",
    "comparison_shopper",
    "ready_to_buy",
    "mobile_skimmer",
    "risk_averse_evaluator",
]
PERSONAS: tuple[str, ...] = Persona.__args__  # type: ignore[attr-defined]
Confidence = Literal["low", "medium", "high"]
Viewport = Literal["desktop", "mobile"]
Role = Literal["heading", "cta", "link", "form_field", "price", "text"]


# ---------- capture ----------
class Block(BaseModel):
    id: str
    tag: str
    role: Role
    text: str
    bbox: list[int]  # x, y, w, h in page coordinates


class Speed(BaseModel):
    source: str = "lab: one local Playwright visit (mobile emulation)"
    ttfb_ms: float | None = None
    dcl_ms: float | None = None
    load_ms: float | None = None
    lcp_ms: float | None = None
    cls: float | None = None
    requests: int | None = None
    transfer_bytes_min: int | None = None
    psi: dict | None = None


class ViewportMeta(BaseModel):
    height: int
    blocks: int
    tiles_sent: int = 0
    truncated: bool = False


class ConsentBanner(BaseModel):
    present: bool = False
    dismissed: bool = False


class CaptureMeta(BaseModel):
    url: str
    final_url: str
    status_code: int
    title: str
    captured_at: str
    consent_banner: ConsentBanner = ConsentBanner()
    speed: Speed = Speed()
    viewports: dict[str, ViewportMeta] = {}


# ---------- LLM step outputs ----------
class Inferred(BaseModel):
    value: str
    confidence: Confidence
    evidence: list[str] = Field(description="block ids this rests on")


class Sourced(Inferred):
    source: Literal["inferred", "given"] = "inferred"


class Plain(BaseModel):
    value: str
    evidence: list[str]


class Awareness(BaseModel):
    value: Literal["unaware", "problem_aware", "solution_aware", "product_aware", "most_aware"]
    confidence: Confidence
    evidence: list[str]


class FiveSecond(BaseModel):
    understood: str = Field(description="what a visitor would take away from the first screen in 5 seconds")
    clear: bool
    specific: bool
    quote: str = Field(description="verbatim headline / subhead copy judged")
    evidence: list[str]


class Understanding(BaseModel):
    audience: Sourced
    job_to_be_done: Inferred
    traffic_source: Sourced
    awareness_level: Awareness
    promise: Plain
    offer: Plain
    five_second: FiveSecond


class LiftScore(BaseModel):
    factor: Literal["value_proposition", "relevance", "clarity", "anxiety", "distraction", "urgency"]
    score: int = Field(ge=1, le=5, description="1 = serious problem, 5 = strong")
    reason: str
    evidence: list[str]


class Stall(BaseModel):
    block_id: str
    why: str


class Objection(BaseModel):
    objection: str
    status: Literal["answered", "partial", "absent"]


class PersonaWalk(BaseModel):
    persona: Persona
    stalls: list[Stall]
    objections: list[Objection]


class EvidenceIn(BaseModel):
    block_id: str
    viewport: Viewport
    quote: str = Field(description="verbatim text copied from that block")


class FindingIn(BaseModel):
    category: Category
    kind: Literal["issue", "absence"]
    title: str
    personas: list[Persona]
    severity: Literal["high", "medium", "low"]
    reasoning: str
    evidence: list[EvidenceIn]


class Unverifiable(BaseModel):
    what: str
    why: str
    assumption: str


class AnalysisOut(BaseModel):
    lift: list[LiftScore]
    personas: list[PersonaWalk]
    findings: list[FindingIn]
    unverifiable: list[Unverifiable]


class Verdict(BaseModel):
    finding_id: str
    verdict: Literal["kept", "flagged", "dropped"]
    reason: str


class CheckOut(BaseModel):
    verdicts: list[Verdict]


class Change(BaseModel):
    from_: str = Field(alias="from")
    to: str

    model_config = {"populate_by_name": True}


class ExperimentIn(BaseModel):
    finding_id: str
    hypothesis: str = Field(
        description="If we change X to Y, then <metric> will <direction> for <segment>, because <evidence>"
    )
    change: Change
    suggested_copy: str | None
    primary_metric: str
    guardrail_metric: str
    feasibility: Literal["ab_ok", "bold_change_only", "qualitative_only"]
    impact: int = Field(ge=1, le=10)
    impact_rationale: str
    ease: int = Field(ge=1, le=10)
    ease_rationale: str


class Top3In(BaseModel):
    finding_id: str
    why: str


class HypothesesOut(BaseModel):
    experiments: list[ExperimentIn]
    top3: list[Top3In]
    summary: str = Field(
        description="3-5 sentences: who the page is for, the biggest problems, what to test first"
    )


# ---------- report@1 ----------
class Evidence(BaseModel):
    block_id: str
    viewport: Viewport
    quote: str
    crop: str | None = None
    valid: bool = False


class Check(BaseModel):
    deterministic: Literal["pass", "fail"]
    verdict: Literal["kept", "flagged", "dropped"]
    reason: str


class Finding(BaseModel):
    id: str
    category: Category
    kind: Literal["issue", "absence"]
    title: str
    personas: list[Persona]
    severity: Literal["high", "medium", "low"]
    reasoning: str
    evidence: list[Evidence]
    check: Check


class ICE(BaseModel):
    impact: int
    confidence: int
    ease: int
    score: float
    rationale: dict[str, str]


class Experiment(BaseModel):
    id: str
    finding_id: str
    hypothesis: str
    change: dict[str, str]
    suggested_copy: str | None
    primary_metric: str
    guardrail_metric: str
    feasibility: Literal["ab_ok", "bold_change_only", "qualitative_only"]
    ice: ICE
    flagged: bool


class Top3(BaseModel):
    experiment_id: str
    why: str


class Call(BaseModel):
    step: str
    model: str
    seconds: float
    input_tokens: int
    output_tokens: int
    usd: float


class Cost(BaseModel):
    total_usd_equivalent: float
    calls: list[Call]


class Given(BaseModel):
    audience: str | None = None
    traffic: str | None = None
    goal: str | None = None


class FeedbackInfo(BaseModel):
    """How many of the user's graded findings the run learned from (eval@2)."""

    enabled: bool = True
    examples: int = 0
    same_site: int = 0


class RunInfo(BaseModel):
    id: str
    url: str
    final_url: str
    started_at: str
    finished_at: str
    provider: str
    model: str
    given: Given
    # who paid for the calls (ADR 0007); None for the fake provider, unknown credentials and
    # reports written before 0.3
    billing: Literal["subscription", "api_key"] | None = None
    feedback: FeedbackInfo | None = None  # null in reports written before 0.3


class Report(BaseModel):
    schema_version: Literal["report@1"] = "report@1"
    run: RunInfo
    capture: CaptureMeta
    understanding: Understanding
    lift: list[LiftScore]
    personas: list[PersonaWalk]
    findings: list[Finding]
    unverifiable: list[Unverifiable]
    experiments: list[Experiment]
    top3: list[Top3]
    summary: str
    cost: Cost
