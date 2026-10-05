"""planner — lightweight LLM step planner (uses local model, no tools)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class T:
    name: str
    description: str
    parameters: dict
    handler: object


def planner_tools():
    def h_plan(ctx, task: str, constraints: str = ""):
        from ..agent.client import LLMClient, LLMError
        client = ctx.client or LLMClient(ctx.cfg)
        prompt = (
            "You are a planner. Break the task into concrete, ordered, executable steps. "
            "Each step: 1 short line (verb first), mention the tool(s) to use. Max 12 steps. "
            "No preamble, no summaries — just the numbered list.\n\n"
            f"Task: {task[:800]}\n"
            f"Constraints: {constraints or 'none'}"
        )
        try:
            out = client.chat("local", [{"role": "user", "content": prompt}])
            return {"task": task[:300], "plan": (out.get("content") or "").strip()[:2500]}
        except LLMError as e:
            return {"error": f"planner model unavailable: {e}",
                    "fallback": "1) explore with file_list/memory_search 2) act with the right tool 3) verify 4) reflect"}

    return [
        T("planner", "Generate a step-by-step execution plan for a task (local model, fast). "
                     "Call this BEFORE complex multi-step work. Args: task, constraints (optional).",
          {"type": "object", "properties": {"task": {"type": "string"}, "constraints": {"type": "string"}},
           "required": ["task"]}, h_plan),
    ]
