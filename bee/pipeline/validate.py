"""Episode validation — the SFT eligibility filter.

An episode is training-eligible only when its outcome is independently
verifiable. Verdicts: pass | fail | unknown. SFT builder keeps `pass`
(--loose also keeps `unknown`); `fail` is never trained on.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..tools.base import eval_safe


def detect_type(task: str, events: list[dict]) -> str:
    tools_used = {e.get("tool") for e in events}
    t = (task or "").lower()
    if "calculator" in tools_used or re.fullmatch(r"[\d\s\+\-\*/%\.\(\),^eE]+", (task or "").strip()):
        return "math"
    if "file_write" in tools_used:
        return "file"
    if any(k in t for k in ("dsa", "algorithm", "sort", "graph", "dp", "dynamic programming", "complexity")):
        return "dsa"
    if "shell" in tools_used or "sandbox_run" in tools_used:
        return "shell"
    if "web_search" in tools_used or "web_fetch" in tools_used:
        return "web"
    if "code_run" in tools_used:
        return "code"
    return "generic"


def _last_ev(events, name):
    out = None
    for e in events:
        if e.get("tool") == name and e.get("ok"):
            out = e
    return out


def validate(row: dict, workspace: Path | None = None) -> dict:
    """row: parsed episode JSON. Returns {type, verdict, why}."""
    task = row.get("task", "")
    events = row.get("events", [])
    output = row.get("output", "") or ""
    etype = detect_type(task, events)

    if not row.get("ok"):
        return {"type": etype, "verdict": "fail", "why": "episode failed"}

    if etype == "math":
        calc = _last_ev(events, "calculator")
        if calc:
            try:
                args = json.loads(calc.get("args") or "{}")
                expr = str(args.get("expression", ""))
                expected = str(eval_safe(expr))
                if expected in output:
                    return {"type": etype, "verdict": "pass", "why": "math verified"}
                return {"type": etype, "verdict": "fail", "why": f"answer lacks computed value {expected}"}
            except Exception as e:
                return {"type": etype, "verdict": "unknown", "why": f"calc check error: {e}"}
        return {"type": etype, "verdict": "unknown", "why": "no calculator event"}

    if etype == "file":
        if workspace is None:
            return {"type": etype, "verdict": "unknown", "why": "no workspace for file check"}
        last = _last_ev(events, "file_write")
        if not last:
            return {"type": etype, "verdict": "fail", "why": "file_write not ok"}
        try:
            args = json.loads(last.get("args") or "{}")
            p = (workspace / str(args.get("path", ""))).resolve()
            content = str(args.get("content", ""))
            if not p.exists():
                return {"type": etype, "verdict": "fail", "why": "written file missing"}
            cur = p.read_text(encoding="utf-8", errors="replace")
            if content and content not in cur:
                return {"type": etype, "verdict": "fail", "why": "file content mismatch"}
            return {"type": etype, "verdict": "pass", "why": "file state verified"}
        except Exception as e:
            return {"type": etype, "verdict": "unknown", "why": str(e)[:80]}

    if etype in ("shell", "code"):
        ok_last = events[-1] if events else None
        if ok_last and ok_last.get("ok"):
            return {"type": etype, "verdict": "pass", "why": "last exec event ok"}
        return {"type": etype, "verdict": "fail", "why": "last exec event not ok"}

    if etype in ("web", "dsa", "generic"):
        return {"type": etype, "verdict": "unknown", "why": "no cheap deterministic check"}

    return {"type": etype, "verdict": "unknown", "why": "?"}
