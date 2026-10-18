"""A60 — BEE can bring up its own local model server.

Nothing used to start Ollama, so a reboot quietly moved every task off the local
model that is the point of the product. `subprocess.Popen` and `httpx.get` are the
only fakes here: the module's own state machine, port binding and gating are driven
for real, and no test launches anything.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time

import pytest

from bee.agent import localserver as ls
from bee.agent.context import Context
from bee.agent.loop import run_agent
from bee.config import Config

BASE = "http://localhost:11434"


class Server:
    """Stand-in for the Ollama HTTP surface, with switchable reachability."""

    def __init__(self, up: bool = False, models=()):
        self.up = up
        self.models = list(models)

    def get(self, url, timeout=None):
        if not self.up:
            raise ConnectionError("connection refused")
        return self._Resp(self.models)

    class _Resp:
        def __init__(self, models):
            self.status_code = 200
            self._models = models

        def json(self):
            return {"models": [{"name": m} for m in self._models]}


class Popen:
    """Records the launch; can flip the fake server up as the child would."""

    def __init__(self, server: Server, flips_up: bool = False):
        self.server = server
        self.flips_up = flips_up
        self.cmd = None
        self.kwargs = {}
        self.calls = 0

    def __call__(self, cmd, **kw):
        self.calls += 1
        self.cmd, self.kwargs = cmd, kw
        if self.flips_up:
            self.server.up = True
        return self


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    """One launch attempt per process is real behaviour — tests must not inherit
    it from each other, and must never touch the real subprocess module."""
    ls.reset()
    yield
    ls.reset()


def _cfg(base=BASE, autostart=True, local=True):
    cfg = Config()
    cfg.ollama.base_url = base
    cfg.ollama.model = "bee4b"
    cfg.ollama.embed_model = "nomic-embed-text"
    cfg.ollama.autostart = autostart
    return cfg


def _wire(monkeypatch, server: Server, popen: Popen):
    monkeypatch.setattr(ls.httpx, "get", server.get)
    monkeypatch.setattr(ls.subprocess, "Popen", popen)
    # Binary discovery (PATH + install dirs) has its own dedicated tests;
    # everything wired here drives the LAUNCH, which must not depend on this
    # runner having Ollama installed (CI has none). Popen is already a double.
    monkeypatch.setattr(ls, "exe_path", lambda: "ollama-stub")


def _launched(popen: Popen, attempts: int = 100) -> None:
    """Wait for the boot thread to reach Popen. Waits on the *launch*, not on the
    outcome: `start_background` then polls the server for up to `wait_s`, which a
    test that never brings a server up must not have to sit through."""
    for _ in range(attempts):
        if popen.calls:
            return
        time.sleep(0.02)
    raise AssertionError("boot thread never launched anything")


def _settled(popen: Popen, attempts: int = 100) -> dict:
    """Wait for the boot thread to record its outcome (it always sets `_attempted`
    in its `finally`, so this only waits for the thread, not for a server)."""
    for _ in range(attempts):
        st = ls.status()
        if st["attempted"]:
            return st
        time.sleep(0.02)
    raise AssertionError(f"boot thread never reported; Popen calls={popen.calls}")


# ------------------------------------------------------------------ the launch
def test_a_dead_server_gets_started(monkeypatch):
    srv = Server(up=False)
    pop = Popen(srv, flips_up=True)
    _wire(monkeypatch, srv, pop)
    ls.start_background(_cfg())
    st = _settled(pop)
    assert st["ready"], st
    assert pop.cmd[-1] == "serve", pop.cmd
    assert pop.kwargs["stdout"] is subprocess.DEVNULL


def test_an_already_running_server_is_left_alone(monkeypatch):
    srv = Server(up=True, models=["bee4b:latest"])
    pop = Popen(srv)
    _wire(monkeypatch, srv, pop)
    assert ls.start_background(_cfg()) is True
    assert pop.calls == 0, "BEE must not start a second server beside a live one"


def test_only_one_attempt_per_process(monkeypatch):
    srv = Server(up=False)
    pop = Popen(srv)
    _wire(monkeypatch, srv, pop)
    cfg = _cfg()
    ls.start_background(cfg, wait_s=0.2)
    _settled(pop)
    first = pop.calls
    ls.start_background(cfg, wait_s=0.2)
    assert pop.calls == first, "a repeatedly failing server must not be re-forked per task"


def test_a_remote_server_is_never_autostarted(monkeypatch):
    srv = Server(up=False)
    pop = Popen(srv)
    _wire(monkeypatch, srv, pop)
    cfg = _cfg(base="https://my-tunnel.example.com:11434")
    assert ls.start_background(cfg) is False
    assert pop.calls == 0, "spawning `ollama serve` for a remote base_url is a lie"


def test_the_autostart_switch_is_not_decorative(monkeypatch):
    srv = Server(up=False)
    pop = Popen(srv)
    _wire(monkeypatch, srv, pop)
    assert ls.start_background(_cfg(autostart=False)) is False
    assert pop.calls == 0


def test_the_child_is_bound_to_the_configured_port(monkeypatch):
    """Without OLLAMA_HOST the server BEE starts would sit on 11434 while BEE polls
    the configured port — the launch would look like a timeout."""
    srv = Server(up=False)
    pop = Popen(srv)
    _wire(monkeypatch, srv, pop)
    cfg = _cfg(base="http://localhost:11455")
    ls.start_background(cfg, wait_s=0.2)
    _launched(pop)
    assert pop.kwargs["env"]["OLLAMA_HOST"] == "127.0.0.1:11455", pop.kwargs["env"]


def test_no_console_window_and_detached_stdio(monkeypatch):
    """A flashing console or a pipe that fills up would make the assistant's boot
    visibly wrong or wedge it; the launch flags are the contract."""
    srv = Server(up=False)
    pop = Popen(srv, flips_up=True)
    _wire(monkeypatch, srv, pop)
    ls.start_background(_cfg())
    _settled(pop)
    if os.name == "nt":
        assert pop.kwargs.get("creationflags") == 0x08000000   # CREATE_NO_WINDOW
    else:
        assert pop.kwargs.get("start_new_session") is True
    assert pop.kwargs["stderr"] is subprocess.DEVNULL


# ------------------------------------------------------------------ discovery
def test_exe_discovery_falls_back_to_the_install_dirs(monkeypatch, tmp_path):
    fake = tmp_path / "Programs" / "Ollama"
    fake.mkdir(parents=True)
    (fake / "ollama.exe").write_text("not a real exe", encoding="utf-8")
    monkeypatch.setattr(ls.shutil, "which", lambda n: None)
    monkeypatch.setattr(os, "environ", {**os.environ, "LOCALAPPDATA": str(tmp_path)})
    assert ls.exe_path() == str(fake / "ollama.exe")


def test_a_missing_binary_is_reported_not_raised(monkeypatch):
    srv = Server(up=False)
    pop = Popen(srv)
    _wire(monkeypatch, srv, pop)
    monkeypatch.setattr(ls, "exe_path", lambda: None)
    ls.start_background(_cfg())
    st = _settled(pop)
    assert not st["ready"] and "not on PATH" in st["error"], st
    assert pop.calls == 0


def test_a_server_without_the_configured_model_is_told_apart_from_a_dead_one(monkeypatch):
    """/api/tags answering is not the question; `bee4b` answering is — otherwise the
    local tier 404s on every call while health says 'ollama up'."""
    srv = Server(up=True, models=["llama3.2:3b", "nomic-embed-text"])
    monkeypatch.setattr(ls.httpx, "get", srv.get)
    assert ls._model_present(_cfg()) is False
    srv.models = ["bee4b:latest"]
    assert ls._model_present(_cfg()) is True


# ------------------------------------------------------------------ the router seam
def test_grace_never_blocks_when_bee_never_launched_anything(monkeypatch):
    """The availability branch runs on every task; an idle-timeout here would be a
    per-task latency bug."""
    srv = Server(up=False)
    monkeypatch.setattr(ls.httpx, "get", srv.get)
    t0 = time.time()
    assert ls.grace(_cfg(), timeout=5.0) is False
    assert time.time() - t0 < 0.2


def test_grace_picks_up_a_launch_that_completes_a_moment_later(monkeypatch):
    srv = Server(up=False)
    monkeypatch.setattr(ls.httpx, "get", srv.get)
    ls._attempted.set()
    threading_release = time.time() + 0.15

    def flip():
        while time.time() < threading_release:
            time.sleep(0.01)
        srv.up = True

    import threading
    threading.Thread(target=flip, daemon=True).start()
    assert ls.grace(_cfg(), timeout=3.0) is True


class _DownClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self.calls: list[str] = []

    def ollama_up(self):
        return False

    def chat(self, name, messages, tools=None, on_tool_call=None):
        self.calls.append(name)
        return {"content": "ok-response", "tool_calls": [],
                "usage": {"prompt": 1, "completion": 1}}


def _ctx(cfg, stub):
    ctx = Context(cfg, workspace=cfg.workspace, name="BEE")
    ctx.client = stub
    return ctx


def _task_cfg():
    cfg = Config()
    cfg.cloud.enabled = True
    cfg.cloud.llm = "gemini/test-flash"
    cfg.cloud.api_key = "test-key"
    cfg.router.ml_enabled = False
    cfg.privacy.redact_cloud = False
    cfg.rag.auto_context = False
    return cfg


def test_the_router_uses_a_server_that_is_on_its_way_up(monkeypatch):
    """Before A60 this path escalated to the cloud (or to deterministic mode) because
    nothing had started the local server yet — the task never reached bee4b."""
    cfg = _task_cfg()
    stub = _DownClient(cfg)
    monkeypatch.setattr(ls, "grace", lambda c, timeout=1.5: True)
    res = run_agent(_ctx(cfg, stub), "explain how a rainbow forms", model="local")
    assert stub.calls == ["local"], stub.calls
    assert res.model == "local"


def test_the_router_still_degrades_when_the_server_stays_down(monkeypatch):
    cfg = _task_cfg()
    stub = _DownClient(cfg)
    monkeypatch.setattr(ls, "grace", lambda c, timeout=1.5: False)
    res = run_agent(_ctx(cfg, stub), "explain how a rainbow forms", model="local")
    assert stub.calls == ["cloud"], f"grace=False must fall through to cloud, got {stub.calls}"
    assert res.model == "cloud" and res.escalated is True


# ------------------------------------------------------------------ the advice
def test_offline_hint_matches_what_actually_happened(monkeypatch):
    srv = Server(up=False)
    pop = Popen(srv)
    _wire(monkeypatch, srv, pop)
    assert "next BEE launch" in ls.offline_hint(_cfg())
    monkeypatch.setattr(ls, "exe_path", lambda: None)
    ls.start_background(_cfg())
    _settled(pop)
    assert "autostart failed" in ls.offline_hint(_cfg())
    assert ls.offline_hint(_cfg(autostart=False)).startswith("autostart is off")


# ------------------------------------------------------------------ A60 history compaction
from bee.agent.context import compact_messages, _token_estimate

def test_token_estimate_is_positive_and_counts_tools():
    tools = [{"type": "function", "function": {"name": "shell", "description": "x" * 100}}]
    msgs = [{"role": "system", "content": "x" * 400}, {"role": "user", "content": "x" * 40}]
    assert _token_estimate(msgs, tools) > _token_estimate(msgs, None)
    assert _token_estimate(msgs, None) > 100

def test_compact_drops_oldest_tool_pairs_to_fit_budget():
    base = [{"role": "system", "content": "system"}, {"role": "user", "content": "task"}]
    history = []
    for i in range(12):
        history.append({"role": "assistant", "content": "", "tool_calls": [{"id": f"c{i}", "function": {"name": "shell", "arguments": "{}"}}]})
        history.append({"role": "tool", "tool_call_id": f"c{i}", "content": "result" * 100})
    messages = base + history
    before = _token_estimate(messages, None)
    compacted, info = compact_messages(messages, None, num_ctx=1024, completion_reserve=0)
    assert info["compacted"] is True
    assert info["removed"] >= 2
    assert _token_estimate(compacted, None) <= 1024
    # system + task are preserved
    assert compacted[0]["role"] == "system" and compacted[1]["role"] == "user"
    # the most recent pair survives
    assert compacted[-1]["role"] == "tool" and compacted[-2].get("role") == "assistant"

def test_compact_is_noop_when_there_is_headroom():
    msgs = [{"role": "system", "content": "hi"}, {"role": "user", "content": "hello"}]
    compacted, info = compact_messages(msgs, None, num_ctx=8192)
    assert compacted is msgs
    assert info["compacted"] is False


def _fat_tools():
    # a fixed floor compaction cannot touch: tool schemas ride on every turn
    return [{"type": "function", "function": {"name": f"t{i}", "description": "d" * 400}}
            for i in range(30)]

def _pairs(n):
    base = [{"role": "system", "content": "s" * 200}, {"role": "user", "content": "t" * 200}]
    hist = []
    for i in range(n):
        hist.append({"role": "assistant", "content": "",
                     "tool_calls": [{"id": f"c{i}", "function": {"name": "shell", "arguments": "{}"}}]})
        hist.append({"role": "tool", "tool_call_id": f"c{i}", "content": "r" * 400})
    return base + hist

def _tool_pairs(msgs):
    return sum(1 for j in range(2, len(msgs) - 1)
               if msgs[j].get("role") == "assistant" and msgs[j].get("tool_calls")
               and msgs[j + 1].get("role") == "tool")

def test_compaction_reports_when_dropping_more_would_still_not_fit():
    # A60c follow-up: the real web_search_tool turn compacted to 8434 est tokens
    # against a 7168 budget and the event claimed nothing about it. It must say so.
    msgs = _pairs(3)
    compacted, info = compact_messages(msgs, _fat_tools(), num_ctx=2048, completion_reserve=512)
    assert info["compacted"] is True
    assert info["removed"] == 2
    assert info["fits"] is False
    assert info["estimate_after"] > info["budget"]
    # the two most recent pairs are kept on purpose
    assert _tool_pairs(compacted) == 2

def test_compaction_reports_when_nothing_is_left_to_drop():
    msgs = _pairs(2)
    compacted, info = compact_messages(msgs, _fat_tools(), num_ctx=2048, completion_reserve=512)
    assert compacted is msgs
    assert info["compacted"] is False
    assert info["fits"] is False
    assert info["estimate"] > info["budget"]

def test_compact_never_drops_system_or_task():
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "task"},
            {"role": "assistant", "content": "a" * 10000}]
    compacted, info = compact_messages(msgs, None, num_ctx=512, completion_reserve=0)
    assert compacted[0]["role"] == "system"
    assert compacted[1]["role"] == "user"
