"""OS-level notifications + threshold alerting (audit item 6).

Two pieces:

  os_notify(title, text) — best-effort desktop toast, no dependencies:
      Windows: msg.exe when present (Windows Server), else the Shell
               NotifyIcon balloon — msg.exe is NOT installed on desktop
               Windows 10/11, so relying on it alone means no toast ever
               appears there. Balloon text passes via env vars, never
               interpolated into the script.
      Linux:   notify-send · macOS: osascript
      Fails quiet (log + return False) — alerting must never break the agent.
      Text is REDACTED and truncated before display: a toast must never
      become a secret leak on a locked-screen popup.

  check_thresholds(ctx) — evaluates the 24h metrics stats against configured
      thresholds and fires a toast + store notification per BREACH, with a
      per-key cooldown (default 1h) so a chronic condition does not spam:
        * provider_fail_rate  — share of failed LLM calls (with min sample)
        * verify_fail_rate    — share of agent tasks failing verification
        * permission_denied   — absolute count of denials in the window
        * metrics_size        — metrics stream near its rotation cap
      Registered as the daily `alert_scan` durable job; job failures/misses
      toast immediately through JobWorker (no job needed).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from .. import paths, privacy

log = logging.getLogger("bee.alerts")

MAX_TOAST_LEN = 200
_state_file = None          # temp/alert_state.json (set lazily per workspace)


def _state_path() -> Path:
    return paths.PROJECT_ROOT / "temp" / "alert_state.json"


def _load_state() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(d: dict) -> None:
    try:
        _state_path().parent.mkdir(parents=True, exist_ok=True)
        _state_path().write_text(json.dumps(d), encoding="utf-8")
    except Exception:
        pass


def _cooldown_ok(key: str, cooldown_s: float) -> bool:
    return time.time() - _load_state().get(key, 0) >= cooldown_s


def _mark_fired(key: str) -> None:
    st = _load_state()
    st[key] = time.time()
    _save_state(st)


_run = subprocess.run    # module-level for test injection


# Shell NotifyIcon balloon — works on every Windows 10/11 build. The title and
# text travel through ENV VARS, never as interpolated script text, so a message
# containing quotes/`$()` can't alter the command (alert text is model-derived).
_WIN_TOAST_PS = r"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon  = [System.Drawing.SystemIcons]::Information
$n.BalloonTipIcon  = 'Info'
$n.BalloonTipTitle = $env:BEE_TOAST_TITLE
$n.BalloonTipText  = $env:BEE_TOAST_TEXT
$n.Visible = $true
$n.ShowBalloonTip(6000)
Start-Sleep -Seconds 7
$n.Dispose()
"""


def _win_toast(title: str, text: str) -> bool:
    env = dict(os.environ, BEE_TOAST_TITLE=title, BEE_TOAST_TEXT=text)
    try:
        r = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                  _WIN_TOAST_PS], capture_output=True, timeout=25, env=env,
                 creationflags=0x08000000)          # CREATE_NO_WINDOW
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.info("windows toast unavailable: %s", e)
        return False
    if r.returncode != 0:
        log.info("windows toast exited %s: %s", r.returncode,
                 (r.stderr or b"").decode("utf-8", "replace")[:160])
    return r.returncode == 0


def os_notify(title: str, text: str) -> bool:
    """Best-effort desktop toast. Returns True only if the notifier actually
    succeeded. Never raises; never shows secrets (redacted + truncated).

    Windows: `msg.exe` ships with Windows SERVER only, so a desktop build used
    to fall through to nothing at all (and the old code still returned True
    without reading the exit status, which is why every alert looked delivered).
    Now: msg.exe first when present, Shell balloon otherwise.
    """
    try:
        msg = f"{title}: {text}"
        s, _n = privacy.redact(msg)
        s = " ".join(s.split())[:MAX_TOAST_LEN]
        t, _n2 = privacy.redact(title)
        t = " ".join(str(t).split())[:80]
        if sys.platform.startswith("win"):
            try:
                r = _run(["msg", "*", "0", s], capture_output=True, timeout=5,
                         creationflags=0x08000000)
                if r.returncode == 0:
                    return True
            except FileNotFoundError:
                pass           # no msg.exe on desktop builds -> balloon
            return _win_toast(t, s)
        if sys.platform == "darwin":
            safe = s.replace('"', "'")
            r = _run(["osascript", "-e",
                      f'display notification "{safe}" with title "{t}"'],
                     capture_output=True, timeout=5)
            return r.returncode == 0
        r = _run(["notify-send", t, s], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception as e:
        log.warning("os_notify failed (continuing): %s", e)
        return False


def _notify_store(ctx, message: str) -> None:
    """Also leave a durable trace in the automation store (if attached)."""
    w = getattr(ctx, "automation_worker", None)
    if w is None:
        return
    try:
        from ..automation.models import Notification
        w.store.add_notification(Notification(kind="alert", message=message[:500]))
    except Exception:
        pass


def check_thresholds(ctx) -> dict:
    """Evaluate 24h stats against cfg.alerts thresholds; fire per-breach
    alerts (toast + store notification) with cooldowns. Pure w.r.t. config
    — safe to run from the daily job or a test."""
    from . import metrics
    from .rotate import CAP_METRICS
    cfg = getattr(ctx.cfg, "alerts", None)
    if cfg is None or not getattr(cfg, "enabled", True):
        return {"skipped": "alerts disabled"}
    s = metrics.stats(window_hours=24)
    fired: list[dict] = []

    def breach(key: str, title: str, text: str):
        if _cooldown_ok(key, cfg.cooldown_seconds):
            toast = os_notify(title, text)
            _mark_fired(key)
            _notify_store(ctx, f"{title}: {text}")
            fired.append({"key": key, "toast": toast})

    llm_n = s.get("llm_calls") or 0
    pf_n = sum((s.get("provider_failures") or {}).values())
    if (llm_n >= cfg.provider_fail_min_calls
            and pf_n / llm_n >= cfg.provider_fail_rate):
        breach("provider", "BEE: provider failures",
               f"{pf_n}/{llm_n} LLM calls failed in 24h: {s.get('provider_failures')}")

    at_n = s.get("agent_tasks") or 0
    vf_n = s.get("agent_verify_fail") or 0
    if at_n >= cfg.min_tasks and vf_n / at_n >= cfg.verify_fail_rate:
        breach("verify", "BEE: verification failures",
               f"{vf_n}/{at_n} tasks failed verification in 24h")

    pd_n = s.get("permission_denied") or 0
    if pd_n >= cfg.permission_denied:
        breach("perm", "BEE: permission denials",
               f"{pd_n} permission denials in 24h (possible attack or misconfig)")

    try:
        size = paths.METRICS_FILE.stat().st_size if paths.METRICS_FILE.exists() else 0
        if size >= 0.8 * CAP_METRICS:
            breach("metrics_size", "BEE: log near cap",
                   f"metrics.jsonl at {size // 1024} KB (cap {CAP_METRICS // 1024} KB) — "
                   f"check the log_rotation job")
    except Exception:
        pass
    return {"breaches": fired,
            "window": {"llm_calls": llm_n, "provider_failures": pf_n,
                       "agent_tasks": at_n, "verify_fail": vf_n,
                       "permission_denied": pd_n}}
