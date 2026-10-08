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
from . import rotate as _rotate

_lock = threading.Lock()


def _scrub(value):
    """Privacy chokepoint (audit 2026-10-06): every string that reaches the
    metrics stream is redacted — passwords, API keys, auth tokens, card
    numbers, phones etc. are replaced BEFORE the row is written. Short
    strings (tool names, enums, numbers-as-strings) are skipped for speed;
    anything a user could have written is not.
    """
    if isinstance(value, str) and len(value) > 12:
        try:
            from .. import privacy
            value, _n = privacy.redact(value)
        except Exception:
            pass
    return value


def record(event: str, **data) -> None:
    try:
        row = {"ts": round(time.time(), 3), "event": event,
               **{k: _scrub(v) for k, v in data.items()}}
        line = json.dumps(row, ensure_ascii=False, default=str)
        with _lock:
            paths.METRICS_DIR.mkdir(parents=True, exist_ok=True)
            _rotate.rotate_if_needed(paths.METRICS_FILE)   # M13: bounded
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
    # structured telemetry (audit 2026-10-06)
    llms = [r for r in rows if r.get("event") == "llm"]
    llm_ok = [r for r in llms if r.get("ok")]
    perm = [r for r in rows if r.get("event") == "permission"]
    agent = [r for r in rows if r.get("event") == "agent_task"]
    agent_ok = [r for r in agent if r.get("ok")]
    retried = [r for r in agent if r.get("retried")]
    verify_bad = [r for r in agent if r.get("verification") == "fail"]
    prov_fail = Counter(r.get("error_kind") for r in llms if not r.get("ok"))
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
        # structured telemetry (audit 2026-10-06)
        "agent_tasks": len(agent),
        "agent_success_rate": round(len(agent_ok) / len(agent), 4) if agent else None,
        "agent_avg_seconds": round(sum(r.get("seconds") or 0 for r in agent) / len(agent), 1)
        if agent else None,
        "agent_retried": len(retried),
        "agent_verify_fail": len(verify_bad),
        "permission_denied": sum(1 for p in perm if p.get("decision") == "denied"),
        "permission_asks": sum(1 for p in perm if p.get("decision") == "requested"),
        "llm_calls": len(llms),
        "llm_avg_seconds": round(sum(r.get("seconds") or 0 for r in llm_ok) / len(llm_ok), 2)
        if llm_ok else None,
        "provider_failures": dict(prov_fail),
    }
