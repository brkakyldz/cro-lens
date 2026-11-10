"""Resume a stopped run from its checkpoints, without a second page visit; detect interrupted runs;
fail fast with a clear message when Claude Code is not signed in. Offline: fake provider,
synthetic capture, no browser."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import pytest
from test_web import URL, make_capture

from cro_lens.config import InvalidInput, StepFailed
from cro_lens.llm import claude_code
from cro_lens.llm.claude_code import ClaudeCodeProvider, NotSignedIn, auth_error
from cro_lens.llm.fake import FakeProvider
from cro_lens.llm.provider import Request
from cro_lens.models import Understanding
from cro_lens.pipeline import run as run_mod
from cro_lens.pipeline import state
from cro_lens.pipeline.run import Options, Pipeline


def events(folder: Path) -> list[dict]:
    return state.read_events(folder)


@pytest.fixture
def visits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Stand-ins for robots + capture that count page visits and copy a synthetic capture."""
    src = make_capture(tmp_path / "synthetic")
    n = {"robots": 0, "capture": 0}

    def fake_robots(url: str) -> str:
        n["robots"] += 1
        return "allowed"

    def fake_capture(url: str, dest: Path):
        n["capture"] += 1
        shutil.copytree(src, dest, dirs_exist_ok=True)
        return run_mod.load_capture(dest)

    monkeypatch.setattr(run_mod, "check_robots", fake_robots)
    monkeypatch.setattr(run_mod, "capture", fake_capture)
    monkeypatch.delenv("CRO_LENS_FAKE_FAIL", raising=False)
    return n


