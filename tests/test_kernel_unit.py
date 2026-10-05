"""Kernel unit tests (Phase 2): state machine, planning, permissions,
cancellation, retries, receipts, verification, conversation continuity,
tool registration, unknown tools, malformed arguments.

Run:  python -m pytest tests/test_kernel_unit.py -q
"""
from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path

import pytest

from bee.kernel import (AgentSession, Action, EventBus, ExecutionReceipt,
                        InvalidTransitionError, MalformedArgsError, Observation,
                        Plan, ReceiptLog, RetryPolicy, Task, TaskState, ToolBus,
                        ToolDef, UnknownToolError, can_transition, check_effect,
                        permission_decide, task_effect_probe, transition, verify_task)
from bee.kernel.models import AgentEvent, AgentEventKind, FailureKind
from bee.kernel.kernel import AgentKernel


# ----------------------------------------------------------------- state
def test_state_happy_path_full_lifecycle():
    t = Task(text="create a folder called invoices")
    for s in (TaskState.UNDERSTANDING, TaskState.PLANNING, TaskState.EXECUTING,
              TaskState.VERIFYING, TaskState.COMPLETED):
        transition(t, s)
        assert t.state == s
    assert t.state in {x for x in TaskState if x.name in ("COMPLETED",)}


def test_state_waiting_for_permission_round_trip():
    t = Task(text="git push origin main")
    transition(t, TaskState.UNDERSTANDING)
    transition(t, TaskState.PLANNING)
    transition(t, TaskState.WAITING_FOR_PERMISSION)
    assert t.state == TaskState.WAITING_FOR_PERMISSION
    transition(t, TaskState.EXECUTING)
    transition(t, TaskState.VERIFYING)
    transition(t, TaskState.COMPLETED)


def test_invalid_transitions_rejected():
    cases = [
        (TaskState.CREATED, TaskState.COMPLETED),        # no shortcut to done
        (TaskState.CREATED, TaskState.EXECUTING),        # must understand+plan first
        (TaskState.COMPLETED, TaskState.EXECUTING),      # terminal
        (TaskState.FAILED, TaskState.EXECUTING),         # terminal (retries go via RETRYING)
        (TaskState.CANCELLED, TaskState.UNDERSTANDING),  # terminal
        (TaskState.UNDERSTANDING, TaskState.VERIFYING),  # out of order
        (TaskState.PLANNING, TaskState.COMPLETED),       # must execute first
    ]
    for start, end in cases:
        t = Task(text="x")
        t.state = start  # place the task, then demand the illegal move
        with pytest.raises(InvalidTransitionError):
            transition(t, end)
        assert t.state == start, "failed transition must not mutate state"


def test_retrying_path_legal():
    t = Task(text="x")
    for s in (TaskState.UNDERSTANDING, TaskState.PLANNING, TaskState.EXECUTING,
              TaskState.VERIFYING, TaskState.RETRYING, TaskState.EXECUTING,
              TaskState.VERIFYING, TaskState.COMPLETED):
        transition(t, s)
    assert can_transition(TaskState.RETRYING, TaskState.PLANNING)


def test_terminal_states_have_no_exits():
    for term in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
        for other in TaskState:
            assert not can_transition(term, other)


# ----------------------------------------------------------------- planning
def test_plan_structure_and_actions():
    p = Plan(goal="send the invoice",
             steps=[Action(description="compose", tool="file_write", risk="medium",
                           capability="fs.write"),
                    Action(description="verify", risk="low")],
             rationale="two-step")
    d = p.to_dict()
    assert d["goal"] == "send the invoice" and len(d["steps"]) == 2
    assert d["steps"][0]["tool"] == "file_write"
    assert d["steps"][0]["capability"] == "fs.write"


def test_kernel_run_creates_plan_with_verify_step(tmp_path):
    k = _kernel(tmp_path)
    r = k.run("what is 2 plus 2", session_id="u_plan")
    assert r.task.plan is not None
    steps = [s.description for s in r.task.plan.steps]
    assert any("verify" in s.lower() for s in steps)


