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

    def ollama_up(self):
        return True

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
    from datetime import date, timedelta

    from bee.commands.plan import classify
    # urgent = due today or tomorrow — compute it, don't hard-code a date
    due_tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert classify("fix the client outage", due_tomorrow) == "P1"    # urgent + important
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


# ============================ /remind (durable reminders) ====================
# Time parsing is deterministic, and a reminder is exactly one durable notify job
# on the SAME store/worker as every other job — no second scheduler, no LLM call.
def test_remind_creates_one_durable_job(tmp_path):
    import sys
    from datetime import datetime, timedelta, timezone
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from test_automation import FakeKernel, Ctx, FakeClock, make_worker
    from bee import commands as reg

    tz = timezone(timedelta(hours=5, minutes=30))
    clock = FakeClock(datetime(2026, 10, 8, 19, 5, tzinfo=tz))
    w = make_worker(tmp_path, FakeKernel(Ctx(), "ok"), clock)
    ctx = type("C", (), {"automation_worker": w, "cfg": None})()

    out = reg.run(ctx, "/remind call the bank tomorrow 9am")
    assert "Reminder set" in out and "call the bank" in out, out
    jobs = [j for j in w.jobs() if j.owner == "reminder"]
    assert len(jobs) == 1
    j = jobs[0]
    assert j.action["type"] == "notify" and j.action["message"] == "Reminder: call the bank"
    assert j.trigger.kind == "one_time"
    # 9 AM IST tomorrow == 03:30 UTC; the store keeps stamps canonically in UTC
    assert j.next_run == "2026-10-09T03:30:00+00:00", j.next_run
    assert j.timezone == w.default_timezone
    # durable means it survives the process: reload the store from disk
    from bee.automation.store import JobStore
    reloaded = [x for x in JobStore(tmp_path / "automation").load_all_jobs()
                if x.owner == "reminder"]
    assert len(reloaded) == 1 and reloaded[0].id == j.id
    assert reloaded[0].next_run == j.next_run and reloaded[0].state == "pending"


def test_remind_relative_time_and_text_preservation(tmp_path):
    import sys
    from datetime import datetime, timedelta, timezone
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from test_automation import FakeKernel, Ctx, FakeClock, make_worker
    from bee import commands as reg

    tz = timezone(timedelta(hours=5, minutes=30))
    w = make_worker(tmp_path, FakeKernel(Ctx(), "ok"),
                    FakeClock(datetime(2026, 10, 8, 19, 5, tzinfo=tz)))
    ctx = type("C", (), {"automation_worker": w, "cfg": None})()
    out = reg.run(ctx, "/remind pay the client -- urgent -- in 20 min")
    j = [x for x in w.jobs() if x.owner == "reminder"][0]
    assert "Reminder set" in out
    assert "pay the client" in j.action["message"] and "urgent" in j.action["message"]
    assert j.next_run == "2026-10-08T13:55:00+00:00", j.next_run   # 19:25 IST


def test_remind_uses_the_worker_clock_not_the_wall_clock(tmp_path):
    """Regression: a reminder is measured against the scheduler's own notion of
    now. If the handler read datetime.now() instead, "in 10 min" would be ten
    minutes after the REAL instant and disagree with the tick that decides
    whether the job is already late."""
    import sys
    from datetime import datetime, timedelta, timezone
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from test_automation import FakeKernel, Ctx, FakeClock, make_worker
    from bee import commands as reg

    tz = timezone(timedelta(hours=5, minutes=30))
    w = make_worker(tmp_path, FakeKernel(Ctx(), "ok"),
                    FakeClock(datetime(2027, 3, 4, 10, 0, tzinfo=tz)))
    ctx = type("C", (), {"automation_worker": w, "cfg": None})()
    reg.run(ctx, "/remind submit the report in 10 min")
    j = [x for x in w.jobs() if x.owner == "reminder"][0]
    assert j.next_run == "2027-03-04T04:40:00+00:00", j.next_run   # 10:10 IST


def test_remind_list_and_cancel(tmp_path):
    import sys
    from datetime import datetime, timedelta, timezone
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from test_automation import FakeKernel, Ctx, FakeClock, make_worker
    from bee import commands as reg

    tz = timezone(timedelta(hours=5, minutes=30))
    w = make_worker(tmp_path, FakeKernel(Ctx(), "ok"),
                    FakeClock(datetime(2026, 10, 8, 9, 0, tzinfo=tz)))
    ctx = type("C", (), {"automation_worker": w, "cfg": None})()
    reg.run(ctx, "/remind water the plants at 18:00")
    reg.run(ctx, "/remind stretch in 45 minutes")
    listing = reg.run(ctx, "/remind list")
    assert listing.count("Reminder") >= 2 and "when (local)" in listing
    ident = [j for j in w.jobs() if j.owner == "reminder"][0].id
    assert "Cancelled" in reg.run(ctx, "/remind cancel " + ident[-6:])
    assert "Cancelled" in reg.run(ctx, "/remind cancel all")
    assert "No reminders" in reg.run(ctx, "/remind list")


def test_remind_reports_errors_rather_than_raising(tmp_path):
    from bee import commands as reg
    from types import SimpleNamespace
    ctx = SimpleNamespace(automation_worker=None, cfg=None)
    out = reg.run(ctx, "/remind call mom tomorrow")
    assert out.startswith("ERROR:") and "automation" in out.lower()


