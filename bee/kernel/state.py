"""Task state machine (Phase 2) — the kernel enforces legal transitions.

The LLM can never set a task's state directly; only Task.transition(),
called by kernel code, moves it. Illegal transitions raise
InvalidTransitionError (fail closed: a confused kernel must not pretend a
task completed).
"""
from __future__ import annotations

from .models import TERMINAL_STATES, Task, TaskState

# allowed: current -> {next, ...}
TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.CREATED: {TaskState.UNDERSTANDING, TaskState.CANCELLED},
    TaskState.UNDERSTANDING: {TaskState.PLANNING, TaskState.WAITING_FOR_USER,
                              TaskState.FAILED, TaskState.CANCELLED},
    TaskState.PLANNING: {TaskState.WAITING_FOR_PERMISSION, TaskState.EXECUTING,
                         TaskState.WAITING_FOR_USER, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.WAITING_FOR_PERMISSION: {TaskState.EXECUTING, TaskState.PLANNING,
                                       TaskState.FAILED, TaskState.CANCELLED},
    TaskState.EXECUTING: {TaskState.VERIFYING, TaskState.RETRYING,
                          TaskState.WAITING_FOR_PERMISSION,  # a mid-run 'ask'
                          TaskState.WAITING_FOR_USER, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.VERIFYING: {TaskState.COMPLETED, TaskState.RETRYING,
                          TaskState.FAILED, TaskState.CANCELLED},
    TaskState.RETRYING: {TaskState.EXECUTING, TaskState.PLANNING,
                         TaskState.FAILED, TaskState.CANCELLED},
    TaskState.WAITING_FOR_USER: {TaskState.UNDERSTANDING, TaskState.PLANNING,
                                 TaskState.EXECUTING, TaskState.CANCELLED},
    # terminals: nothing leaves a finished task
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}


class InvalidTransitionError(Exception):
    def __init__(self, task: Task, target: TaskState):
        self.task = task
        self.target = target
        super().__init__(f"illegal task transition {task.state.value} -> {target.value} (task {task.id})")


def can_transition(current: TaskState, target: TaskState) -> bool:
    return target in TRANSITIONS.get(current, set())


def transition(task: Task, target: TaskState) -> None:
    """Validate + apply a state change on a Task (in place)."""
    if target == task.state:
        task.touch()
        return
    if not can_transition(task.state, target):
        raise InvalidTransitionError(task, target)
    if task.state in TERMINAL_STATES:
        raise InvalidTransitionError(task, target)  # defensive double-check
    task.state = target
    task.touch()
