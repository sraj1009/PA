"""Sub-agents: spawn_task runs a bounded fresh loop with the same tools."""
from __future__ import annotations

from .loop import run_agent

MAX_SUB_ITERS = 15


def spawn(ctx, description: str, max_iters: int = MAX_SUB_ITERS) -> str:
    """Run a focused sub-task in a fresh context; returns its final answer."""
    if not description or not str(description).strip():
        return "error: spawn_task needs a non-empty 'description'"
    sub_ctx = ctx.__class__(cfg=ctx.cfg, workspace=ctx.workspace, name=ctx.name,
                            client=ctx.client, model_note=ctx.model_note)
    r = run_agent(sub_ctx, str(description).strip(), max_iters=max_iters, sub=True)
    head = f"[{'OK' if r.ok else 'FAIL'}] model={r.model} iters={r.iterations} tools={r.tool_calls}"
    if r.error:
        return f"{head}\nerror: {r.error}"
    return f"{head}\n{r.output}"