def test_remind_without_a_time_asks_instead_of_guessing(tmp_path):
    import sys
    from datetime import datetime, timedelta, timezone
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from test_automation import FakeKernel, Ctx, FakeClock, make_worker
    from bee import commands as reg

    tz = timezone(timedelta(hours=5, minutes=30))
    w = make_worker(tmp_path, FakeKernel(Ctx(), "ok"),
                    FakeClock(datetime(2026, 10, 8, 9, 0, tzinfo=tz)))
    ctx = type("C", (), {"automation_worker": w, "cfg": None})()
    out = reg.run(ctx, "/remind call my mother")
    assert out.startswith("ERROR:")
    assert "tomorrow" in out.lower()          # it shows the usage line instead
    assert [j for j in w.jobs() if j.owner == "reminder"] == []


def test_remind_is_registered_and_documented():
    from bee import commands as reg
    assert "remind" in reg.COMMANDS
    assert "/remind" in reg.help_text()
    cmd = reg.COMMANDS["remind"]
    assert cmd.description and cmd.usage.startswith("/remind")


def _reminder_worker(tmp_path, clock, ctx):
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from test_automation import FakeKernel, make_worker
    return make_worker(tmp_path, FakeKernel(ctx, "ok"), clock, ctx=ctx)


def _syspath():
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))


def test_remind_coming_due_reaches_the_desktop(tmp_path, monkeypatch):
    """Delivery, not bookkeeping: a reminder whose time has come must raise an
    OS toast. The toast gate used to cover only failure/missed, so every notify
    job reported 'succeeded' into the store and the log while the user waited."""
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    _syspath()
    from test_automation import Ctx, FakeClock
    from bee import commands as reg
    from bee.monitor import alerts

    toasts: list[tuple] = []
    monkeypatch.setattr(alerts, "os_notify",
                        lambda title, text: toasts.append((title, text)) or True)

    tz = timezone(timedelta(hours=5, minutes=30))
    clock = FakeClock(datetime(2026, 10, 8, 19, 5, tzinfo=tz))
    ctx = Ctx()
    ctx.cfg = SimpleNamespace(alerts=SimpleNamespace(enabled=True))
    w = _reminder_worker(tmp_path, clock, ctx)
    reg.run(ctx, "/remind stretch in 5 minutes")
    j = [x for x in w.jobs() if x.owner == "reminder"][0]
    assert j.state == "pending" and not toasts

    clock.advance(minutes=6)
    assert j.id in w.tick()                      # the scheduler picked it up
    assert w.wait_idle(5.0)
    assert toasts, "reminder came due and nothing reached the desktop"
    assert len(toasts) == 1, f"one reminder must be exactly one popup: {toasts}"
    title, text = toasts[0]
    assert title == "BEE reminder" and "stretch" in text, toasts
    assert w.store.load_job(j.id).state == "completed"


def test_remind_respects_alerts_switch(tmp_path, monkeypatch):
    """cfg.alerts.enabled=false is the user's opt-out from desktop popups —
    the record still lands in the store (and shows in /auto)."""
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    _syspath()
    from test_automation import Ctx, FakeClock
    from bee import commands as reg
    from bee.monitor import alerts

    toasts: list[tuple] = []
    monkeypatch.setattr(alerts, "os_notify",
                        lambda title, text: toasts.append((title, text)) or True)

    tz = timezone(timedelta(hours=5, minutes=30))
    clock = FakeClock(datetime(2026, 10, 8, 19, 5, tzinfo=tz))
    ctx = Ctx()
    ctx.cfg = SimpleNamespace(alerts=SimpleNamespace(enabled=False))
    w = _reminder_worker(tmp_path / "off", clock, ctx)
    reg.run(ctx, "/remind stretch in 5 minutes")
    j = [x for x in w.jobs() if x.owner == "reminder"][0]
    clock.advance(minutes=6)
    w.tick()
    assert w.wait_idle(5.0)
    assert toasts == []
    assert any(n.job_id == j.id for n in w.store.load_notifications())


def test_parse_when_table():
    from datetime import datetime, timedelta, timezone
    from bee.commands.remind import parse_when
    now = datetime(2026, 10, 8, 19, 5, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    cases = {
        "call the bank tomorrow 9am": ("call the bank", (2026, 10, 9, 9, 0)),
        "pay client in 20 min": ("pay client", (2026, 10, 8, 19, 25)),
        "water the plants 18:00": ("water the plants", (2026, 10, 9, 18, 0)),
        "file the taxes 2026-10-12 07:30": ("file the taxes", (2026, 10, 12, 7, 30)),
        "review contract friday 4pm": ("review contract", (2026, 10, 9, 16, 0)),
        "gym tonight": ("gym", (2026, 10, 8, 20, 0)),
        "renew passport day after tomorrow at 11:30": ("renew passport",
                                                       (2026, 10, 10, 11, 30)),
        "submit expense 12 Oct 09:00": ("submit expense", (2026, 10, 12, 9, 0)),
    }
    for text, (want_rest, want_dt) in cases.items():
        dt, rest = parse_when(text, now)
        assert dt is not None, text
        assert (dt.year, dt.month, dt.day, dt.hour, dt.minute) == want_dt, (text, dt)
        assert rest == want_rest, (text, rest)
    for text in ("call mom", "do the thing later"):
        dt, rest = parse_when(text, now)
        assert dt is None, f"{text!r} invented a date: {dt}"
