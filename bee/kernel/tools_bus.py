"""ToolBus (Phase 2) — the single dispatch point for agent tool calls.

Every tool the agent may use is a REGISTERED ToolDef with metadata: risk
level, required capability, timeout, cancellation support, and a
verification method. The LLM can only ever address registered tool NAMES —
it cannot call arbitrary Python callables (a callable that was not
registered is rejected at registration time, not just at call time).

The default bus is built from the existing tool modules (bee.tools) plus the
security risk layer — nothing is duplicated.
"""
from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field

DEFAULT_TIMEOUT = 120.0
_TIMEOUTS = {
    "web_fetch": 35.0,
    "web_search": 35.0,
    "automate": 180.0,
    "sandbox_run": 320.0,
    "shell": 300.0,
    "code_run": 300.0,
}
# cancellation support levels: "none" (must run to completion) or
# "between_steps" (kernel can stop before the next action; the current call
# runs to its timeout). Acceptance audit: shell/code_run ALSO kill their own
# subprocess tree mid-call when ctx.cancel_event is set (tools/cancelable.py),
# so "between_steps" understates them but never overstates; sandbox/automate
# remain timeout-bounded only.
_CANCELLATION = {"shell": "between_steps", "code_run": "between_steps",
                 "sandbox_run": "none", "automate": "none", "spawn_task": "none"}


class UnknownToolError(KeyError):
    pass


# ------------------------------------------------- indeterminate-outcome registry
# P1 (audit): when a handler times out and its termination CANNOT be verified,
# the side effect may still land later. Until the state is checked, a blind
# retry of the SAME call could duplicate that side effect — so it is blocked.
# Key: (tool name, sorted repr of args). Cleared when a later call of the same
# key succeeds (the state WAS effectively checked) or explicitly resolved.
_INDETERMINATE: dict[tuple, dict] = {}
_INDETERMINATE_TTL = 1800.0   # seconds; stale entries expire automatically


def _prune_indeterminate() -> None:
    now = time.time()
    stale = [k for k, v in _INDETERMINATE.items()
             if now - v.get("epoch", now) > _INDETERMINATE_TTL]
    for k in stale:
        _INDETERMINATE.pop(k, None)


def resolve_indeterminate(name: str, args: dict) -> None:
    """Operator/tool-side escape hatch: mark an indeterminate call's state as
    checked so retries are allowed again."""
    key = (name, sorted((k, repr(v)) for k, v in (args or {}).items()))
    _INDETERMINATE.pop(key, None)


class MalformedArgsError(TypeError):
    pass


class ToolTimeoutError(TimeoutError):
    pass


@dataclass
class ToolDef:
    name: str
    description: str
    schema: dict
    handler: object                      # bound from a registered builder ONLY
    risk: str = "low"                     # low | medium | high | critical
    capability: str = ""                  # primary (first) capability — legacy field
    capabilities: tuple = ()              # N9: the FULL list (gate uses the full set)
    timeout: float = DEFAULT_TIMEOUT
    cancellation: str = "between_steps"
    verify: str | None = None             # deterministic postcondition name
    untrusted_output: bool = False


