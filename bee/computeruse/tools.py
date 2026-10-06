"""Computer-use tools (Phase 5) — the agent-facing surface.

Four registered tools, each mapped to a Phase-3 capability:

  computer_observe    desktop.observe    (R1, always_allow) — screenshot +
                        inspect visible UI (structured snapshot, no pixels)
  computer_window     desktop.launch     (R3, ask) — open_application,
                        focus_window, switch_window
  computer_input      desktop.control    (R3, ask) — click, double_click,
                        type_text, key_press, scroll. The risk layer
                        escalates model_raw coordinates and type_text to
                        explicit user confirmation.
  computer_clipboard  desktop.clipboard  (R2, always_allow) — copy, paste

Closed loop: each call is ONE action + post-observation + verification.
The agent plans the next step from the returned observation; a per-task
action budget (config computeruse.max_actions) makes long open-loop
sequences impossible by construction.
"""
from __future__ import annotations

import threading

from ..tools.base import T
from .action import CLIPBOARD_VERBS, INPUT_VERBS, OBSERVE_VERBS, WINDOW_VERBS
from .session import (ComputerUseSession, DEFAULT_MAX_ACTIONS,
                      computeruse_emergency_stop)

_EXPECTED_DESC = ("Expected result to verify after the action: one of "
                  "{\"window_exists\": \"<title>\"}, {\"active_window\": \"<title>\"}, "
                  "{\"screen_changed\": true}, {\"clipboard_changed\": true}, "
                  "{\"clipboard_contains\": \"<value>\"}. Omit to leave unverified.")


def _get_session(ctx) -> ComputerUseSession:
    """One session per task (provenance + budget are task-scoped)."""
    from .desktop import DesktopError, make_desktop
    cfg = getattr(ctx, "cfg", None)
    cu_cfg = getattr(cfg, "computeruse", None) if cfg is not None else None
    tid = getattr(ctx, "current_task_id", "") or "default"
    store = getattr(ctx, "cu_sessions", None)
    if store is None:
        store = {}
        ctx.cu_sessions = store
    if tid not in store:
        desktop = getattr(ctx, "computeruse_desktop", None)
        if desktop is None:
            desktop = make_desktop(cfg)      # raises DesktopError if unsupported
            ctx.computeruse_desktop = desktop
        max_actions = getattr(cu_cfg, "max_actions", DEFAULT_MAX_ACTIONS) or DEFAULT_MAX_ACTIONS
        store[tid] = ComputerUseSession(
            desktop, max_actions=int(max_actions),
            cancel_event=getattr(ctx, "cancel_event", None), task_id=tid)
    return store[tid]


def computer_observe(ctx, **kw):
    from .desktop import DesktopError
    try:
        s = _get_session(ctx)
    except DesktopError as e:
        return {"error": str(e)}
    return s.observe()


def computer_window(ctx, action: str, target: str, expected: dict | None = None,
                    timeout: float = 10.0, **kw):
    from .action import ComputerAction
    from .desktop import DesktopError
    try:
        s = _get_session(ctx)
        a = ComputerAction(action=action, target=target or "",
                           expected=expected or {}, timeout=float(timeout or 10.0))
    except (DesktopError, ValueError) as e:
        return {"error": str(e)}
    if a.action not in WINDOW_VERBS:
        return {"error": f"computer_window takes one of {sorted(WINDOW_VERBS)}"}
    return s.execute(a)


def computer_input(ctx, action: str, target: str = "", x: int | None = None,
                   y: int | None = None, coordinate_source: str = "model_raw",
                   text: str | None = None, keys: list | None = None,
                   amount: int = 0, expected: dict | None = None,
                   description: str = "", timeout: float = 10.0, **kw):
    from .action import ComputerAction
    from .desktop import DesktopError
    try:
        s = _get_session(ctx)
        a = ComputerAction(action=action, target=target or "",
                           x=x, y=y,
                           coordinate_source=(coordinate_source or "model_raw"),
                           text=text, keys=keys or [], amount=int(amount or 0),
                           description=description or "",
                           expected=expected or {}, timeout=float(timeout or 10.0))
    except (DesktopError, ValueError) as e:
        return {"error": str(e)}
    if a.action not in INPUT_VERBS:
        return {"error": f"computer_input takes one of {sorted(INPUT_VERBS)}"}
    return s.execute(a)


