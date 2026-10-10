"""Append-only audit trail for tool calls + permission decisions.

Every execution-tool call (and every guard decision, including denials) is
recorded here as one JSONL row in `audit.jsonl` (project root, git-ignored).
All argument/reason text is passed through bee.privacy.redact BEFORE
persistence — the audit file must never become a new secret sink.

Design:
  - best-effort: auditing must never break the agent (all exceptions swallowed)
  - single lock, O(1) appends, no rotation in Phase 1 (size is small:
    one line per exec-tool call; rotation lands with metrics in Phase 4)
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from .. import privacy

_lock = threading.Lock()


def audit_path() -> Path:
    from .. import paths
    return paths.PROJECT_ROOT / "audit.jsonl"


def record(*, tool: str, args: dict | None, decision, action: str,
           ok: bool = True, seconds: float = 0.0, blocked: bool = False,
           source: str = "agent", path: Path | None = None) -> None:
    """Record one tool-call audit row. `decision` is a risk.RiskDecision
    (or None for non-exec tools, in which case risk fields are omitted)."""
    try:
        row = {"ts": round(time.time(), 3), "tool": tool, "action": action,
               "ok": bool(ok), "blocked": bool(blocked),
               "seconds": round(float(seconds or 0.0), 2), "source": source}
        try:
            s, _ = privacy.redact(json.dumps(args or {}, ensure_ascii=False, default=str))
            row["args"] = s[:2000]
        except Exception:
            row["args"] = "<unserializable>"
        if decision is not None:
            row["risk"] = {"level": decision.level.name,
                           "capabilities": sorted(decision.capabilities),
                           "approval": decision.require_approval}
            try:
                s2, _ = privacy.redact(str(decision.reason or ""))
                row["risk"]["reason"] = s2[:300]
            except Exception:
                row["risk"]["reason"] = ""
        p = path or audit_path()
        line = json.dumps(row, ensure_ascii=False)
        with _lock:
            p.parent.mkdir(parents=True, exist_ok=True)
            from ..monitor.rotate import rotate_if_needed
            rotate_if_needed(p, 2_000_000, 2)               # M13: bounded
            from .. import safeio
            safeio.append_line(p, line)
    except Exception:
        pass  # audit must never break the agent


def recent(n: int = 50) -> list[dict]:
    """Last n audit rows (for /audit-style inspection + tests)."""
    p = audit_path()
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines()[-n:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out
