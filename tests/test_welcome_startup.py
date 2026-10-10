"""A53 — the Welcome Home protocol must only ever touch the windows it owns.

welcome.py documents that IDE/browser detection matches the real process executable
"via QueryFullProcessImageNameW" because "title sniffing matched random windows and
caused cloning". One path still ignored that rule, and one could spawn the clone.
Nothing in the suite drove this module before (19 % covered), which is how both
survived.
"""
from __future__ import annotations

import sys

import pytest

from bee.commands import welcome as w

pytestmark = pytest.mark.skipif(sys.platform != "win32",
                                reason="window placement is the Windows path")


def test_the_browser_window_is_found_by_executable_not_by_what_appeared(monkeypatch):
    seen: dict = {}
    snapped: list = []
    launched: list = []

    monkeypatch.setattr(w, "_chrome_executable", lambda: r"C:\Chrome\Application\chrome.exe")
    monkeypatch.setattr(w, "_visible_hwnds", lambda: {111})
    monkeypatch.setattr(w.subprocess, "Popen",
                        lambda cmd, **kw: launched.append(cmd) or type("P", (), {})())

    def fake_find(exes, exclude=None):
        seen["exes"], seen["exclude"] = tuple(exes), exclude
        return 999

    monkeypatch.setattr(w, "_main_hwnd_win32", fake_find)
    monkeypatch.setattr(w, "_snap_hwnd",
                        lambda hwnd, monitor, fs: snapped.append((hwnd, monitor, fs)))

    out = w.open_url_chrome("https://example.com", 2, False, "Browser 2")

    assert seen["exes"] == ("chrome.exe",), seen       # matched by process exe
    assert seen["exclude"] == {111}                    # and only a NEW window
    assert snapped == [(999, 2, False)]
    assert "monitor 2" in out


def test_a_foreign_new_window_is_never_dragged_onto_a_monitor(monkeypatch):
    """A toast or another app's window appearing during the six-second wait must
    not become the placement target: the pre-fix code took `max(any new hwnd)`."""
    state = {"before": {111}, "now": {111, 555}}      # 555 = someone else's window
    monkeypatch.setattr(w, "_visible_hwnds", lambda: state["now"])
    # the exe filter correctly finds nothing belonging to chrome
    monkeypatch.setattr(w, "_main_hwnd_win32",
                        lambda exes, exclude=None: None)
    assert w._wait_new_window(("chrome.exe",), state["before"], timeout_s=0.3) is None


def test_a_failed_focus_does_not_launch_a_second_window(monkeypatch):
    pops: list = []
    monkeypatch.setattr(w, "_main_hwnd_win32", lambda exes, exclude=None: 777)

    def boom(hwnd):
        raise OSError("foreground lock denied")

    monkeypatch.setattr(w, "_foreground_hwnd", boom)
    monkeypatch.setattr(w.subprocess, "Popen", lambda cmd, **kw: pops.append(cmd))

    class W:
        ide_name, ide_exes, ide_path = "Accio Work", ["accio.exe"], ""

    class Cfg:
        welcome = W()

    out = w.focus_or_launch_ide(Cfg())
    assert pops == [], f"a second instance was launched: {pops}"
    assert "could not be focused" in out and "Accio Work" in out
