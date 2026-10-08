"""Typed planner (Program Phase 8, 2026-10-08).

Division of labor, exactly as the kernel contract requires:
  * the LLM proposes intent/plans INSIDE the executing step;
  * the KERNEL owns task state and VALIDATES every plan BEFORE any ToolBus
    execution — an unvalidated plan never reaches a tool.

This module is DETERMINISTIC (no LLM call): it classifies the user's
request into plan kinds and validates kernel-built plans against the
ToolBus. The classification is conservative on purpose — when in doubt it
chooses the kind that costs LESS to get wrong (single_action), and the
capability gate remains the final authority on every tool call.

Kinds
-----
  informational      "explain X", "what is Y" — answer, no actions
  single_action      one tool call or one direct answer
  multi_step         several actions; kernel re-observes between steps
  requires_approval  contains a high-risk action (delete/send/pay/...)
  impossible         no actionable content (empty, or explicitly infeasible)
  ambiguous          dangling references with no context to resolve against

Validation (validate_plan) rejects, before ToolBus:
  * plans whose steps name tools the ToolBus does not register
  * plans with malformed risk levels
  * multi_step plans with a single executable step (under-declared)
  * requires_approval plans with no risk-bearing step (under-declared)
"""
from __future__ import annotations

import re

from .models import Action, Plan

# --------------------------------------------------------------- kind names
INFORMATIONAL = "informational"
SINGLE_ACTION = "single_action"
MULTI_STEP = "multi_step"
REQUIRES_APPROVAL = "requires_approval"
IMPOSSIBLE = "impossible"
AMBIGUOUS = "ambiguous"

KINDS = (INFORMATIONAL, SINGLE_ACTION, MULTI_STEP, REQUIRES_APPROVAL,
         IMPOSSIBLE, AMBIGUOUS)

_VALID_RISKS = {"low", "medium", "high", "critical"}

# high-risk verbs -> REQUIRES_APPROVAL (deterministic; the capability gate
# still enforces per-tool authorization at execution time)
_RISKY = re.compile(
    r"\b(delete|remove|rm|drop|purge|wipe|erase|format|uninstall|reinstall|"
    r"send|publish|post|email|e-mail|transfer|pay|purchase|buy|order|charge|"
    r"disable|enable|restart|shutdown|reboot|install|upgrade|downgrade|"
    r"overwrite|truncate|kill|terminate|archive|unarchive|deploy|push)\b",
    re.I)

# questions without imperative content -> INFORMATIONAL
_QUESTION = re.compile(
    r"^\s*(what|why|who|whom|whose|when|where|which|how|explain|describe|"
    r"summarize|list|tell\s+me|is\s|are\s|was\s|were\s|do\s|does\s|did\s|"
    r"can\s+you\s+explain|would\s|should\s)\b", re.I)

# dangling references ("do it", "that one", "again", "the same")
_DANGLING = re.compile(
    r"^\s*(do\s+it|just\s+do\s+it|do\s+that|that\s+one|again|same|likewise|"
    r"repeat|one\s+more|next)\s*[.!?]*$", re.I)

# several action verbs, or explicit step markers -> MULTI_STEP
_STEP_MARKERS = re.compile(
    r"\b(and\s+then|then\b|after\s+that|followed\s+by|next,|step\s+\d|"
    r"first\s+.*\bthen\b|1\s*[.)]\s.*2\s*[.)]\s.*3\s*[.)])\b", re.I | re.S)
_ACTION_VERBS = re.compile(
    r"\b(open|close|create|make|write|read|search|find|run|execute|launch|"
    r"start|stop|check|verify|inspect|analyze|analyze|install|configure|"
    r"schedule|remind|book|set|get|fetch|download|upload|move|copy|edit|"
    r"rename|merge|split|send|email|publish|test|deploy|build|train)\b", re.I)

# explicitly infeasible asks (deterministic, small on purpose)
_IMPOSSIBLE = re.compile(
    r"^\s*(i\s+)?(can'?t|cannot|can\s+never)\b.*\b(task|do|that)\b", re.I)


