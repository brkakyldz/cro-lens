"""Shared fixtures and helpers for the cro-lens held-out acceptance scenarios.

Written from spec.md and contracts/ only (testing@1). The product is driven
exclusively through its CLI, its run folders, $CRO_LENS_HOME (runs/ and
grades.json) and its local web app.

Environment: CRO_LENS_REPO = absolute path of the product checkout.
Every test gets its own CRO_LENS_HOME (which also holds that test's grades)
and working directory; CRO_LENS_PROVIDER=fake always; nothing touches the
internet.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import socket
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest

# --------------------------------------------------------------------------
# Contract constants (exact values named by the contracts)
# --------------------------------------------------------------------------

STEPS = ["robots", "capture", "understand", "analyse", "check", "hypotheses", "report"]
LLM_STEPS = {"understand", "analyse", "check", "hypotheses"}
REPORT_H2 = [
    "Summary",
    "Top 3 experiments",
    "Experiment backlog",
    "Findings",
    "What this page is (understanding)",
    "Assumptions and couldn't verify",
    "Dropped by self-check",
    "Page speed",
    "Run",
]
TAXONOMY = {
    "value_prop_clarity", "specificity", "message_match", "offer",
    "pricing_visibility", "social_proof", "trust_risk", "objection_handling",
    "cta", "friction_forms", "visual_hierarchy_distraction", "mobile_speed_access",
}
PERSONAS = {
    "skeptical_first_timer", "comparison_shopper", "ready_to_buy",
    "mobile_skimmer", "risk_averse_evaluator",
}
LIFT_FACTORS = {"value_proposition", "relevance", "clarity", "anxiety", "distraction", "urgency"}
BLOCK_ROLES = {"heading", "cta", "link", "form_field", "price", "text"}
CONFIDENCE = {"low", "medium", "high"}
AWARENESS = {"unaware", "problem_aware", "solution_aware", "product_aware", "most_aware"}
FEASIBILITY = {"ab_ok", "bold_change_only", "qualitative_only"}

# fixture page facts (fake@1)
SAAS_H1 = "Ship invoices in 30 seconds"
SHOP_H1 = "Merino Trail Sock"
FAKE_BAD_QUOTE = "THIS TEXT IS NOT ON THE PAGE"

CLI_TIMEOUT = 300      # generous: the first `uv run` may sync the environment
RUN_TIMEOUT = 240      # one fake-provider run (< 60 s per testing@1), with margin
UI_START_TIMEOUT = 180

RUN_ID_RE = re.compile(r"^\d{8}-\d{6}-127-0-0-1(-[0-9a-z]+)?$")

# eval@2 / cli@2
GRADES_SCHEMA = "grades@1"
EVAL_KEYS = ("graded", "precision", "evidence validity", "next run learns from")
MAX_EXAMPLES = 12


# --------------------------------------------------------------------------
# Locating and running the product
# --------------------------------------------------------------------------

def product_repo() -> Path:
    value = os.environ.get("CRO_LENS_REPO")
    if not value:
        pytest.fail("CRO_LENS_REPO is not set (absolute path of the cro-lens checkout)", pytrace=False)
    repo = Path(value).resolve()
    if not repo.is_dir():
        pytest.fail(f"CRO_LENS_REPO does not exist: {repo}", pytrace=False)
    return repo


def cli_command() -> list[str]:
    repo = product_repo()
    for candidate in (
        repo / ".venv" / "Scripts" / "cro-lens.exe",
        repo / ".venv" / "Scripts" / "cro-lens",
        repo / ".venv" / "bin" / "cro-lens",
    ):
        if candidate.is_file():
            return [str(candidate)]
    return [shutil.which("uv") or "uv", "run", "--project", str(repo), "cro-lens"]


def base_env(home: Path, extra: dict | None = None) -> dict:
    env = dict(os.environ)
    for key in ("CRO_LENS_FAKE_FAIL", "PAGESPEED_API_KEY", "CRO_LENS_HOME", "CRO_LENS_PROVIDER"):
        env.pop(key, None)
    env.update(
        CRO_LENS_HOME=str(home),
        CRO_LENS_PROVIDER="fake",
        PYTHONIOENCODING="utf-8",
        PYTHONUTF8="1",
        NO_PROXY="127.0.0.1,localhost",
        no_proxy="127.0.0.1,localhost",
    )
    for key, value in (extra or {}).items():
        env[key] = str(value)
    return env


@dataclass
class CliResult:
    args: list
    code: int
    out: str
    err: str

    def dump(self) -> str:
        return (f"exit={self.code} args={self.args}\n--- stdout ---\n{self.out}"
                f"\n--- stderr ---\n{self.err}")

    def error_lines(self) -> list[str]:
        """stderr lines starting `error:` (cli@2, codes 2-6)."""
        return [ln.strip() for ln in self.err.splitlines() if ln.strip().startswith("error:")]


def run_cli(args, env: dict, cwd: Path, timeout: int = CLI_TIMEOUT) -> CliResult:
    args = [str(a) for a in args]
    proc = subprocess.run(
        cli_command() + args, env=env, cwd=str(cwd), stdin=subprocess.DEVNULL,
        capture_output=True, timeout=timeout,
    )
    return CliResult(args, proc.returncode,
                     proc.stdout.decode("utf-8", "replace"),
                     proc.stderr.decode("utf-8", "replace"))


# --------------------------------------------------------------------------
# Output / file helpers
# --------------------------------------------------------------------------

_STEP_LINE = re.compile(r"^\s*([✓✗])\s*([a-z]+)\b(.*)$")


@dataclass
class StepLine:
    mark: str
    name: str
    line: str


def step_lines(stdout: str) -> list[StepLine]:
    found = []
    for line in stdout.splitlines():
        m = _STEP_LINE.match(line)
        if m and m.group(2) in STEPS:
            found.append(StepLine(m.group(1), m.group(2), line.strip()))
    return found


def report_path_from(stdout: str) -> Path:
    m = re.search(r"^report:\s*(.+?)\s*$", stdout, re.M)
    assert m, f"no `report: <path>` line in stdout:\n{stdout}"
    p = Path(m.group(1))
    assert p.is_absolute(), f"report path is not absolute: {p}"
    return p.resolve()


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]


def md_sections(md: str) -> dict[str, str]:
    """H2 heading -> body text."""
    sections: dict[str, str] = {}
    current = None
    for line in md.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m and not line.startswith("###"):
            current = m.group(1)
            sections[current] = ""
        elif current is not None:
            sections[current] += line + "\n"
    return sections


def h2_headings(md: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"^##\s+(.+?)\s*$", md, re.M)]


def png_size(data_or_path) -> tuple[int, int]:
    data = data_or_path if isinstance(data_or_path, (bytes, bytearray)) else Path(data_or_path).read_bytes()[:32]
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG file"
    return struct.unpack(">II", bytes(data[16:24]))


def normalise(text: str) -> str:
    return " ".join(str(text).lower().split())


def files_named(root: Path, name: str) -> list[Path]:
    return [p for p in Path(root).rglob(name) if p.is_file()] if Path(root).exists() else []


def llm_steps_logged(root: Path) -> set[str]:
    """LLM step names that appear in any steps.jsonl under root."""
    seen = set()
    for path in files_named(root, "steps.jsonl"):
        for event in read_jsonl(path):
            if event.get("step") in LLM_STEPS:
                seen.add(event["step"])
    return seen


def poll_until(predicate, timeout: float, what: str, interval: float = 0.25):
    """Poll a contract-named state until it holds or the deadline passes."""
    deadline = time.monotonic() + timeout
    last_exc = None
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except AssertionError as exc:
            last_exc = exc
        time.sleep(interval)  # polling interval, not a fixed wait for a state
    raise AssertionError(f"timed out waiting for {what}" + (f": {last_exc}" if last_exc else ""))


# --------------------------------------------------------------------------
# HTTP + SSE helpers (no proxies, localhost only)
# --------------------------------------------------------------------------

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


@dataclass
class HttpResponse:
    status: int
    headers: dict
    body: bytes

    def json(self):
        return json.loads(self.body.decode("utf-8"))

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")


def http(method: str, url: str, body=None, timeout: float = 30) -> HttpResponse:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            return HttpResponse(resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read())
    except urllib.error.HTTPError as exc:
        return HttpResponse(exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, exc.read())


def read_sse(url: str, timeout: float = RUN_TIMEOUT) -> list[tuple[str, object]]:
    """Read an SSE stream until the `end` event (ui@2); returns [(event, data)]."""
    events: list[tuple[str, object]] = []
    req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
    deadline = time.monotonic() + timeout
    with _OPENER.open(req, timeout=timeout) as resp:
        assert resp.status == 200, f"SSE status {resp.status}"
        ctype = resp.headers.get("Content-Type", "")
        assert "text/event-stream" in ctype, f"SSE content-type is {ctype!r}"
        name, data = None, []
        while time.monotonic() < deadline:
            raw = resp.readline()
            if not raw:
                break
            line = raw.decode("utf-8").rstrip("\r\n")
            if line == "":
                if name is not None or data:
                    payload = "\n".join(data)
                    try:
                        parsed = json.loads(payload)
                    except ValueError:
                        parsed = payload
                    events.append((name or "message", parsed))
                    if name == "end":
                        return events
                name, data = None, []
                continue
            if line.startswith(":"):
                continue
            field_name, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if field_name == "event":
                name = value
            elif field_name == "data":
                data.append(value)
    raise AssertionError(f"SSE stream ended without an `end` event; got {events}")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def lan_ip() -> str | None:
    """A non-loopback IPv4 address of this machine, if any (no packet is sent)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return None
    return None if ip.startswith("127.") or ip == "0.0.0.0" else ip


