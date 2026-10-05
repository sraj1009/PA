"""Welcome Home — cinematic workspace startup protocol (ported from Super JARVIS / Hector).

Sequence (all steps from config.yaml `welcome:`):
  1. Welcome track (song_uri — Spotify/YouTube, "" = skip)
  2. Each configured URL in a FRESH Chrome window, snapped to its monitor,
     optionally fullscreen (F11)
  3. Spoken greeting (background thread, when TTS available)
  4. IDE focus: foreground an existing Cursor/VS Code window (never clones),
     or launch one; optional F11 fullscreen

Safety:
  - Retrigger guard (welcome.retrigger_s) so clap/voice spam can't spawn
    dozens of windows.
  - IDE detection matches the real process executable (Cursor.exe/Code.exe)
    via QueryFullProcessImageNameW and picks the largest main window
    (>=200x200) — title sniffing matched random windows and caused "cloning".
  - Every launch uses argument lists, shell=False, CREATE_NO_WINDOW on
    Windows (no cmd.exe intermediary, no stray consoles).

Usage: /welcome  ·  /welcome dry  ·  /welcome reset  ·  "welcome home" (fast path)
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

from . import register

log = logging.getLogger(__name__)

_last_run: float = 0.0  # monotonic timestamp of the last non-dry run


# ------------------------------------------------------------------ win32
def _popen_kwargs() -> dict:
    kw: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kw


def _main_hwnd_win32(process_names: tuple[str, ...]) -> int | None:
    """Largest top-level window of a matching process exe (>=200x200)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        GW_OWNER, GWL_EXSTYLE, GWL_STYLE = 4, -20, -16
        WS_EX_TOOLWINDOW, WS_VISIBLE = 0x80, 0x10000000
        wanted = {n.lower() for n in process_names}
        # (area, hwnd, visible, titled)
        candidates: list[tuple[int, int, bool, bool]] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _enum(hwnd, _lp) -> bool:
            if user32.GetWindow(hwnd, GW_OWNER):
                return True
            if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == 0:
                return True
            hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
            if not hproc:
                return True
            try:
                buf = ctypes.create_unicode_buffer(4096)
                size = wintypes.DWORD(len(buf))
                if not kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(size)):
                    return True
                exe_name = os.path.basename(buf.value).lower()
            finally:
                kernel32.CloseHandle(hproc)
            if exe_name not in wanted:
                return True
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            w, h = rect.right - rect.left, rect.bottom - rect.top
            if w < 200 or h < 200:
                return True
            # Electron hosts (e.g. Accio Work) can transiently lose
            # IsWindowVisible while keeping WS_VISIBLE — record, don't reject.
            visible = bool(user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd)
                           or (user32.GetWindowLongW(hwnd, GWL_STYLE) & WS_VISIBLE))
            titled = False
            tn = user32.GetWindowTextLengthW(hwnd)
            if tn:
                tbuf = ctypes.create_unicode_buffer(tn + 1)
                user32.GetWindowTextW(hwnd, tbuf, tn + 1)
                titled = bool(tbuf.value.strip())
            candidates.append((w * h, int(hwnd), visible, titled))
            return True

        user32.EnumWindows(_enum, 0)
    except Exception as exc:
        log.debug("Win32 window search failed: %s", exc)
        return None
    if not candidates:
        return None
    visible = [c for c in candidates if c[2]]
    if visible:
        return max(visible, key=lambda c: c[0])[1]
    # Transiently-hidden state: fall back to the largest TITLED window of the
    # matched process (still exe-filtered — never another app's window).
    titled = [c for c in candidates if c[3]]
    return max(titled or candidates, key=lambda c: c[0])[1]


def _foreground_hwnd(hwnd: int) -> None:
    import ctypes
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    fg = user32.GetForegroundWindow()
    tid_target = user32.GetWindowThreadProcessId(hwnd, None)
    tid_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    if tid_fg and tid_target:
        user32.AttachThreadInput(tid_fg, tid_target, True)
    user32.SetForegroundWindow(hwnd)
    if tid_fg and tid_target:
        user32.AttachThreadInput(tid_fg, tid_target, False)


def _monitor_rects() -> list[tuple[int, int, int, int]]:
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                        ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

        collected: list[tuple[int, int, int, int]] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                            ctypes.POINTER(RECT), wintypes.LPARAM)
        def _cb(hmon, _hdc, rect_ptr, _lp) -> bool:
            r = rect_ptr.contents
            collected.append((r.left, r.top, r.right, r.bottom))
            return True

        ctypes.windll.user32.EnumDisplayMonitors(None, None, _cb, 0)
        collected.sort(key=lambda box: (box[0], box[1]))
        return collected
    except Exception:
        return []