def classify_intent(text: str, session=None) -> tuple[str, str]:
    """(kind, reason) — deterministic. `session` is only used to detect
    dangling references WITH an active task (those are fine — they're
    follow-ups, handled before the planner runs)."""
    t = (text or "").strip()
    if not t:
        return IMPOSSIBLE, "no actionable content"
    if _IMPOSSIBLE.match(t):
        return IMPOSSIBLE, "explicitly infeasible request"
    has_active = bool(session and (getattr(session, "active_task_id", None)
                                   or getattr(session, "active_task_text", "")))
    if _DANGLING.match(t) and not has_active:
        return AMBIGUOUS, "dangling reference with no active task to resolve"
    # informational: a question with no risky verb and no step structure
    if _QUESTION.match(t) and not _RISKY.search(t) and not _STEP_MARKERS.search(t):
        return INFORMATIONAL, "informational question"
    if _RISKY.search(t):
        return REQUIRES_APPROVAL, "high-risk action verb present"
    if _STEP_MARKERS.search(t):
        return MULTI_STEP, "explicit step structure"
    verbs = _ACTION_VERBS.findall(t.lower())
    # count DISTINCT action verbs — one repeated verb is still one action
    if len(set(verbs)) >= 3:
        return MULTI_STEP, f"multiple distinct actions: {', '.join(sorted(set(verbs)))[:80]}"
    if len(t) > 320 and len(set(verbs)) >= 2:
        return MULTI_STEP, "long multi-action request"
    return SINGLE_ACTION, "single action or direct answer"


def build_plan(kind: str, text: str, session=None) -> Plan:
    """Kernel-built plan for one execution attempt. The kernel (not the LLM)
    constructs this; validation happens in validate_plan() BEFORE execution.
    For multi_step/requires_approval kinds the plan declares the shape so the
    verifier and the UI can reason about it."""
    if kind == MULTI_STEP:
        exec_step = Action(description="multi-step: kernel re-observes between steps",
                           tool=None, risk="medium")
    elif kind == REQUIRES_APPROVAL:
        exec_step = Action(description="requires_approval: capability gate will authorize",
                           tool=None, risk="high")
    else:
        exec_step = Action(description="execute via agent loop (LLM proposes tool actions)",
                           tool=None, risk="low")
    verify_step = Action(description="verify intended effect (deterministic postconditions)",
                         tool=None, risk="low")
    return Plan(goal=(text or "")[:500], steps=[exec_step, verify_step],
                rationale=f"{kind}: {text[:120] if kind == AMBIGUOUS else ''}".strip(": ") or kind,
                kind=kind)


def validate_plan(plan, bus) -> tuple[bool, list[str]]:
    """Plan validation BEFORE ToolBus execution (Phase 8 requirement).

    `bus` may be None (no ToolBus context) — in that case only structural
    rules are checked. Tool-name checks use the bus's registry so a plan can
    never reference a tool that does not exist.
    Returns (ok, errors) — the kernel refuses to execute when not ok.
    """
    errors: list[str] = []
    if plan is None:
        return False, ["plan is None — nothing to execute"]
    if not (plan.goal or "").strip():
        errors.append("plan.goal is empty")
    if plan.kind not in KINDS:
        errors.append(f"unknown plan.kind: {plan.kind!r}")
    steps = plan.steps or []
    if plan.kind in (IMPOSSIBLE, AMBIGUOUS):
        # these kinds must never carry executable steps — the kernel answers
        # (or asks for clarification) without touching the ToolBus
        if any(getattr(s, "tool", None) for s in steps):
            errors.append(f"{plan.kind} plan must not carry executable steps")
        return len(errors) == 0, errors
    if not steps:
        errors.append("plan has no steps")
    registered = None
    if bus is not None:
        try:
            registered = set(bus.names())
        except Exception:
            registered = None
    for i, s in enumerate(steps):
        risk = getattr(s, "risk", "low") or "low"
        if risk not in _VALID_RISKS:
            errors.append(f"step {i}: invalid risk {risk!r} "
                          f"(one of {sorted(_VALID_RISKS)})")
        tool = getattr(s, "tool", None)
        if tool and registered is not None and tool not in registered:
            errors.append(f"step {i}: tool {tool!r} not registered on ToolBus")
    if plan.kind == MULTI_STEP and len(steps) < 2:
        errors.append("multi_step plan declares only one step")
    if plan.kind == REQUIRES_APPROVAL and not any(
            getattr(s, "risk", "low") in ("high", "critical") for s in steps):
        errors.append("requires_approval plan has no high/critical-risk step")
    return len(errors) == 0, errors
