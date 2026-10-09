"""Desktop abstraction (Phase 5).

ComputerUseSession talks ONLY to this protocol. Two concrete desktops:

  MockDesktop      deterministic test double — window registry, launcher
                   hotspots, input log, clipboard, synthetic screenshots.
                   ALL Phase 5 tests run against this (no real automation
                   in CI, by design).
  WindowsDesktop   thin real implementation (win32gui windows/focus,
                   pyautogui input, mss capture, win32clipboard). Every
                   third-party import is LAZY and a missing dependency is a
                   clean DesktopError, never a crash at import time.

Honest status: WindowsDesktop is not exercised by the test suite (no
display in CI); the mock path is what is verified.
"""
from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class DesktopError(RuntimeError):
    pass


@dataclass
class WindowInfo:
    title: str
    cls: str = "Window"
    x: int = 0
    y: int = 0
    w: int = 1000
    h: int = 700
    visible: bool = True
    active: bool = False

    @property
    def rect(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    def contains(self, px: int, py: int) -> bool:
        x0, y0, x1, y1 = self.rect
        return x0 <= px <= x1 and y0 <= py <= y1

    def public(self) -> dict:
        return {"title": self.title, "class": self.cls, "rect": list(self.rect),
                "visible": self.visible, "active": self.active}


@runtime_checkable
class Desktop(Protocol):
    name: str

    def list_windows(self) -> list[WindowInfo]: ...
    def active_window(self) -> WindowInfo | None: ...
    def open_app(self, name: str) -> bool: ...
    def focus_window(self, title: str) -> bool: ...
    def switch_window(self, title: str) -> bool: ...
    def click(self, x: int, y: int, button: str = "left") -> None: ...
    def double_click(self, x: int, y: int) -> None: ...
    def type_text(self, text: str) -> None: ...
    def key_press(self, keys: list) -> None: ...
    def scroll(self, amount: int) -> None: ...
    def copy(self) -> None: ...
    def paste(self) -> None: ...
    def clipboard_get(self) -> str: ...
    def screenshot(self) -> bytes | None: ...


# --------------------------------------------------------------------- mock
class MockDesktop:
    """Deterministic desktop for tests.

    Windows: add_window(); launchers: set_launcher(title, x, y, w, h) — a
    click inside the rect 'opens' that window (mimics a Start-menu entry).
    Screenshots are deterministic byte hashes of the visible state, so
    screen_changed verification is real (a state change flips the hash).
    """

    name = "mock"

    def __init__(self):
        self._lock = threading.RLock()
        self._wins: list[WindowInfo] = []
        self._active: str | None = None
        self.input_log: list[tuple] = []
        self.clipboard = ""
        self.launchers: dict[str, tuple] = {}   # app title -> rect
        self.app_map: dict[str, str] = {}       # "chrome" -> "Google Chrome"
        self.screen_state = "A"
        self.type_buffer = ""

    # ------------------------------------------------------------ windows
    def add_window(self, title: str, cls: str = "Window",
                   rect=(0, 0, 1000, 700), make_active: bool = True) -> WindowInfo:
        w = WindowInfo(title=title, cls=cls, x=rect[0], y=rect[1],
                       w=rect[2] - rect[0], h=rect[3] - rect[1])
        self._wins.append(w)
        if make_active:
            self._active = title
        return w

    def set_launcher(self, app_title: str, x: int, y: int, w: int, h: int) -> None:
        self.launchers[app_title] = (x, y, x + w, y + h)   # stored as (x0,y0,x1,y1)

    def map_app(self, name: str, window_title: str) -> None:
        self.app_map[name.lower().strip()] = window_title

    def list_windows(self) -> list[WindowInfo]:
        with self._lock:
            out = [w for w in self._wins if w.visible]
            for w in out:
                w.active = (w.title == self._active)
            return out

    def active_window(self) -> WindowInfo | None:
        for w in self.list_windows():
            if w.title == self._active:
                return w
        return None

    # ------------------------------------------------------------ actions
    def _set_active(self, title: str) -> None:
        self._active = title
        self.screen_state = f"S-{title[:12]}"

    def open_app(self, name: str) -> bool:
        with self._lock:
            title = self.app_map.get(name.lower().strip()) or name
            if any(w.title == title for w in self._wins):
                self._set_active(title)
                return True
            self.add_window(title, cls="Application", make_active=True)
            return True

    def focus_window(self, title: str) -> bool:
        with self._lock:
            for w in self.list_windows():
                if title.lower() in w.title.lower():
                    self._set_active(w.title)
                    return True
        return False

    def switch_window(self, title: str) -> bool:
        return self.focus_window(title)      # alt-tab to the named window

    def click(self, x: int, y: int, button: str = "left") -> None:
        with self._lock:
            self.input_log.append(("click", x, y, button))
            for app_title, rect in self.launchers.items():
                if (rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]):
                    self.open_app(app_title)
                    return
            aw = self.active_window()
            if aw is not None and aw.contains(x, y):
                self.screen_state += "-c"     # something on screen changed

    def double_click(self, x: int, y: int) -> None:
        with self._lock:
            self.input_log.append(("double_click", x, y))
            for app_title, rect in self.launchers.items():
                if (rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]):
                    self.open_app(app_title)
                    return
            self.screen_state += "-d"

    def type_text(self, text: str) -> None:
        with self._lock:
            self.input_log.append(("type_text", len(text)))
            self.type_buffer += text          # payload stays inside the mock
            self.screen_state += "-t"         # visible text appeared

    def key_press(self, keys: list) -> None:
        with self._lock:
            self.input_log.append(("key_press", tuple(keys)))
            if tuple(k.lower() for k in keys) in (("ctrl", "c"), ("c", "ctrl")):
                pass
            self.screen_state += "-k"

    def scroll(self, amount: int) -> None:
        with self._lock:
            self.input_log.append(("scroll", amount))
            self.screen_state += f"-s{amount}"

    def copy(self) -> None:
        with self._lock:
            self.input_log.append(("copy",))
            self.clipboard = self.type_buffer or f"copied:{self.screen_state}"

    def paste(self) -> None:
        with self._lock:
            self.input_log.append(("paste",))
            self.type_buffer += self.clipboard
            self.screen_state += "-p"

    def clipboard_get(self) -> str:
        with self._lock:
            return self.clipboard

    def screenshot(self) -> bytes | None:
        with self._lock:
            state = "|".join(w.title for w in self.list_windows()) \
                    + f"#{self._active}#{self.screen_state}#{len(self.clipboard)}"
            return hashlib.sha256(state.encode()).digest()[:16]

    # ------------------------------------------------------------ test helpers
    def simulate_external_change(self, note: str = "user-moved") -> None:
        """Simulate the USER (or another app) changing the screen mid-task."""
        with self._lock:
            self.screen_state += f"-ext:{note}"