def _visible_hwnds() -> set[int]:
    if sys.platform != "win32":
        return set()
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        found: set[int] = set()

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _enum(hwnd, _lp) -> bool:
            if user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                found.add(int(hwnd))
            return True

        user32.EnumWindows(_enum, 0)
        return found
    except Exception:
        return set()


def _wait_new_hwnd(before: set[int], timeout_s: float = 6.0) -> int | None:
    deadline = time.monotonic() + max(0.5, timeout_s)
    while time.monotonic() < deadline:
        fresh = _visible_hwnds() - before
        if fresh:
            return max(fresh)
        time.sleep(0.15)
    return None


def _send_f11(hwnd: int) -> None:
    import ctypes
    user32 = ctypes.windll.user32
    VK_F11 = 0x7A
    _foreground_hwnd(hwnd)
    user32.keybd_event(VK_F11, 0, 0, 0)
    user32.keybd_event(VK_F11, 0, 0x0002, 0)


def _snap_hwnd(hwnd: int, monitor: int, fullscreen: bool) -> None:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        rects = _monitor_rects()
        if not rects:
            return
        left, top, right, bottom = rects[min(monitor - 1, len(rects) - 1)]
        SWP_NOZORDER, SWP_SHOWWINDOW = 0x0004, 0x0040
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetWindowPos(hwnd, None, left, top, right - left, bottom - top,
                            SWP_NOZORDER | SWP_SHOWWINDOW)
        if fullscreen:
            _send_f11(hwnd)
    except Exception as exc:
        log.debug("Could not place window: %s", exc)


# ------------------------------------------------------------------ pieces
def _ide_executable() -> str | None:
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            for sub in (os.path.join("Programs", "cursor", "Cursor.exe"),
                        os.path.join("Programs", "Cursor", "Cursor.exe"),
                        os.path.join("Programs", "Microsoft VS Code", "Code.exe")):
                cand = os.path.join(local, sub)
                if os.path.isfile(cand):
                    return cand
    return (shutil.which("cursor") or shutil.which("code")
            or shutil.which("cursor.exe") or shutil.which("Code.exe"))


def focus_or_launch_ide(cfg=None, fullscreen: bool = False) -> str:
    """Foreground the configured app's window (matched by process exe — never
    clones), or launch it from welcome.ide_path when none is running."""
    w = cfg.welcome if cfg is not None else None
    label = (getattr(w, "ide_name", "") or "IDE").strip() if w else "IDE"
    exes = tuple(getattr(w, "ide_exes", None) or ("cursor.exe", "code.exe")) if w else ("cursor.exe", "code.exe")

    hwnd = _main_hwnd_win32(exes)
    if hwnd is not None:
        try:
            _foreground_hwnd(hwnd)
            if fullscreen:
                _send_f11(hwnd)
                return f"{label} focused + fullscreen."
            return f"{label} focused (existing window)."
        except Exception as exc:
            log.debug("focus failed: %s", exc)

    exe = (getattr(w, "ide_path", "") or "").strip() if w else ""
    if not exe or not os.path.isfile(exe):
        exe = _ide_executable()
    if not exe:
        return f"{label} not found (set welcome.ide_path in config.yaml) — step skipped."
    try:
        subprocess.Popen([exe], **_popen_kwargs())
        return f"{label} launched: {os.path.basename(exe)}"
    except OSError as exc:
        return f"Could not launch {label}: {exc}"


def _chrome_executable() -> str | None:
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.environ.get("LOCALAPPDATA", "")):
            if not base:
                continue
            cand = os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
            if os.path.isfile(cand):
                return cand
    return shutil.which("google-chrome") or shutil.which("chrome") or shutil.which("chrome.exe")


def open_url_chrome(url: str, monitor: int, fullscreen: bool, label: str) -> str:
    url = (url or "").strip()
    if not url:
        return f"{label}: no URL configured — skipped."
    chrome = _chrome_executable()
    if not chrome:
        try:
            webbrowser.open(url)
            return f"{label} opened in default browser (Chrome not found)."
        except Exception as exc:
            return f"{label} failed: {exc}"
    before = _visible_hwnds()
    try:
        subprocess.Popen([chrome, "--new-window", url], **_popen_kwargs())
    except OSError as exc:
        return f"{label} failed: {exc}"
    if sys.platform == "win32":
        hwnd = _wait_new_hwnd(before)
        if hwnd is not None:
            _snap_hwnd(hwnd, monitor, fullscreen)
            return f"{label} opened in Chrome on monitor {monitor}{' (fullscreen)' if fullscreen else ''}."
        return f"{label} opened in Chrome (window placement timed out)."
    return f"{label} opened in Chrome."


