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
