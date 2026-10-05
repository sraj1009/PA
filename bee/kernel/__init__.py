"""BEE Agent Kernel (Phase 2) — one coherent agent runtime.

Objects: AgentSession, Task, TaskState, Plan, Action, Observation,
VerificationResult, PermissionDecision, ExecutionReceipt, AgentEvent.

The kernel owns state, permission, verification, receipts, cancellation,
retry and persistence. The LLM proposes (intent / plan / action) and is
executed through the EXISTING run_agent loop + LLMClient — no duplicated
LLM logic.
"""
from .models import (Action, AgentEvent, AgentEventKind, ExecutionReceipt, Observation,
                     Plan, Task, TaskResult, TaskState, VerificationResult, FailureKind,
                     PermissionDecision, new_id)
from .state import TRANSITIONS, can_transition, transition, InvalidTransitionError
from .events import EventBus
from .session import AgentSession
from .tools_bus import ToolBus, ToolDef, UnknownToolError, MalformedArgsError
from .receipts import ReceiptLog
from .retry import RetryPolicy
from .permission import decide as permission_decide
from .verification import check_effect, verify_task, task_effect_probe
from .memory_if import (EpisodicMemory, MemoryStack, ProceduralMemory, SemanticMemory,
                        TemporalMemory, WorkingMemory)
from .kernel import AgentKernel

__all__ = [
    "AgentKernel", "AgentSession", "AgentEvent", "AgentEventKind", "Action",
    "ExecutionReceipt", "Observation", "Plan", "Task", "TaskResult", "TaskState",
    "VerificationResult", "FailureKind", "PermissionDecision", "new_id",
    "TRANSITIONS", "can_transition", "transition", "InvalidTransitionError",
    "EventBus", "ToolBus", "ToolDef", "UnknownToolError", "MalformedArgsError",
    "ReceiptLog", "RetryPolicy", "permission_decide",
    "check_effect", "verify_task", "task_effect_probe", "MemoryStack",
    "WorkingMemory", "EpisodicMemory", "SemanticMemory", "ProceduralMemory",
    "TemporalMemory",
]