# --------------------------------------------------------------------------
# Fixture page server (in-process, request log)
# --------------------------------------------------------------------------

@dataclass
class SeenRequest:
    method: str
    path: str
    user_agent: str


class FixtureSite:
    """Static server over $CRO_LENS_REPO/tests/fixtures/pages/ on 127.0.0.1,
    recording every request so tests can see what the product fetched."""

    def __init__(self, root: Path):
        self.root = root
        self._log: list[SeenRequest] = []
        self._lock = threading.Lock()
        site = self

        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, fmt, *args):  # quiet
                pass

            def end_headers(self):
                self.send_header("Cache-Control", "no-store")
                super().end_headers()

            def _seen(self):
                with site._lock:
                    site._log.append(SeenRequest(self.command, urlsplit(self.path).path,
                                                 self.headers.get("User-Agent", "")))

            def do_GET(self):
                self._seen()
                super().do_GET()

            def do_HEAD(self):
                self._seen()
                super().do_HEAD()

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(root)))
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()
        # ready when it accepts a connection (a bare connect logs no request)
        poll_until(lambda: socket.create_connection(("127.0.0.1", self.port), timeout=2).close() or True,
                   15, "fixture server to accept connections")

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def requests(self, path: str | None = None) -> list[SeenRequest]:
        with self._lock:
            log = list(self._log)
        return [r for r in log if path is None or r.path == path]

    def count(self, path: str) -> int:
        return len(self.requests(path))

    def total(self) -> int:
        with self._lock:
            return len(self._log)

    def html_paths(self) -> set[str]:
        return {r.path for r in self.requests() if r.path.endswith(".html")}

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


