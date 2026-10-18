"""P1-6 — the self-directed practice job (`bee.practice`).

Hermetic: fake clients/agents, redirected paths from the suite fixture, no
network, no model. The fences are pinned as hard as the happy path: idle-only,
local-only, unattended guard, memory-shaped tasks dropped, and episodes that
are tagged `practice` while staying quiet in the user-facing surfaces.
"""
from __future__ import annotations

import json
import time
from types import SimpleNamespace

from bee import practice as pr
from bee.agent.context import Context


class _Client:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def chat(self, model, messages, **kw):
        self.calls.append((model, messages))
        return {"content": self.reply}


def _ctx(reply, tmp_path):
    return Context(cfg=SimpleNamespace(), workspace=tmp_path, client=_Client(reply))


def _quiet(monkeypatch):
    monkeypatch.setattr(pr, "_user_active", lambda: None)
    monkeypatch.setattr(pr, "_gpu_busy", lambda: False)


def test_variations_parse_json_and_filter_unsafe():
    text = ('```json\n["Write a python function that merges two sorted lists.", '
            '"cloud: do the thing", "remember my api key", '
            '"Run the shell command \'git reset --hard HEAD~1\' again.", '
            '"Use cloud storage to write a summary for my notes.", '
            '"Open Chrome and search for example.com.", '
            '"Delete a duplicate value from a sorted list in python.", '
            '"Write a python function that merges two sorted lists.", '
            '"Use the calculator tool to compute 17 * 23."]\n```')
    out = pr._parse_variations(text, 5)
    assert out == ["Write a python function that merges two sorted lists.",
                   "Delete a duplicate value from a sorted list in python.",
                   "Use the calculator tool to compute 17 * 23."]


def test_variations_prose_fallback_numbered_lines():
    out = pr._parse_variations(
        "1. Compute the GCD of 84 and 126 with the calculator tool.\n"
        "2. - Sort [3, 1, 2] by writing a small python snippet.\n", 5)
    assert out == ["Compute the GCD of 84 and 126 with the calculator tool.",
                   "Sort [3, 1, 2] by writing a small python snippet."]


def test_run_defers_when_user_active(monkeypatch):
    rec = []
    monkeypatch.setattr(pr, "_user_active", lambda: 60.0)
    monkeypatch.setattr(pr, "_gpu_busy", lambda: False)
    monkeypatch.setattr(pr.metrics, "record", lambda e, **d: rec.append((e, d)))
    out = pr.run(SimpleNamespace())
    assert out["skipped"].startswith("user active") and out["attempts"] == 0
    assert rec and rec[0][0] == pr.EVENT and "user active" in rec[0][1]["skipped"]


def test_run_defers_when_gpu_busy(monkeypatch):
    monkeypatch.setattr(pr, "_user_active", lambda: None)
    monkeypatch.setattr(pr, "_gpu_busy", lambda: True)
    monkeypatch.setattr(pr.metrics, "record", lambda e, **d: None)
    out = pr.run(SimpleNamespace())
    assert out["skipped"] == "gpu busy" and out["attempts"] == 0


def test_run_builds_a_client_when_the_ctx_has_none(monkeypatch, tmp_path):
    """The nightly job's ctx can be cold; the variation call must still work."""
    import bee.agent.client as client_mod

    made = []

    class FakeLLM:
        def __init__(self, cfg):
            made.append(cfg)

        def chat(self, model, messages, **kw):
            return {"content": '["Practice one with the calculator."]'}

    monkeypatch.setattr(client_mod, "LLMClient", FakeLLM)
    _quiet(monkeypatch)
    monkeypatch.setattr(pr, "_failing_eval_tasks", lambda: ["task A (failed)"])
    monkeypatch.setattr(pr, "_failed_episode_tasks", lambda: [])
    monkeypatch.setattr(pr, "run_agent",
                        lambda ctx, task, **kw: SimpleNamespace(ok=True, verify="pass"))
    monkeypatch.setattr(pr.metrics, "record", lambda e, **d: None)
    cfg = SimpleNamespace()
    ctx = Context(cfg=cfg, workspace=tmp_path)          # client=None
    out = pr.run(ctx)
    assert made == [cfg] and out["attempts"] == 1


def test_run_attempts_variations_locally_and_counts_clean(monkeypatch, tmp_path):
    _quiet(monkeypatch)
    monkeypatch.setattr(pr, "_failing_eval_tasks", lambda: [
        "task A (failed)", "Run git reset --hard HEAD~1 on the repo"])
    monkeypatch.setattr(pr, "_failed_episode_tasks", lambda: [])
    seen = []

    def fake_run_agent(ctx, task, **kw):
        seen.append((task, ctx.practice, ctx.guard_mode, kw.get("model")))
        ok = "one" in task
        return SimpleNamespace(ok=ok, verify=("pass" if ok else "fail"))

    monkeypatch.setattr(pr, "run_agent", fake_run_agent)
    rec = []
    monkeypatch.setattr(pr.metrics, "record", lambda e, **d: rec.append((e, d)))
    ctx = _ctx('["Practice one with the calculator.", "Practice two numbers."]',
               tmp_path)
    out = pr.run(ctx)
    assert out["sources"] == 1 and out["variations"] == 2
    assert out["attempts"] == 2 and out["ok"] == 1 and out["clean"] == 1
    assert seen == [("Practice one with the calculator.", True, "unattended", "local"),
                    ("Practice two numbers.", True, "unattended", "local")]
    assert rec[-1][1]["clean"] == 1 and rec[-1][1]["seconds"] >= 0
    assert ctx.client.calls and ctx.client.calls[0][0] == "local"


