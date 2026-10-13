"""M14 — config-precedence matrix (tests/contract).

Stages each layer independently (tmp config.yaml / .env / models.yaml +
controlled process env) and asserts BOTH the winning value and the reported
source (cfg.precedence). The matrix under test: docs/CONFIG_PRECEDENCE.md.
"""
from __future__ import annotations

import pytest

from bee import paths
from bee.config import load_config

# every env var the config layer consults — cleared per test for isolation
_ENV_VARS = [
    "OLLAMA_MODEL", "OLLAMA_BASE_URL", "OLLAMA_EMBED_MODEL",
    "CLOUD_LLM", "CLOUD_BASE_URL", "EDGE_TTS_KEY",
    "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET",
    "BEE_USER_NAME", "BEE_WORKSPACE",
    "OPENAI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "DEEPSEEK_API_KEY", "XAI_API_KEY",
    "BEE_WEB_TOKEN",
]


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    for v in _ENV_VARS:
        monkeypatch.delenv(v, raising=False)
    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(paths, "PROJECT_ROOT", proj)
    monkeypatch.setattr(paths, "MODELS_YAML", proj / "models.yaml")
    monkeypatch.setattr(paths, "CONFIG_YAML", proj / "config.yaml")
    monkeypatch.setattr(paths, "WORKSPACE", tmp_path / "ws")
    return {"yaml": proj / "config.yaml", "dotenv": proj / ".env",
            "models": proj / "models.yaml", "tmp": tmp_path}


def _write(d: dict, f) -> None:
    import yaml as _yaml
    f.write_text(_yaml.safe_dump(d, sort_keys=False), encoding="utf-8")


# ------------------------------------------------------------- layer basics
def test_defaults_without_any_source(isolated):
    cfg = load_config(isolated["yaml"])
    assert cfg.ollama.model == "bee4b"
    assert cfg.precedence["ollama.model"] == "default"
    assert cfg.precedence["workspace"] == "default"


def test_config_yaml_layer(isolated):
    _write({"ollama": {"model": "bee9b"}}, isolated["yaml"])
    cfg = load_config(isolated["yaml"])
    assert cfg.ollama.model == "bee9b"
    assert cfg.precedence["ollama.model"] == "config.yaml"


def test_dotenv_fills_missing_var(isolated):
    isolated["dotenv"].parent.mkdir(parents=True, exist_ok=True)
    isolated["dotenv"].write_text("OLLAMA_MODEL=bee-from-dotenv\n", encoding="utf-8")
    cfg = load_config(isolated["yaml"])
    assert cfg.ollama.model == "bee-from-dotenv"
    assert cfg.precedence["ollama.model"] == ".env"


def test_process_env_beats_dotenv(isolated, monkeypatch):
    isolated["dotenv"].parent.mkdir(parents=True, exist_ok=True)
    isolated["dotenv"].write_text("OLLAMA_MODEL=bee-from-dotenv\n", encoding="utf-8")
    monkeypatch.setenv("OLLAMA_MODEL", "bee-from-process")
    cfg = load_config(isolated["yaml"])
    assert cfg.ollama.model == "bee-from-process"
    assert cfg.precedence["ollama.model"] == "process-env"


# ---------------------------------------------------------- models.yaml (J3)
def test_models_yaml_beats_config_yaml(isolated):
    _write({"ollama": {"model": "bee9b"}}, isolated["yaml"])
    isolated["models"].write_text("local_model: bee-promoted\n", encoding="utf-8")
    cfg = load_config(isolated["yaml"])
    assert cfg.ollama.model == "bee-promoted"
    assert cfg.precedence["ollama.model"] == "models.yaml"


def test_process_env_beats_models_yaml(isolated, monkeypatch):
    isolated["models"].write_text("local_model: bee-promoted\n", encoding="utf-8")
    monkeypatch.setenv("OLLAMA_MODEL", "bee-from-process")
    cfg = load_config(isolated["yaml"])
    assert cfg.ollama.model == "bee-from-process"
    assert cfg.precedence["ollama.model"] == "process-env"