# ----------------------------------------------------------------- permission
def test_permission_allow_ask_deny():
    a = permission_decide("calculator", {"expression": "1+1"}, mode="unattended")
    assert a.action == "allow" and a.granted
    d = permission_decide("shell", {"command": "rm -rf /tmp/x"}, mode="unattended")
    assert d.action == "deny" and not d.granted and d.reason
    g = permission_decide("shell", {"command": "git push origin main"}, mode="unattended")
    assert not g.granted  # unattended auto-denies asks
    ok = permission_decide("shell", {"command": "git push origin main"}, mode="cli",
                           approver=lambda t, a, r: True)
    assert ok.action == "ask" and ok.granted


def test_permission_risk_metadata():
    d = permission_decide("shell", {"command": "echo hi"}, mode="unattended")
    assert d.risk_level in {"none", "low", "medium", "high", "critical"}
    assert "exec" in d.capabilities or d.capabilities  # capability surfaced


# ----------------------------------------------------------------- cancellation
def test_kernel_cancel_sets_context_event(tmp_path):
    k = _kernel(tmp_path)
    assert isinstance(k.ctx.cancel_event, threading.Event)
    k.cancel()
    assert k.ctx.cancel_event.is_set()


def test_stop_message_cancels_without_running_agent(tmp_path):
    k = _kernel(tmp_path)
    k.run("Remind me to send the invoice", session_id="u_cancel")
    calls_before = len(k.ctx.client.calls)
    r = k.run("stop.", session_id="u_cancel")
    assert r.cancelled is True
    assert r.task.state == TaskState.CANCELLED
    kinds = [e.kind for e in k.events.log]
    assert AgentEventKind.TASK_CANCELLED in kinds
    assert len(k.ctx.client.calls) == calls_before, "cancel must not invoke the LLM"


# ----------------------------------------------------------------- retries
def test_retry_policy_classification():
    p = RetryPolicy()
    assert p.classify("LLM error: 429 quota") == FailureKind.PROVIDER
    assert p.classify("connection timeout") == FailureKind.TRANSIENT
    assert p.classify("blocked by guard: recursive rm", blocked=True) == FailureKind.PERMISSION
    assert p.classify("unknown tool: bogus") == FailureKind.INVALID_INPUT
    assert p.classify("tool raised RuntimeError: boom", tool="shell") == FailureKind.TOOL


def test_retry_policy_never_retries_destructive_or_denied():
    p = RetryPolicy(max_attempts=5)
    assert p.should_retry(FailureKind.PERMISSION, 1) is False
    assert p.should_retry(FailureKind.TOOL, 1, "shell", {"command": "git push origin main"}) is False
    assert p.should_retry(FailureKind.TOOL, 1, "shell", {"command": "rm x.txt"}) is False
    assert p.should_retry(FailureKind.TOOL, 1, "shell", {"command": "ls"}) is True
    assert p.should_retry(FailureKind.TRANSIENT, 5) is False  # attempt budget exhausted


# ----------------------------------------------------------------- receipts
def test_receipt_fields_and_redaction(tmp_path):
    log = ReceiptLog(tmp_path / "receipts.jsonl")
    r = ExecutionReceipt(task_id="t1", session_id="s1", tool="shell",
                         arguments={"command": "export KEY=sk-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"},
                         risk_level="medium", permission="granted",
                         result="ok", verification="unverified", duration=0.5,
                         error="", retry_count=0)
    log.append(r)
    rows = json.loads(log.path.read_text(encoding="utf-8").strip())
    for f in ("task_id", "session_id", "timestamp", "tool", "action", "arguments",
              "risk_level", "permission", "result", "verification", "duration",
              "error", "retry_count"):
        assert f in rows, f"receipt missing field {f}"
    assert "sk-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6" not in log.path.read_text(encoding="utf-8")
    assert len(log.recent(5)) == 1


def test_receipt_log_never_raises(tmp_path):
    log = ReceiptLog(tmp_path / "r.jsonl")
    log.append(ExecutionReceipt(task_id="t", session_id="s", tool="x"))
    log.append(ExecutionReceipt(task_id="t", session_id="s", tool="y",
                                arguments={"v": object()}))  # non-serializable -> str()


# ----------------------------------------------------------------- verification
def _obs(tool, args="", res=""):
    return Observation(tool=tool, args=args if isinstance(args, dict) else {},
                       result_text=res, ok=True)


def test_effect_checks_file_write():
    ws = Path(tempfile.mkdtemp())
    assert check_effect(_obs("file_write", {"path": "a.txt"}), ws).verdict == "fail"
    (ws / "a.txt").write_text("x")
    assert check_effect(_obs("file_write", {"path": "a.txt"}), ws).verdict == "pass"


