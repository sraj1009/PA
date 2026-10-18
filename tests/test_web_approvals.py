"""Web interactive approvals + /voice event-loop safety (2026-10-17).

The web server auto-denied every guard 'ask' ("import os", file writes,
capability confirmations), so the same task worked in the REPL and failed in
the browser. Now the /chat SSE stream carries a permission_request card, the
kernel waits (bounded) for POST /permission, and surfaces without a watching
stream (/voice, jobs) stay fail-closed. Also pins /voice keeping the event
loop free: STT and the kernel run in worker threads, so /health and /cancel
stay responsive during a voice task.

Run:  python -m pytest tests/test_web_approvals.py -q
"""
from __future__ import annotations

import queue
import threading
import time
import types

import numpy as np
import pytest
from fastapi.testclient import TestClient

from bee import webapp

TOKEN = "testtokentesttokentesttoken"  # low-entropy by design: the repo
# secret-scan gate (test_secretscan) rejects plausible tokens even in tests/
H = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(webapp, "_TOKEN", TOKEN)
    return TestClient(webapp.app)


def _run_approver(q, out, ctx=None, tool="code_run",
                  args=None, reason="python: import os"):
    def target():
        webapp._TLS.queue = q
        webapp._TLS.ctx = ctx
        try:
            out["v"] = webapp._web_approver(tool, args or {"code": "import os"}, reason)
        finally:
            webapp._TLS.queue = None
            webapp._TLS.ctx = None
    t = threading.Thread(target=target)
    t.start()
    return t


# ------------------------------------------------------------- approver core
def test_approver_fails_closed_without_stream(monkeypatch):
    monkeypatch.setattr(webapp, "APPROVAL_TIMEOUT", 30.0)
    t0 = time.time()
    assert webapp._web_approver("code_run", {"code": "import os"}, "r") is False
    assert time.time() - t0 < 2.0          # immediate — never waits


def test_approve_card_then_grant(client, monkeypatch):
    monkeypatch.setattr(webapp, "APPROVAL_TIMEOUT", 15.0)
    q: queue.Queue = queue.Queue()
    out: dict = {}
    t = _run_approver(q, out)
    card = q.get(timeout=10)
    assert card["type"] == "permission_request"
    assert card["tool"] == "code_run"
    assert card["reason"] == "python: import os"
    assert "import os" in card["preview"]
    r = client.post("/permission", headers=H, json={"id": card["id"], "grant": True})
    assert r.status_code == 200 and r.json() == {"ok": True, "granted": True}
    t.join(timeout=10)
    assert out["v"] is True


def test_deny_via_route(client, monkeypatch):
    monkeypatch.setattr(webapp, "APPROVAL_TIMEOUT", 15.0)
    q: queue.Queue = queue.Queue()
    out: dict = {}
    t = _run_approver(q, out)
    card = q.get(timeout=10)
    r = client.post("/permission", headers=H, json={"id": card["id"], "grant": False})
    assert r.status_code == 200 and r.json()["granted"] is False
    t.join(timeout=10)
    assert out["v"] is False


def test_timeout_denies_and_late_answer_404s(client, monkeypatch):
    monkeypatch.setattr(webapp, "APPROVAL_TIMEOUT", 0.4)
    q: queue.Queue = queue.Queue()
    out: dict = {}
    t = _run_approver(q, out)
    card = q.get(timeout=10)               # the card is still offered...
    t.join(timeout=10)                     # ...but nobody answered in time
    assert out["v"] is False
    r = client.post("/permission", headers=H, json={"id": card["id"], "grant": True})
    assert r.status_code == 404            # one-time id, already expired


def test_permission_route_needs_auth_and_known_id(client):
    assert client.post("/permission", json={"id": "x", "grant": True}).status_code == 401
    r = client.post("/permission", headers=H, json={"id": "nope", "grant": True})
    assert r.status_code == 404


def test_stop_interrupts_pending_approval(client, monkeypatch):
    """Stop (Escape) must not wait out the approval timeout."""
    monkeypatch.setattr(webapp, "APPROVAL_TIMEOUT", 30.0)
    q: queue.Queue = queue.Queue()
    out: dict = {}
    cancel = threading.Event()
    ctx = types.SimpleNamespace(cancel_event=cancel)
    t = _run_approver(q, out, ctx=ctx)
    q.get(timeout=10)                      # approver is now waiting
    cancel.set()                           # kernel.cancel() sets this event
    t.join(timeout=5)
    assert not t.is_alive()
    assert out["v"] is False


