"""Pin the single documented routing order: bee/agent/router.py:decide().

Order (first hit wins):

  0. deterministic → 1. explicit → 2. smalltalk → 3. fast-path → 4. ML →
  5. heuristic → 6. escalate

Stage 6 (escalate) needs live service probes, so run_agent applies it right
after decide(); its hybrid/fallback behavior is pinned in test_engine_speed.py
and test_localserver.py.
"""
from __future__ import annotations

import pytest

from bee.agent import router
from bee.config import load_config


@pytest.fixture
def cfg():
    c = load_config()
    c.router.ml_enabled = False          # deterministic tiers under test
    return c


def _d(task, cfg, model=None):
    return router.decide(task, cfg, model)


# ------------------------------------------------------------- 0. deterministic
def test_deterministic_wins_over_everything(cfg):
    # an explicit engine argument cannot beat math
    r = _d("2+2*3", cfg, "cloud")
    assert (r["name"], r["source"]) == ("det", "deterministic")
    assert r["fastpath"] is None
    # the loop strips a typed 'cloud:' prefix BEFORE routing, so the stripped
    # utterance reaches the deterministic tier (raw text is explicit — prefix)
    assert router.strip_cloud_prefix("cloud: 2+2*3").strip() == "2+2*3"
    r = _d("cloud: 2+2*3", cfg)
    assert (r["name"], r["source"]) == ("cloud", "explicit")


# ----------------------------------------------------------------- 1. explicit
def test_explicit_beats_smalltalk_and_fastpath(cfg):
    r = _d("hi", cfg, "cloud")            # session engine override...
    assert (r["name"], r["source"]) == ("cloud", "explicit")
    r = _d("hi", cfg)                     # ...vs the same text without it
    assert r["name"] == "smalltalk"
    r = _d("what time is it", cfg, "cloud")   # explicit wins over the fast path
    assert r["source"] == "explicit" and r["fastpath"] is None
    r = _d("use local", cfg)              # in-text hint is explicit too
    assert (r["name"], r["source"]) == ("local", "explicit")


# ---------------------------------------------------------------- 2. smalltalk
def test_smalltalk_precedes_fastpath(cfg):
    r = _d("hello", cfg)
    assert r["name"] == "smalltalk" and r["smalltalk_reply"]
    assert r["fastpath"] is None


# ---------------------------------------------------------------- 3. fast-path
def test_fastpath_claims_before_ml_and_heuristic(cfg):
    r = _d("what time is it", cfg)
    assert r["fastpath"] is not None
    assert r["fastpath"][0].name == "time"
    # the heuristic tier still classified the task (local) — the fast path
    # preempts its execution, it does not rewrite the tier decision
    assert r["source"] == "heuristic"


# ----------------------------------------------------------------------- 4. ML
def test_ml_after_fastpath_and_complexity_floor(cfg, monkeypatch):
    cfg.router.ml_enabled = True
    cfg.cloud.enabled, cfg.cloud.llm = True, (cfg.cloud.llm or "test-model")
    from bee.brain import mlrouter

    def fake_predict(t, min_conf=0.0):
        return ("local", 0.9) if "research report" in t.lower() else ("cloud", 0.9)

    monkeypatch.setattr(mlrouter, "predict", fake_predict)
    # ML decides the tier, but a fast path is still reported alongside it
    r = _d("what time is it", cfg)
    assert (r["name"], r["source"]) == ("cloud", "ml")
    assert r["fastpath"] is not None and r["fastpath"][0].name == "time"
    # ML may not demote a structurally complex task (complexity floor)
    big = ("Write a comprehensive in-depth research report; architect a system, "
           "first gather, then model, then evaluate. " + "x" * 400)
    r = _d(big, cfg)
    assert (r["name"], r["source"]) == ("cloud", "complexity")


# ---------------------------------------------------------------- 5. heuristic
def test_heuristic_is_the_last_tier(cfg):
    r = _d("please tidy up my workspace when you get a chance", cfg)
    assert (r["name"], r["source"]) == ("local", "heuristic")
    assert r["fastpath"] is None


# ------------------------------------------- the loop calls exactly one entry
def test_run_agent_uses_decide_as_the_only_routing_entry(tmp_path, monkeypatch):
    from bee import paths as bee_paths
    from bee.agent.context import Context
    from bee.agent.loop import run_agent
    import bee.memory.md as md
    import bee.monitor.metrics as mt

    monkeypatch.setattr(bee_paths, "WORKSPACE", tmp_path)
    monkeypatch.setattr(md, "diary_add", lambda *a, **k: None)
    monkeypatch.setattr(mt, "record", lambda *a, **k: None)
    c = load_config()
    c.rag.auto_context = False
    c.guard.mode = "always"
    c.router.ml_enabled = False
    ctx = Context(c, workspace=tmp_path)
    ctx.episodes_on = False

    calls = []
    real = router.decide

    def spy(task, cfg2, model=None):
        calls.append((task, model))
        return real(task, cfg2, model)

    monkeypatch.setattr(router, "decide", spy)
    res = run_agent(ctx, "what time is it")
    assert res.ok and res.route_source == "fastpath", (res.output, res.route_source)
    assert len(calls) == 1 and calls[0][0] == "what time is it", calls
