"""Permission decisions (Phase 2) — ONE entry point over the existing guard.

Does not duplicate guard/risk logic: it calls guard.check (which already
layers the regex table + AST risk classifier) and wraps the outcome in a
typed PermissionDecision the kernel can record, emit, and persist.
"""
from __future__ import annotations

from .. import guard
from .models import PermissionDecision


def risk_info(tool: str, args: dict) -> tuple[str, tuple]:
    """(risk_level, capabilities) from the security risk layer; ('low', ()) for
    non-exec tools or when the layer errors (fail open for metadata only —
    the guard itself remains fail-closed)."""
    try:
        from ..security import risk
        d = risk.classify_risk(tool, args or {})
        lvl = d.level
        name = getattr(lvl, "name", None)
        return (name.lower() if isinstance(name, str) else str(lvl)), tuple(d.capabilities)
    except Exception:
        return "low", ()


def decide(tool: str, args: dict, enabled: bool = True, mode: str = "cli",
           approver=None) -> PermissionDecision:
    """Full gate for one tool call.

    `approver` — optional (tool, args, reason) -> bool consulted when the
    guard says 'ask'. The kernel injects its own (interactive prompt, or a
    test callback) so the task state machine can observe the wait.
    """
    args = args or {}
    proceed, action, reason = guard.check(tool, args, enabled, mode, approver=approver)
    level, caps = risk_info(tool, args)
    return PermissionDecision(tool=tool, action=action, granted=bool(proceed),
                              reason=reason, risk_level=level, capabilities=caps)