class ToolBus:
    def __init__(self):
        self._defs: dict[str, ToolDef] = {}

    # ------------------------------------------------------------ register
    def register(self, d: ToolDef) -> None:
        if not isinstance(d, ToolDef) or not callable(d.handler):
            raise TypeError("ToolBus.register requires a ToolDef with a callable handler")
        self._defs[d.name] = d

    def from_default(self) -> "ToolBus":
        """Build from the existing registered tool modules (bee.tools)."""
        from ..tools import build_default_tools
        from ..security import risk as risk_mod
        for t in build_default_tools():
            prof = risk_mod._TOOL_PROFILES.get(t.name)
            caps = sorted(prof[1]) if prof else []
            self.register(ToolDef(
                name=t.name,
                description=t.description,
                schema=t.parameters,
                handler=t.handler,
                risk=getattr(t, "risk", "low") or "low",
                capability=caps[0] if caps else "",
                capabilities=tuple(caps),   # N9: full list, not just the first
                timeout=_TIMEOUTS.get(t.name, DEFAULT_TIMEOUT),
                cancellation=_CANCELLATION.get(t.name, "between_steps"),
                verify=None,
                untrusted_output=bool(getattr(t, "untrusted_output", False)),
            ))
        return self

    # ------------------------------------------------------------- resolve
    def get(self, name: str) -> ToolDef | None:
        return self._defs.get(name)

    def names(self) -> list[str]:
        return sorted(self._defs)

    def schema(self) -> list[dict]:
        """litellm/openai function schemas for the registered tools only."""
        return [{"type": "function",
                 "function": {"name": d.name, "description": d.description,
                              "parameters": d.schema}} for d in self._defs.values()]

    # -------------------------------------------------- indeterminate outcomes
    # P1 (audit): a timed-out handler ran on a daemon thread the bus cannot
    # kill. Python threads are not interruptible, so claiming the action was
    # "stopped" would be a lie. What IS verifiable: cancelable exec tools
    # (shell/code_run) poll ctx.cancel_event and kill their whole process
    # tree, so setting that event + waiting briefly gives real termination
    # evidence. For anything else the side effect may still land later — the
    # outcome is INDETERMINATE and blind automatic retries of the same call
    # are blocked until the state is checked (see IndeterminateRegistry).
    _TERM_GRACE = 5.0   # max wait for a cancel-aware tool to prove termination

    def _terminate(self, ctx, name: str, runner: threading.Thread,
                   q: "queue.Queue") -> bool:
        """Attempt verified termination of a still-running handler.

        Returns True ONLY when the handler finished within the grace window
        after we signalled cancellation (ctx.cancel_event set) — i.e. the
        underlying action stopped, not merely "we gave up waiting".
        """
        ev = getattr(ctx, "cancel_event", None)
        try:
            import threading as _th
            if not isinstance(ev, _th.Event):
                ev = _th.Event()
                ctx.cancel_event = ev
            ev.set()
        except Exception:
            pass
        try:
            tag, payload = q.get(timeout=self._TERM_GRACE)
            return True   # handler exited on its own after the cancel signal
        except queue.Empty:
            return False  # still running: side effects possible, unverifiable

    @staticmethod
    def _retry_key(name: str, args: dict) -> tuple:
        """Hashable, deterministic identity of a (tool, args) call."""
        return (name, tuple(sorted((k, repr(v)) for k, v in (args or {}).items())))

    def call(self, ctx, name: str, args, timeout: float | None = None,
             stop_check=None, allow_indeterminate: bool = False):
        """Execute a registered tool. Returns (result, seconds, ok, meta).

        meta: {timed_out: bool, indeterminate: bool, terminated: bool,
               cancelled: bool, error: str}
        Unknown tool  -> UnknownToolError
        Bad args      -> MalformedArgsError (caller converts to observation)

        Authorization order (every step happens BEFORE any handler runs):
          1 registration check → 2 strict schema validation →
          3 capability authorization (mandatory; never controlled by
          ctx.guard_on) → 4 risk/approval policy (guard) →
          5 pre-call cancellation check → 6 execution under a bounded
          timeout with explicit cancellation/termination attempt →
          7 result → 8 receipt (caller-side; audit + ExecutionReceipt).
        """
        d = self._defs.get(name)
        if d is None:
            raise UnknownToolError(
                f"unknown tool: {name}. Available: {', '.join(self.names())}")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise MalformedArgsError(f"arguments for {name} must be an object, got {type(args).__name__}")
        # --- 2. strict schema validation against the REGISTERED schema.
        # "is a dict" is insufficient: unknown keys, missing required keys and
        # wrong types must never reach a privileged handler.
        from .schema import validate_args
        violations = validate_args(args, d.schema or {})
        if violations:
            raise MalformedArgsError(
                f"bad arguments for {name}: " + "; ".join(violations)[:600])
        # --- 3. capability authorization. MANDATORY whenever a gate exists —
        # deliberately NOT gated on ctx.guard_on: disabling the legacy
        # interactive command guard (`/guard off`) is a REPL convenience and
        # can never bypass capability authorization (Phase-12 N1 invariant,
        # now enforced at the single dispatcher instead of only in the loop).
        gate = getattr(ctx, "capability_gate", None)
        if gate is not None:
            gres = gate.check(name, args,
                              task_id=getattr(ctx, "current_task_id", "") or "",
                              untrusted_context=bool(getattr(ctx, "untrusted_active", False)))
            if not gres.allowed:
                raise PermissionError(
                    f"capability {gres.capability_id}: {gres.reason}")
        # --- 4. risk/approval policy (the legacy guard layer). This — and
        # only this — is what ctx.guard_on controls.
        from .. import guard as _guard
        if name in _guard.EXEC_TOOLS and getattr(ctx, "guard_on", True):
            cfg = getattr(ctx, "cfg", None)
            gen = getattr(getattr(cfg, "guard", None), "enabled", True)
            if gen:
                proceed, action, reason = _guard.check(
                    name, args, True, getattr(ctx, "guard_mode", "cli"),
                    approver=getattr(ctx, "approver", None))
                if not proceed:
                    raise PermissionError(f"guard ({reason}): command not executed")
        # --- 5. cancellation before execution
        if stop_check is not None and stop_check():
            raise PermissionError("cancelled before execution")
        # --- 1b. refuse blind retries of an indeterminate earlier call
        _prune_indeterminate()
        key = self._retry_key(name, args)
        if not allow_indeterminate and key in _INDETERMINATE:
            prior = _INDETERMINATE[key]
            raise PermissionError(
                f"{name} with these arguments TIMED OUT EARLIER and its "
                f"outcome is indeterminate (the action may still have run). "
                f"Blind retry is blocked. First CHECK the current state "
                f"(read-only verification); if it did not happen, re-issue "
                f"with allow_indeterminate=True once you have verified. "
                f"(pending since {prior['ts']})")
        # N3 (debt): a per-tool timeout must actually bound the call. The
        # handler runs in a worker thread; if it outlives the budget the
        # agent is NOT blocked forever — ToolTimeoutError is raised so the
        # loop records a failed observation and moves on. On top of that
        # (P1 fix) we now ATTEMPT explicit termination and, when it cannot
        # be verified, mark the outcome indeterminate instead of pretending
        # the action was stopped.
        eff_timeout = timeout if timeout is not None else d.timeout
        t0 = time.time()
        tag = payload = None
        if eff_timeout and eff_timeout > 0:
            q: "queue.Queue" = queue.Queue(maxsize=1)

            def _runner() -> None:
                try:
                    res = d.handler(ctx, **args)
                except TypeError as e:
                    q.put(("badargs", f"bad arguments for {name}: {e}"))
                except PermissionError as e:
                    q.put(("perm", e))
                except Exception as e:
                    q.put(("error", f"{name} raised {type(e).__name__}: {e}"))
                else:
                    q.put(("ok", res))

            runner = threading.Thread(target=_runner, daemon=True,
                                      name=f"toolbus-{name}")
            runner.start()
            try:
                tag, payload = q.get(timeout=eff_timeout)
            except queue.Empty:
                terminated = self._terminate(ctx, name, runner, q)
                if not terminated:
                    _INDETERMINATE[key] = {"tool": name,
                                          "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                          "epoch": time.time()}
                    raise ToolTimeoutError(
                        f"{name} timed out after {eff_timeout:.0f}s — "
                        "termination NOT verified: the action may still be "
                        "running or may have had an effect. Outcome marked "
                        "INDETERMINATE; blind retries of this exact call are "
                        "blocked until the state is checked.")
                # termination VERIFIED: the handler exited after our cancel
                # signal — drain its verdict so receipts record the truth.
                try:
                    tag, payload = q.get_nowait()
                except queue.Empty:
                    tag, payload = "cancelled", None
                dt = round(time.time() - t0, 3)
                if tag == "perm":
                    raise payload
                if tag in ("badargs", "error"):
                    res = {"error": str(payload)}
                    return res, dt, False, {"timed_out": True, "indeterminate": False,
                                            "terminated": True, "cancelled": False,
                                            "timeout": eff_timeout}
                res = payload if tag == "ok" else (payload or {"cancelled": True})
                return res, dt, False, {"timed_out": True, "indeterminate": False,
                                        "terminated": True, "cancelled": True,
                                        "timeout": eff_timeout}
        else:
            # timeout<=0 / None => unbounded (legacy behavior for opt-out tools)
            try:
                res = d.handler(ctx, **args)
            except TypeError as e:
                raise MalformedArgsError(f"bad arguments for {name}: {e}") from e
            except PermissionError:
                raise
            except Exception as e:
                res = {"error": f"{name} raised {type(e).__name__}: {e}"}
        if eff_timeout and eff_timeout > 0:
            if tag == "badargs":
                raise MalformedArgsError(payload)
            if tag == "perm":
                raise payload
            if tag == "error":
                res = {"error": payload}
            else:
                res = payload
        dt = round(time.time() - t0, 3)
        ok = not (isinstance(res, dict) and (res.get("error") or res.get("blocked")))
        if ok:
            # a verified successful call of this exact (tool,args) resolves any
            # earlier indeterminate record for it (the state WAS checked)
            _INDETERMINATE.pop(key, None)
        return res, dt, ok, {"timed_out": False, "indeterminate": False,
                             "terminated": False, "cancelled": False,
                             "timeout": timeout or d.timeout}

    def __len__(self):
        return len(self._defs)


# ------------------------------------------------------- single dispatcher entry
def bus_for(ctx, names: list[str] | None = None) -> "ToolBus":
    """The authoritative dispatcher for `ctx`.

    P0 (audit): EVERY tool-capable route — the LLM loop, deterministic fast
    paths, snippet verification, planner relay — must dispatch through one
    ToolBus so registration, schema validation, capability authorization,
    risk/approval policy and timeout/cancellation management apply uniformly.
    Kernel-backed contexts reuse the kernel's bus; kernel-less contexts get a
    cached default bus built from the registered tool modules. There is no
    longer any code path that executes a privileged tool outside this object.
    """
    k = getattr(ctx, "kernel", None)
    b = getattr(k, "bus", None) if k is not None else None
    if isinstance(b, ToolBus) and (names is None or all(n in b.names() for n in names)):
        return b
    b = getattr(ctx, "_bee_default_bus", None)
    if not isinstance(b, ToolBus):
        b = ToolBus().from_default()
        try:
            ctx._bee_default_bus = b
        except Exception:
            pass
    return b
