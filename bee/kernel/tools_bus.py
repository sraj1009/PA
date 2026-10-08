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

    # --------------------------------------------------------------- call
    def call(self, ctx, name: str, args, timeout: float | None = None,
             stop_check=None):
        """Execute a registered tool. Returns (result, seconds, ok, meta).

        meta: {timed_out: bool, cancelled: bool, error: str}
        Unknown tool  -> UnknownToolError
        Bad args      -> MalformedArgsError (caller converts to observation)
        """
        d = self._defs.get(name)
        if d is None:
            raise UnknownToolError(
                f"unknown tool: {name}. Available: {', '.join(self.names())}")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise MalformedArgsError(f"arguments for {name} must be an object, got {type(args).__name__}")
        if stop_check is not None and stop_check():
            raise PermissionError("cancelled before execution")
        # N3 (debt): a per-tool timeout must actually bound the call. The
        # handler runs in a worker thread; if it outlives the budget the
        # agent is NOT blocked forever — ToolTimeoutError is raised so the
        # loop records a failed observation and moves on. (Python cannot kill
        # a thread; the tool's own subprocess/timeout limits still bound the
        # underlying work, and cancelable tools die via ctx.cancel_event.)
        eff_timeout = timeout if timeout is not None else d.timeout
        t0 = time.time()
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

            threading.Thread(target=_runner, daemon=True,
                             name=f"toolbus-{name}").start()
            try:
                tag, payload = q.get(timeout=eff_timeout)
            except queue.Empty:
                raise ToolTimeoutError(
                    f"{name} timed out after {eff_timeout:.0f}s "
                    f"(the agent is unblocked; the tool keeps to its own limits)")
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
        return res, dt, ok, {"timed_out": False, "cancelled": False,
                             "timeout": timeout or d.timeout}

    def __len__(self):
        return len(self._defs)
