"""systemctl — PC control tool (ported from Super JARVIS / Hector).

Battery, system stats, volume, brightness, lock, sleep, media keys and
show-desktop. Pure Windows APIs (ctypes keybd_event / powrprof + one CIM
query) — NO pyautogui/psutil, so no import cost and no extra deps. On this
box (low free RAM) that matters: every avoided import is a faster, lighter
process.

Reads (stats/battery) are safe; writes go through the guard: lock/sleep are
classified 'ask' in bee/guard.py, the rest 'allow'.
"""
from __future__ import annotations

import ctypes
import re
import subprocess
import sys
from .base import T

def _win() -> bool:
    return sys.platform == "win32"

def _ps(expr: str) -> str:
    """One PowerShell query; '' on any failure (caller declines/handles)."""
    if not _win():
        return ""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", expr],
                           capture_output=True, text=True, timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        return (r.stdout or "").strip()
    except Exception:
        return ""

# ------------------------------------------------------------------ keybd
_VK_VOLUME_MUTE = 0xAD
_VK_VOLUME_DOWN = 0xAE
_VK_VOLUME_UP = 0xAF
_VK_MEDIA_NEXT = 0xB0   # VK_MEDIA_NEXT_TRACK
_VK_MEDIA_PREV = 0xB1   # VK_MEDIA_PREV_TRACK
_VK_MEDIA_PLAY_PAUSE = 0xB3
_VK_LWIN = 0x5B
_VK_D = 0x44
_KEYUP = 0x0002

def _keybd(vk: int, n: int = 1) -> bool:
    """Send n full press+release cycles of virtual key vk (no console, no deps)."""
    if not _win():
        return False
    try:
        user32 = ctypes.windll.user32
        for _ in range(max(1, int(n))):
            user32.keybd_event(vk, 0, 0, 0)
            user32.keybd_event(vk, 0, _KEYUP, 0)
        return True
    except Exception:
        return False

def _show_desktop() -> bool:
    """Win+D via keybd_event (toggles the desktop)."""
    if not _win():
        return False
    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(_VK_LWIN, 0, 0, 0)
        user32.keybd_event(_VK_D, 0, 0, 0)
        user32.keybd_event(_VK_D, 0, _KEYUP, 0)
        user32.keybd_event(_VK_LWIN, 0, _KEYUP, 0)
        return True
    except Exception:
        return False

# ------------------------------------------------------------------ reads
_BATTERY_RX = re.compile(r"bat=(-?\d+)\s+ac=(-?\d)")
_STATS_RX = re.compile(r"cpu=(\d+)\s+freeMB=(\d+)\s+totMB=(\d+)\s+diskGB=(\d+)\s+bat=(-?\d+)")

# WmiBatteryStatus (root/WMI) on machines that have it; otherwise Win32_Battery
# (root/CIMV2) + Win32_PowerStatus for AC state. Verified on the BEE host, where
# root/WMI is absent and Win32_Battery.EstimatedChargeRemaining is the source.
_BATTERY_PS = (
    "$b=Get-CimInstance -Namespace root/WMI -ClassName WmiBatteryStatus -ErrorAction SilentlyContinue;"
    "if($b){\"bat=$($b.CurrentChargeLevel) ac=$($b.ACLineStatus)\"}else{"
    "$w=Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue;"
    "if($w){$p=Get-CimInstance Win32_PowerStatus -ErrorAction SilentlyContinue;"
    "$ac=-1;if($p){$ac=if($p.BatteryChargeStatus -in 1,3){1}else{0}};"
    "\"bat=$($w.EstimatedChargeRemaining) ac=$ac\"}}"
)

def get_battery() -> tuple[int, int] | None:
    """(percent, ac) — ac: 1 = plugged in, 0 = on battery, -1 = unknown.
    None when no battery is present (desktop/AC power)."""
    out = _ps(_BATTERY_PS)
    m = _BATTERY_RX.search(out or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))

