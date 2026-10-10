"""Cross-process-safe line appends for BEE's JSONL / markdown streams.

Every persistent stream in BEE (metrics, audit, receipts, episodes, memory,
eval results) used the same pattern: a module-level `threading.Lock()` around
`open(path, "a")`. That only serialises threads of ONE process. This machine runs
several BEE processes at once (the assistant, the dashboard, the scheduler, a
voice bridge — see A39, where two of them fought over the working tree), and
Windows makes no atomic-append promise, so their writes interleaved.

Measured before the fix (6 processes x 60 lines each, `tests/test_safe_append.py`
keeps the small version of this): 302 of 360 lines survived at 60 B, 244 at 4 KB,
136 at 60 KB — with 4-94 torn fragments per run. That is the `metrics.jsonl`
fragment A44c recorded as "unattributable". A raw `os.write` on an `O_APPEND` fd
did NOT help (136 of 360); the byte-range lock below is what makes it safe
(360 of 360, 0 torn, at every size).

Rotation stays the caller's business (see `monitor.rotate`): a rotate that loses
the race on a file another process holds open just fails softly and retries,
which is why appending through here does not need to know about caps.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

_lock = threading.Lock()      # flock/lockf are per-fd on some platforms: keep threads out
_TIMEOUT = 10.0               # a wedged writer must not hang the agent


def _acquire(fd: int) -> None:
    deadline = time.time() + _TIMEOUT
    while True:
        try:
            if sys.platform.startswith("win"):
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            if time.time() >= deadline:
                raise
            time.sleep(0.02)


def _release(fd: int) -> None:
    try:
        if sys.platform.startswith("win"):
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


def append_text(path, text: str) -> None:
    """Write `text` (bytes exactly as given) at the end of the file, with no other
    writer able to interleave. Adds the parent directory; never touches the file
    except by appending.

    Raises OSError if the stream cannot be locked within _TIMEOUT — callers that
    treat telemetry as best-effort keep their own try/except.
    """
    data = text.encode("utf-8", errors="replace")
    p = Path(path)
    with _lock:
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(p), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            # Lock byte 0, not the byte at the current position: with O_APPEND
            # every process sits at its own EOF, so locking "here" would let two
            # writers hold non-overlapping ranges and interleave anyway. The
            # append destination is unaffected by the seek (O_APPEND re-positions
            # at write time on both platforms).
            os.lseek(fd, 0, os.SEEK_SET)
            _acquire(fd)
            try:
                while data:
                    data = data[os.write(fd, data):]
            finally:
                _release(fd)
        finally:
            os.close(fd)


def append_line(path, line: str) -> None:
    """Append one JSONL record (the newline is added here)."""
    append_text(path, line + "\n")


def append_json(path, row: dict) -> None:
    append_line(path, json.dumps(row, ensure_ascii=False, default=str))