# ------------------------------------------- kernel -> card -> grant -> run
def test_gated_call_reaches_the_browser_card_end_to_end(client, tmp_path, monkeypatch):
    """LIVE BUG (2026-10-17): the real server denied `import os` in /chat
    without ever showing the card. This runs a REAL kernel + REAL guard with
    the web approver, watches the SSE queue exactly like /chat's worker
    thread, grants through POST /permission and requires the tool to run.
    The launcher regressions (why the card never fired live) are pinned by
    the two ordering tests below."""
    from bee.kernel import AgentEventKind
    from tests.test_kernel_integration import make_kernel, tc

    monkeypatch.setattr(webapp, "APPROVAL_TIMEOUT", 20.0)
    k, _client, ctx = make_kernel(
        tmp_path,
        [tc("c1", "code_run", {"code": "import os\nprint(os.getcwd())"}),
         "The working directory was printed."],
        approver=webapp._web_approver)

    q: queue.Queue = queue.Queue()
    out: dict = {}

    def runner():
        webapp._TLS.queue = q
        webapp._TLS.ctx = ctx
        try:
            out["r"] = k.run("Use the code_run tool to print the working "
                             "directory (import os first).",
                             session_id="webcard")
        except Exception as e:                      # pragma: no cover
            out["err"] = repr(e)
        finally:
            webapp._TLS.queue = None
            webapp._TLS.ctx = None

    t = threading.Thread(target=runner, name="BeeWebChatTest")
    t.start()
    cards = []
    while t.is_alive():
        try:
            ev = q.get(timeout=0.3)
        except queue.Empty:
            continue
        if isinstance(ev, dict) and ev.get("type") == "permission_request":
            cards.append(ev)
            r = client.post("/permission", headers=H,
                            json={"id": ev["id"], "grant": True})
            assert r.status_code == 200 and r.json()["granted"] is True
    t.join(timeout=30)

    assert "err" not in out, out
    guard_cards = [c for c in cards if c.get("tool") == "code_run"]
    assert guard_cards, f"no permission card for code_run (cards={cards})"
    assert "import os" in guard_cards[0].get("preview", "")
    kinds = [e.kind for e in k.events.log]
    assert AgentEventKind.PERMISSION_GRANTED in kinds
    obs = [o for o in out["r"].task.observations if o.tool == "code_run"]
    assert obs and obs[0].ok, "the granted code_run did not execute"


# ------------------------------------- launcher wiring (live bug 2026-10-17)
def test_get_ctx_registers_interactive_kernel_before_automation(monkeypatch):
    """get_ctx() used to start automation FIRST: start_automation() then
    installed ctx.kernel with an auto-deny approver and get_kernel() silently
    reused it — every gated call in the real server was denied before the
    browser could see a card. (The approver unit tests cannot catch this:
    they never build the kernel through get_ctx.)"""
    from bee import config as bee_config
    from bee import scheduler as bee_scheduler
    from bee.agent import context as bee_context

    calls = []
    sentinel = object()

    def fake_create_context(cfg, guard_mode="cli"):
        calls.append(("create_context", guard_mode))
        return types.SimpleNamespace(kernel=None)

    def fake_get_kernel(ctx):
        calls.append(("get_kernel", ctx))
        return sentinel

    def fake_start_automation(ctx, cfg, kernel=None):
        calls.append(("start_automation", kernel))

    monkeypatch.setattr(webapp, "CTX", None)
    monkeypatch.setattr(bee_config, "load_config", lambda: object())
    monkeypatch.setattr(bee_context, "create_context", fake_create_context)
    monkeypatch.setattr(webapp, "get_kernel", fake_get_kernel)
    monkeypatch.setattr(bee_scheduler, "start_automation", fake_start_automation)

    webapp.get_ctx()

    assert [c[0] for c in calls] == \
        ["create_context", "get_kernel", "start_automation"], calls
    assert calls[0][1] == "unattended"
    assert calls[2][1] is sentinel, \
        "automation must receive the interactive kernel, not create its own"


