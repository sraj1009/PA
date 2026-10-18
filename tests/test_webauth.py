"""Web auth (Phase 1 / critical C1): stateful endpoints require a bearer token.

Covers: 401 without token, 401 with wrong token, 200 with correct token,
query-string token REJECTED (header-only), env-fixed token, open routes stay
open, per-start rotation, and the token-file path.

Run:  python -m pytest tests/test_webauth.py -q
"""
from __future__ import annotations

import time
import types
from contextlib import contextmanager
from pathlib import Path

import pytest

from bee import webapp

FIXED = "unit-test-web-token-1234567890"


@pytest.fixture(autouse=True)
def _reset_token(monkeypatch, tmp_path):
    """Each test gets a known token via env; also isolate the token file."""
    monkeypatch.setenv("BEE_WEB_TOKEN", FIXED)
    monkeypatch.setattr(webapp, "_TOKEN_FILE", tmp_path / "web_token.txt")
    webapp.reset_token_for_tests()
    yield
    webapp.reset_token_for_tests()


def _client():
    from fastapi.testclient import TestClient
    # Stub the app context so /health, /face/state and friends never boot
    # the real agent.
    webapp.CTX = types.SimpleNamespace(
        model_override=None,
        client=types.SimpleNamespace(models_list=lambda: []))
    try:
        return TestClient(webapp.app)
    finally:
        webapp.CTX = None


H = {"Authorization": "Bearer " + FIXED}


def test_no_token_rejected():
    c = _client()
    assert c.post("/chat", json={"task": "hi"}).status_code == 401
    assert c.post("/engine", json={"engine": "local"}).status_code == 401
    assert c.post("/livekit/token", json={"room": "bee-pa"}).status_code == 401
    assert c.get("/face/state").status_code == 401


def test_wrong_token_rejected():
    c = _client()
    bad = {"Authorization": "Bearer totally-wrong-token"}
    assert c.post("/engine", json={"engine": "local"}, headers=bad).status_code == 401


def test_correct_token_accepted():
    c = _client()
    # /chat with a valid token passes auth and hits the app-level 400 (empty task).
    r = c.post("/chat", json={"task": ""}, headers=H)
    assert r.status_code == 400
    assert c.get("/face/state", headers=H).status_code == 200


def test_query_string_token_rejected():
    c = _client()
    # ?token= used to be accepted, leaking the credential into history/logs.
    assert c.get(f"/face/state?token={FIXED}").status_code == 401


def test_open_routes_stay_open(monkeypatch):
    # Hermetic: /health and /livekit/status answer from a bare client + config
    # (no runtime), so stub exactly those two seams.
    import bee.agent.client as client_mod
    import bee.config as config_mod
    monkeypatch.setattr(config_mod, "load_config", lambda *a, **k: _stub_cfg())
    monkeypatch.setattr(client_mod, "LLMClient", _StubLLM)
    c = _client()
    assert c.get("/health").status_code == 200
    assert c.get("/").status_code == 200
    assert c.get("/skills").status_code == 200
    assert c.get("/engine").status_code == 200
    assert c.get("/livekit").status_code == 200
    assert c.get("/livekit/status").status_code == 200


def test_env_token_precedence_and_file_fallback(monkeypatch, tmp_path):
    # No env token -> token is auto-generated and persisted to the file.
    monkeypatch.delenv("BEE_WEB_TOKEN", raising=False)
    webapp.reset_token_for_tests()
    monkeypatch.setattr(webapp, "_TOKEN_FILE", tmp_path / "web_token.txt")
    t1 = webapp._resolve_token()
    assert len(t1) == 32                      # token_hex(16)
    assert webapp._TOKEN_FILE.exists()
    assert webapp._TOKEN_FILE.read_text().strip() == t1
    # A fresh process (fresh module state) mints a NEW token — leaked tokens
    # die with the process that minted them; the file only carries the latest.
    webapp.reset_token_for_tests()
    t2 = webapp._resolve_token()
    assert t2 != t1 and len(t2) == 32
    # ...and the env override always wins.
    monkeypatch.setenv("BEE_WEB_TOKEN", FIXED)
    webapp.reset_token_for_tests()
    assert webapp._resolve_token() == FIXED


