"""Native Go telemetry daemon: importability, stats mapping, graceful fallback.

These tests never require the daemon to be running — they exercise the
native-first logic in get_system_stats() with a stubbed native.stats(), and the
PowerShell fallback path with a stubbed _ps().
"""
from bee import native
from bee.tools import systemctl


def test_native_module_surface():
    assert native.ADDR == "127.0.0.1:8790"
    assert native.BASE == "http://127.0.0.1:8790"
    assert callable(native.stats)
    assert callable(native.start_background)
    assert callable(native.healthy)
    assert callable(native.stop)


def test_stats_returns_dict_or_none():
    # No daemon dependency: must return a dict (if up) or None (if down), never raise.
    s = native.stats()
    assert s is None or isinstance(s, dict)


def test_get_system_stats_native_first(monkeypatch):
    """Daemon present -> get_system_stats maps native fields (no PowerShell)."""
    fake = {"cpu_pct": 12.34, "ram_free_mb": 5000.0, "ram_total_mb": 16000.0,
            "ram_pct": 68.7, "disk_free_gb": 200.0, "battery_pct": 96}
    monkeypatch.setattr(native, "stats", lambda *a, **k: fake)
    called = {}
    monkeypatch.setattr(systemctl, "_ps", lambda *a, **k: called.update(ps=1) or "")
    s = systemctl.get_system_stats()
    assert s is not None
    assert s["cpu_pct"] == 12
    assert s["ram_free_mb"] == 5000
    assert s["ram_pct"] == 69          # round(68.7)
    assert s["disk_free_gb"] == 200
    assert s["battery_pct"] == 96
    assert "ps" not in called          # native path must NOT hit PowerShell


def test_get_system_stats_battery_absent(monkeypatch):
    fake = {"cpu_pct": 5.0, "ram_free_mb": 1000.0, "ram_total_mb": 8000.0,
            "ram_pct": 87.5, "disk_free_gb": 50.0, "battery_pct": -1}
    monkeypatch.setattr(native, "stats", lambda *a, **k: fake)
    s = systemctl.get_system_stats()
    assert s is not None
    assert s["battery_pct"] is None    # -1 means no battery
    assert s["ram_pct"] == 88          # round-half-to-even


def test_get_system_stats_fallback_when_daemon_down(monkeypatch):
    """native.stats() is None -> falls back to PowerShell (stubbed), no crash."""
    monkeypatch.setattr(native, "stats", lambda *a, **k: None)
    monkeypatch.setattr(systemctl, "_ps", lambda *a, **k:
                        "cpu=7 freeMB=2000 totMB=16000 diskGB=100 bat=-1")
    s = systemctl.get_system_stats()
    assert s is not None
    assert s["cpu_pct"] == 7
    assert s["ram_free_mb"] == 2000
    assert s["disk_free_gb"] == 100
    assert s["battery_pct"] is None
