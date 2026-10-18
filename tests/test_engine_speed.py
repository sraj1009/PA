"""Engine speed tier: hybrid cloud-first routing, cloud→local de-escalation,
and Ollama keep_alive (memory release). All LLM calls are stubbed — no network,
no model loading.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from bee.agent.client import LLMClient, LLMError
from bee.agent.context import Context
from bee.agent.loop import run_agent
from bee.config import Config, load_config

TASK = "explain how a rainbow forms in simple words"  # heuristic → local, no cues


def _mk_cfg():
    cfg = Config()
    cfg.cloud.enabled = True
    cfg.cloud.llm = "gemini/test-flash"
    cfg.cloud.api_key = "test-key"
    cfg.router.ml_enabled = False   # deterministic routing under test
    cfg.ollama.keep_alive = "60s"
    cfg.privacy.redact_cloud = False
    cfg.rag.auto_context = False
    return cfg


class StubClient:
    """Records which engine each chat() hit; optionally fails the cloud call."""

    def __init__(self, cfg, fail_cloud: bool = False):
        self.cfg = cfg
        self.calls: list[str] = []
        self.fail_cloud = fail_cloud

    def ollama_up(self):
        return True

    def _has_ollama(self):
        return True

    def chat(self, name, messages, tools=None, on_tool_call=None):
        self.calls.append(name)
        if name == "cloud" and self.fail_cloud:
            raise LLMError("cloud down", "connect", True)
        return {"content": "ok-response", "tool_calls": [],
                "usage": {"prompt": 1, "completion": 1}}


def _ctx(cfg, stub):
    ctx = Context(cfg, workspace=cfg.workspace, name="BEE")
    ctx.client = stub
    return ctx


def test_hybrid_cloud_first_for_conversational():
    cfg = _mk_cfg()
    stub = StubClient(cfg)
    res = run_agent(_ctx(cfg, stub), TASK)
    assert stub.calls == ["cloud"], f"expected cloud-first, got {stub.calls}"
    assert res.model == "cloud"
    assert res.ok


def test_hybrid_respects_explicit_local_hint():
    cfg = _mk_cfg()
    stub = StubClient(cfg)
    run_agent(_ctx(cfg, stub), TASK + ", use local")
    assert stub.calls == ["local"]


def test_hybrid_respects_session_engine_local():
    cfg = _mk_cfg()
    stub = StubClient(cfg)
    run_agent(_ctx(cfg, stub), TASK, model="local")
    assert stub.calls == ["local"]


def test_cloud_first_disabled_keeps_local():
    cfg = _mk_cfg()
    cfg.cloud.cloud_first = False
    stub = StubClient(cfg)
    run_agent(_ctx(cfg, stub), TASK)
    assert stub.calls == ["local"]


def test_cloud_first_skipped_when_cloud_unavailable():
    cfg = _mk_cfg()
    cfg.cloud.enabled = False
    stub = StubClient(cfg)
    run_agent(_ctx(cfg, stub), TASK)
    assert stub.calls == ["local"]


def test_deescalation_when_cloud_fails():
    cfg = _mk_cfg()
    stub = StubClient(cfg, fail_cloud=True)
    res = run_agent(_ctx(cfg, stub), TASK)
    assert stub.calls == ["cloud", "local"], f"expected fallback chain, got {stub.calls}"
    assert res.ok
    assert res.model == "local"


def test_smalltalk_never_hits_engine():
    cfg = _mk_cfg()
    stub = StubClient(cfg)
    res = run_agent(_ctx(cfg, stub), "hi")
    assert stub.calls == []
    assert res.route_source == "deterministic"


# ------------------------------------------------------------------ keep_alive
class _FakeOllamaResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": "hi"}, "prompt_eval_count": 1, "eval_count": 1}


def test_keep_alive_native_ollama(monkeypatch):
    from bee.agent import client as c
    captured: dict = {}

    def fake_post(url, json=None, timeout=None):
        captured["payload"] = json
        return _FakeOllamaResp()

    monkeypatch.setattr(c.httpx, "post", fake_post)
    cfg = _mk_cfg()
    info = cfg.get_llm("local")
    out = LLMClient(cfg)._native_ollama(info, [{"role": "user", "content": "hi"}], None, None)
    assert out["content"] == "hi"
    assert captured["payload"]["keep_alive"] == "60s"
    # num_ctx pinning (VRAM saver) must stay intact
    assert captured["payload"]["options"]["num_ctx"] == 8192


def test_keep_alive_litellm_path(monkeypatch):
    from bee.agent import client as c
    captured: dict = {}
    fake_msg = SimpleNamespace(content="hi", tool_calls=None)
    fake_resp = SimpleNamespace(choices=[SimpleNamespace(message=fake_msg)], usage=None)

    def fake_completion(**kw):
        captured["kw"] = kw
        return fake_resp

    monkeypatch.setattr(c.litellm, "completion", fake_completion)
    cfg = _mk_cfg()
    out = LLMClient(cfg).chat("local", [{"role": "user", "content": "hi"}])
    assert out["content"] == "hi"
    assert captured["kw"].get("extra_body", {}).get("keep_alive") == "60s"


def test_keep_alive_native_embedding(monkeypatch):
    """P1-4: `embed()` carried no keep_alive on either transport, so the
    memory/RAG path left the embedding model on Ollama's 5-minute default —
    measured live 2026-10-18: ~299 s after a bare embed vs ~59 s with
    `keep_alive: 60s` (same species as A58, on the serving path)."""
    from bee.agent import client as c
    captured: dict = {}

    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"embedding": [1.0]}

    def fake_post(url, json=None, timeout=None):
        captured["payload"] = json
        return _R()

    monkeypatch.setattr(c, "HAS_LITELLM", False)   # force the native loop
    monkeypatch.setattr(c.httpx, "post", fake_post)
    monkeypatch.setattr(c.LLMClient, "_has_ollama", lambda self: True)
    out = LLMClient(_mk_cfg()).embed(["one text"])
    assert out == [[1.0]]
    assert captured["payload"]["keep_alive"] == "60s"
    assert captured["payload"]["prompt"] == "one text"


def test_keep_alive_litellm_embedding(monkeypatch):
    """Same contract on the primary path — and the form is NOT the chat one.
    Measured live (2026-10-18, unload-separated /api/ps, litellm 1.104.0):
    `extra_body` lands as `options.extra_body` and is ignored (cold call ->
    299 s), while a bare `keep_alive` kwarg reaches the body top level
    (~59 s). Pin the bare-kwarg form."""
    from bee.agent import client as c
    captured: dict = {}

    def fake_embedding(**kw):
        captured["kw"] = kw
        return {"data": [{"embedding": [1.0]}]}

    monkeypatch.setattr(c, "HAS_LITELLM", True)
    monkeypatch.setattr(c.litellm, "embedding", fake_embedding)
    monkeypatch.setattr(c.LLMClient, "_has_ollama", lambda self: True)
    out = LLMClient(_mk_cfg()).embed(["one text"])
    assert out == [[1.0]]
    assert captured["kw"].get("keep_alive") == "60s"
    assert "extra_body" not in captured["kw"]   # measured no-op on embeddings
    assert captured["kw"]["model"].startswith("ollama/")


# ------------------------------------------------- local server options (A58)
class _FakeResp:
    """One stand-in that satisfies both call shapes: `chat()` reads
    `.choices[0].message`, `_litellm_stream` iterates chunks reading
    `.choices[0].delta`."""

    def __init__(self, text: str = "hi"):
        self.choices = [SimpleNamespace(
            message=SimpleNamespace(content=text, tool_calls=None),
            delta=SimpleNamespace(content=text, tool_calls=None))]
        self.usage = None

    def __iter__(self):
        yield self


def _capture_litellm(monkeypatch, resp=None):
    """Fake the ONLY external dependency of the primary path, and hand back the
    kwargs it would have sent."""
    from bee.agent import client as c
    captured: dict = {}

    def fake_completion(**kw):
        captured["kw"] = kw
        return resp or _FakeResp()

    monkeypatch.setattr(c.litellm, "completion", fake_completion)
    return captured


def test_num_ctx_reaches_the_primary_litellm_path(monkeypatch):
    """`cfg.ollama.num_ctx` was sent by the native fallbacks (`_native_ollama`,
    `_ollama_stream`) but by NOTHING on the primary path, so in the shipped
    configuration (litellm installed) the local model always ran with Ollama's own
    context default and silently truncated BEE's prompt. Live on this box, same
    13.3k-token prompt: dropped -> 2050 tokens evaluated, honoured -> 13342.

    The form matters and was measured, not guessed: a TOP-LEVEL litellm param maps
    into Ollama's `options`; `extra_body={"num_ctx": …}` arrives as a bare body
    field Ollama ignores (2050), and `extra_body={"options": {…}}` replaces
    litellm's whole options dict, dropping max_tokens (289 tokens generated when
    8 were asked)."""
    captured = _capture_litellm(monkeypatch)
    LLMClient(_mk_cfg()).chat("local", [{"role": "user", "content": "hi"}])
    assert captured["kw"].get("num_ctx") == 8192, list(captured["kw"])
    # keep_alive still rides in extra_body — Ollama DOES accept it at body top level
    assert captured["kw"].get("extra_body", {}).get("keep_alive") == "60s"
    assert "num_ctx" not in captured["kw"].get("extra_body", {}), \
        "num_ctx in extra_body is the form Ollama ignores"


def test_num_ctx_applies_to_the_streaming_path_too(monkeypatch):
    """Same omission, second method: `chat_stream` built its kwargs without
    num_ctx *or* keep_alive, so the voice/`/talk` surface (always streaming) both
    truncated and left the model loaded for Ollama's 5-minute default."""
    captured = _capture_litellm(monkeypatch)
    LLMClient(_mk_cfg()).chat_stream("local", [{"role": "user", "content": "hi"}],
                                     lambda s: None)
    assert captured["kw"].get("num_ctx") == 8192, list(captured["kw"])
    assert captured["kw"].get("extra_body", {}).get("keep_alive") == "60s"


