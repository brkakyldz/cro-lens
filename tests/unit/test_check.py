from cro_lens.models import Block, EvidenceIn, FindingIn, LiftScore
from cro_lens.pipeline.check import check_evidence, confidence, quote_matches


def _b(i: str, text: str) -> Block:
    return Block(id=i, tag="p", role="text", text=text, bbox=[0, 0, 10, 10])


def test_quote_exact_substring_and_typography() -> None:
    assert quote_matches("ship invoices", "Ship invoices in 30 seconds")
    assert quote_matches("Don’t wait", "Don't  wait for payments")


def test_quote_paraphrase_and_padding_fail() -> None:
    assert not quote_matches("Send bills quickly", "Ship invoices in 30 seconds")
    long = "Ship invoices in 30 seconds and also get a free accountant forever"
    assert not quote_matches(long, "Ship invoices in 30 seconds")


def _f(block_id: str, quote: str, viewport: str = "desktop") -> FindingIn:
    return FindingIn(
        category="cta",
        kind="issue",
        title="t",
        personas=["ready_to_buy"],
        severity="low",
        reasoning="r",
        evidence=[EvidenceIn(block_id=block_id, viewport=viewport, quote=quote)],
    )


def test_check_evidence_wrong_id_or_quote() -> None:
    blocks = {"desktop": [_b("D1", "Start free trial")], "mobile": [_b("M1", "Start free trial")]}
    assert check_evidence(_f("D1", "Start free trial"), blocks)[0].valid
    assert not check_evidence(_f("D9", "Start free trial"), blocks)[0].valid
    assert not check_evidence(_f("D1", "Buy now"), blocks)[0].valid
    # id from the other viewport with the wrong label is resolved
    ev = check_evidence(_f("M1", "Start free trial", "desktop"), blocks)[0]
    assert ev.valid and ev.viewport == "mobile"


def test_confidence_rule_capped() -> None:
    weak = [LiftScore(factor="clarity", score=2, reason="", evidence=[])]
    c, why = confidence("kept", "cta", ["ready_to_buy", "mobile_skimmer"], weak)
    assert c == 6 and "capped" in why
    c, _ = confidence("flagged", "cta", ["ready_to_buy"], [])
    assert c == 3
