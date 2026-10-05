"""Sanitize episodes for export/training: PII scrub + size bounds.

The training plane is rented hardware — nothing personal leaves this machine
unredacted. Counts are kept in metadata so the pipeline report can show how
much PII was present.
"""
from __future__ import annotations

from .. import privacy


def _scrub_str(s: str) -> tuple[str, int]:
    if not isinstance(s, str):
        return s, 0
    out, n = privacy.redact(s)
    return out, n


def scrub_episode(row: dict) -> tuple[dict, int]:
    """Returns (clean_row_copy, total_redactions)."""
    import copy
    r = copy.deepcopy(row)
    total = 0
    t, n = _scrub_str(r.get("task", ""))
    r["task"] = t
    total += n
    t, n = _scrub_str(r.get("output", ""))
    r["output"] = t
    total += n
    for ev in r.get("events", []):
        a, n1 = _scrub_str(ev.get("args", ""))
        ev["args"] = a
        res, n2 = _scrub_str(ev.get("result", ""))
        ev["result"] = res
        total += n1 + n2
    r.setdefault("metadata", {})
    r["metadata"]["redactions"] = total
    return r, total