# --------------------------------------------------------------------------
# UI server
# --------------------------------------------------------------------------

class UiServer:
    def __init__(self, proc: subprocess.Popen, port: int, log_path: Path, log_file):
        self.proc = proc
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self.log_path = log_path
        self._log_file = log_file

    def url(self, path: str = "/") -> str:
        return self.base + path

    def log_text(self) -> str:
        try:
            self._log_file.flush()
        except ValueError:
            pass
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def stop(self) -> None:
        _kill_tree(self.proc)
        try:
            self._log_file.close()
        except ValueError:
            pass


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
    try:
        proc.wait(15)
    except subprocess.TimeoutExpired:
        proc.kill()


# --------------------------------------------------------------------------
# The user's own eval (eval@2): grades, feedback, metrics
# --------------------------------------------------------------------------

def read_grades(home: Path) -> dict:
    """`$CRO_LENS_HOME/grades.json` -> its `grades` map ({} when nothing was ever graded)."""
    path = Path(home) / "grades.json"
    if not path.exists():
        return {}
    data = read_json(path)
    assert data.get("schema_version") == GRADES_SCHEMA, data.get("schema_version")
    return data.get("grades") or {}


def api_run(srv: "UiServer", url: str, **fields) -> str:
    """Start a run with POST /api/runs and follow its SSE stream to a successful `end`."""
    resp = http("POST", srv.url("/api/runs"), {"url": url, **fields})
    assert resp.status == 202, resp.text
    run_id = resp.json()["run_id"]
    events = read_sse(srv.url(f"/api/runs/{run_id}/events"))
    name, end = events[-1]
    assert name == "end" and end["status"] == "done" and end["exit_code"] == 0, events
    return run_id


