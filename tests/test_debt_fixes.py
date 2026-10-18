"""Regression tests for the technical-debt items closed in the coherence
pass (N3, N4, N9, H8, A69). Each test pins the specific behavior so the fix
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
    with pytest.raises(ValueError, match="too large"):   # node-count limit
        eval_safe("1+1+1+1" * 200)
    with pytest.raises(ValueError, match="literal too large"):
        eval_safe('"' + "x" * 12000 + '"')   # < input cap, > literal cap


def test_h8_eval_safe_rejects_deep_and_huge_expressions():
    """H8/R7: deliberately deep (nesting > 20) and huge (> 200 nodes) input is
    rejected by the pre-evaluation bounds — before any evaluation work."""
    from bee.tools.base import eval_safe
    with pytest.raises(ValueError, match="too deep"):
        eval_safe("1" + "+1" * 40)           # 41-deep left chain, 81 nodes
    with pytest.raises(ValueError, match="too large"):
        eval_safe("1+" * 300 + "1")          # 601 nodes, 301 deep
    with pytest.raises(ValueError, match="too long"):
        eval_safe("1+" * 15000 + "1")        # input cap, rejected before parse


def test_h8_eval_safe_pathological_calls_are_bounded():
    """Single C calls no step budget can interrupt are rejected up front:
    sum(range(10**12)) loops, "x" * 10**9 allocates, (10**10000)**10000
    builds a ~40 MB int, factorial(10**8) runs a pure-C loop."""
    from bee.tools.base import eval_safe
    t0 = time.time()
    with pytest.raises(ValueError, match="range"):
        eval_safe("sum(range(10**12))")
    with pytest.raises(ValueError, match="repeat"):
        eval_safe('"x" * 10**9')
    with pytest.raises(ValueError, match="repeat"):
        eval_safe("[0] * 10**9")
    with pytest.raises(ValueError, match="factorial"):
        eval_safe("factorial(10**8)")
    with pytest.raises(ValueError, match="power result too large"):
        eval_safe("(10**10000)**10000")
    # >4300-digit ints cannot be printed (CPython digit ceiling): a bounded
    # descriptor, never an internal error
    assert "bits" in eval_safe("10**10000")
    assert time.time() - t0 < 2.0, "guards must reject before computing"


def test_h8_eval_safe_wall_clock_deadline_is_enforced(monkeypatch):
    """The wall-clock budget is checked at every evaluator step; an elapsed
    deadline aborts with a clear error instead of running to completion."""
    import bee.tools.base as base
    monkeypatch.setattr(base, "_MAX_SECONDS", -1.0)
    with pytest.raises(ValueError, match="timed out"):
        base.eval_safe("1+1")


def test_h8_calculator_tool_reports_clear_errors():
    """Tool boundary: pathological input -> an error string (never a hang);
    legitimate input keeps the normal result envelope."""
    from bee.tools.calculator import calc_tools
    h = calc_tools()[0].handler
    bad = h(None, expression="sum(range(10**12))")
    assert "error" in bad and "range" in bad["error"]
    ok = h(None, expression="2*21")
    assert ok.get("result") == "42"


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


# ------------------------------------------- /exit finalization deadlock (CLI)
def test_repl_process_exits_after_slash_exit(tmp_path):
    """`python -m bee repl` must EXIT — promptly — after /exit.

    Observed 2026-10-17: the process hung for minutes AFTER '/exit'. CPython's
    shutdown freezes daemon threads (TTS speaker, event watchers) wherever they
    are; one frozen mid-import leaks the import lock, and a litellm __del__
    importing aiohttp_transport then blocks on that lock forever (faulthandler
    dump: the lock wait, main thread already inside finalization). cli._hard_exit
    flushes and os._exit()s past finalization; this pins the process contract:
    answer delivered, exit code 0, bounded time, real /metrics untouched
    (BEE_WORKSPACE points at a temp dir).
    """
    if sys.platform != "win32":
        pytest.skip("the freeze was observed on Windows (SAPI/COM shutdown path)")
    import os
    import subprocess

    root = Path(__file__).resolve().parents[1]
    ws = tmp_path / "ws"
    ws.mkdir()
    env = dict(os.environ, BEE_WORKSPACE=str(ws))
    t0 = time.time()
    p = subprocess.run(
        [sys.executable, "-u", "-m", "bee", "repl", "--config", str(root / "config.yaml")],
        input="what is 12 * 12\n/exit\n", text=True, capture_output=True,
        encoding="utf-8", errors="replace", cwd=str(root), env=env, timeout=150)
    elapsed = time.time() - t0
    tail = (p.stdout or "")[-1500:] + "\n--stderr--\n" + (p.stderr or "")[-1200:]
    assert p.returncode == 0, f"repl exited {p.returncode} after {elapsed:.1f}s:\n{tail}"
    assert "12 * 12 = 144" in (p.stdout or ""), tail
    assert elapsed < 120, f"repl took {elapsed:.1f}s — finalization deadlock back?\n{tail}"


# --------------------------- A69: live checks skip, never fail (bare install)
def test_a69_live_checks_skip_when_the_sdk_is_absent(tmp_path):
    """A69 (2026-10-18): `-m core` on a bare install (no livekit SDK) run from
    the repo root — where .env lives — executed the two live-credential checks
    and FAILED with ModuleNotFoundError: creds alone gated them, the SDK never
    did. CI could not see it (no .env there -> the creds gate skipped them),
    so the failure only hit real users' bare installs.

    This runs the REAL file in a child pytest with the SDK blocked and fake
    creds forced through the env (LIVEKIT_* are honoured by bee.config) and
    pins: exit 0, both checks SKIPPED for the missing-optional-dependency
    reason — never the creds one. The blocker must raise ModuleNotFoundError:
    pytest 9's importorskip only skips on that (a module that exists but
    raises a generic ImportError is a real error and must stay one).
    """
    import os
    import subprocess

    root = Path(__file__).resolve().parents[1]
    blocker = tmp_path / "blocker"
    blocker.mkdir()
    (blocker / "livekit.py").write_text(
        "raise ModuleNotFoundError(\"No module named 'livekit' (blocked by "
        "test_a69)\")\n", encoding="utf-8")
    pp = os.environ.get("PYTHONPATH", "")
    env = dict(os.environ,
               LIVEKIT_URL="ws://127.0.0.1:9",
               LIVEKIT_API_KEY="fake-key",
               LIVEKIT_API_SECRET="fake-secret")
    env["PYTHONPATH"] = str(blocker) + (os.pathsep + pp if pp else "")
    p = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_livekit_live.py",
         "-q", "-rs", "-p", "no:cacheprovider", "--no-header"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(root), env=env, timeout=180)
    out = (p.stdout or "") + "\n--stderr--\n" + (p.stderr or "")
    assert p.returncode == 0, out[-1500:]
    assert "2 skipped" in out, out[-1500:]
    assert "MISSING OPTIONAL DEPENDENCY" in out, out[-1500:]
    assert "no LiveKit credentials" not in out, out[-1500:]
