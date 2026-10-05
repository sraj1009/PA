"""BEE command system + Phase-4 hot-path regression tests.

Covers:
- config.yaml -> Config round-trip (voice.tts_voice regression: startup TypeError)
- command registry completeness + dispatch contract (unknown -> None)
- smalltalk fast path (greetings answered in 0 ms, zero LLM calls)
- guard ALLOW path executes the tool (UnboundLocalError res_v regression)
- guard DENY path never executes
- BEE persona present in the system prompt
- reflection skipped for trivial tasks (no wasted local-model calls)
- /plan add/list/done + Eisenhower classify (no LLM)
- /draft /code /think /summarize deterministic fallbacks (dead client)

Run:  python -m pytest tests/test_commands.py -q
"""
from __future__ import annotations

import pytest

from bee import commands as cmdreg
from bee import paths as bee_paths
from bee.agent import reflection, router
from bee.agent.context import Context, build_system_prompt
from bee.agent.loop import AgentResult, run_agent
from bee.config import load_config


class StubClient:
    """Scripted LLMClient stand-in — no network, no model."""

    def __init__(self, script=None):
        self.calls = 0
        self.script = script or []

    def models_list(self):
        return ["stub"]

    def _has_ollama(self):
        return True

    def chat(self, name, messages, tools=None, **kw):
        self.calls += 1
        if self.calls <= len(self.script):
            return self.script[self.calls - 1]
        return {"content": "Done.", "tool_calls": [], "usage": {"prompt": 5, "completion": 5}}


class DeadClient(StubClient):
    """Always fails — forces the deterministic fallbacks."""

    def chat(self, name, messages, tools=None, **kw):
        raise RuntimeError("model unreachable (test)")


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
    c.client = StubClient()
    c.episodes_on = False  # never pollute real training data
    return c


# ------------------------------------------------------------------ config
def test_config_loads_voice_tts_voice():
    """Regression: config.yaml declares voice.tts_voice — Config must accept it."""
    cfg = load_config()
    assert hasattr(cfg.voice, "tts_voice")


# ------------------------------------------------------------------ registry
def test_registry_has_all_core_commands():
    for name in ("plan", "draft", "summarize", "code", "think"):
        c = cmdreg.get(name)
        assert c is not None, f"missing command: {name}"
        assert c.usage and c.description


def test_registry_dispatch_unknown_returns_none(ctx):
    assert cmdreg.run(ctx, "nosuchcmd xyz") is None


# ------------------------------------------------------------------ smalltalk
@pytest.mark.parametrize("phrase", ["hi", "hello", "thanks", "bye", "ok", "good morning"])
def test_smalltalk_routes_deterministic(phrase):
    cfg = load_config()
    r = router.route(phrase, cfg)
    assert r["name"] == "smalltalk", (phrase, r)
    assert r["source"] == "deterministic"
    assert r.get("smalltalk_reply")


def test_substantive_task_not_smalltalk():
    cfg = load_config()
    assert router.route("hi, can you write a python script?", cfg)["name"] != "smalltalk"
    assert router.route("2+2*3", cfg)["name"] == "det"


def test_smalltalk_never_calls_llm(ctx):
    res = run_agent(ctx, "hi")
    assert res.ok
    assert ctx.client.calls == 0
    assert res.model == "deterministic"


# ------------------------------------------------------------- guard paths
def test_guard_allow_executes_tool(ctx):
    """Regression: UnboundLocalError (res_v) when the guard ALLOWED an exec tool."""
    ctx.client = StubClient(script=[
        {"content": "", "tool_calls": [
            {"id": "c1", "name": "shell", "arguments": {"command": "echo bee-guard-ok"}}],
         "usage": {"prompt": 5, "completion": 5}},
        {"content": "Ran it — output: bee-guard-ok", "tool_calls": [],
         "usage": {"prompt": 5, "completion": 5}},
    ])
    res = run_agent(ctx, "run this exactly: echo bee-guard-ok")
    assert res.ok, res.error
    assert res.tool_calls == 1
    assert "bee-guard-ok" in res.output


def test_guard_deny_never_executes(ctx):
    events = []
    ctx.client = StubClient(script=[
        {"content": "", "tool_calls": [
            {"id": "c1", "name": "shell", "arguments": {"command": "rm -rf /"}}],
         "usage": {"prompt": 5, "completion": 5}},
    ])
    res = run_agent(ctx, "delete everything", on_event=events.append)
    assert res.ok
    g = [e for e in events if e.get("type") == "guard"]
    assert g and g[0]["action"] == "deny"
    tr = [e for e in events if e.get("type") == "tool_result"]
    assert tr and tr[0]["ok"] is False


