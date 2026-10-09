"""Tool registry: default toolset + litellm/openai schema export."""
from __future__ import annotations

from . import (automate, calculator, code, files, health_tool, memory, planner, sandbox,
                scheduler_tool, shell, skills, spawn_tool, systemctl, web)

_BUILDERS = [
    files.file_tools,
    automate.automate_tools,
    shell.shell_tools,
    web.web_tools,
    code.code_tools,
    calculator.calc_tools,
    sandbox.sandbox_tools,
    memory.memory_tools,
    skills.skill_tools,
    planner.planner_tools,
    spawn_tool.spawn_tool_fn,
    scheduler_tool.scheduler_tools,
    health_tool.health_tools,
    systemctl.systemctl_tools,
]


def _computeruse_builder():
    # Phase 5: registered from bee.computeruse (kept out of the static list
    # so a missing optional desktop dependency never breaks tool import)
    try:
        from ..config import load_config
        if not load_config().computeruse.enabled:
            return []          # operator kill-switch — see computeruse.enabled
        from ..computeruse import computeruse_tools
        return computeruse_tools()
    except Exception:
        return []


def _automation_builder():
    # Phase 6: durable automation (user-authorized, capability-gated)
    try:
        from ..automation import automation_tools
        return automation_tools()
    except Exception:
        return []


_BUILDERS.append(_computeruse_builder)
_BUILDERS.append(_automation_builder)

_CACHE = None


def build_default_tools():
    global _CACHE
    if _CACHE is None:
        tools = []
        for b in _BUILDERS:
            tools.extend(b())
        _CACHE = tools
    return _CACHE


def tools_by_name() -> dict:
    return {t.name: t.handler for t in build_default_tools()}


def tools_meta() -> dict:
    """name -> full T (for static risk metadata, untrusted_output flags, ...)."""
    return {t.name: t for t in build_default_tools()}


def tools_litellm() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in build_default_tools()
    ]


def tools_openai() -> list[dict]:
    return tools_litellm()
