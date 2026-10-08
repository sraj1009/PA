"""Size-bounded rotation for append-only JSONL streams (M13 — audit item 2).

Every persistent stream in BEE used to grow without bound (metrics.jsonl,
audit.jsonl, receipts.jsonl, episodes/*.jsonl, automation/executions.jsonl).
Now each append chokepoint calls rotate_if_needed() BEFORE writing:

  * below the cap            -> no-op (one cheap stat per throttle window)
  * at/over the cap          -> shift .N-1 -> .N (oldest beyond max_backups
                                is dropped), move current -> .1, continue
                                appending to a fresh file

Guarantees:
  * best-effort: any failure is swallowed — rotation must never break the
    writer (worst case: a slightly oversized file)
  * throttled: at most one check per path per `min_interval_s` (wall clock),
    so a per-tool-call stream pays ~one stat per 30s, not per line
  * readers that need history across rotations (automation execution
    history) read the .1/.2 backups too — see automation/store.py

rotate_all() covers every known stream in one pass and is registered as the
daily `log_rotation` durable job (real work, like the other nightly jobs).
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

_lock = threading.Lock()
_state: dict[str, float] = {}          # path -> last check time

# stream caps (bytes, backups)
CAP_METRICS = 5_000_000                # 5 MB, 2 backups
CAP_AUDIT = 2_000_000                  # 2 MB, 2 backups
CAP_RECEIPTS = 2_000_000               # 2 MB, 2 backups
CAP_EPISODES = 5_000_000               # 5 MB per day-file, 1 backup
CAP_EXECUTIONS = 2_000_000             # 2 MB, 2 backups


def rotate_if_needed(path, max_bytes: int = CAP_METRICS, max_backups: int = 2,
                     min_interval_s: float = 30.0) -> bool:
    """Rotate `path` if it has grown past max_bytes. Returns True if a
    rotation happened. Throttled per path; failures are swallowed."""
    try:
        path = Path(path)
        key = str(path)
        with _lock:
            now = time.time()
            if now - _state.get(key, 0.0) < min_interval_s:
                return False
            _state[key] = now
        if not path.exists() or path.stat().st_size < max_bytes:
            return False
        for i in range(max_backups - 1, 0, -1):
            src = path.with_name(f"{path.name}.{i}")
            if src.exists():
                try:
                    src.replace(path.with_name(f"{path.name}.{i + 1}"))
                except OSError:
                    pass
        path.replace(path.with_name(f"{path.name}.1"))
        return True
    except Exception:
        return False


def force_reset_throttle(path) -> None:
    """Test hook: allow an immediate re-check for this path."""
    with _lock:
        _state.pop(str(path), None)


def rotate_all(workspace=None) -> dict:
    """Rotate every known stream; returns {str(path): 'rotated' | 'ok'}.
    min_interval_s=0 so the maintenance job is never throttled."""
    from .. import paths
    ws = Path(workspace) if workspace else paths.PROJECT_ROOT
    targets = [
        (paths.METRICS_FILE, CAP_METRICS, 2),
        (paths.PROJECT_ROOT / "audit.jsonl", CAP_AUDIT, 2),
        (paths.PROJECT_ROOT / "memory" / "receipts.jsonl", CAP_RECEIPTS, 2),
        (ws / "automation" / "executions.jsonl", CAP_EXECUTIONS, 2),
    ]
    report: dict[str, str] = {}
    for p, mb, bk in targets:
        try:
            report[str(p)] = "rotated" if rotate_if_needed(p, mb, bk, 0) else "ok"
        except Exception:
            report[str(p)] = "error"
    try:
        for f in sorted(paths.EPISODES_DIR.glob("*.jsonl")):
            report[str(f)] = "rotated" if rotate_if_needed(f, CAP_EPISODES, 1, 0) else "ok"
    except Exception:
        pass
    return report
