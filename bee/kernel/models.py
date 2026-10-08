"""Kernel data model (Phase 2) — the typed objects the agent runtime is built from.

The kernel OWNS these objects and their state. The LLM proposes (intent,
plan, action); the kernel decides (permission, execution, success,
persistence). See docs/JARVIS_ARCHITECTURE.md §Agent Kernel.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class TaskState(str, Enum):
    CREATED = "CREATED"
    UNDERSTANDING = "UNDERSTANDING"
    PLANNING = "PLANNING"
    WAITING_FOR_PERMISSION = "WAITING_FOR_PERMISSION"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    RETRYING = "RETRYING"


TERMINAL_STATES = {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}


class FailureKind(str, Enum):
    TRANSIENT = "transient"            # timeout, connection blip — retryable
    PROVIDER = "provider"              # LLM provider error (quota/auth/server)
    TOOL = "tool"                      # tool executed but failed
    INVALID_INPUT = "invalid_input"    # bad args / unknown tool — not retryable as-is
    PERMISSION = "permission"          # denied by guard/approver
    VERIFICATION = "verification"      # ran, but the intended effect did not happen
    UNRECOVERABLE = "unrecoverable"


class AgentEventKind(str, Enum):
    USER_MESSAGE = "user_message"
    TASK_CREATED = "task_created"
    PLAN_CREATED = "plan_created"
    PERMISSION_REQUESTED = "permission_requested"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_COMPLETED = "verification_completed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"
    MEMORY_WRITTEN = "memory_written"


@dataclass
class AgentEvent:
    """One typed event. The kernel emits these; an EventBus fans them out to
    UI adapters (REPL prints, web SSE, later realtime voice / automation)."""
    kind: AgentEventKind
    ts: str = field(default_factory=_ts)
    session_id: str = ""
    task_id: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"kind": self.kind.value, "ts": self.ts, "session_id": self.session_id,
                "task_id": self.task_id, **self.data}


@dataclass
class Action:
    """One executable step in a plan. `tool` is a registered ToolBus name;
    None means 'let the agent loop decide (LLM tool-calling)'."""
    id: str = field(default_factory=lambda: new_id("act"))
    description: str = ""
    tool: str | None = None
    args: dict | None = None
    risk: str = "low"          # low | medium | high | critical (risk-layer output)
    capability: str = ""       # required capability (CAP_EXEC, CAP_NETWORK, ...)
    permission: str = "not_required"   # not_required | pending | granted | denied


@dataclass
class Plan:
    """Kernel-owned execution plan (Phase 8: typed + validated BEFORE ToolBus).

    kind: the deterministic intent class (informational / single_action /
          multi_step / requires_approval / impossible / ambiguous).
    replans: how many times the kernel re-planned after a failed attempt
          (Plan -> Action -> Observation -> Replan lifecycle).
    """
    id: str = field(default_factory=lambda: new_id("plan"))
    goal: str = ""
    steps: list[Action] = field(default_factory=list)
    rationale: str = ""
    kind: str = "single_action"
    replans: int = 0

    def to_dict(self) -> dict:
        return {"id": self.id, "goal": self.goal, "rationale": self.rationale,
                "kind": self.kind, "replans": self.replans,
                "steps": [{"id": s.id, "description": s.description, "tool": s.tool,
                           "risk": s.risk, "capability": s.capability} for s in self.steps]}


@dataclass
class Observation:
    """What the kernel SAW happen for one tool call (never the model's claim)."""
    tool: str
    args: dict = field(default_factory=dict)
    result_text: str = ""
    ok: bool = False
    seconds: float = 0.0
    effect: str = "not_checked"   # pass | fail | unverified (verify_effect output)
    blocked: bool = False


@dataclass
class VerificationResult:
    verdict: str = "not_run"      # pass | fail | unverified | not_run
    checks: list[dict] = field(default_factory=list)   # {check, ok, detail}
    detail: str = ""

    def to_dict(self) -> dict:
        return {"verdict": self.verdict, "checks": self.checks, "detail": self.detail}


@dataclass
class PermissionDecision:
    tool: str
    action: str = "allow"         # allow | ask | deny (guard's verdict)
    granted: bool = True          # final outcome after approver consultation
    reason: str = ""
    risk_level: str = "low"       # from bee.security.risk (NONE..CRITICAL)
    capabilities: tuple = ()

    def to_dict(self) -> dict:
        return {"tool": self.tool, "action": self.action, "granted": self.granted,
                "reason": self.reason, "risk_level": self.risk_level,
                "capabilities": list(self.capabilities)}


@dataclass
class ExecutionReceipt:
    """Append-only proof row for one meaningful action. Secrets are redacted
    before persistence (ReceiptLog does this)."""
    task_id: str
    session_id: str
    tool: str
    action: str = "execute"
    arguments: dict = field(default_factory=dict)
    risk_level: str = "low"
    permission: str = "not_required"
    result: str = ""
    verification: str = "not_run"
    duration: float = 0.0
    error: str = ""
    retry_count: int = 0
    timestamp: str = field(default_factory=_ts)

    def to_dict(self) -> dict:
        return {"task_id": self.task_id, "session_id": self.session_id,
                "timestamp": self.timestamp, "tool": self.tool, "action": self.action,
                "arguments": self.arguments, "risk_level": self.risk_level,
                "permission": self.permission, "result": self.result,
                "verification": self.verification, "duration": self.duration,
                "error": self.error, "retry_count": self.retry_count}


@dataclass
class Task:
    id: str = field(default_factory=lambda: new_id("task"))
    session_id: str = ""
    text: str = ""
    state: TaskState = TaskState.CREATED
    plan: Plan | None = None
    observations: list[Observation] = field(default_factory=list)
    receipts: list[ExecutionReceipt] = field(default_factory=list)
    verification: VerificationResult = field(default_factory=VerificationResult)
    error: str = ""
    failure_kind: str = ""
    retry_count: int = 0
    model: str = ""
    output: str = ""
    created: str = field(default_factory=_ts)
    updated: str = field(default_factory=_ts)

    def touch(self):
        self.updated = _ts()

    def to_dict(self) -> dict:
        return {"id": self.id, "session_id": self.session_id, "text": self.text[:400],
                "state": self.state.value, "error": self.error[:300],
                "failure_kind": self.failure_kind, "retry_count": self.retry_count,
                "model": self.model, "output": self.output[:1000],
                "created": self.created, "updated": self.updated,
                "verification": self.verification.to_dict() if self.verification else {},
                "plan": self.plan.to_dict() if self.plan else None,
                "observations": [{"tool": o.tool, "ok": o.ok, "effect": o.effect,
                                  "seconds": o.seconds, "blocked": o.blocked}
                                 for o in self.observations]}


@dataclass
class TaskResult:
    """What kernel.run() returns. Mirrors AgentResult attributes (model, ok,
    output, error, verify, iterations, tool_calls, escalated, route_source) so
    existing UI code (REPL / web / reflection) keeps working unchanged."""
    task: Task
    agent_result: object = None
    verification: VerificationResult = field(default_factory=VerificationResult)
    cancelled: bool = False
    retried: bool = False

    def __getattr__(self, item):  # delegate to the inner AgentResult
        ar = object.__getattribute__(self, "agent_result")
        if ar is not None and hasattr(ar, item):
            return getattr(ar, item)
        raise AttributeError(item)
