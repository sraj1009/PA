"""J3 — model-upgrade quality gate (contract tests, no live model).

runner.run_suite is replaced with a deterministic fake keyed by model name;
baselines.json / models.yaml are redirected to tmp. What is pinned here is the
PROMOTION CONTRACT: a candidate ships only on (score >= baseline + margin)
AND (no structural regression); rollback removes the models.yaml override.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from bee import paths
from bee.config import Config
from bee.evals import gate


# --------------------------------------------------------------- fixtures
def _rows(per_task: dict[str, bool], model: str) -> list[dict]:
    return [{"id": tid, "ok": ok, "skipped": False, "model": model,
             "error": "" if ok else "fake fail", "seconds": 0.1,
             "ts": "2026-10-06T00:00:00", "repeat": 1, "expect": None,
             "output_excerpt": ""} for tid, ok in per_task.items()]


class FakeClient:
    def __init__(self, models):
        self._models = models

    def models_list(self):
        return list(self._models)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated gate environment: baselines + models.yaml + diary in tmp."""
    cfg = Config()
    cfg.ollama.model = "bee4b"
    ctx = SimpleNamespace(cfg=cfg,
                          client=FakeClient(["bee4b", "bee4b-v2"]))
    baselines = tmp_path / "baselines.json"
    models_yaml = tmp_path / "models.yaml"
    monkeypatch.setattr(gate, "BASELINES_FILE", baselines)
    monkeypatch.setattr(paths, "MODELS_YAML", models_yaml)
    monkeypatch.setattr(gate, "structural_task_ids", lambda: ["t1", "t2"])
    import bee.memory.md as md
    monkeypatch.setattr(md, "diary_add", lambda s: None)
    return {"ctx": ctx, "baselines": baselines, "models_yaml": models_yaml,
            "cfg": cfg}


def _fake_suite(score_map: dict[str, dict], monkeypatch):
    """score_map: model -> {task_id: ok}"""
    def fake_run_suite(ctx, model=None, only=None):
        per = score_map[model]
        if isinstance(only, list):
            per = {k: v for k, v in per.items() if k in only}
        return _rows(per, model)
    monkeypatch.setattr("bee.evals.runner.run_suite", fake_run_suite)


# ------------------------------------------------------------------ tests
def test_no_candidate_is_a_skip(env):
    r = gate.model_quality_gate(env["ctx"])
    assert r["ok"] and "skipped" in r


def test_unknown_candidate_rejected_before_spending_an_eval(env, monkeypatch):
    calls = []

    def spy(ctx, model=None, only=None):
        calls.append(model)
        return []
    monkeypatch.setattr("bee.evals.runner.run_suite", spy)
    r = gate.model_quality_gate(env["ctx"], candidate="ghost-model")
    assert not r["ok"]
    assert "not in `ollama list`" in r["reasons"][0]
    assert calls == []                       # never ran the suite


def test_first_run_seeds_baseline_then_promotes(env, monkeypatch):
    # active model scores 10/10, candidate scores 11/11 -> +1 margin met
    _fake_suite({"bee4b": {f"t{i}": True for i in range(10)},
                 "bee4b-v2": {f"t{i}": True for i in range(11)}}, monkeypatch)
    r = gate.model_quality_gate(env["ctx"], candidate="bee4b-v2", margin=1)
    assert r["ok"] and r["promoted"] == "bee4b-v2", r
    assert env["models_yaml"].exists()
    import yaml
    assert yaml.safe_load(env["models_yaml"].read_text(encoding="utf-8"))["local_model"] == "bee4b-v2"
    data = gate.load_baselines()
    assert "bee4b" in data["models"] and "bee4b-v2" in data["models"]
    assert data["promotions"][-1]["from"] == "bee4b"
    assert data["promotions"][-1]["to"] == "bee4b-v2"


def test_candidate_below_margin_rejected(env, monkeypatch):
    # active 10/10; candidate 10/11 — equal or worse score, no margin
    _fake_suite({"bee4b": {f"t{i}": True for i in range(10)},
                 "bee4b-v2": {**{f"t{i}": True for i in range(10)}, "t99": False}},
                monkeypatch)
    r = gate.model_quality_gate(env["ctx"], candidate="bee4b-v2", margin=1)
    assert not r["ok"]
    assert any("score" in reason for reason in r["reasons"])
    assert not env["models_yaml"].exists()          # NOT promoted


def test_structural_regression_blocks_promotion(env, monkeypatch):
    # candidate scores HIGHER overall but breaks a structural task that
    # passed in the baseline — promotion must still be refused
    _fake_suite({"bee4b": {**{f"t{i}": True for i in range(10)}, "t1": True},
                 "bee4b-v2": {**{f"t{i}": True for i in range(12)}, "t1": False}},
                monkeypatch)
    r = gate.model_quality_gate(env["ctx"], candidate="bee4b-v2", margin=1)
    assert not r["ok"]
    assert r["regressed"] == ["t1"]
    assert any("structural" in reason for reason in r["reasons"])
    assert not env["models_yaml"].exists()


def test_candidate_never_invoked_is_rejected(env, monkeypatch):
    # the "candidate" silently escalated to cloud — the suite rows say so
    def fake(ctx, model=None, only=None):
        m = "cloud" if model == "bee4b-v2" else model
        return _rows({f"t{i}": True for i in range(11)}, m)
    monkeypatch.setattr("bee.evals.runner.run_suite", fake)
    assert gate.set_baseline(env["ctx"], "bee4b")["ok"]
    r = gate.model_quality_gate(env["ctx"], candidate="bee4b-v2", margin=1)
    assert not r["ok"]
    assert "never invoked" in r["reasons"][0]
    assert not env["models_yaml"].exists()


def test_rollback_removes_override(env):
    gate.promote_model("bee4b-v2")
    assert env["models_yaml"].exists()
    r = gate.rollback_model()
    assert r["ok"] and r["rolled_back"] == "bee4b-v2"
    import yaml
    data = yaml.safe_load(env["models_yaml"].read_text(encoding="utf-8")) or {}
    assert "local_model" not in data
    r2 = gate.rollback_model()
    assert not r2["ok"]


def test_baseline_record_roundtrip(env):
    score = {"passed": 7, "total": 9,
             "per_task": {f"t{i}": i % 2 == 0 for i in range(9)},
             "models_used": {"bee4b"}, "rows": []}
    rec = gate.baseline_record("bee4b", score)
    assert rec["score"] == "7/9" and rec["model"] == "bee4b"
    data = {"models": {"bee4b": rec}, "promotions": []}
    gate.save_baselines(data)
    loaded = gate.load_baselines()
    assert loaded["models"]["bee4b"]["per_task"]["t2"] is True


def test_baselines_file_corruption_is_safe(env, monkeypatch):
    env["baselines"].write_text("{not json", encoding="utf-8")
    data = gate.load_baselines()
    assert data == {"models": {}, "promotions": []}
