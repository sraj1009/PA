"""AgentKernel (Phase 2) — the single agent runtime.

Flow (kernel-owned; the LLM only proposes inside the EXECUTING step):

  user request
    → session context (persistent AgentSession)
    → understand intent (follow-up resolution: cancel / continue / new)
    → retrieve relevant memory (session context block + RAG inside the loop)
    → create plan (Plan/Action objects; kernel decides, not the model)
    → request permission when required (guard + approver; WAITING_FOR_PERMISSION)
    → execute action (run_agent — the existing LLM tool-call loop, UNCHANGED)
    → observe result (Observations from real tool events, not model claims)
    → verify result (deterministic effect checks + task-level target probe)
    → record receipt (redacted JSONL, one row per meaningful action)
    → update memory (session state + episodes/diary via the loop)
    → respond to user (TaskResult)

Cancellation is first-class: kernel.cancel() sets the context's cancel
event, which run_agent honors between iterations and before each tool call.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path

from .. import guard, paths
from ..agent.loop import run_agent
from .events import EventBus
from .memory_if import MemoryStack
from .models import (AgentEvent, AgentEventKind, ExecutionReceipt, Observation,
                     Plan, Action, Task, TaskResult, TaskState, VerificationResult,
                     new_id)
from .receipts import ReceiptLog
from .retry import FailureKind, RetryPolicy
from .session import AgentSession
from .state import InvalidTransitionError, transition
from .tools_bus import ToolBus
from .verification import check_effect, verify_task

log = logging.getLogger("bee.kernel")

_STEP_SPLIT = None  # kept simple: the agent loop is already multi-step internally


def _emit(bus: EventBus, kind: AgentEventKind, session_id: str, task_id: str, **data):
    bus.emit(AgentEvent(kind=kind, session_id=session_id, task_id=task_id, data=data))


def _src_label(src) -> str:
    """Friendly name for where a memory hit came from.

    The hybrid index stores absolute paths, so the raw label was
    `[from C:\\Users\\…\\memory\\profile.md]` — the user's folder layout read back
    to them (and during evals, a temp directory path)."""
    s = str(src or "").lower().replace("\\", "/")
    for key, label in (("profile", "profile memory"), ("longterm", "long-term memory"),
                       ("system.md", "system memory"), ("diary", "my diary"),
                       ("lessons", "lessons learned"), ("store.json", "structured memory")):
        if key in s:
            return label
    return (s.rsplit("/", 1)[-1] or "memory")


_QUERY_STOP = {
    "the", "and", "for", "with", "that", "this", "these", "those", "then", "than",
    "you", "your", "yours", "are", "was", "were", "have", "has", "had", "not", "but",
    "about", "what", "when", "where", "which", "who", "whom", "from", "into", "onto",
    "tell", "know", "remember", "recall", "show", "give", "please", "me", "my", "mine",
    "our", "us", "him", "her", "his", "them", "they", "their", "any", "some", "more",
    "most", "much", "many", "did", "does", "doing", "can", "could", "should", "would",
    "will", "all", "everything", "anything", "something", "nothing", "each", "other",
}


def _qwords(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", (text or "").lower())
            if w not in _QUERY_STOP}


def _best_lines(text: str, query: str, limit: int = 2, fallback: bool = True) -> list[str]:
    """The bullets inside a memory chunk that actually answer this query.

    A chunk is ~400 chars of merged bullets; quoting the whole block meant the
    user got unrelated bullets alongside the one they asked for, and the line
    that mattered was cut off mid-word by the character cap. With fallback off a
    hit that matches nothing contributes nothing, so a near-duplicate chunk
    cannot refill the answer with noise. Stopwords are dropped because 'and'
    scored the diary noise higher than the spec line the user asked about."""
    words = _qwords(query)
    cand = [ln.strip().strip("-*•\t ").strip() for ln in (text or "").splitlines()]
    cand = [ln for ln in cand if ln and not ln.startswith("#")]
    if not words or not cand:
        return cand[:limit]

    def _score(ln):
        # Compact compare, not token set: the memory says 'Time zone' and the
        # user asks about 'timezone'; it says 'GPU' and they ask about 'gpu'.
        return sum(1 for w in words if w in re.sub(r"[^a-z0-9]+", "", ln.lower()))

    ranked = [ln for _, ln in sorted(enumerate(cand), key=lambda p: (-_score(p[1]), p[0]))
              if _score(ln) > 0]
    return (ranked or cand)[:limit] if fallback else ranked[:limit]


def _hw_conflict(stored: list[str], hw: dict) -> str:
    """Warn when a stored spec contradicts the machine standing in front of us.

    profile.md says 'NVIDIA RTX 3050 8 GB'; the CIM query reports 4 GB. Quoting
    the note as fact while the hardware disagrees is the same class of defect the
    verifier chases for action claims — a confident answer nothing backs up."""
    if not hw:
        return ""
    vrams = {int(g.get("vram_gb") or 0) for g in hw.get("gpus") or [] if g.get("vram_gb")}
    if not vrams:
        return ""
    families = {m for name in (g.get("name", "") for g in hw.get("gpus") or [])
                for m in re.findall(r"\d{3,}", name)}
    for ln in stored:
        nums = [int(n) for n in re.findall(r"(\d+)\s*GB", ln, re.I)]
        if not nums or not any(f and f in ln for f in families):
            continue
        if not set(nums) & vrams:
            return (f"Heads up: what I have stored says {nums[0]} GB, but this machine "
                    f"currently reports {max(vrams)} GB — the note may be out of date.")
    return ""


def _hardware_note(req) -> tuple[str, dict]:
    """Live inventory for a recall about the box itself ('' / {} if not one)."""
    from .memory_commands import is_hardware_query
    if not is_hardware_query(f"{req.query} {req.text}"):
        return "", {}
    try:
        from ..tools.systemctl import format_hardware, get_hardware
        h = get_hardware()
    except Exception:
        return "", {}
    return (format_hardware(h), h) if h else ("", {})


class AgentKernel:
    def __init__(self, ctx, approver=None, sessions_dir=None, receipts_path=None,
                 policy: RetryPolicy | None = None, bus: ToolBus | None = None,
                 events: EventBus | None = None, memory: MemoryStack | None = None,
                 max_attempts: int = 2, capabilities_path=None, memory_store_path=None):
        self.ctx = ctx
        self.approver = approver if approver is not None else guard.make_approver(ctx.guard_mode)
        self.sessions_dir = Path(sessions_dir) if sessions_dir else (paths.PROJECT_ROOT / "memory" / "sessions")
        self.receipts = ReceiptLog(receipts_path if receipts_path else
                                   paths.PROJECT_ROOT / "memory" / "receipts.jsonl")
        # `x or Default()` is the wrong idiom for injected collaborators: an
        # intentionally empty ToolBus/EventBus is falsy (__len__) and would be
        # silently replaced by the full default bus — i.e. a caller's lockdown
        # ignored. Injected objects are honored whenever they are not None.
        self.policy = policy if policy is not None else RetryPolicy(max_attempts=max_attempts)
        self.bus = bus if bus is not None else ToolBus().from_default()
        self.events = events if events is not None else EventBus()
        # Structured telemetry (audit 2026-10-06): agent_task terminal rows
        # (latency/retries/verification) + permission decisions, into the
        # metrics stream. Best-effort — a monitor failure never breaks the
        # kernel; tests can inject their own events bus / sink.
        try:
            from ..monitor.telemetry import KernelTelemetry
            KernelTelemetry().attach(self.events)
        except Exception:
            pass
        # temporal.schedule resolves the durable worker lazily (automation
        # starts after the kernel exists) — one scheduling architecture only
        self.memory = (memory if memory is not None else
                       MemoryStack(structured_path=memory_store_path,
                                   worker_ref=lambda: getattr(self.ctx, "automation_worker", None),
                                   ctx_ref=lambda: self.ctx))
        self._tasks: dict[str, Task] = {}
        self.last_task: Task | None = None
        self._active_task: Task | None = None
        # Phase 6: serializes kernel EXECUTIONS. Interactive (REPL/web/voice)
        # and scheduled jobs share ONE kernel; concurrent runs would race on
        # task-scoped capability grants (ctx.current_task_id) and last_task.
        # RLock: a run never invokes another run on the same thread.
        self._run_lock = threading.RLock()
        # Phase 3: capability gate — checked BEFORE every tool execution in
        # the loop (ctx.capability_gate). Unattended kernels (web) get the
        # auto-deny approver, so any 'ask' capability fails closed.
        from ..security.capabilities import CapabilityGate, CapabilityStore
        self.gate = CapabilityGate(CapabilityStore(capabilities_path),
                                   confirmer=self._gate_confirm)
        ctx.capability_gate = self.gate

    # ------------------------------------------------------------- sessions
    def get_session(self, session_id: str = "repl") -> AgentSession:
        s = AgentSession.load(self.sessions_dir, session_id)
        if s is None:
            s = AgentSession(id=session_id)
        return s

    # --------------------------------------------------------- cancellation
    def cancel(self) -> None:
        """First-class cancellation: stop the active task safely."""
        ev = self.ctx.cancel_event
        if not isinstance(ev, threading.Event):
            ev = threading.Event()
            self.ctx.cancel_event = ev
        ev.set()

    # ----------------------------------------------------------- main entry
    def run(self, text: str, session_id: str = "repl", on_event=None,
            model: str | None = None, on_token=None,
            max_iters: int | None = None) -> TaskResult:
        self._run_lock.acquire()
        try:
            return self._run_impl(text, session_id, on_event, model, on_token,
                                  max_iters=max_iters)
        finally:
            self._run_lock.release()

    def _run_impl(self, text: str, session_id: str = "repl", on_event=None,
                  model: str | None = None, on_token=None,
                  max_iters: int | None = None) -> TaskResult:
        session = self.get_session(session_id)
        start = time.time()
        session.add_turn("user", text)

        # 1 — UNDERSTANDING
        # Phase 3: explicit memory commands are parsed FIRST — they are
        # self-contained directives ('Forget that.' must never be merged into
        # a previous task as a follow-up).
        from .memory_commands import parse as parse_memory_request
        mem_req = parse_memory_request(text)

        decision, resolved = session.resolve_followup(text)
        if decision == "cancel":
            self.cancel()
            task = Task(session_id=session_id, text=text)
            transition(task, TaskState.CANCELLED)
            _emit(self.events, AgentEventKind.USER_MESSAGE, session_id, task.id, text=text[:200])
            _emit(self.events, AgentEventKind.TASK_CANCELLED, session_id, task.id)
            session.save(self.sessions_dir)
            return TaskResult(task=task, cancelled=True,
                              agent_result=_agent_stub("(stopped: cancelled by user)", ok=False))

        # N4 (debt): the KERNEL owns task-scoped cancellation. A cancel
        # requested for task N applies to task N only — every NEW task starts
        # with the cancel event cleared, so a cancelled/stopped task can never
        # poison the next one, regardless of which surface (REPL/web/voice/
        # job/proactive) invoked run(). Entry points that clear too (REPL,
        # voice engine) remain harmless redundancies.
        ev = self.ctx.cancel_event
        if isinstance(ev, threading.Event):
            ev.clear()

        task = Task(session_id=session_id, text=resolved[:2000])
        self._tasks[task.id] = task
        self.last_task = task
        self._active_task = task
        transition(task, TaskState.UNDERSTANDING)
        _emit(self.events, AgentEventKind.USER_MESSAGE, session_id, task.id, text=text[:200])
        _emit(self.events, AgentEventKind.TASK_CREATED, session_id, task.id, state=task.state.value)

        if mem_req is not None:
            return self._exec_memory_request(task, session, mem_req, on_event=on_event)

        # 2 — memory context (working memory + session state; RAG runs in-loop)
        ctx_block = session.context_block()
        exec_text = resolved
        if ctx_block and decision == "continue":
            exec_text = f"{ctx_block}\n\n{resolved}"

        # 3 — PLANNING (Phase 8): the kernel classifies intent, builds a typed
        # plan, and VALIDATES it against the ToolBus BEFORE any execution.
        # The LLM only proposes tool actions INSIDE the executing step.
        from . import planner
        kind, why = planner.classify_intent(resolved, session)
        transition(task, TaskState.PLANNING)
        if kind == planner.IMPOSSIBLE:
            # no actionable content — answer deterministically BEFORE any
            # plan/LLM/ToolBus touch (no LLM call, no execution)
            msg = ("I don't see an actionable request in that — could you "
                   "tell me what you'd like done?")
            task.plan = planner.build_plan(kind, resolved, session)
            task.output = msg
            # the kernel is asking the user to rephrase — semantically that
            # is WAITING_FOR_USER (the next turn starts a fresh Task)
            transition(task, TaskState.WAITING_FOR_USER)
            session.save(self.sessions_dir)
            _emit(self.events, AgentEventKind.PLAN_CREATED, session_id, task.id,
                  plan=task.plan.to_dict())
            return TaskResult(task=task, agent_result=_agent_stub(msg, ok=True))
        task.plan = planner.build_plan(kind, resolved, session)
        p_ok, p_errs = planner.validate_plan(task.plan, self.bus)
        if not p_ok:
            task.error = "plan rejected: " + "; ".join(p_errs)[:400]
            task.failure_kind = "validation"
            transition(task, TaskState.FAILED)
            session.save(self.sessions_dir)
            _emit(self.events, AgentEventKind.TASK_FAILED, session_id, task.id,
                  error=task.error[:200])
            return TaskResult(task=task, agent_result=_agent_stub(task.error, ok=False))
        task.plan.rationale = (f"{kind} ({why}) — single-executor plan: the "
                               "agent loop performs multi-step tool use internally")
        _emit(self.events, AgentEventKind.PLAN_CREATED, session_id, task.id,
              plan=task.plan.to_dict())

        # 4/5 — EXECUTING (permission waits are observed by the approver below)
        # observations accumulate on the TASK (persistent); verification uses
        # the slice produced by the CURRENT attempt.
        exec_started = time.time()

        def _approver(tool: str, args: dict, reason: str) -> bool:
            transition(task, TaskState.WAITING_FOR_PERMISSION)
            from .permission import risk_info
            lvl, caps = risk_info(tool, args)
            _emit(self.events, AgentEventKind.PERMISSION_REQUESTED, session_id, task.id,
                  tool=tool, reason=reason, risk_level=lvl, capabilities=list(caps))
            try:
                granted = bool(self.approver(tool, args, reason))
            except Exception:
                granted = False
            _emit(self.events, AgentEventKind.PERMISSION_GRANTED if granted
                  else AgentEventKind.PERMISSION_DENIED, session_id, task.id,
                  tool=tool, reason=reason)
            self.receipts.append(ExecutionReceipt(
                task_id=task.id, session_id=session_id, tool=tool, action="permission",
                arguments={}, risk_level=lvl,
                permission="granted" if granted else "denied",
                result=reason, verification="not_run", duration=0.0,
                retry_count=task.retry_count))
            # BOTH outcomes return the task to EXECUTING: on grant the action
            # runs; on deny the model explains the refusal to the user. Either
            # way the waiting phase is over and the task is mid-execution —
            # leaving it in WAITING_FOR_PERMISSION after a denial made the
            # later EXECUTING/VERIFYING move an illegal transition
            # (InvalidTransitionError — found by the guard_blocked eval).
            if task.state != TaskState.EXECUTING:
                transition(task, TaskState.EXECUTING)
            return granted

        def bridge(ev: dict):
            # legacy dict events keep flowing to the UI unchanged...
            if on_event:
                try:
                    on_event(ev)
                except Exception:
                    pass
            t = ev.get("type")
            if t == "tool_start":
                _emit(self.events, AgentEventKind.TOOL_STARTED, session_id, task.id,
                      tool=ev.get("tool"))
                task.observations.append(Observation(tool=str(ev.get("tool") or ""),
                                                     args=dict(ev.get("args") or {})))
            elif t == "tool_result":
                tname = str(ev.get("tool") or "")
                obs = next((o for o in reversed(task.observations)
                            if o.tool == tname and o.effect == "not_checked"), None)
                if obs is None and task.observations:
                    obs = task.observations[-1]
                if obs is not None:
                    obs.ok = bool(ev.get("ok"))
                    obs.seconds = ev.get("seconds", 0.0)
                    obs.result_text = str(ev.get("preview") or "")[:2000]
                    if isinstance(ev.get("args"), dict) and not obs.args:
                        obs.args = dict(ev.get("args") or {})
                    v = check_effect(obs, self.ctx.workspace)
                    obs.effect = v.verdict
                    obs.blocked = (not obs.ok) and ("not executed" in obs.result_text
                                                    or "blocked" in obs.result_text.lower())
                _emit(self.events, AgentEventKind.TOOL_COMPLETED, session_id, task.id,
                      tool=tname, ok=ev.get("ok"), seconds=ev.get("seconds"))
                self.receipts.append(ExecutionReceipt(
                    task_id=task.id, session_id=session_id, tool=tname, action="execute",
                    arguments=(obs.args if obs else {}),
                    risk_level=self._risk_of(tname, obs.args if obs else {}),
                    permission="not_required",
                    result=(obs.result_text if obs else str(ev.get("preview") or ""))[:1500],
                    verification=(obs.effect if obs else "not_run"),
                    duration=obs.seconds if obs else 0.0,
                     error="" if ev.get("ok") else (obs.result_text[:300] if obs else str(ev.get("preview") or "")),
                     retry_count=task.retry_count))
                self._write_checkpoint(task)       # J1: crash-recovery point
            elif t == "guard" and ev.get("action") == "deny":
                _emit(self.events, AgentEventKind.PERMISSION_DENIED, session_id, task.id,
                      tool=ev.get("tool"), reason=ev.get("reason"))
            elif t == "route":
                task.model = str(ev.get("model") or task.model)

        # execute (with bounded retry on verification failure)
        # Phase 3: the loop's capability gate is scoped to THIS task id —
        # grants given mid-task never outlive the task (end_task below).
        self.ctx.current_task_id = task.id
        try:
            result = self._execute_loop(task, session_id, exec_text, model, bridge, _approver,
                                      start, session, on_token, max_iters=max_iters,
                                      # Instant-tier input: what the user actually
                                      # typed. Only when this turn IS a merged
                                      # follow-up ("Remind me X" -> "Tomorrow.")
                                      # does the merged text drive the tiers.
                                      raw_text=(text if (resolved or "").strip()
                                                == (text or "").strip() else resolved))
            # A40b: the self-improvement flywheel used to run only from the REPL,
            # so web / voice / LiveKit / scheduled / proactive tasks never produced
            # lessons — while every one of them READS them in the system prompt.
            # One chokepoint writes them now, so all surfaces learn.
            self._reflect(text, result)
            return result
        finally:
            self.gate.store.end_task(task.id)   # task-scoped grants die with the task
            self.ctx.current_task_id = ""
            self._active_task = None
            # Computer-use sessions are task-scoped too (provenance + action
            # budget); dropping the ref here also releases them from the
            # emergency-stop registry, which is a weak map.
            _cu = getattr(self.ctx, "cu_sessions", None)
            if _cu:
                _cu.pop(task.id, None)
            # J1: only a terminal task clears its checkpoint — a process
            # crash (no finally) is exactly what leaves one behind
            if task.state in (TaskState.COMPLETED, TaskState.FAILED,
                              TaskState.CANCELLED):
                self._clear_checkpoint(task)

    # ------------------------------------------- J1: crash-recovery checkpoints
    def _reflect(self, text: str, result) -> None:
        """Post-task self-review, gated by `learning.reflect`.

        Reflection is an optimization, never a failure source: it gets one bounded
        local-model call and any error is logged, not raised into the user's turn.
        """
        if not getattr(self.ctx.cfg.learning, "reflect", True):
            return
        try:
            from ..agent import reflection
            reflection.reflect(self.ctx, text, result)
        except Exception as e:
            log.warning("reflection failed (task unaffected): %s", e)

    @property
    def _checkpoint_dir(self) -> Path:
        return Path(self.sessions_dir).parent / "checkpoints"

    def _write_checkpoint(self, task, note: str = "") -> None:
        """Persist enough of the in-flight task to RESUME after a crash
        (J1). Redacted, atomic (tmp+replace), best-effort — a checkpoint
        failure never affects the task. Called after every tool observation
        and at execution start; cleared when the task reaches a terminal
        state (a real crash is the only way one persists)."""
        try:
            from .. import privacy
            d = self._checkpoint_dir
            d.mkdir(parents=True, exist_ok=True)
            obs = [{"tool": o.tool, "ok": bool(o.ok), "effect": o.effect,
                    "args": privacy.redact(json.dumps(o.args, default=str))[0][:500],
                    "result": privacy.redact(o.result_text or "")[0][:300]}
                   for o in task.observations[-20:]]
            row = {"task_id": task.id, "session_id": task.session_id,
                   "text": privacy.redact(task.text or "")[0][:2000],
                   "state": task.state.value, "retry_count": task.retry_count,
                   "observations": obs, "note": note, "ts": round(time.time(), 3)}
            f = d / f"{task.id}.json"
            tmp = d / f"{task.id}.json.tmp"
            tmp.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
            tmp.replace(f)
        except Exception:
            pass

    def _clear_checkpoint(self, task) -> None:
        tid = getattr(task, "id", task)     # Task object or bare id
        try:
            (self._checkpoint_dir / f"{tid}.json").unlink(missing_ok=True)
        except Exception:
            pass

    def pending_checkpoints(self, session_id: str | None = None) -> list[dict]:
        """Interrupted (non-terminal) checkpoints, oldest first."""
        d = self._checkpoint_dir
        out: list[dict] = []
        if not d.exists():
            return out
        for f in d.glob("*.json"):
            try:
                row = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if row.get("state") in ("completed", "failed", "cancelled"):
                try:
                    f.unlink()          # stale terminal row — sweep
                except Exception:
                    pass
                continue
            if session_id and row.get("session_id") != session_id:
                continue
            out.append(row)
        return sorted(out, key=lambda r: r.get("ts") or 0)

    def resume(self, task_id: str | None = None, on_event=None) -> "TaskResult":
        """J1 crash recovery: re-run a task whose checkpoint shows it was
        interrupted mid-execution. A deterministic CRASH RECOVERY note tells
        the model which steps were ALREADY executed (so it does not redo
        destructive work), and the pre-crash observations are attached to the
        resumed task afterwards for the verification record.

        Honest limit: this resumes at the task level (model re-plans with
        knowledge of completed steps) — not at the message level of the old
        in-flight loop.
        """
        pends = self.pending_checkpoints()
        if not pends:
            raise RuntimeError("no interrupted tasks to resume")
        row = (next((r for r in pends if r["task_id"] == task_id), None)
               if task_id else pends[-1])
        if row is None:
            raise RuntimeError(f"no interrupted task with id {task_id!r}")
        done = [o for o in row.get("observations") or [] if o.get("ok")]
        lines = "\n".join(f"  - {o.get('tool')} (executed ok)" for o in done) \
            or "  (no completed steps recorded)"
        note = (row.get("text") or "") + (
            "\n\n[CRASH RECOVERY] This task was interrupted by a crash and is now "
            "resuming. The following steps were ALREADY EXECUTED successfully "
            "before the crash — do NOT redo them. If in doubt, verify their "
            "effects first, then finish the remaining work.\n" + lines)
        self._clear_checkpoint(row["task_id"])       # consumed by this resume
        result = self.run(note, session_id=row.get("session_id") or "repl",
                          on_event=on_event)
        for o in row.get("observations") or []:      # attach pre-crash record
            result.task.observations.insert(0, Observation(
                tool=str(o.get("tool") or ""), ok=bool(o.get("ok")),
                effect=str(o.get("effect") or "not_checked"),
                result_text=str(o.get("result") or "")[:2000]))
        return result

    def _execute_loop(self, task, session_id, exec_text, model, bridge, _approver,
                      start, session, on_token=None,
                      max_iters: int | None = None,
                      raw_text: str = "") -> "TaskResult":
        result = None
        attempts = 0
        while True:
            attempts += 1
            if attempts > 1:
                task.retry_count = attempts - 1
                transition(task, TaskState.RETRYING)
            transition(task, TaskState.EXECUTING)
            attempt_start = len(task.observations)
            self._write_checkpoint(task)          # J1: resumable from here
            # exec_text carries the session context for the MODEL; resolved is what
            # the user actually typed — passed so the instant tiers judge the utterance
            # itself, not the context-augmented prompt.
            result = run_agent(self.ctx, exec_text, on_event=bridge, model=model,
                               route_text=raw_text or exec_text,
                               on_ask=_approver, on_token=on_token,
                               **({"max_iters": max_iters} if max_iters else {}))
            attempt_obs = task.observations[attempt_start:]
            if result.error == "cancelled":
                transition(task, TaskState.CANCELLED)
                break

            # 6 — VERIFYING (observe the world; never trust a clean return)
            transition(task, TaskState.VERIFYING)
            _emit(self.events, AgentEventKind.VERIFICATION_STARTED, session_id, task.id)
            vres = verify_task(exec_text, attempt_obs, self.ctx.workspace, result.output)
            if result.verify == "fail" and vres.verdict != "fail":
                vres.verdict = "fail"
                vres.checks.append({"check": "answer_verification", "ok": False,
                                    "detail": "model's answer failed self-verification"})
            task.verification = vres
            _emit(self.events, AgentEventKind.VERIFICATION_COMPLETED, session_id, task.id,
                  verdict=vres.verdict, checks=vres.checks[:8])

            failed = vres.verdict == "fail" or (result.ok is False and result.error
                                                and result.error != "cancelled")
            if not failed:
                break
            kind = self.policy.classify(result.error or "tool failed")
            if vres.verdict == "fail" and kind != FailureKind.UNRECOVERABLE:
                kind = FailureKind.VERIFICATION
            # 'no answer after wrap' stays UNRECOVERABLE even though verification
            # failed: the attempt already spent the full tool budget plus a
            # tools-disabled answer pass. A second attempt re-burns all of it for
            # the same honest failure (measured 39.9 s -> 80 s on the eval box).
            # a blind retry is only allowed when NO action of this attempt was
            # destructive/state-changing
            destructive = any(self.policy.is_destructive(o.tool, o.args) for o in attempt_obs)
            fo = next((o for o in attempt_obs if not o.ok and not o.blocked), None)
            if not destructive and self.policy.should_retry(kind, attempts,
                                                            fo.tool if fo else None,
                                                            fo.args if fo else None):
                  note = ("(PREVIOUS ATTEMPT FAILED VERIFICATION: "
                          + "; ".join(f"{c['check']}: {c.get('detail','')[:120]}"
                                     for c in vres.checks if not c["ok"])[:400]
                          + ". Replan with a different approach, then re-check the ACTUAL effect "
                            "before answering.)")
                  exec_text = f"{task.text}\n{note}"
                  if task.plan is not None:
                      # Plan -> Action -> Observation -> REPLAN lifecycle: the
                      # kernel records that this attempt re-planned.
                      task.plan.replans += 1
                  continue
            break

        # 7 — receipts + 8 — memory + 9 — final state
        task.output = result.output or ""
        task.error = result.error or ""
        task.model = result.model or task.model
        if task.state not in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
            if task.error == "cancelled":
                if task.state != TaskState.CANCELLED:
                    transition(task, TaskState.CANCELLED)
            elif not result.ok or task.verification.verdict == "fail":
                task.failure_kind = self.policy.classify(
                    result.error or "verification failed",
                    attempt_obs[0].tool if attempt_obs else None,
                    blocked=any(o.blocked for o in attempt_obs)).value
                transition(task, TaskState.FAILED)
            else:
                transition(task, TaskState.COMPLETED)

        self.receipts.append(ExecutionReceipt(
            task_id=task.id, session_id=session_id, tool="agent", action="run",
            arguments={"task": task.text[:200]}, risk_level="low",
            permission="not_required", result=(result.output or "")[:1500],
            verification=task.verification.verdict,
            duration=round(time.time() - start, 1),
            error=result.error or "", retry_count=task.retry_count))
        session.record_task(task, result.output, result.ok)
        session.pending_confirmation = ""
        session.save(self.sessions_dir)
        self.memory.working.note("last_task", task.text[:200])
        _emit(self.events, AgentEventKind.MEMORY_WRITTEN, session_id, task.id,
              store="session+episode+diary")

        final_kind = (AgentEventKind.TASK_CANCELLED if task.state == TaskState.CANCELLED
                      else AgentEventKind.TASK_FAILED if task.state == TaskState.FAILED
                      else AgentEventKind.TASK_COMPLETED)
        _emit(self.events, final_kind, session_id, task.id,
              state=task.state.value, retried=task.retry_count,
              verification=task.verification.verdict)
        return TaskResult(task=task, agent_result=result,
                          verification=task.verification,
                          cancelled=task.state == TaskState.CANCELLED,
                          retried=task.retry_count > 0)

    # -------------------------------------------------------- command layer
    def direct(self, kind: str, prompt: str, system: str | None = None,
               max_tokens: int = 700, model: str | None = None) -> str | None:
        """Single-shot LLM task for slash commands — SAME kernel infrastructure
        (provider routing via ctx.client, receipts, events, telemetry). No plan
        or tool execution: commands are read-only drafting operations."""
        session_id = "commands"
        task = Task(session_id=session_id, text=f"/{kind}: {prompt[:300]}")
        self._tasks[task.id] = task
        self.last_task = task
        transition(task, TaskState.UNDERSTANDING)
        transition(task, TaskState.PLANNING)
        transition(task, TaskState.EXECUTING)
        _emit(self.events, AgentEventKind.TASK_CREATED, session_id, task.id, command=kind)
        t0 = time.time()
        out = None
        err = ""
        try:
            msgs = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
            out = self.ctx.client.chat(model or "local", msgs, max_tokens=max_tokens)
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:200]}"
        text = ((out or {}).get("content") or "").strip()
        ok = bool(text) and not err
        transition(task, TaskState.VERIFYING)
        v = VerificationResult("pass" if ok else "fail",
                               [{"check": "output_present", "ok": ok, "detail": err or ""}])
        task.verification = v
        if ok:
            transition(task, TaskState.COMPLETED)
        else:
            task.error = err or "empty model output"
            transition(task, TaskState.FAILED)
        r = ExecutionReceipt(task_id=task.id, session_id=session_id, tool=f"llm.{kind}",
                             action="generate", arguments={"prompt_chars": len(prompt or "")},
                             risk_level="low", permission="not_required",
                             result=text[:1500], verification=v.verdict,
                             duration=round(time.time() - t0, 2), error=err)
        self.receipts.append(r)
        task.receipts.append(r)
        _emit(self.events, AgentEventKind.TASK_COMPLETED if ok else AgentEventKind.TASK_FAILED,
              session_id, task.id, command=kind, seconds=round(time.time() - t0, 1))
        return text or None

    # ------------------------------------------------------ capability gate
    def _gate_confirm(self, cap, reason: str) -> bool:
        """Human (or test) consult for a capability that needs confirmation.
        Mirrors the tool-ask flow: real WAITING_FOR_PERMISSION state, events,
        and a permission receipt."""
        task = self._active_task
        if task is None:
            return False  # no active task -> fail closed
        transition(task, TaskState.WAITING_FOR_PERMISSION)
        _emit(self.events, AgentEventKind.PERMISSION_REQUESTED, task.session_id, task.id,
              capability=cap.id, risk=f"R{int(cap.risk)}", reason=reason)
        try:
            ok = bool(self.approver(f"capability:{cap.id}", {}, reason))
        except Exception:
            ok = False
        _emit(self.events, AgentEventKind.PERMISSION_GRANTED if ok
              else AgentEventKind.PERMISSION_DENIED,
              task.session_id, task.id, capability=cap.id, reason=reason)
        self.receipts.append(ExecutionReceipt(
            task_id=task.id, session_id=task.session_id, tool=f"capability:{cap.id}",
            action="permission", arguments={}, risk_level=f"R{int(cap.risk)}",
            permission="granted" if ok else "denied", result=reason,
            verification="not_run", duration=0.0, retry_count=task.retry_count))
        # the task keeps executing either way (the loop continues with the
        # blocked result); only cancel interrupts from outside
        try:
            if task.state == TaskState.WAITING_FOR_PERMISSION:
                transition(task, TaskState.EXECUTING)
        except InvalidTransitionError:
            pass
        return ok

    # -------------------------------------------------- deterministic memory
    def _exec_memory_request(self, task, session, req, on_event=None) -> TaskResult:
        """remember / recall / forget — kernel operations on the structured
        store. The effect is VERIFIED against the store after the fact."""
        from .models import Observation
        mem = self.memory.structured
        session_id = task.session_id
        task.plan = Plan(goal=req.kind,
                         steps=[Action(description=f"memory.{req.kind}", tool=f"memory.{req.kind}",
                                       risk="low", capability="files.write" if req.kind != "recall" else "files.read"),
                                Action(description="verify store effect", risk="low")],
                         rationale="explicit memory request — deterministic, no LLM")
        transition(task, TaskState.PLANNING)
        _emit(self.events, AgentEventKind.PLAN_CREATED, session_id, task.id, plan=task.plan.to_dict())
        transition(task, TaskState.EXECUTING)
        t0 = time.time()
        error = ""
        try:
            if req.kind == "remember":
                item = mem.remember(req.text, type="fact", source="user",
                                    importance=3, key=req.key, subject=req.subject,
                                    provenance=f"user message {time.strftime('%Y-%m-%d')}",
                                    tags=[req.key] if req.key else [])
                session.last_memory_id = item.id
                ok = mem.recall_by_key(req.key) is not None if req.key \
                    else any(i.id == item.id for i in mem.all())
                response = f"Remembered: {req.text}" + (f"  (saved under '{req.key}')" if req.key else "")
            elif req.kind == "recall":
                items = mem.recall(req.query, k=5)
                hw, hw_data = _hardware_note(req)
                stored = []
                if items:
                    session.last_memory_id = items[0].id
                    lines = [f"- {i.content[:160]}  [source: {i.source}, confidence {i.confidence:.2f}]"
                             for i in items]
                    response = f"Here's what I remember about {req.query or 'it'}:\n" + "\n".join(lines)
                    stored = [i.content for i in items]
                else:
                    # The structured store is not the whole memory. Facts the user
                    # stated months ago live in profile.md / longterm.md and reach
                    # them through the hybrid index — answering "I don't have
                    # anything stored" there was a plain wrong answer to
                    # "Remember my GPU?".
                    hits = []
                    try:
                        hits = self.memory.semantic.search(req.query, k=12) or []
                    except Exception:
                        hits = []
                    hits = [h for h in hits if str(h.get("text") or "").strip()]
                    # Never quote the assistant's own past transcripts back as
                    # fact: a diary chunk that records a previous WRONG answer
                    # ("result: I'm sorry, but I don't have specific information
                    # about the machine's hardware…") would otherwise be served as
                    # the answer, turning one old failure into a permanent lie.
                    transcript = re.compile(r"^##\s*\d{1,2}:\d{2}(:\d{2})?\s*\[model=", re.M)
                    real = [h for h in hits if not transcript.search(str(h.get("text") or ""))]
                    if real:
                        hits = real
                    else:
                        hits = []

                    def _rank(h):
                        # The diary is the assistant's OWN transcript — it contains
                        # every past question and every past wrong answer. Left
                        # unranked, "Remember my GPU?" quoted a previous failed
                        # reply back as fact. Authoritative stores come first.
                        s = str(h.get("source") or "").lower()
                        if "profile" in s or "longterm" in s or "system.md" in s:
                            return 0
                        if "diary" in s:
                            return 2
                        return 1

                    # Source authority first, then literal overlap within a
                    # bucket: hybrid search returned the 'Software & Tools'
                    # section for 'what do you remember about this project' while
                    # longterm.md — which does say what the project is — sat at
                    # equal rank ahead of nothing.
                    qwords = _qwords(req.query)

                    def _overlap(h):
                        compact = re.sub(r"[^a-z0-9]+", "",
                                         str(h.get("text") or "").lower())
                        return sum(1 for w in qwords if w in compact)

                    hits.sort(key=lambda h: (_rank(h), -_overlap(h)))
                    authoritative = [h for h in hits if _rank(h) < 2]
                    if authoritative:
                        hits = authoritative
                    hits = hits[:3]
                    lines, shown = [], set()

                    def _collect(pool, **kw):
                        for h in pool:
                            txt = str(h.get("text") or "").strip()
                            for ln in _best_lines(txt, req.query, **kw):
                                fp = re.sub(r"[^a-z0-9]+", "", ln.lower())[:120]
                                if not ln or fp in shown:
                                    continue
                                shown.add(fp)
                                stored.append(ln)
                                lines.append(
                                    f"- {ln[:300]}  [from {_src_label(h.get('source'))}]")

                    if hits:
                        _collect(hits, fallback=False)
                        if not lines:
                            _collect(hits[:1])     # nothing matched any word
                    if lines:
                        response = (f"Here's what I remember about {req.query or 'it'}:\n"
                                    + "\n".join(lines))
                    else:
                        response = f"I don't have anything stored about '{req.query}' yet."
                if hw:
                    response += f"\n\nBut this machine, as I read it right now: {hw}"
                    warn = _hw_conflict(stored, hw_data)
                    if warn:
                        response += "\n" + warn
                ok = True  # an honest 'I don't remember' IS the correct result
            else:  # forget
                target = session.last_memory_id if req.last else None
                removed = mem.forget(item_id=target, query=None if target else req.query)
                # forgetting nothing is an honest answer, not a failure
                ok = True
                session.last_memory_id = ""
                response = "Forgot it." if removed else "There was nothing matching to forget."
        except Exception as e:
            ok, response, error = False, "", f"{type(e).__name__}: {e}"
        dt = round(time.time() - t0, 3)

        v = VerificationResult("pass" if ok else "fail",
                               [{"check": f"memory.{req.kind}_effect", "ok": ok,
                                 "detail": (error or response[:160])}])
        task.observations.append(Observation(tool=f"memory.{req.kind}",
                                             args={"kind": req.kind, "query": req.query or req.text[:80]},
                                             result_text=response[:500], ok=ok,
                                             seconds=dt, effect=v.verdict))
        task.verification = v
        transition(task, TaskState.VERIFYING)
        _emit(self.events, AgentEventKind.VERIFICATION_STARTED, session_id, task.id)
        _emit(self.events, AgentEventKind.VERIFICATION_COMPLETED, session_id, task.id,
              verdict=v.verdict, checks=v.checks)
        r = ExecutionReceipt(
            task_id=task.id, session_id=session_id, tool=f"memory.{req.kind}",
            action=req.kind, arguments={"query": req.query or req.text[:120]},
            risk_level="low", permission="not_required", result=response[:1500],
            verification=v.verdict, duration=dt, error=error, retry_count=0)
        self.receipts.append(r)
        task.receipts.append(r)
        if ok:
            transition(task, TaskState.COMPLETED)
        else:
            task.error = error or "memory operation failed verification"
            transition(task, TaskState.FAILED)
        task.output = response
        if on_event:
            try:
                on_event({"type": "result", "ok": ok, "output": response})
            except Exception:
                pass
        session.record_task(task, response, ok)
        session.save(self.sessions_dir)
        _emit(self.events, AgentEventKind.MEMORY_WRITTEN, session_id, task.id,
              store="structured", op=req.kind)
        _emit(self.events, AgentEventKind.TASK_COMPLETED if ok else AgentEventKind.TASK_FAILED,
              session_id, task.id, state=task.state.value)
        return TaskResult(task=task, agent_result=_agent_stub(response, ok=ok),
                          verification=v)

    # --------------------------------------------------------------- utils
    def _risk_of(self, tool: str, args: dict) -> str:
        try:
            from .permission import risk_info
            lvl, _ = risk_info(tool, args or {})
            return lvl
        except Exception:
            return "low"


def _agent_stub(output: str, ok: bool = True):
    """Minimal AgentResult-shaped object for kernel-level short circuits
    (e.g. a 'stop' message) so callers never see None."""
    from ..agent.loop import AgentResult
    return AgentResult(output=output, ok=ok, model="kernel", error="")
