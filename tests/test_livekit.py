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


def test_web_livekit_and_face_endpoints():
    from fastapi.testclient import TestClient
    from bee import webapp

    c = TestClient(webapp.app)
    r = c.get("/livekit")
    assert r.status_code == 200 and "Live Voice" in r.text
    r = c.get("/livekit/status")
    assert r.status_code == 200 and r.json()["configured"] is True
    r = c.post("/livekit/token", json={"room": "bee-pa"})
    assert r.status_code == 200 and r.json()["token"].count(".") == 2
    assert r.json()["url"].startswith("wss://")
    r = c.post("/livekit/token", json={"room": "bad room!"})
    assert r.status_code == 400
    r = c.get("/face")
    assert r.status_code == 200 and "BEE" in r.text
    r = c.get("/face/state")
    assert r.status_code == 200 and "state" in r.json()


def test_stt_tts_adapters_construct():
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
