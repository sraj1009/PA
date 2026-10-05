"""Tests for the Super JARVIS port: clap detector, systemctl tool + guard,
welcome protocol, and the new fast paths (wikipedia/play/volume/lock/sleep/
brightness/battery/show-desktop/photo).

Everything is unit-level: synthetic audio frames, monkeypatched Win32/PowerShell
stubs, dry-run protocol — no real key presses, no real windows, no network.
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pytest

from bee.agent import fastpaths
from bee.config import load_config
from bee.commands import welcome
from bee import guard
from bee.tools import systemctl
from bee.voice import clap as clap_mod


# ------------------------------------------------------------------ helpers
def _fastpath_name(task: str) -> str | None:
    hit = fastpaths.match(task)
    return hit[0].name if hit else None


class _FakeHttpResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload


# ================================================================ CLAP DETECTOR
def _mk_det(fired, **kw):
    defaults = dict(sample_rate=44100, block_ms=40, warmup_s=0.0, cooldown_s=1.5,
                    min_rms=0.01, min_double_gap_s=0.06, max_double_gap_s=0.40)
    defaults.update(kw)
    return clap_mod.ClapDetector(lambda: fired.append(1), **defaults)


def _feed(det, levels, dt=0.04, monkeypatch=None, t0=1000.0):
    """Feed synthetic blocks; advance a fake monotonic clock by dt each block."""
    n = det._block_samples()
    t = t0
    if monkeypatch:
        clock = [t]
        monkeypatch.setattr(clap_mod.time, "monotonic", lambda: clock[0])
    det._start_time = 0.0  # warmup_s=0 anyway
    det._running = True    # feed blocks directly (bypasses start()/sounddevice)
    for lvl in levels:
        if monkeypatch:
            clock[0] = t
        det._audio_callback(np.full((n, 1), lvl, dtype=np.float32), n, None, None)
        t += dt


def test_double_clap_triggers_once(monkeypatch):
    fired = []
    det = _mk_det(fired)
    blocks = [0.001] * 12          # noise floor settles ~0.001 -> threshold 0.01
    blocks += [0.5, 0.001]         # clap 1, quiet (re-arms)
    blocks += [0.5]                # clap 2 at +0.12s -> double clap
    _feed(det, blocks, monkeypatch=monkeypatch)
    assert fired == [1]


def test_single_clap_does_not_trigger(monkeypatch):
    fired = []
    det = _mk_det(fired)
    # one clap, then 40 quiet blocks (1.6s) — far beyond the 0.40s double window
    _feed(det, [0.001] * 12 + [0.5] + [0.001] * 40, monkeypatch=monkeypatch)
    assert fired == []


def test_sustained_loud_audio_not_multi_clap(monkeypatch):
    fired = []
    det = _mk_det(fired)
    blocks = [0.001] * 12
    blocks += [0.5] * 20           # sustained loud — hysteresis must not re-arm
    _feed(det, blocks, monkeypatch=monkeypatch)
    assert fired == []


def test_cooldown_blocks_second_double(monkeypatch):
    fired = []
    det = _mk_det(fired, cooldown_s=1.5)
    # first double clap
    seq = [0.001] * 12 + [0.5, 0.001, 0.5]
    _feed(det, seq, monkeypatch=monkeypatch, t0=1000.0)
    assert fired == [1]
    # immediate second double clap 0.6s later -> inside 1.5s cooldown -> ignored
    _feed(det, [0.5, 0.001, 0.5], monkeypatch=monkeypatch, t0=1000.0 + 0.36 + 0.6)
    assert fired == [1]


# ================================================================ SYSTEMCTL
def test_get_battery_parse(monkeypatch):
    monkeypatch.setattr(systemctl, "_ps", lambda expr: "bat=87 ac=0")
    assert systemctl.get_battery() == (87, 0)
    monkeypatch.setattr(systemctl, "_ps", lambda expr: "bat=100 ac=1")
    assert systemctl.get_battery() == (100, 1)
    # AC state unknown (Win32_PowerStatus absent) is a valid reading
    monkeypatch.setattr(systemctl, "_ps", lambda expr: "bat=100 ac=-1")
    assert systemctl.get_battery() == (100, -1)
    # no battery -> no output -> None
    monkeypatch.setattr(systemctl, "_ps", lambda expr: "")
    assert systemctl.get_battery() is None


def test_get_system_stats_parse(monkeypatch):
    # hermetic: native-first path must be disabled (the Go daemon may be live)
    import bee.native as _n
    monkeypatch.setattr(_n, "stats", lambda: None)
    monkeypatch.setattr(
        systemctl, "_ps",
        lambda expr: "cpu=42 freeMB=1234 totMB=15934 diskGB=29 bat=87")
    s = systemctl.get_system_stats()
    assert s["cpu_pct"] == 42
    assert s["ram_free_mb"] == 1234
    assert s["disk_free_gb"] == 29
    assert s["battery_pct"] == 87
    assert 0 <= s["ram_pct"] <= 100
    txt = systemctl.format_system_stats(s)
    assert "CPU 42%" in txt and "Battery 87%" in txt


def test_stats_no_battery(monkeypatch):
    import bee.native as _n
    monkeypatch.setattr(_n, "stats", lambda: None)
    monkeypatch.setattr(
        systemctl, "_ps",
        lambda expr: "cpu=5 freeMB=100 totMB=200 diskGB=10 bat=-1")
    s = systemctl.get_system_stats()
    assert s["battery_pct"] is None
    assert "AC/desktop" in systemctl.format_system_stats(s)


def test_keybd_recording(monkeypatch):
    presses = []
    monkeypatch.setattr(systemctl, "_keybd", lambda vk, n=1: presses.append((vk, n)) or True)
    assert "Volume turned up" in systemctl.set_volume("up", presses=5)
    assert (0xAF, 5) in presses
    assert "Volume turned down" in systemctl.set_volume("lower")
    assert "maximum" in systemctl.set_volume("max")
    assert presses[-1] == (0xAF, 12)
    assert "Muted" in systemctl.set_volume("mute")
    assert "Unknown volume action" in systemctl.set_volume("sideways")


def test_media_and_desktop(monkeypatch):
    presses = []
    monkeypatch.setattr(systemctl, "_keybd", lambda vk, n=1: presses.append(vk) or True)
    monkeypatch.setattr(systemctl, "_show_desktop", lambda: True)
    assert "Play/pause" in systemctl.media("playpause")
    assert 0xB3 in presses
    assert "Next track" in systemctl.media("next")
    assert 0xB0 in presses
    assert "Previous track" in systemctl.media("prev")
    assert "Unknown media action" in systemctl.media("fastforward")
    assert "Desktop shown" in systemctl.show_desktop()


def test_brightness_validation(monkeypatch):
    calls = []
    monkeypatch.setattr(systemctl, "_ps", lambda expr: calls.append(expr) or "0")
    assert "number" in systemctl.set_brightness("abc")
    assert "brightness set to 80%" in systemctl.set_brightness(80).lower()
    # clamping
    assert "set to 100%" in systemctl.set_brightness(250).lower()
    # no WMI result (external display)
    monkeypatch.setattr(systemctl, "_ps", lambda expr: "")
    out = systemctl.set_brightness(50)
    assert "not WMI-adjustable" in out or "no WMI status" in out


def test_systemctl_tool_dispatch(monkeypatch):
    monkeypatch.setattr(systemctl, "_ps", lambda expr: "bat=87 ac=1")
    res = systemctl.systemctl_tool(None, "battery")
    assert res["result"] == "Battery 87% (plugged in)."
    res = systemctl.systemctl_tool(None, "volume", "up")
    assert "error" not in res  # non-win or stubbed keybd path
    res = systemctl.systemctl_tool(None, "bogus")
    assert "unknown action" in res["error"]


def test_guard_systemctl_classification():
    assert "systemctl" in guard.EXEC_TOOLS
    assert guard.classify("systemctl", {"action": "lock"}) == ("ask", "lock PC")
    assert guard.classify("systemctl", {"action": "sleep"}) == ("ask", "sleep PC")
    assert guard.classify("systemctl", {"action": "volume", "value": "up"})[0] == "allow"
    assert guard.classify("systemctl", {"action": "stats"})[0] == "allow"


# ================================================================ WELCOME
def test_welcome_config_loaded():
    cfg = load_config()
    assert cfg.welcome.retrigger_s >= 0
    assert isinstance(cfg.welcome.urls, list)
    for u in cfg.welcome.urls:
        assert u.get("url", "").startswith("http")
    assert cfg.clap.action in ("welcome", "voice")
    assert 0 < cfg.clap.min_gap < cfg.clap.max_gap
    # focus target is configured (this box: Accio Work)
    assert cfg.welcome.ide_name
    assert cfg.welcome.ide_exes
    if cfg.welcome.ide_path:
        import os
        assert os.path.isfile(cfg.welcome.ide_path), "welcome.ide_path must exist"


def test_welcome_retrigger_guard():
    cfg = load_config()
    welcome.reset_guard()
    assert welcome._due(cfg) is True
    welcome._last_run = time.monotonic()
    assert welcome._due(cfg) is False
    welcome.reset_guard()
    assert welcome._due(cfg) is True


def test_welcome_dry_run_plan():
    cfg = load_config()
    out = welcome.run(cfg=cfg, dry_run=True)
    low = out.lower()
    assert "dry run" in low
    # the configured focus target label (e.g. "Accio Work") must appear
    assert (cfg.welcome.ide_name or "IDE").lower() in low
    for u in cfg.welcome.urls:
        assert u["url"] in out
        # regression: config dicts must be unwrapped, not printed as dict reprs
        assert "{" not in out.split(u["url"])[0].rsplit("browser", 1)[-1]
    # monitor settings from config must survive the dry run
    assert f"monitor {cfg.welcome.urls[0].get('monitor', 1)}" in out


def test_welcome_command_registered():
    from bee import commands
    cmd = commands.get("welcome")
    assert cmd is not None
    assert cmd.name == "welcome"
    assert cmd in commands.COMMANDS.values()  # registry intact
    # reset subcommand is side-effect free
    from types import SimpleNamespace
    out = cmd.handler(SimpleNamespace(cfg=load_config()), "reset")
    assert "guard reset" in out.lower()


def test_welcome_run_guarded():
    cfg = load_config()
    welcome._last_run = time.monotonic()  # pretend it just ran
    out = welcome.run(cfg=cfg, dry_run=False)
    assert "already ran" in out.lower()


# ================================================================ FAST PATHS
@pytest.mark.parametrize("task,expected", [
    ("what is the capital of France", "wikipedia"),
    ("who is Nikola Tesla", "wikipedia"),
    ("tell me about quantum computing", "wikipedia"),
    ("play never gonna give you up", "play"),
    ("put on some lofi", "play"),
    ("youtube react videos", "youtube"),
    ("pause the music", "media_pause"),
    ("stop the song", "media_pause"),
    ("resume the music", "media_resume"),
    ("next track", "media_next"),
    ("skip to the next song", "media_next"),
    ("previous track", "media_prev"),
    ("volume up", "volume"),
    ("turn the volume down", "volume"),
    ("volume max", "volume"),
    ("mute", None),  # 'mute' alone is ambiguous -> model pipeline
    ("how much is the battery", "battery"),
    ("battery level", "battery"),
    ("lock my pc", "lock"),
    ("lock", "lock"),
    ("put my pc to sleep", "sleep"),
    ("sleep my laptop", "sleep"),
    ("set brightness to 50", "brightness"),
    ("brightness 80", "brightness"),
    ("show desktop", "show_desktop"),
    ("minimize all windows", "show_desktop"),
    ("welcome home", "welcome"),
    ("take a photo", "photo"),
    ("how is the pc", "sysstats"),
    ("how is the pc doing", "sysstats"),
    # pre-existing routes stay intact
    ("open chrome", "open_app"),
    ("free ram", "sysstats"),
    ("what time is it", "time"),
])
def test_fastpath_matching(task, expected):
    assert _fastpath_name(task) == expected


def test_wikipedia_handler(monkeypatch):
    import httpx
    m = fastpaths.match("what is a transformer")
    assert m[0].name == "wikipedia"
    monkeypatch.setattr(
        httpx, "get",
        lambda *a, **k: _FakeHttpResponse(200, {
            "title": "Transformer (deep learning)", "type": "standard",
            "extract": "In deep learning, a transformer is a model architecture.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Transformer_(deep_learning)"}},
        }))
    out = m[0].handle(None, m[1])
    assert "Transformer (deep learning)" in out
    assert "Read more" in out
    # offline / disambiguation -> decline (None) so the model pipeline takes over
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeHttpResponse(200, {"type": "disambiguation"}))
    assert m[0].handle(None, m[1]) is None
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(OSError("net down")))
    assert m[0].handle(None, m[1]) is None


def test_battery_handler(monkeypatch):
    monkeypatch.setattr(systemctl, "get_battery", lambda: (17, 0))
    m = fastpaths.match("battery level")
    out = m[0].handle(None, m[1])
    assert "17%" in out and "on battery" in out and "low" in out
    monkeypatch.setattr(systemctl, "get_battery", lambda: (100, -1))
    assert "AC status unknown" in m[0].handle(None, m[1])
    monkeypatch.setattr(systemctl, "get_battery", lambda: None)
    assert "No battery" in m[0].handle(None, m[1])


def test_photo_graceful_without_cv2(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "cv2", None)  # force ImportError on `import cv2`
    ctx = type("Ctx", (), {"workspace": tmp_path})()
    out = fastpaths._photo(ctx, None)
    assert "requirements-vision.txt" in out


def test_volume_fastexec_shape():
    m = fastpaths.match("volume up")
    out = m[0].handle(None, m[1])
    assert isinstance(out, fastpaths.FastExec)
    assert out.tool == "systemctl"
    assert out.args == {"action": "volume", "value": "up"}


def test_play_fastexec_shape():
    m = fastpaths.match("play bohemian rhapsody")
    out = m[0].handle(None, m[1])
    assert isinstance(out, fastpaths.FastExec)
    assert out.tool == "shell"
    assert "youtube.com" in out.args["command"]


def test_lock_fastexec_shape():
    m = fastpaths.match("lock my pc")
    out = m[0].handle(None, m[1])
    assert isinstance(out, fastpaths.FastExec)
    assert out.args == {"action": "lock", "value": ""}


def test_brightness_fastexec_shape():
    m = fastpaths.match("set brightness to 50")
    out = m[0].handle(None, m[1])
    assert out.args == {"action": "brightness", "value": "50"}
    # >100 declines to the model pipeline
    assert fastpaths.match("set brightness to 250")[0].handle(None, fastpaths.match("set brightness to 250")[1]) is None
