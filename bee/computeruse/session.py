"""ComputerUseSession (Phase 5) — the closed-loop desktop executor.

Loop discipline: the session NEVER runs an open-ended sequence. One
session call = one action = observe-before (snapshot) -> act ->
observe-after -> verify. The AGENT (LLM, through the kernel) decides the
next step from the returned observation — bounded by a per-task action
budget (max_actions), so a runaway loop stops by construction.

Emergency stop — three independent ways, all immediate:
  1. kernel.cancel()            (REPL 'stop', voice barge-in, web cancel)
                                 — the session watches ctx.cancel_event
  2. computeruse_emergency_stop() — global: stops EVERY active session
  3. global hotkey (default Ctrl+Alt+Q, Windows) — a daemon poller needs
     no focus on the agent; it fires computeruse_emergency_stop()
"""
from __future__ import annotations

import logging
import threading
import weakref
from types import SimpleNamespace

from .action import ComputerAction, is_credential_target
from .privacy import ScreenshotStore, redact_entry
from .verify import snapshot, verify_action
from .vision import make_vision

log = logging.getLogger("bee.computeruse")

DEFAULT_MAX_ACTIONS = 15

# ------------------------------------------------------------------ globals
_ACTIVE_SESSIONS: "weakref.WeakValueDictionary[int, 'ComputerUseSession']" = \
    weakref.WeakValueDictionary()
_REGISTRY_LOCK = threading.Lock()


def computeruse_emergency_stop() -> int:
    """STOP all active computer-control sessions immediately.

    Returns the number of sessions stopped. Safe to call from anywhere
    (hotkey thread, signal handler, REPL command)."""
    with _REGISTRY_LOCK:
        sessions = list(_ACTIVE_SESSIONS.values())
    for s in sessions:
        s.stop()
    return len(sessions)


def active_sessions() -> int:
    with _REGISTRY_LOCK:
        return len(_ACTIVE_SESSIONS)


# -------------------------------------------------------------------- hotkey
class HotkeyStopper:
    """Polls a key-combo (injectable for tests) and fires the emergency
    stop. On Windows the default combo is Ctrl+Alt+Q via GetAsyncKeyState."""

    def __init__(self, key_state_fn, combo=("ctrl", "alt", "q"), interval: float = 0.05):
        self.key_state_fn = key_state_fn        # fn(name) -> bool
        self.combo = combo
        self.interval = interval
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.fired = 0

    def poll(self) -> bool:
        """One poll cycle. Returns True if the stop fired on this poll."""
        if all(self.key_state_fn(k) for k in self.combo):
            computeruse_emergency_stop()
            self.fired += 1
            return True
        return False

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()

        def _run():
            while not self._stop.is_set():
                try:
                    self.poll()
                except Exception:
                    pass
                self._stop.wait(self.interval)
        self._thread = threading.Thread(target=_run, daemon=True,
                                        name="BeeCUHotkey")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


def default_windows_key_state():
    """Ctrl+Alt+Q via GetAsyncKeyState (Windows only, lazy import)."""
    try:
        import win32con
        import win32api
    except ImportError:
        return lambda name: False
    vk = {"ctrl": win32con.VK_CONTROL, "alt": win32con.VK_MENU,
          "q": win32con.VK_Q, "s": win32con.VK_S}

    def state(name: str) -> bool:
        try:
            return bool(win32api.GetAsyncKeyState(vk[name.lower()]) & 0x8000)
        except Exception:
            return False
    return state


# ------------------------------------------------------------------ timeout
def _with_timeout(fn, timeout: float):
    """Run fn() in a worker thread; join(timeout). If it overruns, the call
    is ABANDONED (the thread is daemon; best-effort desktop calls are short).
    Returns (result, timed_out)."""
    box: dict = {}

    def _run():
        try:
            box["res"] = fn()
        except Exception as e:
            box["err"] = f"{type(e).__name__}: {e}"
    t = threading.Thread(target=_run, daemon=True, name="BeeCUAction")
    t.start()
    t.join(timeout)
    if t.is_alive():
        return None, True
    if "err" in box:
        raise box["err"].__class__(box["err"])
    return box.get("res"), False


