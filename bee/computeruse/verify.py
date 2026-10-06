"""Post-action observation + verification (Phase 5).

The core rule of safe computer use: NEVER trust the action — observe the
screen again and verify that the expected UI state actually happened.
Every verification compares a fresh desktop snapshot against the expected
spec; the result is True (verified), False (verified-failed — the effect
is NOT assumed), or None (unverified — honest when no checkable expected
state was given).

Verification checks are structural (window list / active window / screen
hash / clipboard compare) — deterministic and model-free. Pixel CONTENT is
never logged or returned in observations; only hashes and geometry.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Verification:
    verified: bool | None            # True | False | None (unverified)
    strategy: str
    detail: str = ""


def snapshot(desktop) -> dict:
    """Pre-action screen snapshot (nothing sensitive leaves this dict)."""
    aw = desktop.active_window()
    frame = desktop.screenshot()
    import hashlib
    h = hashlib.sha256(frame).hexdigest()[:12] if frame else ""
    return {
        "screen_hash": h,
        "n_windows": len(desktop.list_windows()),
        "active_title": aw.title if aw else "",
        "clipboard_len": len(desktop.clipboard_get() or ""),
    }


def _norm(s: str) -> str:
    return (s or "").lower().strip()


def verify_action(desktop, action, pre: dict) -> Verification:
    strategy = action.default_verification
    if strategy == "none":
        return Verification(None, "none", "no expected state given — unverified")

    if strategy == "window_exists":
        want = _norm(action.expected.get("window_exists") or action.target)
        if not want:
            return Verification(None, strategy, "no window title to check")
        titles = [w.title for w in desktop.list_windows()]
        hit = next((t for t in titles if want in _norm(t)), None)
        return Verification(hit is not None, strategy,
                            f"window {action.target!r} "
                            + ("found" if hit else "NOT found") +
                            f" ({len(titles)} visible windows)")

    if strategy == "active_window":
        want = _norm(action.expected.get("active_window") or action.target)
        aw = desktop.active_window()
        got = _norm(aw.title) if aw else ""
        ok = bool(want) and want in got
        return Verification(ok, strategy,
                            f"active window: expected ~{action.target!r}"
                            + ("" if ok else " (not active)"))

    if strategy == "screen_changed":
        frame = desktop.screenshot()
        h = ""
        if frame:
            import hashlib
            h = hashlib.sha256(frame).hexdigest()[:12]
        if not pre.get("screen_hash") or not h:
            return Verification(None, strategy, "no usable screen hashes")
        ok = h != pre["screen_hash"]
        return Verification(ok, strategy,
                            "screen changed as expected" if ok
                            else "screen UNCHANGED after action — effect not observed")

    if strategy == "clipboard_changed":
        cur = len(desktop.clipboard_get() or "")
        ok = cur != pre.get("clipboard_len", 0)
        return Verification(ok, strategy,
                            "clipboard changed" if ok
                            else "clipboard unchanged — copy had no visible effect")

    if strategy == "clipboard_contains":
        want = _norm(action.expected.get("clipboard_contains") or "")
        got = _norm(desktop.clipboard_get() or "")
        # compare only — the clipboard CONTENT is never logged/returned
        ok = bool(want) and want in got
        return Verification(ok, strategy,
                            "clipboard contains expected value (content not logged)"
                            if ok else "clipboard does not contain expected value")

    return Verification(None, strategy, f"unknown strategy {strategy!r}")
