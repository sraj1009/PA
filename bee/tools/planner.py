"""planner — lightweight LLM step planner (uses local model, no tools)."""
from __future__ import annotations

from .base import T

def planner_tools():
    def h_plan(ctx, task: str, constraints: str = ""):
        from ..agent.client import LLMClient, LLMError
        client = ctx.client or LLMClient(ctx.cfg)
        # A45b: the prompt asked for steps that "mention the tool(s) to use" but
        # never told the model which tools exist. It answered with invented names —
        # `LoadCSVFileUsingLoaderTool(...)`, `CleanDataUsingCleanerTool(...)` — a
        # plan the agent cannot execute and that names no library, so relaying it
        # could not satisfy "plan … use the planner tool" either. Give it the real
        # registry and the skill index; a plan must be expressible in tools BEE has.
        try:
            bus = getattr(getattr(ctx, "kernel", None), "bus", None)
            if bus is not None:
                tool_names = bus.names()
            else:
                from ..tools import tools_by_name
                tool_names = sorted(tools_by_name())
        except Exception:
            tool_names = []
        try:
            from ..agent.context import skills_index
            skills = skills_index(ctx.cfg, force=getattr(ctx, "force_skills", None))
        except Exception:
            skills = ""
        prompt = (
            "You are a planner. Break the task into concrete, ordered, executable steps. "
            "Each step: 1 short line (verb first), naming at most ONE tool from the "
            "AVAILABLE list below — never invent a tool name, and never list a tool "
            "this task does not actually need. For a step that reads, cleans or "
            "aggregates data, use code_run and name the Python library it will import "
            "(pandas or polars). Max 12 steps, and every step must be specific to "
            "this task. No preamble, no summaries — just the numbered list.\n\n"
            f"Available tools: {', '.join(tool_names) or '(none)'}\n"
            f"Skills (procedures already learned; prefer the module names shown):\n"
            f"{skills[:1200] or '(none)'}\n\n"
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