def test_models_yaml_does_not_touch_other_fields(isolated):
    _write({"ollama": {"model": "bee9b", "num_ctx": 1234}}, isolated["yaml"])
    isolated["models"].write_text("local_model: bee-promoted\n", encoding="utf-8")
    cfg = load_config(isolated["yaml"])
    assert cfg.ollama.model == "bee-promoted"
    assert cfg.ollama.num_ctx == 1234          # still from config.yaml
    assert cfg.precedence["ollama.base_url"] == "default"


# ------------------------------------------------------- cloud.api_key rule
def test_cloud_api_key_explicit_yaml_wins_over_env(isolated, monkeypatch):
    _write({"cloud": {"llm": "openai/gpt-4o-mini", "api_key": "sk-config-wins"}},
           isolated["yaml"])
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-should-not-win")
    cfg = load_config(isolated["yaml"])
    assert cfg.cloud.api_key == "sk-config-wins"
    assert cfg.precedence["cloud.api_key"].startswith("config.yaml")


def test_cloud_api_key_provider_matched_from_env(isolated, monkeypatch):
    _write({"cloud": {"llm": "openai/gpt-4o-mini"}}, isolated["yaml"])
    monkeypatch.setenv("OPENAI_API_KEY", "sk-provider-matched")
    cfg = load_config(isolated["yaml"])
    assert cfg.cloud.api_key == "sk-provider-matched"
    assert cfg.precedence["cloud.api_key"].startswith("env")


# ------------------------------------------------------------- misc contract
def test_computeruse_section_is_loaded(isolated):
    _write({"computeruse": {"max_actions": 3, "hotkey": "ctrl+alt+x"}}, isolated["yaml"])
    cfg = load_config(isolated["yaml"])
    assert cfg.computeruse.max_actions == 3
    assert cfg.computeruse.hotkey == "ctrl+alt+x"


def test_unknown_keys_are_ignored(isolated):
    _write({"ollama": {"model": "bee9b", "bogus_field": 123}}, isolated["yaml"])
    cfg = load_config(isolated["yaml"])
    assert cfg.ollama.model == "bee9b"
    assert not hasattr(cfg.ollama, "bogus_field")


def test_workspace_from_dotenv(isolated):
    ws = isolated["tmp"] / "ws2"
    isolated["dotenv"].parent.mkdir(parents=True, exist_ok=True)
    isolated["dotenv"].write_text(f"BEE_WORKSPACE={ws}\n", encoding="utf-8")
    cfg = load_config(isolated["yaml"])
    assert cfg.workspace == ws
    assert cfg.precedence["workspace"] == ".env"


def test_engine_layer_independent(isolated):
    cfg = load_config(isolated["yaml"])
    # settings.json is reported as its own layer, never a Config source
    assert "settings.json" in cfg.precedence.get("engine", "")
    assert cfg.precedence["engine"] == \
        "settings.json (independent of Config — see matrix)"


# ------------------------------------------------- shipped local context window
# A59: measured 2026-10-13 against the live server with BEE's REAL system prompt
# and the 30 shipped tool schemas. Every one of the 11 model-using eval tasks was
# replayed twice — once at the shipped window (delivered = prompt_eval_count) and
# once at num_ctx=12288 with num_predict=1 (required = the true size of the same
# prompt). Real turns are 5772-7339 tokens and the shipped 4096 delivered 2050 of
# them (26-35%): Ollama dropped the rest before the model saw it, yet still
# answered with HTTP 200. The floor is the largest real turn measured.
MIN_LOCAL_TURN_TOKENS = 7339


def test_shipped_local_num_ctx_holds_a_real_agent_turn():
    cfg = load_config(paths.CONFIG_YAML)
    assert cfg.ollama.num_ctx >= MIN_LOCAL_TURN_TOKENS, (
        f"config.yaml ships ollama.num_ctx={cfg.ollama.num_ctx} but a real BEE "
        f"agent turn is up to {MIN_LOCAL_TURN_TOKENS} tokens of prompt. Below that "
        "the local tier is silently truncated by Ollama — the model answers without "
        "its own tool results. Raise it (8192 is the largest window that stays "
        "entirely in this card's VRAM: /api/ps shows 12288 offloads 0.46 GB).")
