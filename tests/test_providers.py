"""Phase 6 — unified LLM provider layer (hermetic contract tests).

Pins: provider detection by model ref, provider-matched key handling
(no cross-provider leaks; explicit-config wins; legacy fallback is
LABELLED), cloud availability comes from the registry (no hard-coded
provider in the loop), and the client's public provider API
(health/capabilities/models_info/ollama_up) without touching the network.
"""
from __future__ import annotations

import pytest

from bee.agent import providers
from bee.agent.providers import (Provider, ProviderConfig, ProviderKind,
                                 cloud_available, env_key_for)
from bee.config import Config


def _cfg(llm: str = "", api_key: str = "", enabled: bool = True,
         ollama_port: int = 1) -> Config:
    c = Config()
    c.cloud.llm = llm
    c.cloud.api_key = api_key
    c.cloud.enabled = enabled
    # dead port -> ollama probes are deterministic (no real Ollama needed)
    c.ollama.base_url = f"http://127.0.0.1:{ollama_port}"
    return c


# ------------------------------------------------------------- detection
def test_kind_for_model_aliases():
    assert providers.kind_for_model("gemini/gemini-3-flash-preview") == ProviderKind.GEMINI
    assert providers.kind_for_model("google/gemini-2.0-flash") == ProviderKind.GOOGLE
    assert providers.kind_for_model("openai/gpt-4o-mini") == ProviderKind.OPENAI
    assert providers.kind_for_model("grok/grok-3") == ProviderKind.XAI
    assert providers.kind_for_model("deepseek/deepseek-chat") == ProviderKind.DEEPSEEK
    assert providers.kind_for_model("openrouter/auto") == ProviderKind.OPENROUTER
    assert providers.kind_for_model("anthropic/claude-3-5") == ProviderKind.ANTHROPIC
    assert providers.kind_for_model("bee4b") is None        # bare = local Ollama
    # litellm's ollama_chat/ prefix is the LOCAL wire notation: no cloud kind,
    # and the registry resolves it to the Ollama provider
    assert providers.kind_for_model("ollama_chat/bee4b") is None
    reg = providers.ProviderRegistry.from_config(_cfg())
    assert reg.for_model("ollama_chat/bee4b").cfg.kind == ProviderKind.OLLAMA


# ------------------------------------------------- key handling (no leaks)
def test_env_key_never_crosses_providers(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-only")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    # a gemini model must NOT be credentialed by an OpenAI key
    assert env_key_for("gemini/gemini-3-flash-preview") == ""
    assert env_key_for("openai/gpt-4o-mini") == "sk-openai-only"


def test_cloud_available_matched_key(monkeypatch):
    for v in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY",
              "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY",
              "XAI_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    ok, reason = cloud_available(_cfg(llm="deepseek/deepseek-chat"))
    assert ok and "deepseek" in reason and "legacy" not in reason


def test_cloud_available_legacy_fallback_is_labeled(monkeypatch):
    for v in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "DEEPSEEK_API_KEY",
              "OPENROUTER_API_KEY", "XAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai")
    # configured model is gemini, only an openai key exists: the legacy
    # fallback keeps old deployments working but must SAY so
    ok, reason = cloud_available(_cfg(llm="gemini/gemini-3-flash-preview"))
    assert ok and "legacy" in reason


def test_cloud_available_no_keys_is_down(monkeypatch):
    for v in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY",
              "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY",
              "XAI_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    ok, reason = cloud_available(_cfg(llm="gemini/gemini-3-flash-preview"))
    assert not ok and "no API key" in reason


def test_explicit_config_key_wins(monkeypatch):
    for v in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY",
              "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY",
              "XAI_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    ok, reason = cloud_available(_cfg(llm="gemini/gemini-3-flash-preview",
                                      api_key="sk-config"))
    assert ok and "explicit api_key in config" in reason


def test_disabled_cloud_is_down():
    ok, _ = cloud_available(_cfg(llm="gemini/x", api_key="sk", enabled=False))
    assert not ok


# ------------------------------------------------------------- health API
def test_provider_health_no_network(monkeypatch):
    for v in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-o")
    ok, _ = cloud_available(_cfg(llm="openai/gpt-4o-mini"))
    assert ok
    p = Provider(ProviderConfig(ProviderKind.OPENAI, "openai/gpt-4o-mini", "", "env"))
    h = p.health()                       # key presence only — no network
    assert h.available and h.kind == ProviderKind.OPENAI
    # ollama health with injected liveness (hermetic)
    po = Provider(ProviderConfig(ProviderKind.OLLAMA, "bee4b", "", "env"))
    assert po.health(ollama_up=True).available
    assert not po.health(ollama_up=False).available


_ALL_KEYS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY",
             "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY",
             "XAI_API_KEY")


def test_client_provider_api_is_public_and_hermetic(monkeypatch):
    for v in _ALL_KEYS:
        monkeypatch.delenv(v, raising=False)
    from bee.agent.client import LLMClient, LLMRequest, LLMResponse
    c = LLMClient(_cfg(llm="gemini/gemini-3-flash-preview"))
    caps = c.capabilities()
    for k in ("chat", "streaming_chat", "tool_calling", "health", "model_info"):
        assert caps[k] is True
    assert caps["embeddings"] is False          # ollama on a dead port
    h = c.health()
    assert "ollama" in h and h["ollama"]["available"] is False
    assert "gemini" in h and h["gemini"]["available"] is False
    assert "no key" in h["gemini"]["reason"]
    info = c.models_info()
    assert info["cloud_configured"] == "gemini/gemini-3-flash-preview"
    assert info["ollama_models"] == []          # dead port -> no crash
    assert c.ollama_up() is False
    # typed envelopes round-trip
    req = LLMRequest(name="local", messages=[{"role": "user", "content": "hi"}])
    assert req.max_retries == 2
    resp = LLMResponse(content="hello", tool_calls=[], usage={"prompt": 1, "completion": 2})
    assert resp.to_dict()["content"] == "hello"


def test_loop_cloud_up_uses_registry_not_hardcoded(monkeypatch):
    """The loop's cloud-availability check must track the ACTUAL configured
    provider (deepseek example), never a hard-coded gemini/openai assumption."""
    from bee.agent.loop import _cloud_up
    for v in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY",
              "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "XAI_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    assert _cloud_up(_cfg(llm="deepseek/deepseek-chat")) is False
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    assert _cloud_up(_cfg(llm="deepseek/deepseek-chat")) is True
    # ...and a different provider's key does not light up a deepseek model
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai")
    ok, reason = cloud_available(_cfg(llm="deepseek/deepseek-chat"))
    assert ok and "legacy" in reason            # labelled fallback, still honest