def test_token_is_never_printed_or_logged():
    # The auth failure response must not echo the real token.
    c = _client()
    r = c.post("/engine", json={"engine": "local"})
    assert r.status_code == 401
    assert FIXED not in r.text
    assert "Bearer" in r.text  # tells the client the expected scheme


def test_malformed_non_ascii_header_is_401_not_500():
    """hmac.compare_digest raises TypeError on non-ASCII strings, so a header
    carrying accented bytes (which any raw client can send) answered 500
    instead of 401 — a crash-on-garbage in the permission layer."""
    c = _client()
    for value in (b"Bearer t\xc3\xb4k\xc3\xa9n",        # UTF-8 accented
                  b"Bearer caf\xe9",                     # latin-1
                  b"Bearer \xe4\xb8\xad\xe6\x96\x87"):   # CJK
        r = c.get("/face/state", headers=[("authorization", value)])
        assert r.status_code == 401, f"{value!r} -> {r.status_code}"


# ------------------------------------------------------------------ clients
# Server-side 401s were covered; the bug that shipped anyway was the FACE PAGE
# itself: it polled the gated /face/state with no Authorization header and
# swallowed the 401 in an empty catch, so the visualizer sat on "idle" forever.
def _page(name: str) -> str:
    return (Path(webapp.__file__).parent / "web" / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("page,gated", [
    ("face.html", "/face/state"),
    ("livekit.html", "/livekit/token"),
    ("index.html", "/chat"),
])
def test_every_page_that_calls_a_gated_endpoint_sends_the_token(page, gated):
    src = _page(page)
    assert gated in src, f"{page} should call {gated}"
    assert "authHeaders()" in src, f"{page} builds no Authorization header"
    assert "localStorage" in src, f"{page} does not share the token across pages"
    # an empty catch is how this defect hid — failures must be visible.
    # Normalize BOTH sides: comparing a spaced needle against a space-stripped
    # haystack makes an assertion that can never fire.
    assert "catch(e){}" not in src.replace(" ", "").replace("\n", ""), \
        f"{page} swallows a fetch failure in an empty catch"


def test_pages_are_not_cacheable():
    """The kiosk/face tab stays open for days — a cached page silently keeps
    running an old UI (and hid a face fix during verification)."""
    c = _client()
    for page in ("/", "/livekit", "/face"):
        r = c.get(page)
        assert r.status_code == 200
        assert r.headers.get("cache-control") == "no-store", f"{page} is cacheable"


def test_face_page_survives_a_rejected_token():
    src = _page("face.html")
    assert "401" in src, "face.html must handle an expired/wrong token"
    assert "promptToken" in src
    # a cancelled prompt must not re-fire on every 900 ms poll (verified live:
    # without this guard the kiosk window prompts forever)
    assert "promptDeclined" in src


# ------------------------------------------------------------------ /cancel
# The REPL has Ctrl-C/'stop' and the voice engine has barge-in; the web UI had
# no way to stop a running task. These pin the route and, critically, that it
# reaches the kernel (a route that only returns 200 would pass a shape test).
class _Task:
    id = "task_probe_1"


class _StubKernel:
    def __init__(self, active=None):
        self._active_task = active
        self.cancelled = 0

    def cancel(self):
        self.cancelled += 1


@contextmanager
def _client_with_kernel(kernel):
    """A TestClient whose app context carries a specific kernel (restored after)."""
    from fastapi.testclient import TestClient
    prev = webapp.CTX
    webapp.CTX = types.SimpleNamespace(kernel=kernel, model_override=None,
                                       client=types.SimpleNamespace(models_list=lambda: []))
    try:
        yield TestClient(webapp.app)
    finally:
        webapp.CTX = prev


def test_cancel_requires_auth():
    with _client_with_kernel(_StubKernel(_Task())) as c:
        assert c.post("/cancel").status_code == 401
        assert c.post("/cancel", headers=H).status_code == 200


def test_cancel_reaches_the_kernel_when_a_task_is_running():
    k = _StubKernel(_Task())
    with _client_with_kernel(k) as c:
        r = c.post("/cancel", headers=H)
        assert r.status_code == 200
        body = r.json()
        assert body["cancelled"] is True and body["running"] is True
        assert body["task_id"] == "task_probe_1"
        assert k.cancelled == 1, "the route must actually cancel, not just answer"


def test_cancel_is_honest_when_nothing_is_running():
    k = _StubKernel(active=None)
    with _client_with_kernel(k) as c:
        body = c.post("/cancel", headers=H).json()
        assert body["cancelled"] is True and body["running"] is False
        assert "nothing to stop" in body["note"]
        assert k.cancelled == 1          # idempotent: the kernel owns the scope


def test_cancel_without_any_kernel_does_not_claim_success():
    with _client_with_kernel(None) as c:
        body = c.post("/cancel", headers=H).json()
        assert body["cancelled"] is False and body["running"] is False


def test_chat_page_exposes_the_stop_control():
    """A backend route with no user-facing handle is the dead-code defect class
    this repo recorded as A12 — so the button is part of the fix."""
    src = _page("index.html")
    assert 'id="stop"' in src
    assert "/cancel" in src
    assert "setBusy" in src and "finally" in src


# ------------------------------------------------------- live dashboard (M8)
class _StubMetrics:
    """Stands in for the metrics stream so the page reflects events we choose
    rather than whatever this machine happened to record."""

    def __init__(self):
        self.rows = []

    def add(self, event, **kw):
        self.rows.append(dict(ts=time.time(), event=event, ok=True, **kw))

    def load_all(self):
        return list(self.rows)

    def stats(self, window_hours=168.0):
        n = sum(1 for r in self.rows if r.get("event") == "task")
        return {"total_tasks": n, "tasks_ok": n, "success_rate": 1.0,
                "avg_seconds": 0.2, "avg_iters": 1, "escalations": 0,
                "guard_denied": 0, "guard_asks": 0, "redactions": 0,
                "verify_fail": 0}


@pytest.fixture
def dash_env(monkeypatch):
    from bee.monitor import dashboard as dash
    m = _StubMetrics()
    m.add("task", model="bee4b", seconds=0.2)
    monkeypatch.setattr(dash, "metrics", m)        # restored automatically
    c = _client()
    return c, m, dash, time


def test_dashboard_requires_auth(dash_env):
    c, _m, _dash, _t = dash_env
    assert c.get("/dashboard").status_code == 401
    assert c.get("/dashboard", headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = c.get("/dashboard", headers=H)
    assert r.status_code == 200 and "MONITORING" in r.text
    assert c.get(f"/dashboard?token={FIXED}").status_code == 401


def test_dashboard_serves_live_data_not_a_snapshot(dash_env):
    """The whole point of the route: a second request after a new event shows it.
    The old `/dashboard` was a file written when the user asked for it."""
    c, m, _dash, t = dash_env
    first = c.get("/dashboard", headers=H).text
    m.add("task", model="glm-5.2", seconds=0.5)
    m.add("route", source="ml-router")
    second = c.get("/dashboard", headers=H).text
    assert first != second
    assert "bee4b" in first and "glm-5.2" not in first
    assert "glm-5.2" in second and "ml-router" in second
    assert 'http-equiv="refresh"' in second          # and it keeps itself current


def test_dashboard_is_not_cacheable(dash_env):
    c, _m, _dash, _t = dash_env
    r = c.get("/dashboard", headers=H)
    assert r.headers["cache-control"] == "no-store"
    # the snapshot file the CLI writes must NOT auto-reload: it is a point in time
    html = _dash.render()
    assert 'http-equiv="refresh"' not in html


# ------------------------------------------------ full route-table audit (2026-10-18)
# The route table IS the security surface. Every route must be classified
# below: gated -> 401 without a token; open -> static/read-only AND must not
# boot the agent runtime. A route added, removed or re-methoded without being
# classified here fails the audit on purpose.
_FRAMEWORK_DOCS = {("GET", "/openapi.json"), ("GET", "/docs"),
                   ("GET", "/docs/oauth2-redirect"), ("GET", "/redoc")}
_OPEN = _FRAMEWORK_DOCS | {
    ("GET", "/"), ("GET", "/face"), ("GET", "/livekit"),          # static pages
    ("GET", "/health"), ("GET", "/skills"), ("GET", "/engine"),   # status/info
    ("GET", "/livekit/status"),                                   # config probe
}
# Probe payloads: just enough for FastAPI to reach the handler, which calls
# require_auth() before anything else. (/voice needs a file part or FastAPI
# answers 422 during validation, before the handler could 401.)
_GATED_PROBES = {
    ("POST", "/chat"): {"json": {"task": "hi"}},
    ("POST", "/voice"): {"files": {"file": ("a.webm", b"\x00\x01", "audio/webm")}},
    ("POST", "/engine"): {"json": {"engine": "local"}},
    ("POST", "/cancel"): {},
    ("POST", "/permission"): {"json": {"id": "x", "grant": False}},
    ("POST", "/livekit/token"): {"json": {"room": "bee-pa"}},
    ("POST", "/livekit/state"): {"json": {"state": "idle"}},
    ("GET", "/dashboard"): {},
    ("GET", "/face/state"): {},
}


def _registered_routes() -> set:
    from starlette.routing import Route        # APIRoute subclasses Route
    out = set()
    for r in webapp.app.routes:
        if isinstance(r, Route):
            for m in (getattr(r, "methods", None) or []):
                if m in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                    out.add((m, r.path))
    return out


def test_route_table_is_fully_classified():
    actual = _registered_routes()
    classified = _OPEN | set(_GATED_PROBES)
    assert actual == classified, (
        "route table changed — classify the difference as gated (add a 401 "
        "probe in _GATED_PROBES) or open (static/read-only, add to _OPEN). "
        f"Unclassified: {sorted(actual - classified)}; "
        f"stale: {sorted(classified - actual)}")


def test_every_gated_route_rejects_unauthenticated_requests():
    c = _client()
    for (method, path), kw in sorted(_GATED_PROBES.items()):
        r = c.request(method, path, **kw)
        assert r.status_code == 401, f"{method} {path} answered {r.status_code}"


class _StubLLM:
    def __init__(self, cfg):
        pass

    def models_list(self):
        return ["stub-model"]


def _stub_cfg():
    return types.SimpleNamespace(
        workspace=Path("."),
        voice=types.SimpleNamespace(model="base.en", device="cpu",
                                    compute_type="int8"),
        livekit=types.SimpleNamespace(url="wss://lk.test", api_key="k",
                                      api_secret="s", room="bee-pa",
                                      enabled=True))


def test_open_routes_never_boot_the_agent_runtime(monkeypatch):
    """A fresh `uvicorn bee.webapp:app` used to have its WHOLE runtime booted
    (context, kernel, scheduler automation) by the first unauthenticated
    /health; /livekit/status did the same via get_ctx(). Token-less routes
    must stay side-effect-free."""
    import bee.agent.client as client_mod
    import bee.config as config_mod
    monkeypatch.setattr(config_mod, "load_config", lambda *a, **k: _stub_cfg())
    monkeypatch.setattr(client_mod, "LLMClient", _StubLLM)

    def _explode(*a, **kw):
        raise AssertionError("a token-less request booted the agent runtime")

    monkeypatch.setattr(webapp, "get_ctx", _explode)
    webapp.CTX = None
    try:
        from fastapi.testclient import TestClient
        c = TestClient(webapp.app)
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json()["ollama_models"] == ["stub-model"]
        assert c.get("/livekit/status").status_code == 200
        assert webapp.CTX is None, "an open route mutated the global context"
    finally:
        webapp.CTX = None


def test_public_bind_warning_flags_only_non_loopback():
    assert webapp.public_bind_warning("127.0.0.1") == ""
    assert webapp.public_bind_warning("localhost") == ""
    assert webapp.public_bind_warning("::1") == ""
    assert webapp.public_bind_warning("127.0.0.9") == ""
    w = webapp.public_bind_warning("0.0.0.0")
    assert "WARNING" in w and "0.0.0.0" in w and "shell" in w.lower()
    assert "192.168.1.20" in webapp.public_bind_warning("192.168.1.20")


def test_cli_warns_before_a_public_bind(capsys):
    from bee import cli
    cli._warn_if_public_bind("127.0.0.1")
    assert capsys.readouterr().out == ""
    cli._warn_if_public_bind("0.0.0.0")
    out = capsys.readouterr().out
    assert "WARNING" in out and "0.0.0.0" in out