def play_song(uri: str) -> str:
    uri = (uri or "").strip()
    if not uri:
        return "Welcome song skipped (no song_uri configured)."
    try:
        if sys.platform == "win32":
            os.startfile(uri)  # noqa: S606 - user-configured media URI
        else:
            webbrowser.open(uri)
        return f"Welcome track playing: {uri}"
    except OSError as exc:
        return f"Welcome song failed: {exc}"


# ------------------------------------------------------------------ protocol
def reset_guard() -> None:
    global _last_run
    _last_run = 0.0


def _due(cfg) -> bool:
    """Retrigger guard: has enough time passed since the last real run?"""
    return (time.monotonic() - _last_run) >= float(getattr(cfg.welcome, "retrigger_s", 60.0))


def run(*, cfg, dry_run: bool = False, speak_cb=None) -> str:
    """Execute the Welcome Home protocol. dry_run = report the plan only."""
    global _last_run
    w = cfg.welcome

    if not dry_run and not _due(cfg):
        elapsed = time.monotonic() - _last_run
        return (f"Welcome protocol already ran {elapsed:.0f}s ago "
                f"(min {float(w.retrigger_s):.0f}s between runs). Standing by. "
                f"`/welcome reset` to force.")

    if not getattr(w, "enabled", True):
        return "Welcome protocol is disabled in config.yaml (welcome.enabled: false)."

    urls = w.urls or []
    user = getattr(w, "user", "Boss")

    if dry_run:
        lines = ["**Welcome protocol — dry run (nothing opened):**"]
        lines.append(f"- song: {'play ' + w.song_uri if w.song_uri else 'skip (no song_uri)'}")
        for i, u in enumerate(urls, 1):
            if not isinstance(u, dict):
                u = {"url": str(u), "monitor": 1, "fullscreen": False}
            lines.append(f"- browser {i}: {u.get('url')} "
                         f"(monitor {u.get('monitor', 1)}, "
                         f"{'fullscreen' if u.get('fullscreen') else 'windowed'})")
        if speak_cb:
            lines.append(f"- greeting: 'Welcome home, {user}.'")
        ide_label = (getattr(w, "ide_name", "") or "IDE").strip()
        lines.append(f"- {ide_label}: {'focus/launch' + (' + F11' if w.ide_fullscreen else '') if w.focus_ide else 'skip'}")
        return "\n".join(lines)

    steps: list[str] = [play_song(w.song_uri)]
    for i, u in enumerate(urls, 1):
        if not isinstance(u, dict):
            u = {"url": str(u), "monitor": 1, "fullscreen": False}
        steps.append(open_url_chrome(u.get("url", ""), int(u.get("monitor", 1)),
                                     bool(u.get("fullscreen", False)), f"Browser {i}"))
    if speak_cb:
        threading.Thread(target=lambda: _safe_speak(speak_cb, user), daemon=True).start()
        steps.append(f"Speaking greeting: 'Welcome home, {user}.'")
    if w.focus_ide:
        steps.append(focus_or_launch_ide(cfg, fullscreen=bool(w.ide_fullscreen)))
    _last_run = time.monotonic()
    return "**Welcome home** ✅\n" + "\n".join(f"- {s}" for s in steps)


def _safe_speak(cb, user: str) -> None:
    try:
        cb()
    except Exception as exc:
        log.debug("welcome greeting failed: %s", exc)


# ------------------------------------------------------------------ command
@register("welcome", "/welcome [dry|reset]",
          "Run the Welcome Home workspace protocol (song → Chrome windows → greeting → IDE focus)")
def welcome_cmd(ctx, arg: str) -> str:
    a = (arg or "").strip().lower()
    if a == "reset":
        reset_guard()
        return "Welcome retrigger guard reset — next run will execute."
    dry = a in ("dry", "dry-run", "preview")
    speak_cb = None
    if not dry and ctx.cfg.voice.enabled and ctx.cfg.voice.speak:
        from ..voice import speak
        user = ctx.cfg.welcome.user
        speak_cb = lambda: speak.speak(f"Welcome home, {user}.", ctx.cfg)
    return run(cfg=ctx.cfg, dry_run=dry, speak_cb=speak_cb)
