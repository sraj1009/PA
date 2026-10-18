"""AgentResult — the loop's task result record (moved out of loop.py).

Kept importable from `bee.agent.loop` (public entry point), so existing
callers do not change: kernel.py, evals/runner.py, commands, tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentResult:
    output: str
    model: str = ""
    iterations: int = 0
    escalated: bool = False
    tool_calls: int = 0
    ok: bool = True
    error: str = ""
    est_tokens: int = 0
    sub_results: list = field(default_factory=list)
    verify: str = ""
    route_source: str = ""
