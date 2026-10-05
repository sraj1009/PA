"""Event metrics — append-only JSONL stream + rolling stats.

Events: task, tool, route, redact, guard, verify, offline, episode.
No server, no dependencies; the dashboard and health check read the file.
"""
from __future__ import annotations

import json
import threading
import time
from collections import Counter

from .. import paths

_lock = threading.Lock()


def record(event: str, **data) -> None:
    try:
        row = {"ts": round(time.time(), 3), "event": event, **data}
        line = json.dumps(row, ensure_ascii=False, default=str)
        with _lock:
            paths.METRICS_DIR.mkdir(parents=True, exist_ok=True)
            with paths.METRICS_FILE.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        pass  # metrics must never break the agent


def load_all() -> list[dict]:
    if not paths.METRICS_FILE.exists():
        return []
    out = []
    for ln in paths.METRICS_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not ln.strip():
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def stats(window_hours: float = 24 * 7) -> dict:
    """Rolling aggregates over the last `window_hours`."""
    rows = load_all()
    if not rows:
        return {"total_tasks": 0}
    cutoff = time.time() - window_hours * 3600
    rows = [r for r in rows if r.get("ts", 0) >= cutoff]
    tasks = [r for r in rows if r.get("event") == "task"]
    tools = [r for r in rows if r.get("event") == "tool"]
    ok = sum(1 for t in tasks if t.get("ok"))
    tool_by_name = Counter(t.get("tool") for t in tools)
    tool_fail = Counter(t.get("tool") for t in tools if not t.get("ok"))
    return {
        "window_hours": window_hours,
        "total_tasks": len(tasks),
        "tasks_ok": ok,
        "success_rate": round(ok / len(tasks), 4) if tasks else None,
        "escalations": sum(1 for t in tasks if t.get("escalated")),
        "avg_seconds": round(sum(t.get("seconds", 0) for t in tasks) / len(tasks), 1) if tasks else None,
        "avg_iters": round(sum(t.get("iters", 0) for t in tasks) / len(tasks), 1) if tasks else None,
        "avg_tokens": round(sum(t.get("tokens", 0) for t in tasks) / len(tasks)) if tasks else None,
        "by_model": dict(Counter(t.get("model") for t in tasks)),
        "tool_calls": sum(tool_by_name.values()),
        "tool_failures": dict(tool_fail.most_common(10)),
        "top_tools": dict(tool_by_name.most_common(10)),
        "redactions": sum(1 for r in rows if r.get("event") == "redact"),
        "guard_denied": sum(1 for r in rows if r.get("event") == "guard" and r.get("action") == "deny"),
        "guard_asks": sum(1 for r in rows if r.get("event") == "guard" and r.get("action") == "ask"),
        "verify_fail": sum(1 for r in rows if r.get("event") == "verify" and r.get("verdict") == "fail"),
    }
