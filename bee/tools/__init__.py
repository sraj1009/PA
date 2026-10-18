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


# P0-1 (2026-10-17): context floor for the local route. num_ctx is 8192 and the
# compaction budget 7168 est tokens; all 30 schemas are ~16.0k chars ≈ 5.2k of
# that — a live web_search_tool turn measured 8434 est tokens with NOTHING left
# to compact, i.e. the schema list alone starved the history before any tool
# result arrived. The local route now gets this fitted subset (≈7.2k chars ≈
# 2.4k est) that keeps everything an offline session needs day to day. The
# heavy capability tools it drops (automate 2.2k, automation_job 1.3k,
# systemctl 842, computer_input/window/clipboard/observe/stop ≈3.0k combined,
# sandbox_run 579, spawn_task 511 chars) stay fully callable — cloud keeps the
# complete set, the executor registry is unchanged, and a local task that needs
# one fails over through the hybrid/kernel retry instead of every local call
# paying the schema cost.
LOCAL_TOOL_NAMES = frozenset({
    # exec / files / math — the everyday core
    "file_read", "file_write", "file_edit", "file_list",
    "shell", "code_run", "calculator",
    # memory
    "memory_search", "profile_add", "diary_add", "memory_longterm",
    # skills — the system prompt tells the model to load and distill them
    "skill_search", "skill_list", "skill_get", "skill_create",
    # planning / web / health / reminders
    "planner", "web_search", "web_fetch", "system_health", "scheduler",
})


def tools_litellm(local: bool = False) -> list[dict]:
    """Model-loop schemas. `local=True` = the P0-1 fitted subset above; the
    default full set is what cloud calls and the API surfaces get."""
    tools = build_default_tools()
    if local:
        tools = [t for t in tools if t.name in LOCAL_TOOL_NAMES]
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


def tools_openai() -> list[dict]:
    return tools_litellm()
