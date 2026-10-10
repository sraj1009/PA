"""Self-improvement loop (Phase 3): post-task reflection.

After each completed task, BEE writes a brief self-review into
memory/lessons/YYYY-MM-DD.md: what worked / what failed / what to change.
These lessons are injected into the system prompt for future tasks.
"""
from __future__ import annotations

import logging
import re
from datetime import date

from .. import paths
from .client import LLMClient, LLMError
from .loop import AgentResult, _META_RAMBLE_RE

log = logging.getLogger("bee.reflect")

# Shapes the loop's answer detector does NOT cover, each one taken verbatim from
# memory/lessons/ on this machine (A40a). They talk about the tool surface or the
# loop's own counters instead of the task, and lessons get injected into every
# future system prompt — so a wrong example here is replayed indefinitely.
_PLUMBING_RE = re.compile(
    r"(?:provided|available|listed)\s+(?:function|tool)s?"
    r"|\bspecific\s+function\s+calls?"
    r"|\bthe\s+prompt\s+(?:did|does|doesn'?t|doesn)\b"
    r"|\blimitations\s+of\s+the\s+system\b|\b(?:my|its)\s+limitations\b"
    r"|\btask\s+stopped\s+early\b|\bstopped\s+by\s+user\b"
    r"|\bno\s+tool\s+failures\b"
    r"|\b\d+\s+iterations\b", re.I)

_EMPTYISH = {"", "none", "n/a", "na", "nil", "-", "nothing", "no issues", "n/a."}


def _all_bullets_empty(lesson: str) -> bool:
    """`worked: None / failed: None / next: None` teaches nothing and burns the
    prompt budget three files deep."""
    vals = re.findall(r"^\s*[-*]\s*(?:worked|failed|next)\s*:\s*(.*)$", lesson, re.I | re.M)
    if not vals:
        return False                      # not bullet-shaped; don't guess
    return all(v.strip().strip(".!").lower() in _EMPTYISH for v in vals)


def _usable(lesson: str, result: AgentResult) -> tuple[bool, str]:
    """A lesson is not a note to self — `context.recent_lessons()` injects it into
    every future system prompt, so junk here is replayed forever.

    The store on this machine holds `worked: No issues identified in task execution
    as the prompt did not include specific function calls for execution` and
    `worked: None of the provided functions support directly opening Chrome`: the
    exact plumbing-ramble the loop refuses to SHIP (A27e/A33) was allowed to be
    LEARNED, which teaches the model to answer about its own tool surface.
    """
    if len(lesson.strip()) < 24:
        return False, "too short to teach anything"
    if _META_RAMBLE_RE.search(lesson):
        return False, "about the tool surface, not the task"
    m = _PLUMBING_RE.search(lesson)
    if m:
        return False, f"about BEE's own machinery ({m.group(0)!r})"
    if _all_bullets_empty(lesson):
        return False, "every bullet is empty"
    return True, ""


def _trivial(result: AgentResult, task: str) -> bool:
    """Trivial tasks (canned replies, one-shot local answers, no tools) yield no
    lesson and would just burn an extra local-model call after every message."""
    if result.model in ("deterministic", "offline-rules"):
        return True
    if result.tool_calls > 0 or result.escalated or not result.ok:
        return False
    return result.iterations <= 1 and len(task or "") < 60


def reflect(ctx, task: str, result: AgentResult) -> str:
    """LLM-based self-review. Returns the lesson text ("" if skipped)."""
    if _trivial(result, task):
        return ""
    if getattr(result, "cancelled", False):
        # 'Stopped by user prematurely' is not a lesson; it is a stop (A40c).
        return ""
    cfg = ctx.cfg
    client = ctx.client or LLMClient(cfg)
    excerpt = (result.output or result.error or "")[:1200]
    prompt = (
        "You are reviewing your own completed task to get better. Write a VERY short review "
        "(max 120 words, bullet points) in this exact format:\n"
        "- worked: <what worked>\n- failed: <what failed or was weak; 'none' if smooth>\n"
        "- next: <one concrete thing to do differently next time>\n"
        f"Task: {task[:300]}\nFinal output: {excerpt}\n"
        f"Stats: model={result.model} iterations={result.iterations} tools={result.tool_calls} ok={result.ok}"
    )
    try:
        out = client.chat("local", [{"role": "user", "content": prompt}])
        lesson = (out.get("content") or "").strip()
    except LLMError:
        # never let reflection break the main flow
        lesson = f"- worked: {'task completed' if result.ok else 'task FAILED'} (auto-note, model {result.model})"
    except Exception:
        lesson = f"- worked: {'task completed' if result.ok else 'task FAILED'} (auto-note)"
    if not lesson:
        return ""
    keep, why = _usable(lesson, result)
    if not keep:
        log.info("lesson not stored: %s", why)
        return ""
    try:
        p = paths.LESSONS_DIR / f"{date.today().isoformat()}.md"
        stamp = time_stamp()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(f"\n## {stamp}\n{lesson}\n")
    except Exception as e:
        # A lesson that could not be written must not look like it was (A7).
        log.warning("could not write lesson: %s", e)
        return ""
    return lesson


def time_stamp() -> str:
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S")