def get_system_stats() -> dict | None:
    """CPU / RAM / disk / battery.

    Native-first: query the resident Go telemetry daemon (~1 ms). If it's not
    up (or not buildable), fall back to ONE PowerShell/CIM round-trip (~0.5-1 s).
    Returns None only if both paths fail.
    """
    try:
        from .. import native
        nat = native.stats()
    except Exception:
        nat = None
    if nat:
        free_mb = int(nat.get("ram_free_mb", 0))
        tot_mb = int(nat.get("ram_total_mb", 0))
        bat = nat.get("battery_pct", -1)
        ram_pct = nat.get("ram_pct")
        if ram_pct is None:
            ram_pct = int(round(100 * (1 - free_mb / tot_mb))) if tot_mb else 0
        return {
            "cpu_pct": int(round(float(nat.get("cpu_pct", 0)))),
            "ram_free_mb": free_mb,
            "ram_total_mb": tot_mb,
            "ram_pct": int(round(float(ram_pct))),
            "disk_free_gb": int(nat.get("disk_free_gb", 0)),
            "battery_pct": None if bat in (None, -1) else int(bat),
        }

    # Fallback: single PowerShell/CIM round-trip.
    out = _ps(
        "$c=[int]((Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average);"
        "$o=Get-CimInstance Win32_OperatingSystem;"
        "$f=[int]($o.FreePhysicalMemory/1MB); $t=[int]($o.TotalVisibleMemorySize/1024);"
        "$d=[int]((Get-PSDrive C).Free/1GB);"
        "$b=(Get-CimInstance -Namespace root/WMI -ClassName WmiBatteryStatus -ErrorAction SilentlyContinue);"
        "if($b){$bp=$b.CurrentChargeLevel}else{"
        "$w=Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue;"
        "$bp=if($w){$w.EstimatedChargeRemaining}else{-1}};"
        "\"cpu=$c freeMB=$f totMB=$t diskGB=$d bat=$bp\""
    )
    m = _STATS_RX.search(out or "")
    if not m:
        return None
    free_mb, tot_mb = int(m.group(2)), int(m.group(3))
    return {
        "cpu_pct": int(m.group(1)),
        "ram_free_mb": free_mb,
        "ram_total_mb": tot_mb,
        "ram_pct": int(round(100 * (1 - free_mb / tot_mb))) if tot_mb else 0,
        "disk_free_gb": int(m.group(4)),
        "battery_pct": None if m.group(5) == "-1" else int(m.group(5)),
    }

def format_system_stats(s: dict) -> str:
    ram = f"RAM {s['ram_free_mb']:,} MB free of {s['ram_total_mb']:,} MB ({s['ram_pct']}% used)"
    bat = f"Battery {s['battery_pct']}%" if s["battery_pct"] is not None else "Power: AC/desktop"
    return f"CPU {s['cpu_pct']}% · {ram} · C: {s['disk_free_gb']} GB free · {bat}"

# ------------------------------------------------------------------ writes
def set_volume(action: str, presses: int = 5) -> str:
    a = (action or "").lower().strip()
    if not _win():
        return "Volume control is only available on Windows."
    try:
        if a == "mute":
            return "Muted." if _keybd(_VK_VOLUME_MUTE) else "Could not toggle mute."
        if a == "unmute":
            return "Unmuted." if _keybd(_VK_VOLUME_MUTE) else "Could not toggle mute."
        if a in ("up", "increase", "raise", "louder", "higher"):
            n = int(presses)
        elif a in ("down", "decrease", "lower", "quieter"):
            n = -int(presses)
        elif a in ("max", "maximum"):
            n = 12
        else:
            return f"Unknown volume action '{action}' (up|down|max|mute|unmute)."
        ok = _keybd(_VK_VOLUME_UP if n > 0 else _VK_VOLUME_DOWN, abs(n))
        if not ok:
            return "Could not change volume."
        if n >= 12:
            return "Volume set to maximum."
        return f"Volume turned {'up' if n > 0 else 'down'}."
    except Exception as e:
        return f"Volume control error: {e}"