def test_effect_check_file_edit():
    ws = Path(tempfile.mkdtemp())
    f = ws / "doc.txt"
    f.write_text("hello world")
    assert check_effect(_obs("file_edit", {"path": "doc.txt", "new": "there"}), ws).verdict == "fail"
    f.write_text("there world")
    assert check_effect(_obs("file_edit", {"path": "doc.txt", "new": "there"}), ws).verdict == "pass"


def test_effect_check_mkdir_shell():
    ws = Path(tempfile.mkdtemp())
    assert check_effect(_obs("shell", {"command": "mkdir invoices"}), ws).verdict == "fail"
    (ws / "invoices").mkdir()
    assert check_effect(_obs("shell", {"command": "mkdir invoices"}), ws).verdict == "pass"
    assert check_effect(_obs("shell", {"command": "python train.py"}), ws).verdict == "unverified"


def test_effect_check_calculator_uses_result():
    ws = Path(tempfile.mkdtemp())
    assert check_effect(_obs("calculator", {"expression": "2*21"}, '{"expression": "2*21", "result": 42}'), ws).verdict == "pass"
    assert check_effect(_obs("calculator", {"expression": "x"}, '{"error": "cannot evaluate"}'), ws).verdict == "fail"


def test_verification_failure_when_target_missing():
    ws = Path(tempfile.mkdtemp())
    obs = [Observation(tool="shell", args={"command": "mkdir wrongdir"},
                       ok=True, effect="pass", result_text="")]
    (ws / "wrongdir").mkdir()
    v = verify_task("Create a folder called invoices.", obs, ws, "Done.")
    assert v.verdict == "fail"
    assert any(c["check"].startswith("target_exists") for c in v.checks)


def test_verification_pass_when_target_created():
    ws = Path(tempfile.mkdtemp())
    (ws / "invoices").mkdir()
    obs = [Observation(tool="shell", args={"command": "mkdir invoices"},
                       ok=True, effect="pass", result_text="")]
    assert verify_task("Create a folder called invoices.", obs, ws, "Done.").verdict == "pass"


def test_verification_unverified_for_generic_shell():
    ws = Path(tempfile.mkdtemp())
    obs = [Observation(tool="shell", args={"command": "echo hi"}, ok=True,
                       effect="unverified", result_text="hi")]
    assert verify_task("say hello", obs, ws, "hello").verdict == "unverified"


def test_verification_blocked_is_not_failure():
    ws = Path(tempfile.mkdtemp())
    obs = [Observation(tool="shell", args={"command": "rm -rf /"}, ok=False,
                       effect="not_checked", result_text="guard (recursive rm): command not executed",
                       blocked=True)]
    v = verify_task("delete everything", obs, ws, "I cannot do that — blocked.")
    assert v.verdict == "unverified"  # permission outcome, not execution failure


def test_task_effect_probe():
    assert task_effect_probe("Create a folder called invoices.") == ("dir", "invoices")
    assert task_effect_probe("Make a file named report.pdf") == ("file", "report.pdf")
    assert task_effect_probe("What's the weather?") is None


# ----------------------------------------------------------------- sessions
def test_session_followup_resolution():
    s = AgentSession(id="t")
    s.active_task_text = "Remind me to send the invoice"
    assert s.resolve_followup("Tomorrow.")[0] == "continue"
    merged = s.resolve_followup("Actually make it 10 AM.")[1]
    assert "invoice" in merged and "10 AM" in merged
    assert s.resolve_followup("stop.")[0] == "cancel"
    assert s.resolve_followup("what is the weather in paris")[0] == "new"
    # no active task -> everything is new
    s2 = AgentSession(id="t2")
    assert s2.resolve_followup("Tomorrow.")[0] == "new"


def test_session_persistence_round_trip(tmp_path):
    s = AgentSession(id="persist-test")
    s.add_turn("user", "hello")
    s.active_task_text = "draft the invoice"
    s.entities["last_path"] = "drafts/invoice.md"
    s.pending_confirmation = "send it tomorrow?"
    s.save(tmp_path)
    s2 = AgentSession.load(tmp_path, "persist-test")
    assert s2 is not None
    assert s2.active_task_text == "draft the invoice"
    assert s2.entities["last_path"] == "drafts/invoice.md"
    assert s2.pending_confirmation == "send it tomorrow?"
    assert AgentSession.load(tmp_path, "nope") is None


