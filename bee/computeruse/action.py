"""Computer-use action model (Phase 5) — one safe desktop action.

Every action the agent may perform on the user's desktop is a
ComputerAction with an EXPLICIT target, coordinates (with provenance),
a semantic description, an expected result, a timeout, a risk level,
and a verification strategy. Coordinates are NEVER trusted blindly:
a click whose coordinates cannot be traced back to a structural UI
snapshot (window/element rect from the last `observe`) is downgraded
to "model_raw" and must either have been explicitly confirmed by the
user (risk layer escalates it) or is blocked by the session.

The Phase 5 safe set intentionally EXCLUDES: unattended deletion,
financial transactions, credential entry, arbitrary downloads/execution,
and destructive system actions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# verb -> (risk level, default verification strategy)
VERBS = {
    # observation (no input device touched)
    "screenshot":      ("low",    "none"),
    "inspect_ui":      ("low",    "none"),
    # window management (launch/focus — no content manipulation)
    "open_application": ("medium", "window_exists"),
    "focus_window":    ("medium", "active_window"),
    "switch_window":   ("medium", "active_window"),
    # input (side effect on the user's session — confirm at task level)
    "click":           ("medium", "screen_changed"),
    "double_click":    ("medium", "screen_changed"),
    "type_text":       ("high",   "screen_changed"),
    "key_press":       ("medium", "screen_changed"),
    "scroll":          ("medium", "screen_changed"),
    # clipboard (local data movement)
    "copy":            ("low",    "clipboard_changed"),
    "paste":           ("low",    "screen_changed"),
}

WINDOW_VERBS = {"open_application", "focus_window", "switch_window"}
INPUT_VERBS = {"click", "double_click", "type_text", "key_press", "scroll"}
OBSERVE_VERBS = {"screenshot", "inspect_ui"}
CLIPBOARD_VERBS = {"copy", "paste"}

# credential-entry block: we never TYPE where the user's credentials live
CREDENTIAL_RE = re.compile(
    r"\b(password|passwd|pwd|pin|otp|secret|credential|cvv|token|passphrase)\b", re.I)


def is_credential_target(target: str, description: str) -> bool:
    """Heuristic gate for the 'no credential entry' rule (checked on the
    SEMANTIC fields, not on the text payload — the payload is never
    inspected or logged)."""
    return bool(CREDENTIAL_RE.search(f"{target or ''} {description or ''}"))


@dataclass
class ComputerAction:
    action: str                          # verb (VERBS key)
    target: str = ""                     # app/window/element name (semantic)
    x: int | None = None
    y: int | None = None
    coordinate_source: str | None = None # "window_rect" | "element_rect" | "model_raw"
    text: str | None = None              # type_text payload (NEVER logged)
    keys: list = field(default_factory=list)   # key_press: ["ctrl", "s"]
    amount: int = 0                      # scroll: +up / -down (notches)
    description: str = ""                # semantic description (for logs/model)
    expected: dict = field(default_factory=dict)  # expected result spec
    timeout: float = 10.0                # per-action execution timeout (s)

    def __post_init__(self):
        if self.action not in VERBS:
            raise ValueError(f"unsupported computer-use action: {self.action!r} "
                             f"(safe set: {', '.join(sorted(VERBS))})")
        if self.action in ("click", "double_click") and (self.x is None or self.y is None):
            raise ValueError(f"{self.action} requires coordinates (x, y)")
        if self.action == "type_text" and not self.text:
            raise ValueError("type_text requires text")
        if self.action == "key_press" and not self.keys:
            raise ValueError("key_press requires keys")

    # ------------------------------------------------------------ risk
    @property
    def base_risk(self) -> str:
        return VERBS[self.action][0]

    def effective_risk(self, coords_proven: bool) -> str:
        """Risk after provenance: unproven click coordinates escalate to
        high (the risk layer turns that into an explicit user confirm)."""
        r = self.base_risk
        if self.action in ("click", "double_click") and not coords_proven:
            r = "high"
        return r

    @property
    def default_verification(self) -> str:
        # expected spec keys win; otherwise the verb's default strategy
        for k in ("window_exists", "active_window", "screen_changed",
                  "clipboard_changed", "clipboard_contains"):
            if k in self.expected:
                return k
        return VERBS[self.action][1]

    def public(self) -> dict:
        """Log/audit-safe view — NEVER includes the typed text payload,
        clipboard contents, or pixel data (see privacy.py)."""
        d = {
            "action": self.action,
            "target": self.target,
            "description": self.description,
            "x": self.x, "y": self.y,
            "coordinate_source": self.coordinate_source,
            "expected": self.expected,
            "verification": self.default_verification,
            "timeout": self.timeout,
            "risk": self.base_risk,
        }
        if self.action == "type_text":
            d["text_len"] = len(self.text or "")      # length only
        if self.action == "key_press":
            d["keys"] = list(self.keys)               # key NAMES, not content
        if self.action == "scroll":
            d["amount"] = self.amount
        return d