def put_grade(srv: "UiServer", run_id: str, finding_id: str, verdict: str, note: str | None = None) -> dict:
    """The grade action of ui@2 (PUT /api/runs/{id}/grades/{finding_id})."""
    body = {"verdict": verdict}
    if note is not None:
        body["note"] = note
    resp = http("PUT", srv.url(f"/api/runs/{run_id}/grades/{finding_id}"), body)
    assert resp.status == 200, resp.text
    saved = resp.json()
    assert saved["finding_id"] == finding_id and saved["verdict"] == verdict, saved
    return saved


def eval_lines(stdout: str) -> dict[str, str]:
    """`cro-lens eval` (cli@2): the four metric lines, in order -> {key: value}."""
    found = []
    for line in stdout.splitlines():
        m = re.match(r"^\s*(graded|precision|evidence validity|next run learns from)\s*:\s*(.*?)\s*$", line, re.I)
        if m:
            found.append((m.group(1).lower(), m.group(2)))
    assert [k for k, _ in found] == list(EVAL_KEYS), stdout
    return dict(found)


def percent_of(text: str) -> float:
    """The first `<x>%` in a text, as a 0-1 ratio."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    assert m, f"no percentage in {text!r}"
    return float(m.group(1)) / 100


def evidence_ratio(*reports: dict) -> float:
    """eval@2 evidence validity over the given finished runs' report.json (dropped included)."""
    items = [e for rep in reports for f in rep["findings"] for e in f["evidence"]]
    assert items, "no evidence items"
    return sum(1 for e in items if e["valid"] is True) / len(items)


def run_section(run_dir: Path) -> str:
    """Body of the `## Run` section of a run's report.md."""
    md = (Path(run_dir) / "report.md").read_text(encoding="utf-8")
    sections = md_sections(md)
    assert "Run" in sections, h2_headings(md)
    return sections["Run"]


def learned_from_re(n: int, k: int) -> re.Pattern:
    """report@1 `## Run` line: `Learned from <n> of your graded findings (<k> from this site).`"""
    return re.compile(rf"learned from\s+{n}\s+of your graded findings\s*\(\s*{k}\s+from this site\s*\)", re.I)


# report@1 `## Run` / ui@2 `feedback-used` when the run learned from no grades by choice
FEEDBACK_OFF_RE = re.compile(r"\b(off|disabled)\b|no-feedback|\b(not|n.t) learn", re.I)
# a positive "learned from <n>" claim, n >= 1
LEARNED_SOME_RE = re.compile(r"learned from\s+[1-9]", re.I)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture
def home(tmp_path) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    return path


@pytest.fixture
def workdir(tmp_path) -> Path:
    """cwd for every product process, so nothing a product process writes lands in a repo."""
    path = tmp_path / "work"
    path.mkdir()
    return path


@pytest.fixture
def cli(home, workdir):
    """Run `cro-lens <args>` with this test's env; returns CliResult."""
    def run(*args, env_extra: dict | None = None, timeout: int = CLI_TIMEOUT) -> CliResult:
        return run_cli(args, base_env(home, env_extra), workdir, timeout)
    return run


@pytest.fixture
def site():
    root = product_repo() / "tests" / "fixtures" / "pages"
    assert root.is_dir(), f"fixture pages missing: {root}"
    server = FixtureSite(root)
    yield server
    server.stop()


@pytest.fixture
def ui(home, workdir, tmp_path):
    """Factory: ui(env_extra=None) -> UiServer, ready on /healthz."""
    started: list[UiServer] = []

    def start(env_extra: dict | None = None) -> UiServer:
        port = free_port()
        args = cli_command() + ["ui", "--port", str(port)]
        log_path = tmp_path / f"ui-{port}.log"
        log_file = open(log_path, "wb")
        kwargs = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                  else {"start_new_session": True})
        proc = subprocess.Popen(args, env=base_env(home, env_extra), cwd=str(workdir),
                                stdin=subprocess.DEVNULL, stdout=log_file,
                                stderr=subprocess.STDOUT, **kwargs)
        server = UiServer(proc, port, log_path, log_file)
        started.append(server)

        def healthy():
            if proc.poll() is not None:
                raise RuntimeError(f"`cro-lens ui` exited with {proc.returncode}:\n{server.log_text()}")
            try:
                resp = http("GET", server.url("/healthz"), timeout=5)
            except OSError:
                return False
            return resp.status == 200 and resp.json().get("ok") is True

        poll_until(healthy, UI_START_TIMEOUT, "GET /healthz -> 200 {ok: true}")
        return server

    yield start
    for server in started:
        server.stop()