# ------------------------------------------------------------------ persona
def test_persona_in_system_prompt(ctx):
    sp = build_system_prompt(ctx)
    assert "Persona" in sp
    assert "No greetings" in sp


# ------------------------------------------------------------------ reflection
def test_reflection_skips_trivial_tasks():
    r = AgentResult(output="Ready.", model="deterministic", ok=True)
    assert reflection.reflect(None, "hi", r) == ""
    r2 = AgentResult(output="ok", model="local", ok=True, iterations=1)
    assert reflection._trivial(r2, "write a quick note") is True
    r3 = AgentResult(output="ok", model="local", ok=True, iterations=1, tool_calls=1)
    assert reflection._trivial(r3, "write a quick note") is False


# ------------------------------------------------------------------ /plan
def test_plan_classify_eisenhower():
    from bee.commands.plan import classify
    assert classify("fix the client outage", "2026-10-05") == "P1"   # urgent + important
    assert classify("prepare Q1 strategy review") == "P2"             # important only
    assert classify("water the plants") == "P4"                       # neither


def test_plan_add_list_done(ctx):
    out = cmdreg.run(ctx, 'plan add "Ship BEE v1" due 2026-12-31 P1')
    assert out is not None and not out.startswith("ERROR")
    assert "t1" in out
    out = cmdreg.run(ctx, "plan list")
    assert "Ship BEE v1" in out
    out = cmdreg.run(ctx, "plan done t1")
    assert out.startswith("Marked 1 done")
    out = cmdreg.run(ctx, "plan list")
    assert "No open tasks" in out


# ------------------------------------------------------------------ /draft
def test_draft_extract_deterministic_fallback(ctx):
    ctx.client = DeadClient()
    out = cmdreg.run(ctx,
                     "draft extract We decided to launch on Friday. Raj to send the invoice. "
                     "Action: I must review the contract. Follow-up call next Tuesday.")
    assert not out.startswith("ERROR")
    for sec in ("Key decisions", "Action items", "Owners", "Follow-ups"):
        assert sec in out
    assert "Raj" in out


def test_draft_email_deterministic_fallback(ctx):
    ctx.client = DeadClient()
    out = cmdreg.run(ctx, "draft email tell the client the milestone slips one week tone: apologetic")
    assert not out.startswith("ERROR")
    assert "Subject" in out
    assert "apologetic" in out


# ------------------------------------------------------------------ /code
def test_code_python_fallback_has_tests(ctx):
    ctx.client = DeadClient()
    out = cmdreg.run(ctx, "code python sort a list of dicts by price")
    assert not out.startswith("ERROR")
    assert "```python" in out
    assert "## Tests" in out


def test_code_lang_detection(ctx):
    from bee.commands.code import _detect_lang
    assert _detect_lang("bash backup my workspace")[0] == "bash"
    assert _detect_lang("a typescript util with an interface")[0] == "typescript"
    assert _detect_lang("node script using console.log")[0] == "javascript"
    assert _detect_lang("just do it")[0] == "python"


def test_code_debug_fallback(ctx):
    ctx.client = DeadClient()
    out = cmdreg.run(ctx, "code debug " + "def f():\n  return 1/0\n" * 3 + "observed error: ZeroDivisionError: division by zero")
    assert not out.startswith("ERROR")
    assert "ZeroDivisionError" in out or "debug" in out.lower()


# ------------------------------------------------------------------ /think
def test_think_fallback_structure(ctx):
    ctx.client = DeadClient()
    out = cmdreg.run(ctx, "think alternatives we will launch a paid tier at $29 with a 14 day trial")
    assert not out.startswith("ERROR")
    assert "Verdict" in out
    assert "Trade-offs" in out
    assert "Strategic alternatives" in out


# --------------------------------------------------------------- /summarize
def test_summarize_fallback_sections(ctx, tmp_path):
    ctx.client = DeadClient()
    body = ("Alpha scored 12 points in the trial and shipped on time. "
            "Beta scored 9 points and missed the deadline by two days. "
            "The cost of Alpha was 5000 dollars while Beta cost 3000 dollars. "
            "Both systems handle the core workload and both passed the security review.")
    out = cmdreg.run(ctx, "summarize " + body)
    assert not out.startswith("ERROR")
    assert "## TL;DR" in out
    assert "## Key points" in out
    assert "Comparative table" in out