# --------------------------------------------------------------------- win32
class WindowsDesktop:
    """Real desktop (Windows-first). Lazy imports; missing deps -> DesktopError.

    Untested in CI (no display) — the mock path is the verified one.
    """

    name = "win32"

    def __init__(self):
        self._imports()

    def _imports(self):
        try:
            import win32con      # noqa: F401
            import win32gui      # noqa: F401
        except ImportError as e:
            raise DesktopError(
                f"win32 API unavailable: {e} — pip install -r requirements-desktop.txt")

    # ------------------------------------------------------------ windows
    def list_windows(self) -> list[WindowInfo]:
        import win32gui
        out: list[WindowInfo] = []
        fg = win32gui.GetForegroundWindow()

        def _cb(h, _):
            if not win32gui.IsWindowVisible(h):
                return
            title = win32gui.GetWindowText(h)
            if not title.strip():
                return
            l, t, r, b = win32gui.GetWindowRect(h)
            out.append(WindowInfo(title=title,
                                  cls=win32gui.GetClassName(h),
                                  x=l, y=t, w=max(1, r - l), h=max(1, b - t),
                                  active=(h == fg)))
        win32gui.EnumWindows(_cb, None)
        return out

    def active_window(self) -> WindowInfo | None:
        """Resolve the foreground window from its handle directly.

        The old version searched list_windows() for a window flagged active —
        but that list drops every untitled window, so a real foreground window
        with an empty title (common for Electron/overlay apps) reported
        "active: null", and the `active_window` verification strategy then
        reported a FAILED match when the truth is that it never saw the window.
        GetForegroundWindow() == 0 (a non-interactive session) still returns
        None: unknown is honest, a guess would be a false success."""
        import win32gui
        try:
            h = win32gui.GetForegroundWindow()
            if not h or not win32gui.IsWindow(h):
                return None
            title = win32gui.GetWindowText(h) or ""
            l, t, r, b = win32gui.GetWindowRect(h)
            return WindowInfo(title=title, cls=win32gui.GetClassName(h) or "",
                              x=l, y=t, w=max(1, r - l), h=max(1, b - t),
                              active=True)
        except Exception:
            for w in self.list_windows():     # last resort: the enumerated flag
                if w.active:
                    return w
            return None

    def _find_hwnd(self, title: str):
        import win32gui
        found = {}

        def _cb(h, _):
            if not win32gui.IsWindowVisible(h):
                return
            t = win32gui.GetWindowText(h)
            if t.strip() and title.lower() in t.lower():
                found.setdefault(h, t)
        win32gui.EnumWindows(_cb, None)
        return next(iter(found), None) if found else None

    def focus_window(self, title: str) -> bool:
        import win32gui
        h = self._find_hwnd(title)
        if not h:
            return False
        try:
            if win32gui.IsIconic(h):
                win32gui.ShowWindow(h, 9)   # SW_RESTORE
            win32gui.SetForegroundWindow(h)
            return True
        except Exception:
            return False

    def switch_window(self, title: str) -> bool:
        if self.focus_window(title):
            return True
        # alt-tab fallback
        import pyautogui
        pyautogui.hotkey("alt", "tab")
        return False                          # best effort — verify will decide

    def open_app(self, name: str) -> bool:
        import os
        import shutil
        import subprocess
        n = name.strip()
        p = shutil.which(n)
        if p:
            subprocess.Popen([p], shell=False)
            return True
        try:
            os.startfile(n)                   # known app / association
            return True
        except Exception:
            return False

    # ------------------------------------------------------------ input
    def _input(self):
        try:
            import pyautogui
        except ImportError as e:
            raise DesktopError(f"pyautogui unavailable: {e}")
        return pyautogui

    def click(self, x: int, y: int, button: str = "left") -> None:
        self._input().click(int(x), int(y), button=button)

    def double_click(self, x: int, y: int) -> None:
        self._input().doubleClick(int(x), int(y))

    def type_text(self, text: str) -> None:
        self._input().typewrite(text, interval=0.02)

    def key_press(self, keys: list) -> None:
        self._input().hotkey(*[str(k).lower() for k in keys])

    def scroll(self, amount: int) -> None:
        self._input().scroll(int(amount))

    def copy(self) -> None:
        self._input().hotkey("ctrl", "c")

    def paste(self) -> None:
        self._input().hotkey("ctrl", "v")

    def clipboard_get(self) -> str:
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            try:
                return win32clipboard.GetClipboardData(1) or ""   # CF_UNICODETEXT
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            return ""

    def screenshot(self) -> bytes | None:
        try:
            import mss
        except ImportError:
            return None
        try:
            with mss.mss() as sct:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                shot = sct.grab(mon)
                return bytes(shot.rgb)
        except Exception:
            return None


def make_desktop(cfg=None):
    """Default desktop factory — WindowsDesktop on Windows, DesktopError
    elsewhere (other platforms: not implemented yet, see docs). Tests inject
    MockDesktop via ctx.computeruse_desktop and never reach this."""
    import platform
    if platform.system() == "Windows":
        return WindowsDesktop()
    raise DesktopError(
        f"computer use is not implemented on {platform.system()} — "
        "supported platform: Windows 10/11 (see docs/COMPUTER_USE.md)")
