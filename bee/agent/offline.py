"""Deterministic offline fallback — real answers for a narrow task class when
neither local nor cloud LLM is reachable. Never guesses: anything outside the
handled classes gets an explicit "what I can still do" message.

This is the bottom of the fallback chain: local LLM → cloud LLM → offline rules.
"""
from __future__ import annotations

import datetime
import re

from ..tools.base import eval_safe

def _try_math(task: str) -> str | None:
    from . import router  # lazy import: shared phrase-aware math extractor
    expr = router.math_expr(task)
    if expr is None:
        return None
    try:
        return f"{task.strip()} = {eval_safe(expr)}"
    except Exception:
        return None

def _try_sort(task: str) -> str | None:
    m = re.search(r"\[([^\[\]]+)\]", task)
    if not m or not re.search(r"\bsort|ascending|descending|smallest|largest|order\b", task, re.I):
        return None
    try:
        nums = [float(x) for x in re.findall(r"-?\d+\.?\d*", m.group(1))]
    except ValueError:
        return None
    if not nums:
        return None
    desc = re.search(r"\bdesc|largest|reverse|highest\b", task, re.I)
    out = sorted(nums, reverse=bool(desc))
    out = [int(x) if x == int(x) else x for x in out]
    return f"Sorted ({'descending' if desc else 'ascending'}): {out}"

def _try_list(task: str, workspace) -> str | None:
    if not re.search(r"\b(list|show|ls)\b.*\b(file|folder|directory|workspace|top.level)\b", task, re.I):
        return None
    entries = sorted(p.name + ("/" if p.is_dir() else "") for p in workspace.iterdir()
                     if not p.name.startswith("."))
    return "Top-level workspace entries:\n" + "\n".join(entries[:80]) or "(empty)"

def run_offline(task: str, workspace) -> str:
    """Returns a deterministic answer, or an honest capability message."""
    t = _try_math(task)
    if t:
        return f"[offline·deterministic] {t}"
    t = _try_sort(task)
    if t:
        return f"[offline·deterministic] {t}"
    t = _try_list(task, workspace)
    if t:
        return f"[offline·deterministic] {t}"
    if re.search(r"\b(time|date|day)\b", task, re.I):
        return f"[offline·deterministic] Now: {datetime.datetime.now():%Y-%m-%d %H:%M:%S} (Asia/Kolkata)"
    if re.search(r"\b(who are you|your name|what are you)\b", task, re.I):
        return "[offline] I'm BEE. The language models (local & cloud) are unreachable right now, " \
               "so I can only run deterministic operations: math, sorting, file listing, and time."
    return ("[offline] No language model reachable (Ollama down and no cloud configured/reachable). "
            "I can still do deterministically: math expressions, sorting a numeric list, listing the "
            "workspace, and the clock. Start Ollama (`ollama serve` / app) for full capabilities.")
