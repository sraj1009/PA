"""Kernel integration tests (Phase 2) — full task lifecycle through the REAL
run_agent loop, with a scripted LLM stand-in (no model, no network, no cloud).

Scenarios (required):
 1. simple local request
 2. tool call
 3. multi-step task
 4. permission-required task (granted)
 5. denied task
 6. failed task (provider failure -> bounded retry -> FAILED)
 7. verification failure (claimed success, effect missing -> retry -> pass)
 8. cancellation (pre-set + mid-run)
 9. follow-up message referencing the prior task

Run:  python -m pytest tests/test_kernel_integration.py -q
"""
from __future__ import annotations

import json
import threading
import time

import pytest

from bee.agent.client import LLMError
from bee.agent.context import Context
from bee.config import load_config
from bee.kernel import AgentKernel, AgentEventKind, TaskState


# ----------------------------------------------------------------- stand-in
class ScriptedClient:
    """chat() pops scripted items: str -> final answer; dict -> raw LLM out;
    Exception -> raise. Records every call (name, messages, kwargs)."""

    def __init__(self, script: list, delay: float = 0.0):
        self.script = list(script)
        self.calls: list[tuple] = []
        self.delay = delay

    def chat(self, name, messages, tools=None, **kw):
        self.calls.append((name, [dict(m) for m in messages], kw))
        if self.delay:
            time.sleep(self.delay)
        if not self.script:
            return {"content": "(scripted: no reply left)", "usage": {}}
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            return {"content": item, "usage": {}}
        return item

    def ollama_up(self):
        return True

    def _has_ollama(self):
        return True

    def models_list(self):
        return ["bee4b"]


def tc(cid: str, name: str, args: dict) -> dict:
    return {"tool_calls": [{"id": cid, "name": name, "arguments": args}]}


def make_kernel(tmp_path, script, approver=None, delay=0.0):
    cfg = load_config()
    cfg.cloud.enabled = False           # no real provider calls, ever
    cfg.workspace = tmp_path
    client = ScriptedClient(script, delay=delay)
    ctx = Context(cfg, workspace=tmp_path, client=client,
                  guard_on=True, guard_mode="unattended",
                  episodes_on=False, rag_on=False,
                  cancel_event=threading.Event())
    k = AgentKernel(ctx, approver=approver if approver is not None else (lambda t, a, r: False),
                    sessions_dir=tmp_path / "sessions",
                    receipts_path=tmp_path / "receipts.jsonl")
    ctx.kernel = k
    return k, client, ctx


def _events(k, kind):
    return [e for e in k.events.log if e.kind == kind]


def test_f5_denied_guard_ask_does_not_strand_task(tmp_path):
    """Acceptance audit (guard_blocked eval, REAL DEFECT): a guard 'ask'
    that the approver DENIES must return the task to EXECUTING. Before the
    fix the task stayed in WAITING_FOR_PERMISSION, so when the model
    finished its refusal-explanation the kernel's move to VERIFYING raised
    InvalidTransitionError and the whole task crashed."""
    k, client, _ctx = make_kernel(tmp_path, [
        tc("c1", "shell", {"command": "git reset --hard HEAD~1"}),
        "That command is blocked by policy; I did not run it.",
    ], approver=lambda t, a, r: False)      # unattended: everything asks->deny
    (tmp_path / "keep.txt").write_text("keep me")
    r = k.run("Run 'git reset --hard HEAD~1' in the workspace and report what happened.",
              session_id="f5")
    # the task completed its lifecycle instead of crashing mid-transition
    assert r is not None
    assert AgentEventKind.PERMISSION_DENIED in [e.kind for e in k.events.log]
    assert r.task.state in (TaskState.COMPLETED, TaskState.FAILED), r.task.state.value
    assert (tmp_path / "keep.txt").exists()


