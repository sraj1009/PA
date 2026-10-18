"""Tool-call plumbing moved out of the agent loop: safe argument decoding,
result formatting, text tool-call recovery, pre-execution validation, audit
rows, ToolBus dispatch and fast-path execution.

Verbatim moves from `bee.agent.loop` — behavior must stay identical (the
error phrasing here is what the model and the receipts see).
"""
from __future__ import annotations

import json
import re
import time

from .. import guard
from ..monitor import metrics
from ..security import audit as audit_mod
from .episode_metrics import finish
from .result import AgentResult

MAX_OUTPUT_CHARS = 6000


def safe_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw) if isinstance(raw, str) else raw
        return v if isinstance(v, dict) else {"value": v}
    except Exception:
        return {"_raw": str(raw)}


def fmt_result_text(res) -> str:
    if isinstance(res, dict):
        try:
            return json.dumps(res, ensure_ascii=False)[:MAX_OUTPUT_CHARS]
        except Exception:
            return str(res)[:MAX_OUTPUT_CHARS]
    return str(res)[:MAX_OUTPUT_CHARS]


def iter_json_blocks(c: str):
    """Yield each top-level {...} block (string/escape aware). Handles JSONL-style output."""
    i, n = 0, len(c)
    while i < n:
        if c[i] != "{":
            i += 1
            continue
        depth, in_str, esc = 0, False, False
        for j in range(i, n):
            ch = c[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        yield c[i:j + 1]
                        i = j + 1
                        break
        else:
            break


def extract_text_tool_calls(content: str) -> list:
    """Small local models sometimes emit tool calls as TEXT (JSON / JSONL / fenced).
    Recover them. Only dicts having both 'name' and 'arguments' are accepted."""
    if not content:
        return []
    c = content.strip()
    candidates = [c]
    m = re.search(r"```(?:json)?\s*([\[{].*?[\]}])\s*```", c, re.S)
    if m:
        candidates.append(m.group(1))
    for cand in candidates:
        try:
            data = json.loads(cand)
        except Exception:
            data = None
        if data is not None:
            items = data if isinstance(data, list) else [data]
            tcs = []
            for it in items:
                if isinstance(it, dict) and "name" in it and "arguments" in it:
                    args = it["arguments"]
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {"_raw": args}
                    if not isinstance(args, dict):
                        args = {"value": args}
                    tcs.append({"id": f"call_{len(tcs)}", "name": str(it["name"]), "arguments": args})
            if tcs:
                return tcs
    blocks = []
    for block in iter_json_blocks(c):
        try:
            it = json.loads(block)
        except Exception:
            continue
        if isinstance(it, dict) and "name" in it and "arguments" in it:
            blocks.append(it)
    if not blocks:
        return []
    tcs = []
    for it in blocks:
        args = it["arguments"]
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {"_raw": args}
        if not isinstance(args, dict):
            args = {"value": args}
        tcs.append({"id": f"call_{len(tcs)}", "name": str(it["name"]), "arguments": args})
    return tcs


def validate_call(tname: str, args, meta: dict) -> str:
    """Mechanical pre-check for one tool call. Returns "" when callable, else a
    repair nudge for the model. Runs BEFORE gate/guard/execution so malformed
    calls cannot burn permission breakers or iterations — the model gets one
    targeted correction naming the exact defect (unknown name with close
    matches, non-object args, missing required fields from the tool schema).
    Shaped for the unknown-tool error path below (fail_streak, not denials).
    """
    import difflib
    names = sorted(meta.keys()) if meta else []
    if tname not in (meta or {}):
        hint = ""
        close = difflib.get_close_matches(tname, names, n=3, cutoff=0.6) if names else []
        if close:
            hint = f" Did you mean: {', '.join(close)}?"
        avail = f" Available: {', '.join(names)}" if names else ""
        return (f"unknown tool: {tname}.{hint}{avail} Reply with a corrected "
                "call using an exact tool name, or answer without tools.")
    if not isinstance(args, dict):
        return (f"malformed arguments for {tname}: must be a JSON object, got "
                f"{type(args).__name__}. Reply with a corrected call.")
    try:
        required = ((meta[tname].parameters or {}).get("required", []) or [])
    except Exception:
        required = []
    missing = [r for r in required if r not in args]
    if missing:
        return (f"missing required arguments for {tname}: {', '.join(missing)}. "
                "Reply with a corrected call including them.")
    return ""


def audit_record(tname: str, args, action: str, ok: bool, dt: float,
                 blocked: bool, source: str = "agent") -> None:
    """Persistent audit row for one tool call (redacted; never raises)."""
    try:
        decision = None
        if tname in guard.EXEC_TOOLS:
            from ..security import risk
            decision = risk.classify_risk(tname, args)
        audit_mod.record(tool=tname, args=args, decision=decision, action=action,
                         ok=ok, seconds=dt, blocked=blocked, source=source)
    except Exception:
        pass


def execute_tool(ctx, tname: str, args, registry, stop_check) -> tuple:
    """Run one tool call through the ToolBus (kernel-backed runs) or the
    registry (legacy kernel-less direct run_agent).

    Returns (result, cancelled). cancelled=True means the task was cancelled
    (bus stop_check fired or the handler raised KeyboardInterrupt) — the
    caller sets its cancel event and stops the loop.
    """
    bus = getattr(getattr(ctx, "kernel", None), "bus", None)
    try:
        if bus is not None:
            res_v, _bdt, _bok, _bmeta = bus.call(ctx, tname, args, stop_check=stop_check)
        else:
            res_v = registry[tname](ctx, **args)
    except PermissionError as e:
        # bus.call raises PermissionError("cancelled before execution") when
        # stop_check() fires. A PermissionError from the handler itself
        # (e.g. workspace jail) is an ERROR for this call, not a task
        # cancellation.
        if "cancelled" in str(e):
            return None, True
        res_v = {"error": f"{tname} raised PermissionError: {e}"}
    except TypeError as e:
        # The ToolBus already phrases this as
        # 'bad arguments for <tool>: …'; wrapping it again produced
        # 'bad arguments for scheduler: bad arguments for scheduler: …'
        # in front of the model and in the receipts (live probe).
        msg = str(e)
        res_v = {"error": msg if msg.startswith("bad arguments for")
                 else f"bad arguments for {tname}: {msg}"}
    except KeyboardInterrupt:
        return None, True
    except Exception as e:
        res_v = {"error": f"{tname} raised {type(e).__name__}: {e}"}
    return res_v, False


def run_fastpath(ctx, cfg, task: str, fp, m, episode, start: float, emit, sub: bool,
                 on_ask=None):
    """Execute one matched fast path. Returns an AgentResult, or None to fall
    through to the normal (model) pipeline when the handler declines/errors."""
    from . import fastpaths
    try:
        out = fp.handle(ctx, m)
    except Exception as e:
        emit({"type": "fastpath", "name": fp.name, "fell_through": str(e)[:120]})
        return None
    if out is None:
        return None
    if isinstance(out, fastpaths.FastExec):
        from ..tools import tools_by_name
        reg = {} if sub else tools_by_name()
        if out.tool not in reg:
            return None
        emit({"type": "fastpath", "name": fp.name, "tool": out.tool})
        proceed, action, reason = True, "allow", "not needed"
        if out.tool in guard.EXEC_TOOLS and ctx.guard_on and cfg.guard.enabled:
            # same approver contract as the model tool-call path: the
            # kernel-injected approver (web: SSE permission card) governs
            # 'ask'; None keeps the legacy mode-approver behavior.
            proceed, action, reason = guard.check(out.tool, out.args, True,
                                                  ctx.guard_mode, approver=on_ask)
            metrics.record("guard", tool=out.tool, action=action, reason=reason)
            emit({"type": "guard", "tool": out.tool, "action": action, "reason": reason})
        if not proceed:
            audit_record(out.tool, out.args, action, False, 0.0, blocked=True, source="fastpath")
            text = out.blocked(reason) if callable(out.blocked) else str(out.blocked)
            n_tools = 0
        else:
            emit({"type": "tool_start", "tool": out.tool, "args": out.args})
            t0 = time.time()
            try:
                res_v = reg[out.tool](ctx, **out.args)
            except Exception as e:
                res_v = {"error": str(e)}
            ok_v = not (isinstance(res_v, dict) and (res_v.get("error") or res_v.get("blocked")))
            dt = round(time.time() - t0, 1)
            audit_record(out.tool, out.args, action, ok_v, dt,
                         blocked=bool(isinstance(res_v, dict) and res_v.get("blocked")),
                         source="fastpath")
            metrics.record("tool", tool=out.tool, ok=ok_v, seconds=dt)
            emit({"type": "tool_result", "tool": out.tool, "ok": ok_v, "seconds": dt,
                  "preview": str(res_v)[:120]})
            text = out.reply(res_v) if callable(out.reply) else str(out.reply)
            n_tools = 1
        res = AgentResult(output=text, model="deterministic", ok=True, verify="pass",
                          route_source="fastpath", tool_calls=n_tools)
        metrics.record("route", task=task[:200], route="fastpath", source=fp.name)
        return finish(ctx, task, episode, res, start, emit, sub)
    res = AgentResult(output=str(out), model="deterministic", ok=True, verify="pass",
                      route_source="fastpath")
    metrics.record("route", task=task[:200], route="fastpath", source=fp.name)
    return finish(ctx, task, episode, res, start, emit, sub)