# ------------------------------------------------------------------ session
class ComputerUseSession:
    """One task's computer-control state: budget, provenance, stop state,
    redacted log. The session is created per task id (see tools.py)."""

    def __init__(self, desktop, max_actions: int = DEFAULT_MAX_ACTIONS,
                 stop_event: threading.Event | None = None,
                 cancel_event: threading.Event | None = None,
                 task_id: str = "", on_event=None,
                 screenshots: ScreenshotStore | None = None,
                 vision=None):
        self.desktop = desktop
        self.max_actions = max_actions
        self.task_id = task_id
        self.on_event = on_event
        self.actions_taken = 0
        self._stop_event = stop_event or threading.Event()
        self._cancel_event = cancel_event
        self._lock = threading.RLock()
        self._last_rects: list[tuple] = []     # provenance from last observe
        self.log: list[dict] = []
        self.screenshots = screenshots or ScreenshotStore()
        # Phase 10: pluggable vision backend (vendor-neutral). A failing
        # backend degrades to structural — it never blocks the loop.
        self.vision = vision if vision is not None else make_vision()
        with _REGISTRY_LOCK:
            _ACTIVE_SESSIONS[id(self)] = self

    # ------------------------------------------------------------ lifecycle
    @property
    def stopped(self) -> bool:
        if self._stop_event.is_set():
            return True
        return self._cancel_event is not None and self._cancel_event.is_set()

    def stop(self) -> None:
        self._stop_event.set()
        self.screenshots.purge()

    def _emit(self, ev: dict) -> None:
        if self.on_event:
            try:
                self.on_event(ev)
            except Exception:
                pass

    # --------------------------------------------------------- provenance
    def _coords_proven(self, x: int, y: int) -> bool:
        """True iff (x, y) lies inside a rect seen in the LAST observe."""
        for (x0, y0, x1, y1) in self._last_rects:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return True
        return False

    # ------------------------------------------------------------ observe
    def observe(self) -> dict:
        """Inspect the visible UI (read-only). Returns the structured
        snapshot the agent reasons from; records rects for provenance."""
        if self.stopped:
            return {"blocked": True, "error": "computer control stopped"}
        wins = self.desktop.list_windows()
        aw = self.desktop.active_window()
        frame = self.desktop.screenshot()
        self.screenshots.push(frame)
        with self._lock:
            self._last_rects = [w.rect for w in wins]
        out = {
            "active": aw.public() if aw else None,
            "windows": [w.public() for w in wins],
            "n_windows": len(wins),
            "screen_hash": (self.screenshots.hashes() or [""])[-1],
        }
        # vision layer (Phase 10): elements + description from the backend.
        # Degrades silently — a broken vision model must not block control.
        try:
            els = self.vision.detect_elements(self.desktop, frame)
            out["elements"] = [{"label": e.label, "rect": list(e.rect),
                                "score": e.score, "kind": e.kind}
                               for e in els[:24]]
            out["vision"] = getattr(self.vision, "name", "?")
            for e in els:                    # element rects join provenance
                with self._lock:
                    self._last_rects.append(e.rect)
            desc = self.vision.describe(self.desktop, frame)
            out["description"] = desc[:500]
        except Exception as e:
            out["vision"] = "unavailable"
            out["vision_error"] = str(e)[:120]
        return out

    # ------------------------------------------------------------- execute
    def execute(self, action: ComputerAction) -> dict:
        """One action, closed-loop: snapshot -> act -> snapshot -> verify.

        Returns a dict tool observation:
          blocked      -> {"blocked": True, "error": reason}
          executed     -> {"executed": True, "verified": True/False/None,
                           "verification": strategy, "observation": {...},
                           "actions_used": k, "max_actions": m, ...}
        """
        t0 = _now()
        if self.stopped:
            return self._blocked(action, "computer control stopped (emergency stop or task cancel)")
        with self._lock:
            if self.actions_taken >= self.max_actions:
                return self._blocked(
                    action,
                    f"action budget exhausted ({self.actions_taken}/{self.max_actions}) — "
                    "report the current state and stop; do not continue open-loop")
        if is_credential_target(action.target, action.description):
            return self._blocked(
                action, "credential entry is not in the Phase 5 safe set — "
                        "never type passwords/PINs/tokens")

        # Phase 10: semantic target -> coordinates via the vision backend,
        # resolved against the FRESH UI snapshot (never stale model-side
        # pixels). If the model gave no coordinates, this is the only way
        # in; if it did, they are still provenance-checked below.
        if action.action in ("click", "double_click") \
                and (action.x is None or action.y is None):
            resolved = None
            try:
                resolved = self.vision.locate(self.desktop, None, action.target)
            except Exception:
                resolved = None
            if resolved is None:
                return self._blocked(
                    action, f"no coordinates and vision could not locate "
                            f"{action.target!r} — call computer_observe, then "
                            "click a rect from the snapshot")
            action.x, action.y, _conf = resolved
            action.coordinate_source = "element_rect"

        # coordinate provenance — NEVER trust coordinates blindly
        proven = None
        if action.action in ("click", "double_click"):
            proven = self._coords_proven(action.x, action.y)
            if not proven:
                if action.coordinate_source == "model_raw":
                    action.coordinate_source = "model_raw"   # explicit -> must be confirmed (risk layer)
                else:
                    # claimed window/element coords that no observe supports
                    return self._blocked(
                        action,
                        "coordinates cannot be traced to a UI snapshot — "
                        "call computer_observe first, then click the element's rect")
            else:
                action.coordinate_source = action.coordinate_source or "window_rect"

        pre = snapshot(self.desktop)
        try:
            _res, timed_out = _with_timeout(lambda: self._dispatch(action),
                                            action.timeout)
        except Exception as e:
            return self._fail(action, t0, pre,
                              f"action failed: {type(e).__name__}: {e}")
        if timed_out:
            return self._fail(action, t0, pre,
                              f"action timed out after {action.timeout:.0f}s (abandoned)")

        with self._lock:
            self.actions_taken += 1
            used = self.actions_taken

        verification = verify_action(self.desktop, action, pre)
        post = snapshot(self.desktop)
        entry = redact_entry(action, verification, _now() - t0, True, post)
        with self._lock:
            self.log.append(entry)
        self._emit({"type": "computer_action", "action": action.action,
                    "target": action.target, "verified": verification.verified,
                    "used": used, "max": self.max_actions})

        obs = {
            "active_title": post["active_title"] or None,
            "n_windows": post["n_windows"],
            "screen_hash": post["screen_hash"][:8],
        }
        out = {
            "executed": True,
            "verified": verification.verified,
            "verification": verification.strategy,
            "verify_detail": verification.detail,
            "observation": obs,
            "actions_used": used,
            "max_actions": self.max_actions,
        }
        if verification.verified is False:
            out["error"] = ("verification FAILED — the expected effect did not "
                            "happen; do not claim success. Re-observe and decide: "
                            + verification.detail)
        return out

    def _blocked(self, action: ComputerAction, reason: str) -> dict:
        entry = redact_entry(action,
                             SimpleNamespace(verified=None, strategy="blocked", detail=reason),
                             0.0, False)
        with self._lock:
            self.log.append(entry)
        self._emit({"type": "computer_blocked", "action": action.action,
                    "reason": reason})
        return {"blocked": True, "error": reason}

    def _fail(self, action: ComputerAction, t0: float, pre: dict, reason: str) -> dict:
        entry = redact_entry(action,
                             SimpleNamespace(verified=False, strategy="exception", detail=reason),
                             _now() - t0, False, pre)
        with self._lock:
            self.log.append(entry)
        return {"blocked": True, "error": reason}

    # ------------------------------------------------------------ dispatch
    def _dispatch(self, a: ComputerAction) -> None:
        d = self.desktop
        if a.action in ("screenshot", "inspect_ui"):
            d.screenshot()
            return
        if a.action == "open_application":
            if not d.open_app(a.target):
                raise RuntimeError(f"could not launch {a.target!r}")
        elif a.action == "focus_window":
            if not d.focus_window(a.target):
                raise RuntimeError(f"no visible window matching {a.target!r}")
        elif a.action == "switch_window":
            if not d.switch_window(a.target):
                raise RuntimeError(f"could not switch to {a.target!r}")
        elif a.action == "click":
            d.click(int(a.x), int(a.y))
        elif a.action == "double_click":
            d.double_click(int(a.x), int(a.y))
        elif a.action == "type_text":
            d.type_text(a.text or "")
        elif a.action == "key_press":
            d.key_press(list(a.keys))
        elif a.action == "scroll":
            d.scroll(int(a.amount))
        elif a.action == "copy":
            d.copy()
        elif a.action == "paste":
            d.paste()
        else:
            raise RuntimeError(f"no dispatcher for {a.action!r}")


def _now() -> float:
    import time
    return time.time()
