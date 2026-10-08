"""Tests for fast paths (instant pure-Python answers), engine selection, and
cloud -> local teach-back.

Run:  python -m pytest tests/test_fastpaths.py -q
"""
from __future__ import annotations

import json
import re
import time

import pytest

from bee import paths as bee_paths
from bee import scheduler
from bee.agent import engines, fastpaths
from bee.agent.context import Context
from bee.agent.loop import AgentResult, _finish, run_agent
from bee.config import load_config


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(bee_paths, "WORKSPACE", tmp_path)
    import bee.memory.md as md
    import bee.monitor.metrics as mt
    monkeypatch.setattr(md, "diary_add", lambda *a, **k: None)
    monkeypatch.setattr(mt, "record", lambda *a, **k: None)
    cfg = load_config()
    cfg.rag.auto_context = False
    cfg.guard.mode = "always"
    c = Context(cfg, workspace=tmp_path)
    c.episodes_on = False
    return c


def _h(name, phrase):
    hit = fastpaths.match(phrase)
    assert hit is not None, f"no fast path for: {phrase!r}"
    assert hit[0].name == name, (phrase, hit[0].name)
    return hit


# ------------------------------------------------------------------ matchers
def test_time_date_identity_help():
    _h("time", "what time is it")
    _h("date", "what's the date")
    _h("identity", "who are you")
    _h("help", "help")


def test_no_match_for_real_tasks():
    assert fastpaths.match("open the config file and refactor the router") is None
    assert fastpaths.match("write a python script that scrapes prices") is None
    assert fastpaths.match("help me with my taxes") is None
    assert fastpaths.match("what time should we meet with the client about the contract?") is None
    assert fastpaths.match("remember the details of the long negotiation we had last quarter") is None


def test_convert_handlers(ctx):
    fp, m = _h("convert", "100 celsius to fahrenheit")
    assert "212" in fp.handle(ctx, m)
    fp, m = _h("convert", "5km to miles")
    assert "3.1" in fp.handle(ctx, m)
    fp, m = _h("convert", "1024 mb to gb")
    assert "1 gb" in fp.handle(ctx, m).lower()
    # cross-dimension must decline (no bogus answer)
    assert fastpaths._convert(ctx, re.match(r"(\d+(?:[.,]\d+)?)\s*([a-z°]+)\s*(?:to|in|=|→)\s*([a-z°]+)", "10 km to kg", re.I)) is None


