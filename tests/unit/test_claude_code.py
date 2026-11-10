import json

import pytest

from cro_lens.config import StepFailed
from cro_lens.llm.claude_code import build_command, parse_result, to_call
from cro_lens.llm.provider import Image, Request, content_blocks, inline_schema
from cro_lens.models import AnalysisOut, HypothesesOut, Understanding

STREAM = "\n".join(
    [
        json.dumps({"type": "system", "subtype": "init"}),
        "not json",
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "structured_output": {"a": 1},
                "total_cost_usd": 0.0474,
                "usage": {
                    "input_tokens": 2,
                    "cache_creation_input_tokens": 11556,
                    "cache_read_input_tokens": 10,
                    "output_tokens": 117,
                },
                "modelUsage": {"claude-sonnet-5-5": {}},
            }
        ),
    ]
)


def test_parse_result_and_usage() -> None:
    r = parse_result(STREAM)
    assert r["structured_output"] == {"a": 1}
    c = to_call("analyse", "sonnet", 5.43, r)
    assert (c.input_tokens, c.output_tokens, c.usd, c.model) == (11568, 117, 0.0474, "claude-sonnet-5-5")


def test_parse_result_missing() -> None:
    with pytest.raises(StepFailed):
        parse_result(json.dumps({"type": "assistant"}))


def test_command_has_no_tools_and_schema() -> None:
    cmd = build_command(Request("understand", "sys", ["hi"], Understanding, "opus"), exe="claude")
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--model") + 1] == "opus"
    assert "--bare" not in cmd  # V-1b: bare breaks subscription auth
    json.loads(cmd[cmd.index("--json-schema") + 1])


@pytest.mark.parametrize("model", [Understanding, AnalysisOut, HypothesesOut])
def test_inline_schema_has_no_refs(model) -> None:
    s = json.dumps(inline_schema(model))
    assert "$ref" not in s and "$defs" not in s


def test_hypotheses_schema_uses_from_alias() -> None:
    s = inline_schema(HypothesesOut)
    change = s["properties"]["experiments"]["items"]["properties"]["change"]
    assert set(change["required"]) == {"from", "to"}


def test_content_blocks_images() -> None:
    blocks = content_blocks(["t", Image(b"\x89PNG", "image/png")])
    assert blocks[0] == {"type": "text", "text": "t"}
    assert blocks[1]["source"]["media_type"] == "image/png"


def test_unescape_quotes() -> None:
    from cro_lens.llm.claude_code import unescape

    assert unescape({"s": ['the \\"New Loops\\" link']}) == {"s": ['the "New Loops" link']}
