"""Item 10 — LiveKit state bridge: agent -> web UI over loopback HTTP.

The temp-JSON file bridge is gone. This test verifies BOTH halves with real
mechanics:
  * webapp half: POST /livekit/state (bearer auth) -> in-memory snapshot ->
    GET /face/state reflects it (with age_s), 401 without a token;
  * agent half: bee.livekit.state.set_state actually POSTs to a live local
    HTTP server with the bearer token, and a downed web UI never raises
    (best-effort — the live call must not break).
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bee import webapp
from bee.livekit import state as lk_state


# ------------------------------------------------------------- webapp half
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(webapp, "_TOKEN", "test-token")
    # start from a clean in-memory snapshot
    with webapp._LK_LOCK:
        webapp._LK_STATE.update({"state": "idle", "last_user": "", "last_reply": "",
                                 "engine": "", "ts": 0.0, "seq": 0})
    return TestClient(webapp.app)


def test_push_then_poll_reflects_state(client):
    r = client.post("/livekit/state",
                    json={"state": "thinking", "last_user": "what time is it?",
                          "engine": "hybrid", "seq": 3},
                    headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200 and r.json()["ok"]
    got = client.get("/face/state",
                     headers={"Authorization": "Bearer test-token"}).json()
    assert got["state"] == "thinking"
    assert got["last_user"] == "what time is it?"
    assert got["engine"] == "hybrid"
    assert got["seq"] == 3
    assert 0 <= got["age_s"] < 5          # fresh: pushed a moment ago


def test_push_requires_auth(client):
    r = client.post("/livekit/state", json={"state": "speaking"})
    assert r.status_code == 401
    r2 = client.post("/livekit/state", json={"state": "speaking"},
                     headers={"Authorization": "Bearer wrong"})
    assert r2.status_code == 401
    # state must be untouched
    got = client.get("/face/state",
                     headers={"Authorization": "Bearer test-token"}).json()
    assert got["state"] == "idle"


def test_stale_state_reports_age(client):
    with webapp._LK_LOCK:
        webapp._LK_STATE["ts"] = 0.0
    got = client.get("/face/state",
                     headers={"Authorization": "Bearer test-token"}).json()
    assert got["age_s"] is None or got["age_s"] > 0


# ------------------------------------------------------------- agent half
def test_set_state_pushes_to_live_server(monkeypatch):
    captured = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(n)
            captured["path"] = self.path
            captured["auth"] = self.headers.get("authorization")
            captured["body"] = json.loads(body)
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        monkeypatch.setenv("BEE_WEB_PORT", str(port))
        monkeypatch.setenv("BEE_WEB_TOKEN", "agent-token")
        lk_state.reset_for_tests()
        lk_state.set_state("listening", last_user="hey bee", engine="local")
        assert captured["path"] == "/livekit/state"
        assert captured["auth"] == "Bearer agent-token"
        assert captured["body"]["state"] == "listening"
        assert captured["body"]["last_user"] == "hey bee"
        assert captured["body"]["seq"] == 1
        # local (debug) view matches too
        local = lk_state.get_state()
        assert local["state"] == "listening"
        assert 0 <= local["age_s"] < 5
    finally:
        srv.shutdown()
        srv.server_close()


def test_set_state_is_best_effort_when_web_ui_down(monkeypatch):
    # a port nothing listens on — the live call must NOT raise
    monkeypatch.setenv("BEE_WEB_PORT", "1")        # port 1: closed everywhere
    monkeypatch.setenv("BEE_WEB_TOKEN", "x")
    lk_state.reset_for_tests()
    lk_state.set_state("speaking", last_reply="done")
    local = lk_state.get_state()
    assert local["state"] == "speaking"            # kept locally either way


def test_temp_json_bridge_is_gone(monkeypatch):
    """Regression pin: the old temp-dir JSON file must no longer be created."""
    state_file = Path(__import__("tempfile").gettempdir()) / "bee_livekit_state.json"
    try:
        state_file.unlink()          # clean any legacy leftover from old runs
    except FileNotFoundError:
        pass
    monkeypatch.setenv("BEE_WEB_PORT", "1")
    monkeypatch.setenv("BEE_WEB_TOKEN", "x")
    lk_state.reset_for_tests()
    lk_state.set_state("idle")
    assert not state_file.exists()
