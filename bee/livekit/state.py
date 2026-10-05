"""Shared live-voice state, bridged across processes via a temp-dir JSON file.

The LiveKit agent runs in its OWN process; the Web UI (``/face`` + ``/livekit``)
runs in the webapp process. Two processes can't share module memory, so state is
persisted to a tiny JSON file in the OS temp dir:

  * single writer  = the agent (writes on every state change)
  * multi-reader   = the webapp (reads on every ``/face/state`` poll)

Writes are a handful of bytes and only happen on state transitions
(idle/listening/thinking/speaking/error), so the cost is negligible — and the
temp dir keeps it off OneDrive, so there is no sync latency or file locking.
Kept in its own module so ``webapp`` never imports the (heavy) livekit deps.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

# state: idle | listening | thinking | speaking | error
_STATE = {
    "state": "idle",
    "last_user": "",
    "last_reply": "",
    "ts": 0.0,
    "engine": "",
}

_STATE_FILE = Path(tempfile.gettempdir()) / "bee_livekit_state.json"


def _write_file(snapshot: dict) -> None:
    """Atomic best-effort write (temp + replace) so readers never see partial JSON."""
    try:
        tmp = _STATE_FILE.with_name(_STATE_FILE.name + ".tmp")
        tmp.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, _STATE_FILE)
    except Exception:
        # state persistence must never break the live call
        pass


def set_state(state: str, *, last_user: str = "", last_reply: str = "",
              engine: str = "") -> None:
    _STATE["state"] = state
    if last_user:
        _STATE["last_user"] = last_user[:300]
    if last_reply:
        _STATE["last_reply"] = last_reply[:600]
    if engine:
        _STATE["engine"] = engine
    _STATE["ts"] = time.time()
    _write_file(dict(_STATE))


def get_state() -> dict:
    """Return the latest state, preferring the on-disk snapshot (which is what
    the *other* process — the agent — last wrote)."""
    snap = None
    try:
        if _STATE_FILE.exists():
            snap = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            if not isinstance(snap, dict):
                snap = None
    except Exception:
        snap = None
    out = dict(snap) if snap else dict(_STATE)
    out.setdefault("state", "idle")
    out.setdefault("last_user", "")
    out.setdefault("last_reply", "")
    out.setdefault("engine", "")
    ts = out.get("ts")
    out["age_s"] = round(max(0.0, time.time() - float(ts)), 1) if ts else None
    return out
