"""LiveKit live voice: config/.env, room validation, JWT tokens (offline mint),
shared state, web endpoints (/livekit, /face), STT/TTS adapter construction.
No room connections — the agent worker itself needs a live mic + network.
"""
from __future__ import annotations

import base64
import json

import pytest

from bee.config import load_config


def test_livekit_config_loaded():
    cfg = load_config()
    assert cfg.livekit.url.startswith("wss://")
    assert cfg.livekit.api_key.startswith("APIK")
    assert cfg.livekit.api_secret
    assert cfg.livekit.room == "bee-pa"
    assert cfg.livekit.enabled is True


def test_validate_room():
    from bee.livekit.agent import validate_room
    assert validate_room("bee-pa") == "bee-pa"
    with pytest.raises(ValueError):
        validate_room("bad room!")
    with pytest.raises(ValueError):
        validate_room("")
    with pytest.raises(ValueError):
        validate_room("a" * 65)


def test_make_token_grants():
    pytest.importorskip("livekit", reason="MISSING OPTIONAL DEPENDENCY: livekit "
                              "SDK (pip install -r requirements-livekit.txt)")
    from bee.livekit.agent import make_token
    cfg = load_config()
    tok = make_token(cfg, "bee-pa")
    assert tok.count(".") == 2  # JWT
    payload = tok.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    assert claims["sub"] == "bee-web"
    # modern LiveKit SDK nests video grants under top-level "video"
    auth = claims["video"]
    assert auth["room"] == "bee-pa"
    assert auth["roomJoin"] is True
    assert auth["canPublish"] is True
    assert auth["canSubscribe"] is True
    assert claims["exp"] > claims["nbf"]  # valid 2h window


def test_state_roundtrip():
    from bee.livekit import state
    state.set_state("thinking", last_user="hello bee", engine="hybrid")
    s = state.get_state()
    assert s["state"] == "thinking"
    assert s["last_user"] == "hello bee"
    assert s["engine"] == "hybrid"
    assert s["age_s"] is not None
    state.set_state("idle")  # leave clean


def test_web_livekit_and_face_endpoints(monkeypatch):
    pytest.importorskip("livekit", reason="MISSING OPTIONAL DEPENDENCY: livekit "
                              "SDK (pip install -r requirements-livekit.txt)")
    from fastapi.testclient import TestClient
    from bee import webapp
    # Phase 1: stateful endpoints (token mint, face state) require the web
    # bearer token — fix it via env for deterministic tests.
    monkeypatch.setenv("BEE_WEB_TOKEN", "test-token-livekit")
    webapp.reset_token_for_tests()
    H = {"Authorization": "Bearer test-token-livekit"}

    c = TestClient(webapp.app)
    r = c.get("/livekit")
    assert r.status_code == 200 and "Live Voice" in r.text
    r = c.get("/livekit/status")
    assert r.status_code == 200 and r.json()["configured"] is True
    # unauthenticated stateful calls are rejected
    assert c.post("/livekit/token", json={"room": "bee-pa"}).status_code == 401
    assert c.get("/face/state").status_code == 401
    r = c.post("/livekit/token", json={"room": "bee-pa"}, headers=H)
    assert r.status_code == 200 and r.json()["token"].count(".") == 2
    assert r.json()["url"].startswith("wss://")
    r = c.post("/livekit/token", json={"room": "bad room!"}, headers=H)
    assert r.status_code == 400
    r = c.get("/face")
    assert r.status_code == 200 and "BEE" in r.text
    r = c.get("/face/state", headers=H)
    assert r.status_code == 200 and "state" in r.json()


def test_stt_tts_adapters_construct():
    pytest.importorskip("livekit", reason="MISSING OPTIONAL DEPENDENCY: livekit "
                              "SDK (pip install -r requirements-livekit.txt)")
    cfg = load_config()
    from bee.livekit.agent import make_stt, make_tts
    stt = make_stt(cfg)
    assert "faster-whisper" in stt.model
    assert stt.provider == "bee-local"
    tts = make_tts(cfg)
    assert tts.sample_rate == 24000
    assert tts.num_channels == 1
    assert "bee-tts" in tts.model


def test_personalization_in_prompt():
    from bee.agent.context import Context, build_system_prompt
    cfg = load_config()
    ctx = Context(cfg, workspace=cfg.workspace, name="BEE")
    prompt = build_system_prompt(ctx)
    assert cfg.user.name in prompt
    assert cfg.user.timezone in prompt


def test_entrypoint_session_call_matches_installed_sdk():
    """Live-room regression (2026-10-15): a real dispatched job crashed with
    TypeError because entrypoint() passed start_agent= to AgentSession —
    a kwarg the pinned livekit-agents 1.4.6 SDK does not accept. No mocked
    test could reach it, so pin the call shape here at two levels."""
    import ast
    from pathlib import Path
    src = Path("bee/livekit/agent.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    ctor_calls = [n for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "AgentSession"]
    assert ctor_calls, "AgentSession construction disappeared from entrypoint"
    for call in ctor_calls:
        kw = {k.arg for k in call.keywords}
        assert "start_agent" not in kw, \
            "AgentSession(start_agent=...) crashes the pinned SDK — pass the agent to start()"
    # livekit-agents 1.4.6 callback shapes (second live-room crash class):
    # on_enter() / on_user_turn_completed() take no session arg, and the
    # offline BeeSTT must be wrapped in a StreamAdapter with a VAD.
    src_fns = {n.name: n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert [a.arg for a in src_fns["on_enter"].args.args] == ["self"]
    user_turn_args = [a.arg for a in src_fns["on_user_turn_completed"].args.args]
    assert "agent_session" not in user_turn_args, \
        "1.4.6 calls on_user_turn_completed without a session arg"
    assert "StreamAdapter" in src, "BeeSTT must be wrapped in StreamAdapter+VAD"
    # runtime level: the installed SDK must accept the exact call shape
    livekit = pytest.importorskip("livekit", reason="livekit SDK required")
    import inspect
    sig = inspect.signature(livekit.agents.AgentSession.__init__)
    assert "start_agent" not in sig.parameters
    assert "stt" in sig.parameters and "tts" in sig.parameters
    assert "agent" in inspect.signature(livekit.agents.AgentSession.start).parameters


def test_pyttsx3_fallback_produces_audio():
    """Live-room regression (2026-10-15): the greeting failed with 'TTS
    produced no audio' because save_to_file to a BytesIO yields 0 bytes AND
    edge-tts returned 403 in this environment. The offline fallback must
    produce real bytes through a temp file path."""
    import os
    if os.name != "nt":
        pytest.skip("pyttsx3 SAPI probe is Windows-only")
    from bee.livekit.agent import _pyttsx3_wav
    out = _pyttsx3_wav("Hello test one two three", "", 190)
    assert len(out) > 44, "WAV output is empty — fallback is broken"
