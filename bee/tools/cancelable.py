"""Cancellable subprocess execution (J1 — audit item 3).

The old exec tools used `subprocess.run(timeout=...)`: a HUNG child (sleep,
network I/O, a wedged external tool) could not be cancelled by the user
(`kernel.cancel()` only set the loop's event, which `subprocess.run` never
consults), and on Windows a timeout killed the shell but often ORPHANED the
real child.

Now:
  * Popen + 200 ms poll loop
  * ctx.cancel_event is checked every poll -> the whole PROCESS TREE is
    killed (taskkill /T on Windows, killpg elsewhere) and the tool returns
    a 'cancelled' observation immediately — user cancellation propagates to
    running subprocesses, closing the "mid-subprocess kill" gap
  * timeout likewise guarantees a tree kill (no orphans)
  * children run in their own process group / new session so the tree kill
    is reliable
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

_POLL = 0.2
_NO_WINDOW = 0x08000000     # CREATE_NO_WINDOW
_NEW_GROUP = 0x00000200     # CREATE_NEW_PROCESS_GROUP


def _kill_tree(p: subprocess.Popen) -> None:
    try:
        if sys.platform.startswith("win"):
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                           capture_output=True, timeout=5,
                           creationflags=_NO_WINDOW)
        else:
            os.killpg(os.getpgid(p.pid), 9)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def run_cancelable(cmd, cwd, timeout: int, cancel_event=None,
                   shell: bool = False, env: dict | None = None,
                   encoding: str | None = None):
    """Run `cmd`; returns (returncode, stdout, stderr, kind) with kind in
    {'ok', 'timeout', 'cancelled'}. Never raises for control-flow cases.

    `encoding` decodes the child's pipes with errors='replace' instead of the
    locale codec (cp1252 here), for children told to write that encoding."""
    kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(cwd))
    if encoding:
        kwargs.update(encoding=encoding, errors="replace")
    else:
        kwargs["text"] = True
    if env is not None:
        kwargs["env"] = env
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = _NEW_GROUP
    else:
        kwargs["start_new_session"] = True
    p = subprocess.Popen(cmd, shell=shell, **kwargs)
    deadline = time.time() + max(1, int(timeout))
    while True:
        try:
            out, err = p.communicate(timeout=_POLL)
            code = p.returncode if p.returncode is not None else 1
            return code, out or "", err or "", "ok"
        except subprocess.TimeoutExpired:
            if cancel_event is not None and cancel_event.is_set():
                _kill_tree(p)
                try:
                    out, err = p.communicate(timeout=3)
                except Exception:
                    out, err = "", ""
                return 130, out or "", err or "", "cancelled"
            if time.time() > deadline:
                _kill_tree(p)
                try:
                    out, err = p.communicate(timeout=3)
                except Exception:
                    out, err = "", ""
                return 124, out or "", err or "", "timeout"