def test_local_only_params_are_never_sent_to_a_cloud_provider(monkeypatch):
    """litellm raises UnsupportedParamsError for a param a provider does not
    implement unless drop_params=True (which BEE does not set) — so num_ctx must
    stay on the local branch or every cloud call breaks."""
    captured = _capture_litellm(monkeypatch)
    cfg = _mk_cfg()
    cfg.cloud.enabled = True
    cfg.cloud.llm = "openai/gpt-4o-mini"
    cfg.cloud.api_key = "test-key"
    LLMClient(cfg).chat("cloud", [{"role": "user", "content": "hi"}])
    assert "num_ctx" not in captured["kw"], list(captured["kw"])
    assert "extra_body" not in captured["kw"], list(captured["kw"])


def test_is_gemini3plus_detection():
    from bee.agent.client import _is_gemini3plus as g
    assert g("gemini/gemini-3.6-flash") is True
    assert g("gemini/gemini-3-flash-preview") is True
    assert g("gemini/gemini-flash-latest") is True
    assert g("gemini/gemini-2.5-flash") is False
    assert g("openai/gpt-4o-mini") is False
    assert g("ollama_chat/qwen3:8b") is False


def test_gemini3plus_omits_temperature(monkeypatch):
    """Gemini 3+: Google deprecates temperature AND warns temp<1.0 degrades
    reasoning / can loop — so BEE must NOT send temperature (let Google use the
    default 1.0). Non-Gemini-3 cloud models keep their configured temperature."""
    from bee.agent import client as c
    captured: dict = {}
    fake_msg = SimpleNamespace(content="hi", tool_calls=None)
    fake_resp = SimpleNamespace(choices=[SimpleNamespace(message=fake_msg)], usage=None)

    def fake_completion(**kw):
        captured["kw"] = kw
        return fake_resp

    monkeypatch.setattr(c.litellm, "completion", fake_completion)

    cfg = Config()
    cfg.cloud.enabled = True
    cfg.cloud.llm = "gemini/gemini-3.6-flash"
    cfg.cloud.api_key = "test-key"
    cfg.privacy.redact_cloud = False
    LLMClient(cfg).chat("cloud", [{"role": "user", "content": "hi"}])
    assert "temperature" not in captured["kw"], list(captured["kw"])

    cfg.cloud.llm = "openai/gpt-4o-mini"
    cfg.cloud.temperature = 0.3
    LLMClient(cfg).chat("cloud", [{"role": "user", "content": "hi"}])
    assert captured["kw"].get("temperature") == 0.3


def test_real_config_defaults():
    cfg = load_config()
    assert cfg.cloud.cloud_first is True
    assert cfg.ollama.keep_alive == "60s"
