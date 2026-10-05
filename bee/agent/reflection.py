"""Self-improvement loop (Phase 3): post-task reflection.

After each completed task, BEE writes a brief self-review into
memory/lessons/YYYY-MM-DD.md: what worked / what failed / what to change.
These lessons are injected into the system prompt for future tasks.
"""
from __future__ import annotations

from datetime import date

from .. import paths
from .client import LLMClient, LLMError
from .loop import AgentResult


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
    try:
        p = paths.LESSONS_DIR / f"{date.today().isoformat()}.md"
        stamp = time_stamp()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(f"\n## {stamp}\n{lesson}\n")
    except Exception:
        pass
    return lesson


def time_stamp() -> str:
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S")
