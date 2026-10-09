"""Regression tests for the technical-debt items closed in the coherence
pass (N3, N4, N9, H8). Each test pins the specific behavior so the fix
cannot silently regress.

Run:  python -m pytest tests/test_debt_fixes.py -q
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest                                   # noqa: E402
from bee.kernel.tools_bus import (              # noqa: E402
    MalformedArgsError, ToolBus, ToolDef, ToolTimeoutError)


# ------------------------------------------------------------------ N9 (bus)
def test_n9_bus_records_full_capability_list():
    """N9: from_default() must record ALL of a tool's capabilities, not just
    the first — otherwise the bus under-maps once it is the authoritative
    dispatcher (the gate itself already uses the full list)."""
    bus = ToolBus().from_default()
    web = bus.get("web_fetch")
    assert web is not None
    # web_fetch carries {fs.read, network} — before N9 only the first survived
    assert set(web.capabilities) == {"fs.read", "network"}
    assert web.capability in web.capabilities      # primary is a member
    shell = bus.get("shell")
    assert set(shell.capabilities) == {"exec", "fs.write", "network"}


# ------------------------------------------------------------------ N3 (bus)
def test_n3_bus_timeout_enforced():
    """N3: a handler that outlives its budget must raise ToolTimeoutError so
    the agent is unbounded-for-no-reason is gone. We give the slow tool a
    small timeout and confirm we get the error back in bounded time."""
    bus = ToolBus()
    bus.register(ToolDef(
        name="slowpoke", description="slow", schema={"type": "object",
        "properties": {}},
        handler=lambda ctx: time.sleep(5) or {"ok": True},
        timeout=5.0))
    t0 = time.time()
    with pytest.raises(ToolTimeoutError):
        bus.call(None, "slowpoke", {}, timeout=0.15)
    assert time.time() - t0 < 2.0, "timeout must unblock the caller quickly"


def test_n3_fast_call_unaffected_by_timeout_path():
    """A handler that finishes well inside its budget returns normally and
    reports timed_out=False (the timeout machinery adds no false positives)."""
    bus = ToolBus()
    bus.register(ToolDef(
        name="quick", description="q", schema={"type": "object",
        "properties": {}},
        handler=lambda ctx: {"ok": True}, timeout=5.0))
    res, dt, ok, meta = bus.call(None, "quick", {}, timeout=5.0)
    assert ok and res == {"ok": True}
    assert meta["timed_out"] is False
    assert dt < 2.0


def test_n3_handler_exception_still_maps():
    """Timeout wrapping must preserve the existing error contract: a raising
    handler still becomes a MalformedArgsError / error dict, not a crash."""
    bus = ToolBus()
    bus.register(ToolDef(
        name="boom", description="b", schema={"type": "object",
        "properties": {}},
        handler=lambda ctx: (_ for _ in ()).throw(TypeError("bad arg")),
        timeout=5.0))
    with pytest.raises(MalformedArgsError):
        bus.call(None, "boom", {}, timeout=5.0)


# ------------------------------------------------------------------ H8 (calc)
def test_h8_eval_safe_exponent_guard_blocks_explosion():
    """H8/R7: a tiny AST that is uncomputable (9**9**9**9) must be rejected
    fast by the exponent guard — a single ** is one _ev step, so the step
    budget alone cannot see it; the guarded pow is the real bound."""
    from bee.tools.base import eval_safe
    t0 = time.time()
    with pytest.raises(ValueError):
        eval_safe("9**9**9**9")
    assert time.time() - t0 < 2.0, "exponent guard must abort fast"
    with pytest.raises(ValueError):          # built-in pow() form too
        eval_safe("pow(2, 10**9)")
    assert "1024" in eval_safe("2**10")      # legitimate exponents unaffected


def test_h8_eval_safe_normal_math_still_works():
    """The bounds must not reject legitimate work."""
    from bee.tools.base import eval_safe
    assert "42" in eval_safe("2*21")
    assert "12" in eval_safe("2+3*4-5//2")   # 2 + 12 - 2
    assert "4" in eval_safe("sqrt(16)")
    assert "8" in eval_safe("pow(2, 3)")


def test_h8_eval_safe_bounds_still_enforced():
    """Existing size/depth/literal limits remain in force alongside the
    exponent guard and step budget."""
    from bee.tools.base import eval_safe
    with pytest.raises(ValueError):          # node-count limit
        eval_safe("1+1+1+1" * 200)
    with pytest.raises(ValueError):          # literal limit
        eval_safe('"' + "x" * 60000 + '"')


# ------------------------------------------------------------------ N4 (kern)
def test_n4_stale_cancel_event_does_not_poison_new_task(tmp_path):
    """N4: the KERNEL owns task-scoped cancellation. A cancel event left
    SET by a previously-cancelled task must not cancel the NEXT task —
    kernel.run clears it at task start, so no entry point can forget."""
    from test_kernel_integration import make_kernel, tc
    from bee.kernel.models import AgentEventKind

    k, client, ctx = make_kernel(tmp_path, [
        tc("c1", "calculator", {"expression": "2*21"}),
        "The answer is 42.",
    ])
    ctx.cancel_event.set()   # stale: a previous task was cancelled
    r = k.run("What is 2*21? Use the calculator tool.", session_id="n4")
    # the task ran to completion — it was NOT cancelled by the stale event
    cancelled = [e for e in k.events.log if e.kind == AgentEventKind.TASK_CANCELLED]
    assert not cancelled, "stale cancel event poisoned the new task"
    assert r is not None and not r.cancelled
    # and the event is clean for whatever comes next
    assert not ctx.cancel_event.is_set()


def test_repeated_denials_lock_tools_instead_of_burning_the_budget(tmp_path):
    """Loop breaker gap: the exact-args breakers never match when a small model
    re-requests the same denied tool with slightly different arguments (eval: 6
    automation_job asks, 12 of 25 iterations wasted). Per-tool denial counting
    must short-circuit and then lock, so the remaining budget goes to an answer."""
    import json
    from test_kernel_integration import make_kernel, tc

    script = [tc(f"c{i}", "automation_job",
                 {"op": "create", "note": f"attempt {i}"}) for i in range(6)]
    script.append("I could not create that job without your approval.")
    k, client, _ctx = make_kernel(tmp_path, script,
                                  approver=lambda *a: False)
    r = k.run("Create a daily automation job for me", session_id="lock1")
    assert r.ok
    rows = [json.loads(l) for l in (tmp_path / "receipts.jsonl").read_text(
        encoding="utf-8").splitlines()]
    aj = [x for x in rows if x["tool"] == "automation_job"]
    assert len(aj) >= 3, f"expected the model to retry and be short-circuited: {aj}"
    reasons = " | ".join(str(x.get("result", "")) for x in aj)
    assert "stop calling it" in reasons or "no more tools" in reasons, \
        f"the denial breaker never fired: {reasons[:300]}"
    # no attempt may have executed
    assert all("blocked" in str(x.get("result", "")) for x in aj)


def test_repeated_tool_failures_lock_without_punishing_good_work(tmp_path):
    """Retrying one failing call with reworded arguments used to burn the whole
    budget (the exact-args breaker only). Failures are now counted per tool."""
    from test_kernel_integration import make_kernel, tc
    script = [tc(f"c{i}", "file_read", {"path": f"missing{i}.txt"}) for i in range(5)]
    script.append("Those files do not exist.")
    k, _client, _ctx = make_kernel(tmp_path, script)
    results: list = []
    k.run("Read missing0..4 and tell me what is in them", session_id="faillock",
          on_event=lambda e: results.append(e) if e.get("type") == "tool_result" else None)
    real = [e for e in results if "not found" in str(e.get("preview"))]
    locked = [e for e in results if "has failed" in str(e.get("preview"))]
    assert len(real) == 3, f"expected exactly 3 executions before the lock: {len(real)}"
    assert locked, f"the failure breaker never fired: {[e.get('preview') for e in results]}"
    assert len(real) + len(locked) == len(results)


def test_successive_different_tool_calls_are_not_locked(tmp_path):
    from test_kernel_integration import make_kernel, tc
    (tmp_path / "a.txt").write_text("A")
    (tmp_path / "b.txt").write_text("B")
    (tmp_path / "c.txt").write_text("C")
    script = [tc("c1", "file_read", {"path": "a.txt"}),
              tc("c2", "file_read", {"path": "b.txt"}),
              tc("c3", "file_read", {"path": "c.txt"}),
              "Read all three."]
    k, client, _ctx = make_kernel(tmp_path, script)
    r = k.run("Read a.txt, b.txt and c.txt and tell me their contents", session_id="okflow")
    assert r.ok
    assert len(client.calls) == 4, "legitimate multi-step tool use must not be locked"