def test_cli_web_registers_interactive_kernel_before_automation(monkeypatch):
    """`python -m bee web` goes through cli._web — same live bug, second
    launcher: it started automation with no kernel, so the scheduler's
    auto-deny kernel owned every /chat permission ask."""
    import sys
    from bee import cli as bee_cli
    from bee import scheduler as bee_scheduler
    from bee.agent import context as bee_context
    from bee.agent import engines as bee_engines
    from bee.voice import transcribe as bee_transcribe

    calls = []
    sentinel = object()
    fake_ctx = types.SimpleNamespace(kernel=None)

    class _Cfg:
        voice = types.SimpleNamespace(model="base.en", device="cpu",
                                      compute_type="int8")

    def fake_create_context(cfg, guard_mode="cli"):
        calls.append(("create_context", guard_mode))
        return fake_ctx

    def fake_get_kernel(ctx):
        calls.append(("get_kernel", ctx))
        return sentinel

    def fake_start_automation(ctx, cfg, kernel=None):
        calls.append(("start_automation", kernel))

    prewarm_done = threading.Event()
    monkeypatch.setattr(bee_context, "create_context", fake_create_context)
    monkeypatch.setattr(webapp, "get_kernel", fake_get_kernel)
    monkeypatch.setattr(bee_scheduler, "start_automation", fake_start_automation)
    monkeypatch.setattr(bee_engines, "ask_engine", lambda: "hybrid")
    monkeypatch.setattr(bee_engines, "override_for", lambda engine: None)
    monkeypatch.setattr(bee_transcribe, "_load",
                        lambda *a, **k: prewarm_done.set())
    monkeypatch.setattr(webapp, "_resolve_token",
                        lambda: "testtokentesttokentesttoken")
    monkeypatch.setattr(webapp, "CTX", None)
    monkeypatch.setitem(
        sys.modules, "uvicorn",
        types.SimpleNamespace(run=lambda *a, **k: calls.append(("uvicorn.run",))))

    bee_cli._web(_Cfg(), "127.0.0.1", 0)

    assert prewarm_done.wait(10), "STT prewarm thread did not finish in time"
    assert [c[0] for c in calls] == \
        ["create_context", "get_kernel", "start_automation", "uvicorn.run"], calls
    assert calls[0][1] == "unattended"
    assert calls[2][1] is sentinel, \
        "automation must receive the interactive kernel, not create its own"


# --------------------------------------------------------- /voice event loop
class _FakeKernel:
    def run(self, text, session_id="web", **kw):
        res = types.SimpleNamespace(model="stub", escalated=False)
        return types.SimpleNamespace(agent_result=res, output=f"got: {text}", ok=True)


def test_voice_keeps_server_responsive_live(monkeypatch):
    """While /voice is stuck in STT, other routes must still answer — the
    blocking pipeline froze the whole server (so /cancel was dead).

    Runs a REAL uvicorn server: TestClient isolates each request's event
    loop, so an in-process test cannot see the blockage (proven empirically:
    a loop-blocking handler stalls real uvicorn by its full sleep)."""
    import requests
    import uvicorn

    from bee.voice import mic, transcribe

    started = threading.Event()
    release = threading.Event()

    def slow_transcribe(audio, **kw):
        started.set()
        release.wait(timeout=20)
        return "hello bee"

    monkeypatch.setattr(webapp, "_TOKEN", TOKEN)
    monkeypatch.setattr(webapp, "_voice_available", lambda: True)
    monkeypatch.setattr(mic, "read_wav",
                        lambda p, target_rate=16000: (np.zeros(1600, np.float32), target_rate))
    monkeypatch.setattr(transcribe, "transcribe_audio", slow_transcribe)
    ctx = types.SimpleNamespace(
        cfg=types.SimpleNamespace(
            voice=types.SimpleNamespace(model="base.en", device="cpu", compute_type="int8")),
        kernel=_FakeKernel())
    monkeypatch.setattr(webapp, "CTX", ctx)

    server = uvicorn.Server(uvicorn.Config(webapp.app, host="127.0.0.1", port=0,
                                           log_level="critical"))
    sth = threading.Thread(target=server.run, daemon=True)
    sth.start()
    t0 = time.time()
    while not server.started and time.time() - t0 < 15:
        time.sleep(0.05)
    assert server.started, "uvicorn did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    try:
        resp: dict = {}

        def call_voice():
            try:
                resp["r"] = requests.post(
                    f"{base}/voice", headers=H,
                    files={"file": ("q.wav", b"RIFF0000", "audio/wav")}, timeout=30)
            except Exception as e:                      # surfaced below
                resp["err"] = f"{type(e).__name__}: {e}"

        vt = threading.Thread(target=call_voice)
        vt.start()
        # NOTE: diagnose with status_code, never with the Response object —
        # a 401/500 Response is FALSY and `resp.get('r') or ...` hides it.
        if not started.wait(timeout=15):
            got = resp.get("err") or getattr(resp.get("r"), "status_code", None) or "no response"
            raise AssertionError(f"voice request never reached STT ({got})")
        t0 = time.time()
        r = requests.get(f"{base}/engine", timeout=5)
        elapsed = time.time() - t0
        assert r.status_code == 200
        assert elapsed < 3.0, f"server unresponsive for {elapsed:.1f}s during voice STT"
        release.set()
        vt.join(timeout=20)
        assert resp["r"].status_code == 200
        body = resp["r"].json()
        assert body["transcript"] == "hello bee"
        assert body["output"] == "got: hello bee"
    finally:
        release.set()
        server.should_exit = True
        sth.join(timeout=10)