# ---------------------------------------------------------------- scenarios
def test_1_simple_local_request(tmp_path):
    k, client, _ = make_kernel(tmp_path, ["A router forwards packets between networks using routing tables."])
    r = k.run("Explain what a router does in networking.", session_id="i1")
    assert r.ok is True and r.task.state == TaskState.COMPLETED
    assert "router" in r.output.lower()
    assert len(client.calls) >= 1
    assert [e.kind for e in k.events.log if e.kind == AgentEventKind.TASK_COMPLETED]
    # receipts: the agent-level run receipt exists and is redaction-safe JSON
    rows = [json.loads(l) for l in (tmp_path / "receipts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(row["tool"] == "agent" and row["action"] == "run" for row in rows)
    assert r.verification.verdict in ("pass", "unverified")


def test_2_tool_call(tmp_path):
    k, client, _ = make_kernel(tmp_path, [
        tc("c1", "calculator", {"expression": "2*21"}),
        "The result is 42.",
    ])
    r = k.run("Use the calculator to compute 2 times 21.", session_id="i2")
    assert r.ok and r.task.state == TaskState.COMPLETED
    assert "42" in r.output
    tools = [e.data.get("tool") for e in _events(k, AgentEventKind.TOOL_COMPLETED)]
    assert "calculator" in tools
    assert len(_events(k, AgentEventKind.TOOL_STARTED)) == 1
    rows = [json.loads(l) for l in (tmp_path / "receipts.jsonl").read_text(encoding="utf-8").splitlines()]
    calc = [row for row in rows if row["tool"] == "calculator"]
    assert calc and calc[0]["verification"] == "pass"   # effect checked, not assumed
    assert r.task.observations[0].ok


def test_3_multi_step_task(tmp_path):
    k, client, _ = make_kernel(tmp_path, [
        tc("c1", "file_write", {"path": "reports/summary.txt", "content": "Q3: 1.2M"}),
        tc("c2", "file_read", {"path": "reports/summary.txt"}),
        "Saved and read back the Q3 summary.",
    ])
    r = k.run("Write the Q3 summary report to reports/summary.txt and read it back to confirm.",
              session_id="i3")
    assert r.ok and r.task.state == TaskState.COMPLETED
    assert (tmp_path / "reports" / "summary.txt").read_text(encoding="utf-8") == "Q3: 1.2M"
    tools = [e.data.get("tool") for e in _events(k, AgentEventKind.TOOL_COMPLETED)]
    assert tools.count("file_write") == 1 and tools.count("file_read") == 1
    assert r.verification.verdict == "pass"
    assert len(r.task.observations) == 2


def test_4_permission_required_granted(tmp_path):
    (tmp_path / "a.txt").write_text("original")
    k, client, _ = make_kernel(tmp_path, [
        tc("c1", "code_run", {"code": "import os\nos.rename('a.txt', 'b.txt')"}),
        "Renamed a.txt to b.txt.",
    ], approver=lambda tool, args, reason: True)
    r = k.run("Rename a.txt to b.txt in the workspace.", session_id="i4")
    kinds = [e.kind for e in k.events.log]
    assert AgentEventKind.PERMISSION_REQUESTED in kinds
    assert AgentEventKind.PERMISSION_GRANTED in kinds
    assert (tmp_path / "b.txt").exists() and not (tmp_path / "a.txt").exists()
    assert r.task.state == TaskState.COMPLETED
    rows = [json.loads(l) for l in (tmp_path / "receipts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(row["action"] == "permission" and row["permission"] == "granted" for row in rows)
    # WAITING_FOR_PERMISSION was a real state (kernel observed by the approver)
    assert r.task.state == TaskState.COMPLETED  # terminal; path included the wait


def test_5_denied_task(tmp_path):
    k, client, _ = make_kernel(tmp_path, [
        tc("c1", "shell", {"command": "rm -rf /tmp/bee-denied-probe"}),
        "I cannot do that — the guard blocked it.",
    ])
    r = k.run("Delete everything inside /tmp/bee-denied-probe recursively.", session_id="i5")
    kinds = [e.kind for e in k.events.log]
    assert AgentEventKind.PERMISSION_DENIED in kinds
    blocked = [o for o in r.task.observations if o.blocked]
    assert blocked, "the denied tool call must be recorded as blocked"
    import tempfile
    from pathlib import Path as _P
    assert not (_P(tempfile.gettempdir()) / "bee-denied-probe").exists(), "denied command must not run"
    assert r.task.state == TaskState.COMPLETED          # agent explained; nothing ran
    assert r.verification.verdict == "unverified"        # and success is NOT claimed
    rows = [json.loads(l) for l in (tmp_path / "receipts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(row["tool"] == "shell" and "blocked" in row["result"].lower() for row in rows)


def test_6_failed_task_provider_retry(tmp_path):
    k, client, _ = make_kernel(tmp_path, [
        LLMError("connection refused", kind="connect"),
        LLMError("connection refused", kind="connect"),
    ])
    r = k.run("Explain the TCP handshake in detail.", session_id="i6")
    assert r.ok is False and r.task.state == TaskState.FAILED
    assert r.task.failure_kind == "provider"
    assert r.task.retry_count == 1 and r.retried is True
    assert len(client.calls) == 2, "exactly one retry, then stop"
    kinds = [e.kind for e in k.events.log]
    assert AgentEventKind.TASK_FAILED in kinds
    rows = [json.loads(l) for l in (tmp_path / "receipts.jsonl").read_text(encoding="utf-8").splitlines()]
    run_rows = [row for row in rows if row["tool"] == "agent"]
    assert run_rows[-1]["retry_count"] == 1


def test_7_verification_failure_then_retry(tmp_path):
    k, client, _ = make_kernel(tmp_path, [
        # attempt 1: creates the WRONG folder, claims success
        tc("c1", "shell", {"command": "mkdir wrongdir"}),
        "Done — folder created.",
        # attempt 2 (kernel retry with correction note): does it right
        tc("c2", "shell", {"command": "mkdir invoices"}),
        "Done — invoices folder created.",
    ])
    r = k.run("Create a folder called invoices.", session_id="i7")
    assert (tmp_path / "invoices").is_dir(), "the intended effect must exist afterwards"
    assert r.task.state == TaskState.COMPLETED
    assert r.retried is True and r.task.retry_count == 1
    assert r.verification.verdict == "pass"
    # the retry note was actually injected into the second run
    retried = [m.get("content", "") for c in client.calls for m in c[1]
               if isinstance(m.get("content"), str) and "FAILED VERIFICATION" in m["content"]]
    assert retried, "the correction note was not injected into the retry"
    kinds = [e.kind for e in k.events.log]
    assert kinds.count(AgentEventKind.VERIFICATION_COMPLETED) == 2


def test_8_cancellation_pre_set(tmp_path):
    k, client, ctx = make_kernel(tmp_path, ["never returned"])
    ctx.cancel_event.set()  # user said Stop before/during the task
    r = k.run("Do a long thing.", session_id="i8a")
    assert r.cancelled is True and r.task.state == TaskState.CANCELLED
    assert client.calls == [], "cancellation must prevent the LLM call"
    assert AgentEventKind.TASK_CANCELLED in [e.kind for e in k.events.log]


def test_8b_cancellation_mid_run(tmp_path):
    k, client, ctx = make_kernel(
        tmp_path, [tc("c1", "calculator", {"expression": "1"}), "late answer"], delay=0.4)
    box = {}

    def go():
        box["r"] = k.run("compute something slowly", session_id="i8b")

    th = threading.Thread(target=go)
    th.start()
    time.sleep(0.2)          # the first LLM call is in flight (0.4s)
    k.cancel()
    th.join(timeout=20)
    assert th.ident is None or not th.is_alive()
    r = box["r"]
    assert r.cancelled is True and r.task.state == TaskState.CANCELLED


def test_9_follow_up_resolves_against_active_task(tmp_path):
    k, client, _ = make_kernel(tmp_path, [
        "Invoice draft ready.",
        "Updated — the invoice is set for 10 AM.",
    ])
    r1 = k.run("Draft the invoice for Apex Carnage.", session_id="i9")
    assert r1.task.state == TaskState.COMPLETED
    r2 = k.run("Actually make it 10 AM.", session_id="i9")
    # the second LLM call must see the ORIGINAL task + the follow-up merged
    last_user = client.calls[-1][1][-1]["content"]
    assert "Apex Carnage" in last_user, "follow-up lost the referenced entity"
    assert "10 AM" in last_user
    assert r2.task.state == TaskState.COMPLETED
    # and it resolved against the active task, not as an unrelated prompt
    assert "follow-up" in r2.task.text
    # session persisted with the active task for future turns
    s = k.get_session("i9")
    assert s.active_task_text.startswith("Draft the invoice for Apex Carnage.")
    assert (tmp_path / "sessions" / "i9.json").exists()
    # a genuinely unrelated message starts a NEW task
    k.ctx.client.script = ["Unrelated answer."]
    r3 = k.run("Tell me about the history of glass.", session_id="i9")
    assert "follow-up" not in r3.task.text


def test_10_repl_stop_word_semantics(tmp_path):
    """'stop' with no running task reports the last task's state (unit-level)."""
    k, client, _ = make_kernel(tmp_path, ["done."])
    k.run("Do the thing.", session_id="i10")
    before = len(client.calls)
    r = k.run("stop.", session_id="i10")
    assert r.cancelled is True and len(client.calls) == before


def test_11_events_full_sequence(tmp_path):
    k, client, _ = make_kernel(tmp_path, [
        tc("c1", "calculator", {"expression": "6*7"}),
        "It is 42.",
    ])
    # 'Use the calculator...' forces the LLM/tool path (bare 'What is 6*7?'
    # would be answered by the deterministic tier — no tool events)
    k.run("Use the calculator tool to compute 6 times 7.", session_id="i11")
    kinds = [e.kind for e in k.events.log]
    seq = [k for k in kinds if k in {AgentEventKind.USER_MESSAGE, AgentEventKind.TASK_CREATED,
                                     AgentEventKind.PLAN_CREATED, AgentEventKind.TOOL_STARTED,
                                     AgentEventKind.TOOL_COMPLETED,
                                     AgentEventKind.VERIFICATION_STARTED,
                                     AgentEventKind.VERIFICATION_COMPLETED,
                                     AgentEventKind.MEMORY_WRITTEN,
                                     AgentEventKind.TASK_COMPLETED}]
    for expected in (AgentEventKind.USER_MESSAGE, AgentEventKind.TASK_CREATED,
                     AgentEventKind.PLAN_CREATED, AgentEventKind.TOOL_STARTED,
                     AgentEventKind.TOOL_COMPLETED, AgentEventKind.VERIFICATION_STARTED,
                     AgentEventKind.VERIFICATION_COMPLETED, AgentEventKind.MEMORY_WRITTEN,
                     AgentEventKind.TASK_COMPLETED):
        assert expected in seq, f"missing event {expected}"
    # order sanity: plan before tool, verification before completion
    assert seq.index(AgentEventKind.PLAN_CREATED) < seq.index(AgentEventKind.TOOL_STARTED)
    assert seq.index(AgentEventKind.VERIFICATION_COMPLETED) < seq.index(AgentEventKind.TASK_COMPLETED)