def test_run_stops_when_user_returns_mid_run(monkeypatch, tmp_path):
    seq = [None, None, 5.0]     # gate, first loop check, second loop check
    calls = {"i": 0}

    def active():
        i = calls["i"]
        calls["i"] += 1
        return seq[i] if i < len(seq) else 5.0

    monkeypatch.setattr(pr, "_user_active", active)
    monkeypatch.setattr(pr, "_gpu_busy", lambda: False)
    monkeypatch.setattr(pr, "_failing_eval_tasks", lambda: ["task A (failed)"])
    monkeypatch.setattr(pr, "_failed_episode_tasks", lambda: [])
    monkeypatch.setattr(pr, "run_agent",
                        lambda ctx, task, **kw: SimpleNamespace(ok=True, verify="pass"))
    monkeypatch.setattr(pr.metrics, "record", lambda e, **d: None)
    ctx = _ctx('["Practice alpha one.", "Practice beta two."]', tmp_path)
    out = pr.run(ctx)
    assert out["attempts"] == 1 and out["skipped"] == "user returned mid-run"


def test_user_active_ignores_practice_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(pr.paths, "EPISODES_DIR", tmp_path)
    now = time.time()
    rows = [
        {"ts": now - 3600, "seconds": 2, "tag": "practice"},
        {"ts": now - 60, "seconds": 2, "tag": ""},
    ]
    f = tmp_path / "day.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert pr._user_active() is not None and pr._user_active() < 120
    rows[1]["tag"] = "practice"
    f.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert pr._user_active() is None


def test_failed_episode_sources_keep_only_verifiable_families(monkeypatch):
    """A failed desktop/web episode makes bad practice material — unattended
    practice must be self-verifiable and side-effect-free."""
    import bee.pipeline.build_sft as bs

    rows = [
        {"ok": False, "task": "Compute the GCD of 84 and 126.",
         "events": [{"tool": "calculator"}]},
        {"ok": False, "task": "Open Chrome and search for example.com",
         "events": [{"tool": "computer_input"}]},
        {"ok": False, "task": "Search the web for today's news",
         "events": [{"tool": "web_search"}]},
        {"ok": True, "task": "passing task", "events": []},
        {"ok": False, "task": "Write a python function that merges lists.",
         "events": [{"tool": "code_run"}]},
    ]
    monkeypatch.setattr(bs, "load_episodes", lambda: rows)
    assert pr._failed_episode_tasks(cap=5) == [
        "Write a python function that merges lists.",
        "Compute the GCD of 84 and 126."]


def test_finish_is_quiet_for_practice_but_normal_otherwise(monkeypatch):
    from bee.agent import episode_metrics as em
    from bee.agent.result import AgentResult
    from bee.episodes.logger import Episode
    import bee.memory.md as mdmod

    diaries, wins = [], []
    monkeypatch.setattr(em, "diary", lambda t, r: diaries.append(t))
    monkeypatch.setattr(mdmod, "record_win", lambda t, o: wins.append(t))
    rec = []
    monkeypatch.setattr(em.metrics, "record", lambda e, **d: rec.append((e, d)))
    res = AgentResult(output="done", ok=True, tool_calls=2, model="local")
    cfg = SimpleNamespace(get_llm=lambda n: {})

    em.finish(SimpleNamespace(practice=True, cfg=cfg), "practice task",
              Episode("practice task", model="local"),
              res, time.time(), lambda e: None, False)
    assert diaries == [] and wins == [] and rec[-1][1]["practice"] is True

    em.finish(SimpleNamespace(practice=False, cfg=cfg), "user task",
              Episode("user task", model="local"),
              res, time.time(), lambda e: None, False)
    assert diaries == ["user task"] and wins == ["user task"]
    assert rec[-1][1]["practice"] is False


def test_end_to_end_practice_run_is_tagged_and_quiet(monkeypatch, tmp_path):
    """One REAL loop pass (deterministic task, no model) with practice=True:
    the episode is tagged, diary/win stay silent. The control keeps normal
    behaviour — this is the A38-style proof that the flag gates only the
    practice path."""
    from bee.agent import episode_metrics as em
    from bee.agent import loop as agent_loop
    from bee.config import load_config
    import bee.memory.md as mdmod

    monkeypatch.setattr(pr.paths, "EPISODES_DIR", tmp_path / "episodes")
    diaries, wins = [], []
    monkeypatch.setattr(em, "diary", lambda t, r: diaries.append(t))
    monkeypatch.setattr(mdmod, "record_win", lambda t, o: wins.append(t))
    monkeypatch.setattr(em.metrics, "record", lambda e, **d: None)

    def rows():
        return [json.loads(l) for f in (tmp_path / "episodes").glob("*.jsonl")
                for l in f.read_text(encoding="utf-8").splitlines()]

    cfg = load_config()
    pctx = Context(cfg=cfg, workspace=tmp_path, practice=True, guard_mode="unattended")
    res = agent_loop.run_agent(pctx, "12 + 30")
    assert res.ok and res.model == "deterministic"
    assert diaries == [] and wins == []
    assert rows()[-1]["tag"] == "practice" and rows()[-1]["task"] == "12 + 30"

    uctx = Context(cfg=cfg, workspace=tmp_path)
    agent_loop.run_agent(uctx, "7 + 8")
    assert diaries == ["7 + 8"]
    assert rows()[-1]["tag"] == ""


def test_practice_is_a_registered_system_job():
    from bee import scheduler
    assert "practice" in scheduler._SYSTEM_JOB_IDS
    from bee.automation.worker import FUNCTIONS
    assert "bee.practice.run" in FUNCTIONS
    # the parity pins in tests/test_audit_fixes.py prove the specs list and the
    # worker allowlist both match this registry in either direction