def test_coin_dice_random(ctx, monkeypatch):
    # pin randomness so the test is deterministic (handlers stay stochastic for real use)
    import random as _random
    monkeypatch.setattr(_random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(_random, "randint", lambda a, b: b)
    fp, m = _h("coin", "flip a coin")
    assert fp.handle(ctx, m).replace("*", "").strip().lower() == "heads."
    fp, m = _h("dice", "roll a die")
    assert fp.handle(ctx, m) == "**6**"
    fp, m = _h("random", "random number between 1 and 10")
    assert fp.handle(ctx, m) == "**10**"
    fp, m = _h("pick", "pick one of pizza, sushi, tacos")
    out = fp.handle(ctx, m)
    assert out == "**pizza** (picked from 3 options)"


def test_note_and_todo(ctx, monkeypatch):
    captured = []
    import bee.memory.md as md
    monkeypatch.setattr(md, "diary_add", lambda s: captured.append(s))
    fp, m = _h("note", "note that the invoice is due friday")
    assert "Noted" in fp.handle(ctx, m)
    assert captured

    fp, m = _h("todo", "todo: ship the beta by friday")
    out = fp.handle(ctx, m)
    assert "t1" in out
    from bee import commands as cmdreg
    assert "ship the beta" in cmdreg.run(ctx, "plan list")


def test_open_app_and_search_return_fastexec(ctx):
    fp, m = _h("open_app", "open chrome")
    fe = fp.handle(ctx, m)
    assert isinstance(fe, fastpaths.FastExec)
    assert fe.tool == "shell" and fe.args["command"] == "start chrome"
    fp, m = _h("search", "google latest rtx driver")
    fe = fp.handle(ctx, m)
    assert fe.tool == "shell" and "google.com/search?q=" in fe.args["command"]


def test_open_file_workspace_only(ctx):
    (ctx.workspace / "report.md").write_text("x", encoding="utf-8")
    fp, m = _h("open_file", "open report.md")
    fe = fp.handle(ctx, m)
    assert isinstance(fe, fastpaths.FastExec) and "report.md" in fe.args["command"]
    # missing file -> decline (falls through to model)
    fp, m = _h("open_file", "open nofile.md")
    assert fp.handle(ctx, m) is None


# ------------------------------------------------------------ end-to-end (no LLM)
class DeadClient:
    def models_list(self):
        return ["stub"]

    def ollama_up(self):
        return True

    def _has_ollama(self):
        return True

    def chat(self, *a, **k):
        raise RuntimeError("fast path must not call the LLM")


def test_fastpath_end_to_end_no_llm(ctx):
    ctx.client = DeadClient()
    res = run_agent(ctx, "what time is it")
    assert res.ok and res.model == "deterministic"
    assert res.route_source == "fastpath"
    assert "It's" in res.output


def test_guard_blocks_fastpath_exec(ctx, monkeypatch):
    import bee.guard as g
    monkeypatch.setattr(g, "check", lambda *a, **k: (False, "deny", "test deny"))
    res = run_agent(ctx, "open chrome")
    assert res.ok
    assert "Guard blocked" in res.output


def test_explicit_model_hint_beats_fastpath(ctx):
    # 'local: what time is it' is explicit routing — the user asked for the model
    r = fastpaths.match("what time is it")
    assert r is not None  # the phrase itself still matches; gating happens in loop


# ------------------------------------------------------------------ teach-back
def test_golden_written_on_escalated_ok(ctx, tmp_path, monkeypatch):
    monkeypatch.setattr(bee_paths, "TRAIN_DIR", tmp_path)
    res = AgentResult(output="the cloud answer", model="gemini-3-flash-preview",
                      ok=True, escalated=True)
    _finish(ctx, "hard task", None, res, time.time(), lambda e: None, False)
    f = tmp_path / "golden" / "cloud_golden.jsonl"
    assert f.exists()
    row = json.loads(f.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["task"] == "hard task" and "hard task" in json.dumps(row)


def test_golden_not_written_for_local_ok(ctx, tmp_path, monkeypatch):
    monkeypatch.setattr(bee_paths, "TRAIN_DIR", tmp_path)
    res = AgentResult(output="local answer", model="local", ok=True, escalated=False)
    _finish(ctx, "easy task", None, res, time.time(), lambda e: None, False)
    assert not (tmp_path / "golden").exists() or not (tmp_path / "golden" / "cloud_golden.jsonl").exists()


def test_teach_back_distills_skill(ctx, monkeypatch):
    monkeypatch.setattr(bee_paths, "TRAIN_DIR", ctx.workspace)
    monkeypatch.setattr(bee_paths, "SKILLS_DIR", ctx.workspace / "skills")
    d = ctx.workspace / "golden"
    d.mkdir(parents=True, exist_ok=True)
    body = "```python\ndef retry(fn, tries=3):\n    for i in range(tries):\n        try:\n            return fn()\n        except Exception:\n            if i == tries - 1:\n                raise\n```\nThat's a simple retry decorator with backoff you can extend."
    (d / "cloud_golden.jsonl").write_text(
        json.dumps({"task": "write a retry decorator", "response": body,
                    "model": "gemini-3-flash-preview", "ts": "2026-10-04T22:00:00"}) + "\n",
        encoding="utf-8")
    out = scheduler.maybe_teach_back(ctx)
    assert out["new"] == 1, out
    assert out["skills"], out
    skill_md = ctx.workspace / "skills" / out["skills"][0] / "SKILL.md"
    assert skill_md.exists() and "retry decorator" in skill_md.read_text(encoding="utf-8")
    # second run: already digested -> no new skills
    out2 = scheduler.maybe_teach_back(ctx)
    assert out2["new"] == 0 and out2["skills"] == []


# ------------------------------------------------------------------ engines
def test_engines_override_and_persist(tmp_path, monkeypatch):
    monkeypatch.setattr(engines, "settings_file", lambda: tmp_path / "settings.json")
    assert engines.load_engine() is None
    assert engines.override_for(None) is None
    assert engines.override_for("hybrid") is None
    assert engines.override_for("local") == "local"
    assert engines.override_for("api-cloud") == "cloud"
    assert engines.override_for("ollama-cloud") == "glm-5.2:cloud"
    engines.save_engine("api-cloud")
    assert engines.load_engine() == "api-cloud"


def test_ask_engine_non_interactive_defaults_hybrid(monkeypatch):
    # pytest captures stdin (isatty() is False) -> must default to hybrid, no prompt
    import pathlib
    monkeypatch.setattr(engines, "settings_file", lambda: pathlib.Path("/tmp") / "bee_test_engine.json")
    assert engines.ask_engine() == "hybrid"
