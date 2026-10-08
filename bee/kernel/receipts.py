"""Execution receipts (Phase 2) — append-only, redacted JSONL proof rows.

Every meaningful action (tool call + task-level run) produces a receipt.
Secrets are redacted through bee.privacy BEFORE writing — receipts are
telemetry, never a secret sink. Best-effort: persistence errors are logged,
never raised into the agent loop.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from .. import privacy
from .models import ExecutionReceipt

log = logging.getLogger("bee.kernel.receipts")
_lock = threading.Lock()


def _redact_value(v) -> str:
    try:
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    except Exception:
        s = str(v)
    s, _n = privacy.redact(s)
    return s[:4000]


class ReceiptLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, r: ExecutionReceipt) -> ExecutionReceipt:
        row = r.to_dict()
        row["arguments"] = _redact_value(row.get("arguments") or {})
        row["result"] = _redact_value(row.get("result") or "")
        row["error"] = _redact_value(row.get("error") or "")
        try:
            from ..monitor.rotate import rotate_if_needed
            with _lock:
                rotate_if_needed(self.path, 2_000_000, 2)   # M13: bounded
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception as e:
            log.debug("receipt persist failed (continuing in-memory): %s", e)
        return r

    def recent(self, n: int = 20) -> list[dict]:
        try:
            lines = [l for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]
        except Exception:
            return []
        out = []
        for l in lines[-n:]:
            try:
                out.append(json.loads(l))
            except Exception:
                continue
        return out
