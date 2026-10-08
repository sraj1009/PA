"""Live-voice shared state — HTTP push bridge (replaces the temp-JSON file).

The LiveKit agent runs in its OWN process; the Web UI runs in the webapp
process. The previous design bridged them through a temp-dir JSON file
(single writer / multi reader) — which had a classic cross-process hazard
stale readers can see a half-fresh snapshot, no delivery signal, and the
file survived restarts so a dead agent's last state looked live forever.

Now the agent PUSHES each state transition to the web UI over loopback
HTTP (POST /livekit/state, bearer-authenticated like every other stateful
endpoint). The webapp holds the snapshot in MEMORY:

  * single writer  = the agent (one POST per state change)
  * single reader  = the webapp process (the /face/state poll)
  * no file        = no races, no temp-dir debris, nothing survives a
                     webapp restart (which is exactly what we want: a
                     restarted UI must not show a ghost from a dead agent)

Liveness: the snapshot carries a monotonic ts; /face/state reports age_s,
and once the agent's pushes stop (process died) the UI can tell the state
is stale (age_s grows) — something the file bridge could never show.

The push is best-effort by construction: a failed/absent web UI never
breaks the live call (short timeout, bounded warning rate).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.request

log = logging.getLogger("bee.livekit.state")

WEB_PORT_DEFAULT = 8787
PUSH_TIMEOUT_S = 0.8
WARN_COOLDOWN_S = 30.0

_STATE = {
    "state": "idle",
    "last_user": "",
    "last_reply": "",
    "ts": 0.0,
    "engine": "",
}
_LOCK = threading.Lock()
_last_warn = 0.0
_seq = 0


def _web_port() -> int:
    try:
        return int(os.environ.get("BEE_WEB_PORT") or WEB_PORT_DEFAULT)
    except ValueError:
        return WEB_PORT_DEFAULT


def _bearer_token() -> str:
    """Same source the webapp resolves from: BEE_WEB_TOKEN env, else the
    per-server token file (temp/web_token.txt — git-ignored)."""
    t = (os.environ.get("BEE_WEB_TOKEN") or "").strip()
    if t:
        return t
    try:
        from .. import paths
        f = paths.PROJECT_ROOT / "temp" / "web_token.txt"
        if f.exists():
            t = f.read_text(encoding="utf-8").strip()
            if t:
                return t
    except Exception:
        pass
    return ""


def set_state(state: str, *, last_user: str = "", last_reply: str = "",
              engine: str = "") -> None:
    """Record the state locally (debug) and push it to the web UI."""
    global _seq
    with _LOCK:
        _STATE["state"] = state
        if last_user:
            _STATE["last_user"] = last_user[:300]
        if last_reply:
            _STATE["last_reply"] = last_reply[:600]
        if engine:
            _STATE["engine"] = engine
        _STATE["ts"] = time.time()
        _seq += 1
        snap = dict(_STATE)
        snap["seq"] = _seq
    _push(snap)


def _push(snap: dict) -> bool:
    """Best-effort POST to the web UI. Returns True on 2xx."""
    global _last_warn
    port = _web_port()
    body = json.dumps(snap, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/livekit/state",
        data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {_bearer_token()}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=PUSH_TIMEOUT_S) as r:
            return 200 <= r.status < 300
    except Exception:
        # the live call must NEVER break on state delivery; warn at a
        # bounded rate (the web UI may simply be down)
        now = time.time()
        if now - _last_warn >= WARN_COOLDOWN_S:
            _last_warn = now
            log.warning("live voice state push failed (web UI up? port %s) — "
                        "state kept locally only", port)
        return False


def get_state() -> dict:
    """Last state recorded in THIS process (debug/diagnostics). The web UI
    reads its own in-memory copy (fed by the push), not this."""
    with _LOCK:
        out = dict(_STATE)
    ts = out.get("ts")
    out["age_s"] = round(max(0.0, time.time() - float(ts)), 1) if ts else None
    return out


def reset_for_tests() -> None:
    global _STATE, _seq, _last_warn
    with _LOCK:
        _STATE.update({"state": "idle", "last_user": "", "last_reply": "",
                       "ts": 0.0, "engine": ""})
        _seq = 0
        _last_warn = 0.0
