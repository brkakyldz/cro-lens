"""Provider over the Claude Code CLI (`claude -p`) on the user's subscription (ADR 0001, spike V-1/V-2)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field

from pydantic import BaseModel, ValidationError

from cro_lens.config import StepFailed
from cro_lens.llm.provider import Request, content_blocks, inline_schema
from cro_lens.models import Call

TIMEOUT_S = 600
TOKEN_VAR, KEY_VAR = "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"
TOKEN_VARS = (TOKEN_VAR, KEY_VAR)
AGAIN = (
    "then open a new terminal and start the audit again — a run that already has its capture "
    "can be resumed instead of re-run. See README → Signing in"
)
LOGIN_HELP = (
    "Claude Code is not signed in. Open a terminal, run `claude auth login` "
    f"(or start `claude` and type /login); {AGAIN}"
)
# What `claude -p` prints when a credential is refused (Claude Code 2.1.318, spike 2026-11-11).
AUTH_ERRORS = (
    "not logged in",
    "please run /login",
    "invalid api key",
    "fix external api key",
    "oauth token has expired",
    "invalid bearer token",
    "failed to authenticate",
    "session has expired",
)


@dataclass(frozen=True)
class Notice:
    """Something the user should know before a run, and how to make it go away (ADR 0007)."""

    code: str
    title: str
    text: str
    steps: list[str] = field(default_factory=list)
    commands: list[dict[str, str]] = field(default_factory=list)  # [{"label", "command"}]

    def __str__(self) -> str:
        return f"{self.title} {self.text}"

    def to_dict(self) -> dict:
        return asdict(self)

    def lines(self) -> list[str]:
        """The notice as plain text, for the CLI."""
        out = [self.title, self.text]
        out += [f"{i}. {s}" for i, s in enumerate(self.steps, 1)]
        out += [f"   {c['label']}: {c['command']}" for c in self.commands]
        return out


def remove_var_commands(var: str) -> list[dict[str, str]]:
    return [
        {
            "label": "Windows (PowerShell)",
            "command": f"[Environment]::SetEnvironmentVariable('{var}', $null, 'User')",
        },
        {
            "label": "macOS / Linux",
            "command": f"delete the `export {var}=…` line from ~/.zshrc or ~/.bashrc, then `unset {var}`",
        },
        {"label": 'Check (should say "authMethod": "claude.ai")', "command": "claude auth status --json"},
    ]


RESTART = (
    "Close every terminal (and this app), open a new terminal and start cro-lens again: "
    "a program that is already running keeps the old variable."
)
MACHINE_WIDE = (
    "Still there afterwards? It is set for the whole computer: run the same command with "
    "'Machine' instead of 'User' in an administrator PowerShell, or delete it in "
    "System Properties → Environment Variables."
)
TOKEN_FALLBACK = Notice(
    code="token_fallback",
    title="Your saved Claude Code token has expired. Audits still work.",
    text=(
        f"This computer has a {TOKEN_VAR} environment variable, and Claude Code no longer "
        "accepts it (it expired or was revoked). cro-lens works around it: each audit leaves the "
        "variable out and uses your normal `claude auth login` sign-in, on your Claude "
        "subscription, so nothing is billed extra. Fixing it saves a few seconds at the start of "
        "every audit and stops other tools that use Claude Code from failing on the dead token."
    ),
    steps=[
        "Remove the variable (unless a server or CI job needs a token): run the command for your system below.",
        RESTART,
        MACHINE_WIDE,
        f"Need a token on purpose? Run `claude setup-token` and put the new value in {TOKEN_VAR} instead.",
    ],
    commands=remove_var_commands(TOKEN_VAR),
)
KEY_BILLED = Notice(
    code="api_key_billed",
    title="Audits will be billed to your Anthropic API key.",
    text=(
        f"{KEY_VAR} is set, and Claude Code uses it before your Claude subscription, so every "
        "model call is charged to that API account (a Sonnet audit is about $0.40). If that is "
        "what you want, nothing needs fixing."
    ),
    steps=[
        "To use your Claude subscription instead, remove the variable with the command for your system below.",
        RESTART,
        "Run `claude auth login` once if you have never signed in.",
    ],
    commands=remove_var_commands(KEY_VAR),
)
# authMethod from `claude auth status --json` → who pays. Anything else (a cloud provider,
# an unknown method) is left unlabelled rather than guessed.
BILLING = {"claude.ai": "subscription", "oauth_token": "subscription", "api_key": "api_key"}


def base_env() -> dict[str, str]:
    return {**os.environ, "PYTHONIOENCODING": "utf-8"}


def login_help(env: dict[str, str] | None = None) -> str:
    """The sign-in message for the credential Claude Code is actually using: a variable in the
    environment wins over `claude auth login`, and `claude auth status` calls it signed in even
    after the API has stopped accepting it."""
    env = base_env() if env is None else env
    if env.get(KEY_VAR):
        return (
            f"Claude Code rejected the key in {KEY_VAR}, which overrides every other sign-in. "
            f"Fix the key, or remove the variable to use `claude auth login` instead; {AGAIN}"
        )
    if env.get(TOKEN_VAR):
        return (
            f"Claude Code rejected the token in {TOKEN_VAR}, and there is no working "
            "`claude auth login` sign-in to use instead. Run `claude auth login`, or put a fresh "
            f"value from `claude setup-token` in the variable; {AGAIN}"
        )
    return LOGIN_HELP


def credential(status: dict) -> str | None:
    """Which credential `claude -p` will use: `api_key`, `oauth_token`, `claude.ai` or None."""
    if status.get("apiKeySource") or status.get("authMethod") == "api_key":
        return "api_key"
    method = status.get("authMethod")
    return method if isinstance(method, str) else None


class NotSignedIn(StepFailed):
    """Claude Code is installed but has no usable sign-in; retrying cannot help."""


def auth_error(text: str) -> bool:
    t = text.lower()
    return any(s in t for s in AUTH_ERRORS)


def build_command(req: Request, exe: str = "claude") -> list[str]:
    return [
        exe,
        "-p",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
        "--json-schema",
        json.dumps(inline_schema(req.schema)),
        "--model",
        req.model,
        "--tools",
        "",
        "--system-prompt",
        req.system,
    ]


def parse_result(stdout: str) -> dict:
    """Return the final `result` event of a stream-json transcript."""
    result = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "result":
            result = ev
    if result is None:
        raise StepFailed("claude -p returned no result event")
    return result


def to_call(step: str, model: str, seconds: float, result: dict) -> Call:
    u = result.get("usage") or {}
    inp = (
        int(u.get("input_tokens") or 0)
        + int(u.get("cache_creation_input_tokens") or 0)
        + int(u.get("cache_read_input_tokens") or 0)
    )
    used_model = next(iter(result.get("modelUsage") or {model: None}))
    return Call(
        step=step,
        model=used_model,
        seconds=round(seconds, 2),
        input_tokens=inp,
        output_tokens=int(u.get("output_tokens") or 0),
        usd=round(float(result.get("total_cost_usd") or 0), 4),
    )


def unescape(node):
    """Models sometimes emit JSON-escaped quotes inside string values (`\\"New\\"`); undo that."""
    if isinstance(node, str):
        return node.replace('\\"', '"')
    if isinstance(node, list):
        return [unescape(x) for x in node]
    if isinstance(node, dict):
        return {k: unescape(v) for k, v in node.items()}
    return node


class ClaudeCodeProvider:
    name = "claude-code"

    def __init__(self) -> None:
        exe = shutil.which("claude")
        if not exe:
            raise StepFailed(
                "Claude Code CLI not found on PATH — install it and sign in (`claude`), "
                "or use --provider fake"
            )
        self.exe = exe
        self.env = base_env()  # what every `claude` subprocess gets; preflight may drop a dead token
        self.billing: str | None = None  # "subscription" | "api_key" | None (not known)
        self.notices: list[Notice] = []  # shown before the run starts (CLI, UI)

    def preflight(self) -> None:
        """Fail fast, before any page visit, when Claude Code cannot make a model call, and
        record who pays for the calls it will make.

        `claude auth status --json` answers in well under a second without a model call and
        names the credential (`authMethod`, `apiKeySource`). It calls a variable's credential
        signed in without testing it, so for CLAUDE_CODE_OAUTH_TOKEN and ANTHROPIC_API_KEY one
        tiny haiku call checks it. A rejected token falls back to the `claude auth login`
        sign-in when that one works; a rejected API key stops the run. If the installed CLI
        has no such command or answers in an unknown shape, the run goes ahead and the first
        model call catches a sign-in problem."""
        self.env, self.notices = base_env(), []
        status = self._status(self.env)
        if status is None:
            self.billing = "api_key" if self.env.get(KEY_VAR) else None
            self.notices = [KEY_BILLED] if self.env.get(KEY_VAR) else []
            return
        method = credential(status)
        if method in ("api_key", "oauth_token") and not self._probe(self.env):
            if method == "oauth_token" and self._fall_back_to_login():
                method = "claude.ai"
                self.notices.append(TOKEN_FALLBACK)
            else:
                raise NotSignedIn(login_help(self.env))
        self.billing = BILLING.get(method or "")
        if method == "api_key":
            self.notices.append(KEY_BILLED)

    def _status(self, env: dict[str, str]) -> dict | None:
        """`claude auth status --json`, or None when this CLI cannot answer it."""
        p = self._run([self.exe, "auth", "status", "--json"], timeout=30, env=env)
        if p is None:
            return None
        try:
            data = json.loads(p.stdout or "")
        except json.JSONDecodeError:
            if auth_error((p.stdout or "") + (p.stderr or "")):
                raise NotSignedIn(LOGIN_HELP) from None
            return None
        if not isinstance(data, dict):
            return None
        if data.get("loggedIn") is False:
            raise NotSignedIn(LOGIN_HELP)
        return data

    def _probe(self, env: dict[str, str]) -> bool:
        """One tiny call. False only when the API refused the credential."""
        probe = self._run(
            [self.exe, "-p", "Reply with ok.", "--model", "haiku", "--output-format", "json", "--tools", ""],
            timeout=90,
            env=env,
        )
        return probe is None or not auth_error((probe.stdout or "") + (probe.stderr or ""))

    def _fall_back_to_login(self) -> bool:
        """Drop a rejected CLAUDE_CODE_OAUTH_TOKEN for this run when `claude auth login` works."""
        env = {k: v for k, v in self.env.items() if k != TOKEN_VAR}
        try:
            status = self._status(env)
        except NotSignedIn:
            return False
        if status is None or credential(status) != "claude.ai" or not self._probe(env):
            return False
        self.env = env
        return True

    @staticmethod
    def _run(cmd: list[str], timeout: int, env: dict[str, str]) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

    def _once(self, req: Request) -> tuple[dict, float]:
        msg = {"type": "user", "message": {"role": "user", "content": content_blocks(req.parts)}}
        env = self.env
        t = time.time()
        try:
            p = subprocess.run(
                build_command(req, self.exe),
                input=json.dumps(msg) + "\n",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=TIMEOUT_S,
                env=env,
            )
        except subprocess.TimeoutExpired as e:
            raise StepFailed(f"{req.step}: claude -p timed out after {TIMEOUT_S}s") from e
        try:
            return parse_result(p.stdout or ""), time.time() - t
        except StepFailed:
            if auth_error((p.stdout or "") + (p.stderr or "")):
                raise NotSignedIn(f"{req.step}: {login_help(self.env)}") from None
            raise

    def complete(self, req: Request) -> tuple[BaseModel, Call]:
        last_err = ""
        total_s, calls_usd, tin, tout = 0.0, 0.0, 0, 0
        for _attempt in range(2):
            result, secs = self._once(req)
            c = to_call(req.step, req.model, secs, result)
            total_s += c.seconds
            calls_usd += c.usd
            tin += c.input_tokens
            tout += c.output_tokens
            if result.get("is_error"):
                last_err = str(result.get("result") or result.get("subtype"))[:300]
                if auth_error(last_err):
                    raise NotSignedIn(f"{req.step}: {login_help(self.env)}")
                continue
            data = result.get("structured_output")
            if data is None:
                try:
                    data = json.loads(result.get("result") or "")
                except json.JSONDecodeError:
                    last_err = "no structured output"
                    continue
            try:
                out = req.schema.model_validate(unescape(data))
            except ValidationError as e:
                last_err = f"schema validation: {str(e).splitlines()[0]}"
                continue
            return out, Call(
                step=req.step,
                model=c.model,
                seconds=round(total_s, 2),
                input_tokens=tin,
                output_tokens=tout,
                usd=round(calls_usd, 4),
            )
        raise StepFailed(f"{req.step}: model call failed after retry — {last_err}")
