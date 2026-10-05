"""spawn_task — delegate a bounded sub-task to a fresh sub-agent (context isolation)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class T:
    name: str
    description: str
    parameters: dict
    handler: object


def spawn_tool_fn():
    def h_spawn(ctx, description: str, max_iters: int = 15):
        from ..agent import spawn
        return spawn.spawn(ctx, description, max_iters=max(3, min(int(max_iters or 15), 15)))

    return [
        T("spawn_task",
          "Delegate a self-contained sub-task to a fresh sub-agent (isolated context, same tools, max 15 iters). "
          "Use for: parallelizable research, big file summarization, anything that would bloat your context. "
          "The description MUST be fully self-contained (the sub-agent sees nothing else). Args: description, max_iters (default 15).",
          {"type": "object", "properties": {
              "description": {"type": "string"}, "max_iters": {"type": "integer"}},
           "required": ["description"]}, h_spawn),
    ]