def set_brightness(level) -> str:
    try:
        level = int(level)
    except (TypeError, ValueError):
        return "Brightness must be a number between 0 and 100."
    level = max(0, min(100, level))
    if not _win():
        return f"Brightness control is only available on Windows (would set {level}%)."
    out = _ps(f"(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods).WmiSetBrightness(1, {level})")
    if out == "0":
        return f"Screen brightness set to {level}%."
    if not out:
        return f"Brightness set to {level}% (no WMI status returned — some displays ignore it)."
    return f"Brightness control returned status {out[:80]} (external displays are often not WMI-adjustable)."

def lock_workstation() -> str:
    if not _win():
        return "Lock is only available on Windows."
    try:
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"],
                       capture_output=True, timeout=10,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        return "PC locked."
    except Exception as e:
        return f"Could not lock the PC: {e}"

def sleep_pc() -> str:
    if not _win():
        return "Sleep is only available on Windows."
    try:
        powr = ctypes.windll.powrprof
        powr.SetSuspendState.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
        if powr.SetSuspendState(1, 0, 0):
            return "PC is going to sleep."
        return "Sleep requested (Windows declined — check power settings)."
    except Exception as e:
        return f"Could not put the PC to sleep: {e}"

def media(action: str) -> str:
    """System media keys (play/pause, next, previous) — no Spotify API needed."""
    if not _win():
        return "Media keys are only available on Windows."
    a = (action or "").lower().strip()
    if a in ("playpause", "play", "pause", "toggle"):
        ok, msg = _keybd(_VK_MEDIA_PLAY_PAUSE), "Play/pause sent."
    elif a in ("next", "nexttrack"):
        ok, msg = _keybd(_VK_MEDIA_NEXT), "Next track sent."
    elif a in ("prev", "previous", "prevtrack"):
        ok, msg = _keybd(_VK_MEDIA_PREV), "Previous track sent."
    else:
        return f"Unknown media action '{action}' (playpause|next|prev)."
    return msg if ok else "Could not send the media key."

def show_desktop() -> str:
    if not _win():
        return "Show-desktop is only available on Windows."
    return "Desktop shown (all windows minimized)." if _show_desktop() else "Could not show the desktop."

# ------------------------------------------------------------------ tool
def systemctl_tool(ctx, action: str, value: str = "") -> dict:
    """Dispatch one system action. Returns {'result': str} or {'error': str}."""
    a = (action or "").lower().strip()
    v = (value or "").strip()
    try:
        if a in ("stats", "system_stats", "status"):
            s = get_system_stats()
            if s is None:
                return {"error": "system stats unavailable (non-Windows or CIM query failed)"}
            return {"result": format_system_stats(s)}
        if a in ("battery", "battery_level"):
            b = get_battery()
            if b is None:
                return {"result": "No battery detected — desktop / AC power."}
            pct, ac = b
            state = {1: "plugged in", 0: "on battery"}.get(ac, "AC status unknown")
            return {"result": f"Battery {pct}% ({state})."}
        if a == "volume":
            return {"result": set_volume(v or "up")}
        if a == "brightness":
            return {"result": set_brightness(v)}
        if a == "lock":
            return {"result": lock_workstation()}
        if a == "sleep":
            return {"result": sleep_pc()}
        if a == "media":
            return {"result": media(v or "playpause")}
        if a in ("show_desktop", "desktop"):
            return {"result": show_desktop()}
    except Exception as e:
        return {"error": str(e)}
    return {"error": f"unknown action '{action}' (stats|battery|volume|brightness|lock|sleep|media|show_desktop)"}

def systemctl_tools():
    return [
        T("systemctl",
          "Control the PC (Windows): action=stats (CPU/RAM/disk/battery one-liner), battery, "
          "volume (value: up|down|max|mute|unmute), brightness (value: 0-100), lock, sleep, "
          "media (value: playpause|next|prev), show_desktop. Use for 'lock my pc', 'volume up', "
          "'next track', 'battery', 'system stats', 'put pc to sleep'. Returns a short result string.",
          {"type": "object", "properties": {
              "action": {"type": "string", "enum": ["stats", "battery", "volume", "brightness",
                                                    "lock", "sleep", "media", "show_desktop"]},
              "value": {"type": "string", "description": "action-dependent: volume dir, brightness 0-100, media key"}},
           "required": ["action"]},
          systemctl_tool),
    ]
