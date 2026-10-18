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
    gate_candidate = tmp_path / "train" / "gate_candidate.json"
    monkeypatch.setattr(gate, "BASELINES_FILE", baselines)
    monkeypatch.setattr(paths, "MODELS_YAML", models_yaml)
    monkeypatch.setattr(gate, "GATE_CANDIDATE_FILE", gate_candidate)
    monkeypatch.setattr(gate, "structural_task_ids", lambda: ["t1", "t2"])
    import bee.memory.md as md
    monkeypatch.setattr(md, "diary_add", lambda s: None)
    return {"ctx": ctx, "baselines": baselines, "models_yaml": models_yaml,
            "gate_candidate": gate_candidate, "cfg": cfg}


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
    # same task set both arms: active scores 9/10, candidate 10/10 -> +1 margin met
    _fake_suite({"bee4b": {**{f"t{i}": True for i in range(10)}, "t9": False},
                 "bee4b-v2": {f"t{i}": True for i in range(10)}}, monkeypatch)
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
    # active 10/10; candidate 9/10 on the same tasks — worse score, no margin
    _fake_suite({"bee4b": {f"t{i}": True for i in range(10)},
                 "bee4b-v2": {**{f"t{i}": True for i in range(10)}, "t9": False}},
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


def test_a_baseline_seeded_from_a_partial_run_is_not_comparable_later(env, monkeypatch):
    """A64 close (2026-10-18): the A62 guard refused only a SMALLER candidate.
    A baseline SEEDED from a partial run (cloud was down: 8 of 10 tasks ran)
    compared against a later larger candidate, raw pass COUNTS again — the
    candidate here even loses t0, a task the baseline passed, and the old code
    still promoted it on the two extra wins. The task sets must be identical,
    whichever side is bigger."""
    _fake_suite({"bee4b": {f"t{i}": True for i in range(8)},          # partial seed
                 "bee4b-v2": {**{f"t{i}": True for i in range(10)}, "t0": False}},
                monkeypatch)
    assert gate.set_baseline(env["ctx"], "bee4b")["ok"]
    r = gate.model_quality_gate(env["ctx"], candidate="bee4b-v2", margin=1)
    assert not r["ok"], r
    assert any("not comparable" in reason for reason in r["reasons"]), r["reasons"]
    assert any("ran only for the candidate" in reason for reason in r["reasons"]), r["reasons"]
    assert not env["models_yaml"].exists()


def test_two_arms_that_skipped_identically_are_comparable(env, monkeypatch):
    """The guard is about identical task sets, not about the full suite: when
    both arms skipped the same tasks the comparison is fair and must proceed
    (here to the score test, which refuses on the margin)."""
    _fake_suite({"bee4b": {f"t{i}": True for i in range(8)},
                 "bee4b-v2": {**{f"t{i}": True for i in range(8)}, "t7": False}},
                monkeypatch)
    assert gate.set_baseline(env["ctx"], "bee4b")["ok"]
    r = gate.model_quality_gate(env["ctx"], candidate="bee4b-v2", margin=1)
    assert not r["ok"], r
    assert not any("not comparable" in reason for reason in r["reasons"]), r["reasons"]
    assert any("score" in reason for reason in r["reasons"]), r["reasons"]


def test_structural_regression_blocks_promotion(env, monkeypatch):
    # raw counts are LEVEL (9/10 both sides; margin=0 clears the score test) but
    # the candidate breaks a structural task the baseline passed — the
    # structural guard must refuse promotion on its own
    _fake_suite({"bee4b": {**{f"t{i}": True for i in range(10)}, "t9": False},
                 "bee4b-v2": {**{f"t{i}": True for i in range(10)}, "t1": False,
                              "t9": True}},
                monkeypatch)
    r = gate.model_quality_gate(env["ctx"], candidate="bee4b-v2", margin=0)
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


def test_rate_limited_candidate_arm_voids_the_comparison(env, monkeypatch):
    """LIVE 2026-10-17: the Gemini quota died between the two arms; the
    candidate's cloud-dependent tasks failed with litellm.RateLimitError and
    the gate printed "14/21 < baseline 16/21 + margin 1" — reading as model
    quality when it was provider availability. A 429-dead candidate arm must
    void the comparison (no promotion), not count as a rejection, and must not
    be recorded as the candidate's score."""
    def fake_run_suite(ctx, model=None, only=None):
        rows = _rows({f"t{i}": True for i in range(10)}, model)
        if model == "bee4b-v2":
            rows.append({"id": "cloud_task", "ok": False, "skipped": False,
                         "model": model, "seconds": 1.0, "ts": "2026-10-17T00:00:00",
                         "repeat": 1, "expect": None, "output_excerpt": "",
                         "error": 'LLM error: litellm.RateLimitError: geminiException - '
                                  '{"error": {"code": 429, "message": "You exceeded your '
                                  'current quota"}}'})
        return rows
    monkeypatch.setattr("bee.evals.runner.run_suite", fake_run_suite)
    assert gate.set_baseline(env["ctx"], "bee4b")["ok"]
    r = gate.model_quality_gate(env["ctx"], candidate="bee4b-v2", margin=1)
    assert not r["ok"] and r.get("void"), r
    assert "rate limit" in r["reasons"][0].lower()
    assert r["rate_limited"] == ["cloud_task"]
    assert not env["models_yaml"].exists()
    assert "bee4b-v2" not in gate.load_baselines()["models"]


def test_rate_limited_baseline_seed_is_refused(env, monkeypatch):
    """The other half: a quota-dead arm must not become the BASELINE either —
    every later comparison would inherit the lie."""
    def fake_run_suite(ctx, model=None, only=None):
        rows = _rows({f"t{i}": True for i in range(3)}, model)
        rows.append({"id": "cloud_task", "ok": False, "skipped": False,
                     "model": model, "seconds": 1.0, "ts": "2026-10-17T00:00:00",
                     "repeat": 1, "expect": None, "output_excerpt": "",
                     "error": "litellm.RateLimitError: 429 Too Many Requests"})
        return rows
    monkeypatch.setattr("bee.evals.runner.run_suite", fake_run_suite)
    r = gate.set_baseline(env["ctx"], "bee4b")
    assert not r["ok"] and "rate limit" in r["reason"].lower(), r
    assert not env["baselines"].exists()


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


# --------------------------------- P0-5: candidate queue + adjudication power
def test_queued_candidate_is_picked_up_and_consumed_on_reject(env, monkeypatch):
    """The auto-chain queue (train/gate_candidate.json) feeds the gate exactly
    once: a decided verdict consumes it (see the void test for the exception)."""
    gate.queue_candidate("bee4b-v2", src="auto-chain")
    assert env["gate_candidate"].exists()
    assert gate.pending_candidate() == "bee4b-v2"
    _fake_suite({"bee4b": {f"t{i}": True for i in range(10)},
                 "bee4b-v2": {**{f"t{i}": True for i in range(10)}, "t9": False}},
                monkeypatch)
    r = gate.model_quality_gate(env["ctx"], margin=1)      # no explicit candidate
    assert not r["ok"] and any("score" in x for x in r["reasons"]), r
    assert not env["gate_candidate"].exists()              # consumed
    assert "bee4b-v2" in gate.load_baselines()["models"]   # attempt recorded


def test_queued_candidate_promotes_and_is_consumed(env, monkeypatch):
    gate.queue_candidate("bee4b-v2", src="auto-chain")
    _fake_suite({"bee4b": {**{f"t{i}": True for i in range(10)}, "t9": False},
                 "bee4b-v2": {f"t{i}": True for i in range(10)}}, monkeypatch)
    r = gate.model_quality_gate(env["ctx"], margin=1)
    assert r["ok"] and r.get("promoted") == "bee4b-v2", r
    assert not env["gate_candidate"].exists()


def test_queued_candidate_survives_a_void(env, monkeypatch):
    """A 429-dead arm is not an attempt: the queued artifact must stay so the
    nightly gate retries when the quota recovers (the live 2026-10-17 lesson)."""
    gate.queue_candidate("bee4b-v2", src="auto-chain")

    def fake_run_suite(ctx, model=None, only=None):
        rows = _rows({f"t{i}": True for i in range(10)}, model)
        if model == "bee4b-v2":
            rows.append({"id": "cloud_task", "ok": False, "skipped": False,
                         "model": model, "seconds": 1.0, "ts": "2026-10-17T00:00:00",
                         "repeat": 1, "expect": None, "output_excerpt": "",
                         "error": "litellm.RateLimitError: 429 Too Many Requests"})
        return rows
    monkeypatch.setattr("bee.evals.runner.run_suite", fake_run_suite)
    assert gate.set_baseline(env["ctx"], "bee4b")["ok"]
    r = gate.model_quality_gate(env["ctx"], margin=1)
    assert not r["ok"] and r.get("void"), r
    assert env["gate_candidate"].exists()                  # retry later


def test_explicit_candidate_never_consumes_the_queue(env, monkeypatch):
    """`/gate other-model` evaluates the operator's choice; the queued artifact
    is a DIFFERENT candidate and must survive for its own attempt."""
    gate.queue_candidate("bee4b-v3", src="auto-chain")
    _fake_suite({"bee4b": {**{f"t{i}": True for i in range(10)}, "t9": False},
                 "bee4b-v2": {f"t{i}": True for i in range(10)}}, monkeypatch)
    r = gate.model_quality_gate(env["ctx"], candidate="bee4b-v2", margin=1)
    assert r["ok"] and r.get("promoted") == "bee4b-v2", r
    assert gate.pending_candidate() == "bee4b-v3"          # untouched


def test_adjudication_flips_a_flaky_verdict(env, monkeypatch):
    """P0-5: at n=21, one flaky task could flip a verdict either way (the live
    2026-10-17 run sat inside ±2-3 stochastic noise). Tasks the two arms
    DISAGREE on are re-run per side and a majority decides: a single flaky
    fail is no longer a structural regression. margin=0 so the promotion
    condition stays reachable on an identical task set: the flipped task is
    the decider."""
    calls = []

    def fake_run_suite(ctx, model=None, only=None):
        calls.append((model, list(only) if only else None))
        if only:      # adjudication re-runs of the disputed task all pass
            return _rows({tid: True for tid in only}, model)
        per = {f"t{i}": True for i in range(10)}
        if model == "bee4b-v2":
            per = {**per, "t1": False}   # flaky t1 fail; adjudication must flip it
        return _rows(per, model)
    monkeypatch.setattr("bee.evals.runner.run_suite", fake_run_suite)
    assert gate.set_baseline(env["ctx"], "bee4b")["ok"]
    r = gate.model_quality_gate(env["ctx"], candidate="bee4b-v2", margin=0)
    assert r["ok"] and r.get("promoted") == "bee4b-v2", r
    reruns = [c for c in calls if c[1] is not None]
    assert reruns and all(c[1] == ["t1"] for c in reruns), calls
    assert len(reruns) == 4                                # 2 rounds × 2 sides
    data = gate.load_baselines()
    assert data["models"]["bee4b-v2"]["per_task"]["t1"] is True    # majority vote


def test_adjudication_rounds_zero_restores_single_shot(env, monkeypatch):
    env["cfg"].model_gate.adjudication_rounds = 0
    calls = []

    def fake_run_suite(ctx, model=None, only=None):
        calls.append((model, only))
        per = {f"t{i}": True for i in range(10)}
        if model == "bee4b-v2":
            per = {**per, "t1": False}
        return _rows(per, model)
    monkeypatch.setattr("bee.evals.runner.run_suite", fake_run_suite)
    assert gate.set_baseline(env["ctx"], "bee4b")["ok"]
    r = gate.model_quality_gate(env["ctx"], candidate="bee4b-v2", margin=1)
    assert not r["ok"] and r["regressed"] == ["t1"]        # single-shot verdict
    assert all(o is None for _, o in calls)                # no re-runs at all


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
