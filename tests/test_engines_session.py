"""Tests: engine choice (ctx.model_override) flows through run_agent in every
launch mode (repl/voice/web all set ctx.model_override), and the web /engine
endpoints persist + apply it.

Run:  python -m pytest tests/test_engines_session.py -q
"""
from __future__ import annotations

import types

import pytest

from bee import paths as bee_paths
from bee.agent import engines
from bee.agent.context import Context
from bee.agent.loop import run_agent
from bee.config import load_config


class RecordingClient:
    def __init__(self):
        self.last_model = None
        self.calls = 0

    def models_list(self):
        return ["stub"]

    def ollama_up(self):
        return True

    def _has_ollama(self):
        return True

    def chat(self, name, messages, tools=None, **kw):
        self.calls += 1
        self.last_model = name
        if self.calls == 1 and name in ("local", "glm-5.2:cloud", "cloud"):
            return {"content": "poem: hum, hum, hum — busy bee", "tool_calls": [],
                    "usage": {"prompt": 5, "completion": 5}}
        return {"content": "done", "tool_calls": [], "usage": {"prompt": 5, "completion": 5}}


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(bee_paths, "WORKSPACE", tmp_path)
    import bee.memory.md as md
    import bee.monitor.metrics as mt
    monkeypatch.setattr(md, "diary_add", lambda *a, **k: None)
    monkeypatch.setattr(mt, "record", lambda *a, **k: None)
    cfg = load_config()
    cfg.rag.auto_context = False
    c = Context(cfg, workspace=tmp_path)
    c.client = RecordingClient()
    c.episodes_on = False
    return c


TASK = "write a one line poem about bees"  # substantive -> routes to a model


def test_no_override_uses_auto_routing(ctx):
    res = run_agent(ctx, TASK)
    assert res.ok
    # hybrid speed tier (cloud_first default): substantive conversational work
    # goes to the fast cloud model, local stays the automatic fallback.
    assert ctx.client.last_model == "cloud"


def test_cloud_first_toggle_selects_local(ctx):
    ctx.cfg.cloud.cloud_first = False
    run_agent(ctx, TASK)
    assert ctx.client.last_model == "local"  # classic local-first hybrid


def test_ctx_model_override_local(ctx):
    ctx.model_override = "local"
    run_agent(ctx, TASK)
    assert ctx.client.last_model == "local"


def test_ctx_model_override_ollama_cloud(ctx):
    ctx.model_override = "glm-5.2:cloud"
    run_agent(ctx, TASK)
    assert ctx.client.last_model in ("glm-5.2:cloud", "cloud")


def test_explicit_prefix_beats_session_override(ctx):
    ctx.model_override = "local"
    res = run_agent(ctx, "cloud: " + TASK)
    assert res.ok
    assert ctx.client.last_model == "cloud"


def test_engine_endpoints_persist_and_apply(tmp_path, monkeypatch):
    monkeypatch.setattr(engines, "settings_file", lambda: tmp_path / "settings.json")
    import bee.webapp as w
    # Phase 1: /engine POST requires the web bearer token — fix it via env.
    monkeypatch.setenv("BEE_WEB_TOKEN", "test-token-engines")
    w.reset_token_for_tests()
    monkeypatch.setattr(w, "CTX", types.SimpleNamespace(model_override=None))
    from fastapi.testclient import TestClient
    client = TestClient(w.app)
    H = {"Authorization": "Bearer test-token-engines"}

    j = client.get("/engine").json()  # read stays open
    assert j["current"] == "hybrid"
    assert {e["name"] for e in j["engines"]} == {"hybrid", "local", "ollama-cloud", "api-cloud"}

    # unauthenticated stateful calls are rejected
    r = client.post("/engine", json={"engine": "local"})
    assert r.status_code == 401
    assert client.get("/face/state").status_code == 401

    fake_ctx = w.CTX
    r = client.post("/engine", json={"engine": "local"}, headers=H)
    assert r.status_code == 200 and r.json()["ok"]
    assert fake_ctx.model_override == "local"
    assert engines.load_engine() == "local"

    r = client.post("/engine", json={"engine": "does-not-exist"}, headers=H)
    assert r.status_code == 400

    r = client.post("/engine", json={"engine": "hybrid"}, headers=H)
    assert r.json()["override"] is None
    assert fake_ctx.model_override is None