def test_session_context_block():
    s = AgentSession(id="t")
    s.active_task_text = "draft the invoice for Apex"
    s.last_time_hint = "10 AM"
    s.recent_results.append({"tool": "file_write", "ok": True, "preview": "path: drafts/x.md", "ts": ""})
    b = s.context_block()
    assert "Active task" in b and "10 AM" in b


# ----------------------------------------------------------------- tool bus
def test_toolbus_default_metadata():
    bus = ToolBus().from_default()
    assert len(bus) >= 24
    shell = bus.get("shell")
    assert shell is not None
    assert shell.risk in {"low", "medium", "high", "critical"}
    assert shell.capability  # capability exposed
    assert shell.timeout > 0
    assert shell.cancellation in {"none", "between_steps"}
    web = bus.get("web_fetch")
    assert web.untrusted_output is True


def test_toolbus_unknown_tool_rejected():
    bus = ToolBus().from_default()
    k = _kernel(Path(tempfile.mkdtemp()))
    with pytest.raises(UnknownToolError):
        bus.call(k.ctx, "totally_bogus_tool", {})


def test_toolbus_malformed_arguments():
    bus = ToolBus().from_default()
    k = _kernel(Path(tempfile.mkdtemp()))
    with pytest.raises(MalformedArgsError):
        bus.call(k.ctx, "calculator", ["not", "a", "dict"])
    with pytest.raises(MalformedArgsError):
        bus.call(k.ctx, "calculator", {"expression": "1+1", "bogus_param": 5})


def test_toolbus_register_requires_tooldef():
    bus = ToolBus()
    with pytest.raises(TypeError):
        bus.register({"name": "x"})  # type: ignore
    bus.register(ToolDef(name="x", description="d", schema={"type": "object", "properties": {}},
                         handler=lambda ctx: {"ok": True}))
    res, dt, ok, meta = bus.call(None, "x", {})
    assert ok and res == {"ok": True}


def test_toolbus_good_call():
    bus = ToolBus().from_default()
    k = _kernel(Path(tempfile.mkdtemp()))
    res, dt, ok, meta = bus.call(k.ctx, "calculator", {"expression": "2*21"})
    assert ok and "42" in json.dumps(res)


# ----------------------------------------------------------------- events
def test_event_bus_fanout_and_error_isolation():
    bus = EventBus()
    seen, bad = [], []
    bus.subscribe(lambda e: seen.append(e.kind))
    bus.subscribe(lambda e: bad.append(1) or 1 / 0)  # subscriber that always raises
    bus.emit(AgentEvent(kind=AgentEventKind.TASK_CREATED, session_id="s", task_id="t"))
    assert seen == [AgentEventKind.TASK_CREATED]
    assert bus.by_kind(AgentEventKind.TASK_CREATED)


# ----------------------------------------------------------------- helpers
class _ScriptedClient:
    """LLM stand-in: pops scripted replies; records every chat() call."""
    def __init__(self, script: list):
        self.script = list(script)
        self.calls: list[tuple] = []

    def chat(self, name, messages, tools=None, **kw):
        self.calls.append((name, [m.get("content", "")[:80] for m in messages], kw))
        if not self.script:
            return {"content": "(scripted: no reply left)"}
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            return {"content": item, "usage": {}}
        return item

    def _has_ollama(self):
        return True

    def models_list(self):
        return ["bee4b"]


def _kernel(tmp_path, script=None, approver=None):
    from bee.config import load_config
    from bee.agent.context import Context
    cfg = load_config()
    cfg.cloud.enabled = False          # no real provider calls in unit tests
    cfg.workspace = tmp_path
    ctx = Context(cfg, workspace=tmp_path,
                  client=_ScriptedClient(script or ["ok"]),
                  guard_on=True, guard_mode="unattended",
                  episodes_on=False, rag_on=False,
                  cancel_event=threading.Event())
    k = AgentKernel(ctx, approver=approver if approver is not None else (lambda t, a, r: False),
                    sessions_dir=tmp_path / "sessions",
                    receipts_path=tmp_path / "receipts.jsonl")
    ctx.kernel = k
    return k
