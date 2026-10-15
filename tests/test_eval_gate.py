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


def test_a_candidate_that_ran_fewer_tasks_cannot_be_compared(env, monkeypatch):
    """A62: `run_score` drops skipped rows, so the two sides can have different
    denominators while the score test compares raw pass COUNTS. Baseline 10/21,
    candidate 12/12 (only 12 tasks ran, because cloud was down) used to read as an
    improvement and promote the candidate."""
    _fake_suite({"bee4b": {**{f"t{i}": True for i in range(10)},
                           **{f"t{i}": False for i in range(10, 21)}},
                 "bee4b-v2": {f"t{i}": True for i in range(12)}}, monkeypatch)
    r = gate.model_quality_gate(env["ctx"], candidate="bee4b-v2", margin=1)
    assert not r["ok"], r
    assert any("not comparable" in reason for reason in r["reasons"]), r["reasons"]
    assert not env["models_yaml"].exists()


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


# ------------------------------------------- eval permission posture + workspace (A36)
def test_the_eval_answers_prompts_the_way_a_user_would(tmp_path):
    """The suite used to auto-deny every prompt, which made any task whose correct
    answer requires executing code unsatisfiable BY CONFIGURATION. Local compute and
    file actions are granted; anything destructive or externally visible stays denied
    so `guard_blocked` still proves the block is real."""
    from bee.evals import runner
    for tool in ("code_run", "file_write", "file_read", "file_list", "planner"):
        assert runner.eval_approver(tool, {}, "r"), tool
    for tool in ("shell", "sandbox_run", "systemctl", "automation_job", "skill_create",
                 "email", "browser"):
        assert not runner.eval_approver(tool, {}, "r"), tool


def test_the_eval_may_create_a_file_but_never_clobber_one(tmp_path):
    """`file_roundtrip` asks for a NEW eval_probe.txt; granting file_write wholesale
    would let a run overwrite real source. Creation yes, destruction no — the
    restore guard stays the backstop, not the control."""
    from bee.evals import runner
    (tmp_path / "bee").mkdir()
    (tmp_path / "bee" / "agent.py").write_text("USER WORK\n", encoding="utf-8")
    assert runner.eval_approver("file_write", {"path": "notes/new.txt"}, "r",
                               workspace=tmp_path) is True
    assert runner.eval_approver("file_write", {"path": "bee/agent.py"}, "r",
                               workspace=tmp_path) is False
    assert runner.eval_approver("file_write", {"path": "../outside.py"}, "r",
                                workspace=tmp_path) is True   # guard/capability still apply


def test_restore_workspace_undoes_everything_the_run_touched(tmp_path):
    import shutil as _sh
    import subprocess
    from bee.evals.runner import _restore_workspace

    if not _sh.which("git"):
        pytest.skip("git unavailable")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(repo), check=True)
    (repo / "keep.txt").write_text("original\n", encoding="utf-8")
    (repo / "doomed.txt").write_text("still here\n", encoding="utf-8")
    (repo / "dirty_before.txt").write_text("uncommitted work\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=str(repo), check=True)
    # 'dirty before' will be made dirty BEFORE the context opens: it must survive
    # untouched even though the run also changes it.
    (repo / "dirty_before.txt").write_text("MY UNCOMMITTED WORK\n", encoding="utf-8")

    with _restore_workspace(repo):
        (repo / "eval_probe.txt").write_text("BEE EVAL OK", encoding="utf-8")
        (repo / "keep.txt").write_text("clobbered by the run\n", encoding="utf-8")
        (repo / "doomed.txt").unlink()
        (repo / "dirty_before.txt").write_text("mangled by the run\n", encoding="utf-8")

    assert (repo / "keep.txt").read_text(encoding="utf-8") == "original\n"
    assert (repo / "doomed.txt").read_text(encoding="utf-8") == "still here\n"
    assert not (repo / "eval_probe.txt").exists()
    # work that was already uncommitted before the run is never reverted
    assert (repo / "dirty_before.txt").read_text(encoding="utf-8") == "MY UNCOMMITTED WORK\n"


# ------------------------------------------------ gate identity contract (A##)
def test_the_route_keeps_the_pinned_engine_as_its_name():
    """gate.set_baseline / model_quality_gate build `models_used` from every row's
    `model`, and refuse a model that never appears. That only works because
    `router.route()` keeps an explicit `model=` argument as the returned route
    NAME (source='explicit'), so AgentResult.model becomes the engine string
    ('bee4b'), not the coarse 'local'. If a refactor collapses that back to
    'local', the gate silently can never seed — and every test in this file
    stays green because they fake `run_suite` outright."""
    from bee.agent.router import route
    from bee.config import Config
    cfg = Config()
    r = route("tell me a story about dragons", cfg, model="bee4b")
    assert r["name"] == "bee4b", r
    assert r["source"] == "explicit", r
    # a non-route model string must survive too (candidate = 'qwen2.5:3b' etc.)
    r2 = route("hello there", cfg, model="qwen2.5:3b")
    assert r2["name"] == "qwen2.5:3b", r2


def test_the_eval_row_takes_model_from_agentresult_not_route_source():
    """The other half of the same contract: `runner._run_tasks` must put
    `last_r.model` (the engine string from AgentResult) into row['model'], not
    `last_r.route_source`. A swap would rewrite every row to 'explicit' / 'fastpath'
    / 'hybrid-speed' and the gate would refuse to seed with 'bee4b was never
    invoked during the suite'. The gate's unit tests fake run_suite and cannot
    see this drift — hence a static source check, the same pattern that re-feeds
    A27a/A37a into themselves so the guard cannot pass by being unable to fire."""
    import inspect
    from bee.evals import runner
    src = inspect.getsource(runner._run_tasks)
    # two row literals exist: the skipped-task stub (`"model": None`) and the
    # executed-task row we care about. Assert on the executed one.
    assert '"model": last_r.model' in src, (
        "the executed eval row must record last_r.model (the answered engine); "
        "if it reads route_source instead the J3 gate silently can never seed")
    assert '"model": last_r.route_source' not in src, (
        "eval row 'model' must not read route_source")
