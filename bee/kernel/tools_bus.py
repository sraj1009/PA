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
# runs to its timeout) — host subprocess tools do not support mid-call kill
# in this architecture yet (honest documentation, not a claim).
_CANCELLATION = {"shell": "none", "code_run": "none", "sandbox_run": "none",
                 "automate": "none", "spawn_task": "none"}


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
    capability: str = ""
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
        t0 = time.time()
        try:
            res = d.handler(ctx, **args)
        except TypeError as e:
            raise MalformedArgsError(f"bad arguments for {name}: {e}") from e
        except PermissionError:
            raise
        except Exception as e:
            res = {"error": f"{name} raised {type(e).__name__}: {e}"}
        dt = round(time.time() - t0, 3)
        ok = not (isinstance(res, dict) and (res.get("error") or res.get("blocked")))
        return res, dt, ok, {"timed_out": False, "cancelled": False,
                             "timeout": timeout or d.timeout}

    def __len__(self):
        return len(self._defs)
