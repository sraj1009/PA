"""Sub-agents: spawn_task runs a bounded fresh loop with the same tools."""
from __future__ import annotations

from .loop import run_agent

MAX_SUB_ITERS = 15


def spawn(ctx, description: str, max_iters: int = MAX_SUB_ITERS) -> str:
    """Run a focused sub-task in a fresh context; returns its final answer.

    Acceptance audit P0-1: the sub-context MUST inherit the authorization
    and control wiring from its parent — capability gate, task id (so
    sub-agent grants stay task-scoped), cancel event (so cancelling the
    parent task also stops its sub-agents), and the guard mode. Before this
    fix a sub-agent ran gate-less: the LLM could route any tool work
    through spawn_task to bypass capability authorization."""
    if not description or not str(description).strip():
        return "error: spawn_task needs a non-empty 'description'"
    sub_ctx = ctx.__class__(cfg=ctx.cfg, workspace=ctx.workspace, name=ctx.name,
                            client=ctx.client, model_note=ctx.model_note)
    sub_ctx.capability_gate = getattr(ctx, "capability_gate", None)
    sub_ctx.current_task_id = getattr(ctx, "current_task_id", "") or ""
    sub_ctx.cancel_event = getattr(ctx, "cancel_event", None)
    sub_ctx.guard_mode = getattr(ctx, "guard_mode", "cli")
    sub_ctx.guard_on = getattr(ctx, "guard_on", True)
    r = run_agent(sub_ctx, str(description).strip(), max_iters=max_iters, sub=True)
    head = f"[{'OK' if r.ok else 'FAIL'}] model={r.model} iters={r.iterations} tools={r.tool_calls}"
    if r.error:
        return f"{head}\nerror: {r.error}"
    return f"{head}\n{r.output}"
