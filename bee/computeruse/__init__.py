"""bee.computeruse — Phase 5: SAFE computer use.

Desktop capture -> structured UI inspection -> target identification ->
action proposal (LLM, through the kernel) -> permission check (Phase-3
capability gate + risk layer) -> mouse/keyboard action -> screen
observation -> verification -> next action (agent-decided, budget-bounded).

Safe set only: observe/screenshot, window management, click/type/keys/
scroll, clipboard. NOT implemented: unattended deletion, financial
transactions, credential entry, arbitrary downloads/execution,
destructive system actions.

Privacy in code: no typed text / clipboard content / pixels / window
titles in logs; screenshots kept in a bounded hash ring (retention).
"""
from .action import (ComputerAction, VERBS, WINDOW_VERBS, INPUT_VERBS,
                     OBSERVE_VERBS, CLIPBOARD_VERBS, is_credential_target)
from .desktop import (Desktop, DesktopError, MockDesktop, WindowInfo,
                      WindowsDesktop, make_desktop)
from .privacy import ScreenshotStore, redact_entry
from .session import (ComputerUseSession, DEFAULT_MAX_ACTIONS, HotkeyStopper,
                      active_sessions, computeruse_emergency_stop,
                      default_windows_key_state)
from .tools import computeruse_tools
from .verify import Verification, snapshot, verify_action

__all__ = [
    "ComputerAction", "VERBS", "WINDOW_VERBS", "INPUT_VERBS", "OBSERVE_VERBS",
    "CLIPBOARD_VERBS", "is_credential_target", "Desktop", "DesktopError",
    "MockDesktop", "WindowInfo", "WindowsDesktop", "make_desktop",
    "ScreenshotStore", "redact_entry", "ComputerUseSession",
    "DEFAULT_MAX_ACTIONS", "HotkeyStopper", "active_sessions",
    "computeruse_emergency_stop", "default_windows_key_state",
    "computeruse_tools", "Verification", "snapshot", "verify_action",
]
