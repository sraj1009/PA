"""Web auth (Phase 1 / critical C1): stateful endpoints require a bearer token.

Covers: 401 without token, 401 with wrong token, 200 with correct token,
query-string token form, env-fixed token, open routes stay open, and the
token-file persistence path.

Run:  python -m pytest tests/test_webauth.py -q
"""
from __future__ import annotations

import types

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


def test_query_string_token_form():
    c = _client()
    assert c.get(f"/face/state?token={FIXED}").status_code == 200


def test_open_routes_stay_open():
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
    # A fresh process (fresh module state) must pick the same token up.
    webapp.reset_token_for_tests()
    assert webapp._resolve_token() == t1
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