def test_resume_continues_from_the_failed_step_without_a_second_visit(
    tmp_path: Path, visits: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "run"
    monkeypatch.setenv("CRO_LENS_FAKE_FAIL", "check")
    with pytest.raises(StepFailed):
        Pipeline(FakeProvider(), Options(model="opus"), out).run(URL, "r1")
    assert not (out / "report.json").exists() and not (out / "heartbeat").exists()
    assert {p.stem for p in (out / "state").glob("*.json")} == {"robots", "capture", "understand", "analyse"}
    assert state.resume_point(out) == "check"

    monkeypatch.delenv("CRO_LENS_FAKE_FAIL")
    seen: list[dict] = []
    pipe, spec, start = Pipeline.for_resume(FakeProvider(), out, on_event=seen.append)
    assert (start, spec.model, spec.url) == ("check", "opus", URL)
    rep = pipe.resume(spec, start)

    assert visits == {"robots": 1, "capture": 1}, "resume visited the page again"
    assert (out / "report.json").exists() and rep.run.model == "opus"
    assert [c.step for c in rep.cost.calls] == ["understand", "analyse", "check", "hypotheses"]
    ran = [e["step"] for e in seen if e["status"] == "started"]
    assert ran == ["check", "hypotheses", "report"], "reused steps must not run again"
    assert seen[0] == {**seen[0], "step": "resume", "status": "done"}
    latest = state.last_status(events(out))
    assert latest["check"]["status"] == "done" and latest["report"]["status"] == "done"
    # same result as an uninterrupted run
    fresh = Pipeline(FakeProvider(), Options(model="opus"), tmp_path / "fresh").run(URL, "r2")
    assert [f.model_dump() for f in rep.findings] == [f.model_dump() for f in fresh.findings]
    assert [e.ice.score for e in rep.experiments] == [e.ice.score for e in fresh.experiments]


def test_reuse_stops_at_the_first_step_that_runs_again(tmp_path: Path, visits: dict[str, int]) -> None:
    out = tmp_path / "run"
    Pipeline(FakeProvider(), Options(), out).run(URL, "r1")
    (out / "report.json").unlink()
    (out / "state" / "analyse.json").unlink()  # analyse must re-run, so check/hypotheses must too
    pipe, spec, start = Pipeline.for_resume(FakeProvider(), out)
    seen: list[str] = []
    pipe.log.on_event = lambda e: seen.append(e["step"]) if e["status"] == "started" else None
    pipe.resume(spec, start)
    assert start == "analyse" and seen == ["analyse", "check", "hypotheses", "report"]


def test_cannot_resume_without_a_capture_or_after_success(tmp_path: Path, visits: dict[str, int]) -> None:
    out = tmp_path / "run"
    Pipeline(FakeProvider(), Options(), out).run(URL, "r1")
    with pytest.raises(InvalidInput, match="already finished"):
        Pipeline.for_resume(FakeProvider(), out)

    no_cap = tmp_path / "no-capture"
    no_cap.mkdir()
    (no_cap / "run.json").write_text(state.RunSpec(url=URL, run_id="x").model_dump_json(), encoding="utf-8")
    (no_cap / "steps.jsonl").write_text(
        json.dumps({"step": "capture", "status": "failed", "detail": "timeout"}) + "\n", encoding="utf-8"
    )
    assert state.resume_point(no_cap) is None
    with pytest.raises(InvalidInput, match="visit the page again"):
        Pipeline.for_resume(FakeProvider(), no_cap)
    with pytest.raises(InvalidInput, match="not a cro-lens run"):
        Pipeline.for_resume(FakeProvider(), tmp_path / "empty-nothing")


def test_legacy_run_without_checkpoints_resumes_from_understand(
    tmp_path: Path, visits: dict[str, int]
) -> None:
    """Runs made before checkpoints existed: capture/ and steps.jsonl only."""
    out = tmp_path / "legacy"
    make_capture(out / "capture")
    lines = [
        {"step": "robots", "status": "done", "t": "2026-11-10T19:30:00+00:00"},
        {"step": "capture", "status": "done", "t": "2026-11-10T19:30:20+00:00"},
        {"step": "understand", "status": "failed", "detail": "understand: Not logged in"},
    ]
    (out / "steps.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    pipe, spec, start = Pipeline.for_resume(FakeProvider(), out)
    assert spec.legacy and spec.url == URL and start == "understand"
    pipe.resume(spec, start)
    assert visits == {"robots": 0, "capture": 0}
    assert (out / "report.json").exists()
    assert not state.RunSpec.model_validate_json((out / "run.json").read_text(encoding="utf-8")).legacy


def test_ctrl_c_leaves_a_failed_step_not_a_running_ghost(
    tmp_path: Path, visits: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self, cap, u):
        raise KeyboardInterrupt

    monkeypatch.setattr(Pipeline, "analyse", boom)
    out = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        Pipeline(FakeProvider(), Options(), out).run(URL, "r1")
    latest = state.last_status(events(out))
    assert latest["analyse"]["status"] == "failed" and "interrupted" in latest["analyse"]["detail"]
    assert not (out / "heartbeat").exists()
    assert state.resume_point(out) == "analyse"


# ---------------------------------------------------------------- review 6f08904 regressions
def _failed_at_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "run"
    monkeypatch.setenv("CRO_LENS_FAKE_FAIL", "check")
    with pytest.raises(StepFailed):
        Pipeline(FakeProvider(), Options(), out).run(URL, "r1")
    monkeypatch.delenv("CRO_LENS_FAKE_FAIL")
    return out


def test_no_second_resume_while_one_is_running(
    tmp_path: Path, visits: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    out = _failed_at_check(tmp_path, monkeypatch)
    (out / state.HEARTBEAT).write_text("x", encoding="utf-8")  # another process is on it
    with pytest.raises(InvalidInput, match="still running"):
        Pipeline.for_resume(FakeProvider(), out)


@pytest.mark.parametrize("damage", ["delete", "corrupt"])
def test_damaged_capture_never_falls_back_to_a_visit(
    tmp_path: Path, visits: dict[str, int], monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    out = _failed_at_check(tmp_path, monkeypatch)
    blocks = out / "capture" / "blocks_desktop.json"
    if damage == "delete":
        blocks.unlink()
    else:
        blocks.write_text("{not json", encoding="utf-8")
    assert state.resume_point(out) is None
    with pytest.raises(InvalidInput, match="visit the page again"):
        Pipeline.for_resume(FakeProvider(), out)
    assert visits == {"robots": 1, "capture": 1}


def test_capture_damaged_after_for_resume_still_does_not_visit(
    tmp_path: Path, visits: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    out = _failed_at_check(tmp_path, monkeypatch)
    pipe, spec, start = Pipeline.for_resume(FakeProvider(), out)
    (out / "capture" / "meta.json").unlink()
    with pytest.raises(InvalidInput, match="missing or damaged"):
        pipe.resume(spec, start)
    assert visits == {"robots": 1, "capture": 1}


def test_model_switch_refused_once_llm_steps_are_saved(
    tmp_path: Path, visits: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    out = _failed_at_check(tmp_path, monkeypatch)
    with pytest.raises(InvalidInput, match="same model"):
        Pipeline.for_resume(FakeProvider(), out, model="opus")
    _, spec, _ = Pipeline.for_resume(FakeProvider(), out, model="sonnet")
    assert spec.model == "sonnet"


def test_reused_steps_supersede_their_stale_failed_events(
    tmp_path: Path, visits: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A step interrupted after its checkpoint but before `done` keeps a failed event; once a
    resume reuses it, that event must no longer make the run look failed."""
    out = tmp_path / "run"
    real = state.save_checkpoint

    def save_then_die(folder, step, result, calls):
        real(folder, step, result, calls)
        if step == "analyse":
            raise KeyboardInterrupt

    monkeypatch.setattr(run_mod, "save_checkpoint", save_then_die)
    with pytest.raises(KeyboardInterrupt):
        Pipeline(FakeProvider(), Options(), out).run(URL, "r1")
    monkeypatch.setattr(run_mod, "save_checkpoint", real)
    assert state.last_status(events(out))["analyse"]["status"] == "failed"
    assert state.resume_point(out) == "check"
    pipe, spec, start = Pipeline.for_resume(FakeProvider(), out)
    pipe.resume(spec, start)
    latest = state.last_status(events(out))
    assert all(e["status"] == "done" for e in latest.values()), latest


def test_heartbeat_liveness(tmp_path: Path) -> None:
    d = tmp_path / "r"
    d.mkdir()
    hb = d / state.HEARTBEAT
    hb.write_text("x", encoding="utf-8")
    assert state.alive(d)
    old = time.time() - state.STALE_S - 5
    os.utime(hb, (old, old))
    assert not state.alive(d), "a heartbeat nobody touches any more means the process is gone"


# ---------------------------------------------------------------- Claude Code sign-in
def test_auth_error_patterns() -> None:
    assert auth_error("Not logged in · Please run /login")
    assert auth_error("Invalid API key · Please run /login")
    # what Claude Code 2.1.318 prints for a revoked token and a bad key (spike 2026-11-11)
    assert auth_error("Failed to authenticate. API Error: 401 Invalid bearer token")
    assert auth_error("Invalid API key · Fix external API key")
    assert not auth_error("schema validation: field required")


def _req() -> Request:
    return Request("understand", "sys", ["hi"], Understanding)


@pytest.fixture(autouse=True)
def no_token_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in claude_code.TOKEN_VARS:
        monkeypatch.delenv(v, raising=False)


def test_not_signed_in_fails_at_once_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def once(self, req):
        calls.append(req.step)
        return {"type": "result", "is_error": True, "result": "Not logged in · Please run /login"}, 0.1

    monkeypatch.setattr(claude_code.shutil, "which", lambda _: "claude")
    monkeypatch.setattr(ClaudeCodeProvider, "_once", once)
    with pytest.raises(NotSignedIn, match="claude auth login") as e:
        ClaudeCodeProvider().complete(_req())
    assert calls == ["understand"], "a sign-in error must not be retried"
    assert e.value.exit_code == 6


@pytest.mark.parametrize(
    ("stdout", "raises"),
    [
        ('{"loggedIn": false, "authMethod": "none"}', True),
        ('{"loggedIn": true, "authMethod": "claude.ai"}', False),
        ("error: unknown command 'auth'", False),  # older CLI: let the first call decide
    ],
)
def test_preflight(monkeypatch: pytest.MonkeyPatch, stdout: str, raises: bool) -> None:
    class Done:
        def __init__(self, out: str) -> None:
            self.stdout, self.stderr, self.returncode = out, "", 0

    monkeypatch.setattr(claude_code.shutil, "which", lambda _: "claude")
    monkeypatch.setattr(claude_code.subprocess, "run", lambda *a, **k: Done(stdout))
    prov = ClaudeCodeProvider()
    if raises:
        with pytest.raises(NotSignedIn, match="claude auth login"):
            prov.preflight()
    else:
        prov.preflight()


class FakeClaude:
    """Plays `claude auth status --json` and `claude -p` for the credential in the env it gets,
    the way Claude Code 2.1.318 answered in the 2026-11-11 spike: status names the credential
    and calls it signed in without testing it; only the call fails."""

    def __init__(
        self, *, login_works: bool = True, token_works: bool = False, key_works: bool = True
    ) -> None:
        self.login_works, self.token_works, self.key_works = login_works, token_works, key_works
        self.calls: list[tuple[str, str]] = []  # (command, credential)

    def __call__(self, cmd, **kw):
        env = kw["env"]
        cred = (
            "api_key"
            if env.get("ANTHROPIC_API_KEY")
            else "oauth_token"
            if env.get("CLAUDE_CODE_OAUTH_TOKEN")
            else "claude.ai"
        )
        works = {"api_key": self.key_works, "oauth_token": self.token_works, "claude.ai": self.login_works}[
            cred
        ]
        kind = "status" if cmd[1:3] == ["auth", "status"] else "call"
        self.calls.append((kind, cred))
        if kind == "status":
            if cred == "claude.ai" and not self.login_works:
                return Done('{"loggedIn": false, "authMethod": "none"}')
            extra = ', "apiKeySource": "ANTHROPIC_API_KEY"' if cred == "api_key" else ""
            return Done(f'{{"loggedIn": true, "authMethod": "{cred}"{extra}}}')
        if works:
            return Done('{"type": "result", "is_error": false, "result": "ok"}')
        msg = {
            "api_key": "Invalid API key · Fix external API key",
            "oauth_token": "Failed to authenticate. API Error: 401 Invalid bearer token",
            "claude.ai": "Not logged in · Please run /login",
        }[cred]
        return Done(json.dumps({"type": "result", "is_error": True, "result": msg}))


class Done:
    def __init__(self, out: str) -> None:
        self.stdout, self.stderr, self.returncode = out, "", 0


def _provider(monkeypatch: pytest.MonkeyPatch, fake: FakeClaude) -> ClaudeCodeProvider:
    monkeypatch.setattr(claude_code.shutil, "which", lambda _: "claude")
    monkeypatch.setattr(claude_code.subprocess, "run", fake)
    return ClaudeCodeProvider()


def test_login_needs_no_probe_and_is_a_subscription(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeClaude()
    prov = _provider(monkeypatch, fake)
    prov.preflight()
    assert fake.calls == [("status", "claude.ai")], "a plain login is not probed"
    assert prov.billing == "subscription" and prov.notices == []


def test_rejected_token_falls_back_to_a_working_login(monkeypatch: pytest.MonkeyPatch) -> None:
    """`claude auth status` says loggedIn: true for any CLAUDE_CODE_OAUTH_TOKEN; the API says 401.
    The stored `claude auth login` still works, so the run uses it and says so."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "stale")
    fake = FakeClaude(token_works=False, login_works=True)
    prov = _provider(monkeypatch, fake)
    prov.preflight()
    assert fake.calls == [
        ("status", "oauth_token"),
        ("call", "oauth_token"),
        ("status", "claude.ai"),
        ("call", "claude.ai"),
    ]
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in prov.env, "model calls must not send the dead token"
    assert prov.billing == "subscription"
    (n,) = prov.notices
    assert n.code == "token_fallback" and "expired" in n.title and "CLAUDE_CODE_OAUTH_TOKEN" in n.text
    assert "still work" in n.title, "a worked-around token is not an error"
    assert any(
        "SetEnvironmentVariable('CLAUDE_CODE_OAUTH_TOKEN', $null, 'User')" in c["command"] for c in n.commands
    )
    assert any("claude setup-token" in s for s in n.steps) and any("new terminal" in s for s in n.steps)

    # the model calls of the run go out without the token
    seen: list[dict] = []

    def run(cmd, **kw):
        seen.append(kw["env"])
        return Done(json.dumps({"type": "result", "is_error": False, "structured_output": {}, "usage": {}}))

    monkeypatch.setattr(claude_code.subprocess, "run", run)
    with pytest.raises(StepFailed):  # {} is not an Understanding; only the env matters here
        prov.complete(_req())
    assert seen and all("CLAUDE_CODE_OAUTH_TOKEN" not in e for e in seen)


def test_rejected_token_without_a_login_stops_with_both_fixes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "stale")
    prov = _provider(monkeypatch, FakeClaude(token_works=False, login_works=False))
    with pytest.raises(NotSignedIn, match="CLAUDE_CODE_OAUTH_TOKEN.*claude auth login.*claude setup-token"):
        prov.preflight()


def test_working_token_is_used_as_is(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fresh")
    fake = FakeClaude(token_works=True)
    prov = _provider(monkeypatch, fake)
    prov.preflight()
    assert fake.calls == [("status", "oauth_token"), ("call", "oauth_token")]
    assert prov.env.get("CLAUDE_CODE_OAUTH_TOKEN") == "fresh"
    assert prov.billing == "subscription" and prov.notices == []


def test_api_key_is_billed_and_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """ANTHROPIC_API_KEY wins over the token and the login (spike: authMethod api_key with both set)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fresh")
    prov = _provider(monkeypatch, FakeClaude(key_works=True))
    prov.preflight()
    assert prov.billing == "api_key"
    (n,) = prov.notices
    assert n.code == "api_key_billed" and "billed" in n.title
    assert any("ANTHROPIC_API_KEY" in c["command"] for c in n.commands)


def test_rejected_api_key_stops_and_names_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-bad")
    fake = FakeClaude(key_works=False, login_works=True)
    prov = _provider(monkeypatch, fake)
    with pytest.raises(NotSignedIn, match="rejected the key in ANTHROPIC_API_KEY"):
        prov.preflight()
    assert ("status", "claude.ai") not in fake.calls, "a bad key is not silently swapped for the subscription"
