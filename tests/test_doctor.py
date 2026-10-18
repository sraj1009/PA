"""`python -m bee.cli doctor` / `/doctor` — hermetic unit tests.

Every probe is mocked; nothing touches the network or starts a service. Pins:
report content, verdict/exit codes (0 healthy, 1 no local core, 2 broken
config), the no-secrets guarantee, and the CLI dispatch (doctor runs before
config load and before any background service).

Registered in tests/conftest.py:_UNIT.
"""
from __future__ import annotations

import os
import types

import pytest

from bee import cli as bee_cli
from bee import paths
from bee.monitor import doctor


def _fake_cfg(tmp_path, *, api_key="", precedence=None):
    return types.SimpleNamespace(
        workspace=tmp_path,
        ollama=types.SimpleNamespace(base_url="http://localhost:11434",
                                     model="bee4b", embed_model="nomic-embed-text"),
        guard=types.SimpleNamespace(mode="always"),
        cloud=types.SimpleNamespace(enabled=True, llm="gemini/gemini-2.5-flash",
                                    api_key=api_key),
        precedence=(precedence if precedence is not None
                    else {"ollama.model": "config.yaml"}),
    )


@pytest.fixture
def healthy(monkeypatch, tmp_path):
    """All probes healthy; memory + evals pointed at a scratch tree."""
    monkeypatch.setattr(paths, "VECTOR_DIR", tmp_path / "vectors")
    monkeypatch.setattr(paths, "EVALS_DIR", tmp_path / "evals")
    monkeypatch.setattr(paths, "EVAL_RESULTS", tmp_path / "evals" / "results.jsonl")
    monkeypatch.setattr(doctor, "_cloud_configured", lambda c: True)
    monkeypatch.setattr(doctor, "_probe_ollama", lambda c: {
        "up": True, "base_url": "http://localhost:11434",
        "models": ["bee4b:latest", "nomic-embed-text:latest", "qwen3:8b"],
        "error": ""})
    return _fake_cfg(tmp_path)


# --------------------------------------------------------------- report body
def test_render_healthy_exit_zero(healthy):
    rep = doctor.collect(healthy)
    text = doctor.render(rep)
    assert "== BEE doctor ==" in text
    assert "bee4b OK" in text and "nomic-embed-text OK" in text
    assert "configured: yes" in text
    assert "verdict: OK" in text
    assert doctor.exit_code(rep) == 0


def test_ollama_down_exit_one(healthy, monkeypatch):
    monkeypatch.setattr(doctor, "_probe_ollama", lambda c: {
        "up": False, "base_url": "http://127.0.0.1:11434",
        "models": [], "error": "ConnectError: refused"})
    rep = doctor.collect(healthy)
    text = doctor.render(rep)
    assert "DOWN" in text
    assert "verdict: DEGRADED" in text
    assert doctor.exit_code(rep) == 1


def test_missing_required_model_exit_one(healthy, monkeypatch):
    monkeypatch.setattr(doctor, "_probe_ollama", lambda c: {
        "up": True, "base_url": "http://127.0.0.1:11434",
        "models": ["nomic-embed-text:latest"], "error": ""})
    rep = doctor.collect(healthy)
    text = doctor.render(rep)
    assert "bee4b MISSING" in text
    assert doctor.exit_code(rep) == 1


def test_has_model_tag_insensitive():
    assert doctor._has_model(["bee4b:latest"], "bee4b")
    assert doctor._has_model(["nomic-embed-text:v1.5"], "nomic-embed-text")
    assert not doctor._has_model(["other:latest"], "bee4b")


def test_report_never_contains_key_material(healthy, tmp_path):
    # built at runtime: token-shaped (>= 24 chars) but low-entropy, so the
    # repo's own secretscan gate sees no fake key literal in this file
    secret = "sk-live-" + "a1b2c3" * 6
    cfg = _fake_cfg(tmp_path, api_key=secret)
    rep = doctor.collect(cfg)
    blob = doctor.render(rep)
    assert secret not in blob and secret not in str(rep)
    assert "configured: yes" in blob          # presence, not the value


def test_dirty_queue_and_index_age_rendered(healthy, monkeypatch):
    from bee.memory import search
    monkeypatch.setattr(search, "pending_paths", lambda: ["a", "b", "c"])
    vd = paths.VECTOR_DIR
    vd.mkdir(parents=True, exist_ok=True)
    f = vd / "table.lance"
    f.write_text("x", encoding="utf-8")
    old = f.stat().st_mtime - 7200
    os.utime(f, (old, old))
    rep = doctor.collect(healthy)
    text = doctor.render(rep)
    assert "3 file(s) pending embed" in text
    assert "h old" in text


def test_precedence_summary_buckets():
    s = doctor._precedence_summary({
        "a": "config.yaml", "b": "config.yaml", "c": ".env", "d": "default",
        "e": "process-env",
        "f": "settings.json (independent of Config — see matrix)"})
    assert "config.yaml 2" in s and ".env 1" in s and "default 1" in s
    assert "other 1" in s
    assert s.index("config.yaml") < s.index(".env") < s.index("default")


def test_human_age_boundaries():
    assert doctor._human_age(5) == "5 s"
    assert doctor._human_age(600) == "10.0 m"
    assert doctor._human_age(7200) == "2.0 h"
    assert doctor._human_age(3 * 86400) == "3.0 d"


# --------------------------------------------------------------- run / codes
def test_run_healthy_returns_zero(healthy, monkeypatch, capsys):
    monkeypatch.setattr(doctor, "load_config", lambda p=None: healthy)
    assert doctor.run() == 0
    assert "verdict: OK" in capsys.readouterr().out


def test_run_broken_config_exit_two_and_scrubbed(monkeypatch, capsys):
    secret = "rpa-secret-" + "z9y8" * 8      # token-shaped, low-entropy (see above)

    def boom(_p=None):
        raise RuntimeError(f"bad yaml near api_key: {secret}")

    monkeypatch.setattr(doctor, "load_config", boom)
    code = doctor.run()
    out = capsys.readouterr().out
    assert code == 2
    assert "BROKEN" in out
    assert secret not in out
    assert "[redacted]" in out


# --------------------------------------------------------------- CLI wiring
def test_cli_doctor_mode_skips_services_and_forwards_config(monkeypatch):
    calls = []
    monkeypatch.setattr(doctor, "run", lambda path=None: (calls.append(path), 0)[1])

    import bee.native as native
    monkeypatch.setattr(native, "start_background",
                        lambda *a, **k: pytest.fail("doctor must not start the telemetry daemon"))
    from bee.agent import localserver
    monkeypatch.setattr(localserver, "start_background",
                        lambda *a, **k: pytest.fail("doctor must not start the model server"))
    from bee import config as beeconfig
    monkeypatch.setattr(beeconfig, "load_config",
                        lambda *a, **k: pytest.fail("doctor loads (and reports) config itself"))

    assert bee_cli.main(["doctor"]) == 0
    assert bee_cli.main(["doctor", "--config", "x.yaml"]) == 0
    assert calls == [None, "x.yaml"]


def test_cli_health_mode(monkeypatch):
    seen = []
    from bee.monitor import health
    monkeypatch.setattr(health, "cli_report", lambda cfg: seen.append(cfg))
    from bee import config as beeconfig
    monkeypatch.setattr(beeconfig, "load_config", lambda p=None: "CFG")
    assert bee_cli.main(["health"]) == 0
    assert seen == ["CFG"]