def computer_clipboard(ctx, action: str, expected: dict | None = None,
                       timeout: float = 10.0, **kw):
    from .action import ComputerAction
    from .desktop import DesktopError
    try:
        s = _get_session(ctx)
        a = ComputerAction(action=action, expected=expected or {},
                           timeout=float(timeout or 10.0))
    except (DesktopError, ValueError) as e:
        return {"error": str(e)}
    if a.action not in CLIPBOARD_VERBS:
        return {"error": f"computer_clipboard takes one of {sorted(CLIPBOARD_VERBS)}"}
    return s.execute(a)


def computer_stop(ctx, **kw):
    """Emergency stop for the user (also: REPL '/cu stop', global hotkey)."""
    n = computeruse_emergency_stop()
    return {"stopped_sessions": n}


def computeruse_tools() -> list[T]:
    return [
        T(name="computer_observe",
          description="Observe the desktop: list visible windows (title, class, rect, active) "
                      "and take a screenshot (returned as a hash; pixels are never sent to the "
                      "model). Call this BEFORE any click to get valid coordinates.",
          parameters={"type": "object", "properties": {}},
          handler=computer_observe, risk="low",
          capabilities=("desktop.observe",)),
        T(name="computer_window",
          description="Window management: open_application (launch an app), focus_window, "
                      "switch_window. target = app or window title. Verify with expected "
                      "e.g. {\"window_exists\": \"Chrome\"}.",
          parameters={"type": "object",
                      "properties": {
                          "action": {"type": "string",
                                     "enum": sorted(WINDOW_VERBS)},
                          "target": {"type": "string"},
                          "expected": {"type": "object", "description": _EXPECTED_DESC},
                          "timeout": {"type": "number"}},
                      "required": ["action", "target"]},
          handler=computer_window, risk="medium",
          capabilities=("desktop.launch",)),
        T(name="computer_input",
          description="Desktop input: click, double_click (x,y from the LAST computer_observe "
                      "rects — unproven coordinates are rejected or require explicit user "
                      "confirmation), type_text (text is never logged), key_press (e.g. "
                      "[\"ctrl\",\"s\"]), scroll (notches, +up/-down). Always set expected.",
          parameters={"type": "object",
                      "properties": {
                          "action": {"type": "string", "enum": sorted(INPUT_VERBS)},
                          "target": {"type": "string", "description": "element/window name (semantic)"},
                          "x": {"type": "integer"}, "y": {"type": "integer"},
                          "coordinate_source": {"type": "string",
                                                "enum": ["window_rect", "element_rect", "model_raw"]},
                          "text": {"type": "string"},
                          "keys": {"type": "array", "items": {"type": "string"}},
                          "amount": {"type": "integer"},
                          "description": {"type": "string"},
                          "expected": {"type": "object", "description": _EXPECTED_DESC},
                          "timeout": {"type": "number"}},
                      "required": ["action"]},
          handler=computer_input, risk="medium",
          capabilities=("desktop.control",)),
        T(name="computer_clipboard",
          description="Clipboard: copy (Ctrl+C) or paste (Ctrl+V). Content is never logged.",
          parameters={"type": "object",
                      "properties": {
                          "action": {"type": "string", "enum": sorted(CLIPBOARD_VERBS)},
                          "expected": {"type": "object", "description": _EXPECTED_DESC},
                          "timeout": {"type": "number"}},
                      "required": ["action"]},
          handler=computer_clipboard, risk="low",
          capabilities=("desktop.clipboard",)),
        T(name="computer_stop",
          description="Emergency stop: immediately end ALL computer control (also: Ctrl+Alt+Q, "
                      "or the 'stop' command in any interface).",
          parameters={"type": "object", "properties": {}},
          handler=computer_stop, risk="low",
          capabilities=("desktop.control",)),
    ]
