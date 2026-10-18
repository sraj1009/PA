"""JobWorker (Phase 6) — durable execution through the AGENT KERNEL.

scheduled job -> AgentSession -> Task -> Permission -> Tools ->
Verification -> Receipt -> notification

The worker is the ONLY thing that executes jobs. It:

  * restores jobs on restart and recomputes next_run — real work is never
    replaced by a no-op (nightly jobs are durable jobs with registered
    function actions, not callback registrations that vanish);
  * prevents duplicate execution on TWO levels:
      - the execution row is persisted BEFORE a run starts (crash-safe
        history + retry budget: a job found RUNNING after a restart is
        marked interrupted and re-queued only if its retry budget allows);
      - a file claim token with TTL (JobStore.try_claim) stops two PROCESSES
        (bee-runfull = web + repl) from running the same job;
  * handles missed jobs: one-time jobs catch up once if inside the grace
    window, are marked MISSED beyond it; recurring jobs skip missed
    occurrences (notify, don't backfill);
  * controls concurrency: a JobQueue (single-flight per job + global
    max_parallel cap) — a single job can never run twice simultaneously;
  * enforces max_runtime via a watchdog that sets a JOB-SCOPED cancel event
    (the loop checks it every iteration) — a job timeout cancels the job,
    never interactive user work;
  * runs every agent_task through the SAME kernel instance as interactive
    requests (same sessions, receipts, capability store, event bus). The
    kernel serializes executions (its run-lock), so a job and a chat turn
    never interleave mid-task;
  * runs jobs UNATTENDED by design: the approver is swapped for the run to
    a fail-closed policy that allows ONLY the job's explicitly
    preapproved_capabilities — everything that asks is denied.

The clock is injectable — every test drives tick() with a fake `now` and
never sleeps.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

from .events import (BusEvent, EventBus, ProactivePolicy)
from .models import (CANCELLED, COMPLETED, DISABLED, FAILED, MISSED, PENDING,
                     RUNNING, SUCCEEDED, Job, JobExecution, Notification,
                     iso, parse_dt)
from .queue import JobQueue
from .schedule import get_tz, next_run as compute_next_run
from .store import JobStore

log = logging.getLogger("bee.automation")

DEFAULT_MISS_GRACE = 15 * 60      # one-time jobs catch up if missed by <= 15 min
CLAIM_GRACE = 300                 # claim TTL beyond max_runtime (crash takeover)


def effective_max_attempts(job: Job) -> int:
    """Retry budget for a job (scheduling unification, 2026-10-08).

    Destructive/side-effecting work must not be retried BLINDLY: an
    `agent_task` re-runs an LLM task that may already have partially acted
    (sent a message, moved a file), so it gets **max 1 attempt by default**.
    Explicit opt-in via `retry_policy.retry_agent_task: true` (e.g. a job the
    user declared idempotent) restores the configured budget. `function` and
    `notify` jobs are maintenance/idempotent and keep their retry budget.
    """
    rp = job.retry_policy or {}
    if (job.action or {}).get("type") == "agent_task" and not rp.get("retry_agent_task"):
        return 1
    return max(1, int(rp.get("max_attempts", 2)))


# ------------------------------------------------------------ real-work registry
# Dotted names -> functions (ctx) -> dict. Nightly jobs use these so REAL
# work survives restarts instead of callback registrations that vanish
# (and silently no-op when a library is missing). No-op is structurally
# impossible: an unknown fn name fails the job with a message.
def _fn_consolidate(ctx) -> dict:
    from .. import scheduler
    return scheduler.consolidate(ctx)


def _fn_rebuild_vectors(ctx) -> dict:
    from .. import scheduler
    return scheduler.rebuild_vectors(ctx)

def _fn_flush_memory_index(ctx) -> dict:
    from .. import scheduler
    return scheduler.flush_memory_index(ctx)


def _fn_train_router(ctx) -> dict:
    from .. import scheduler
    return scheduler.maybe_train_router(ctx)


def _fn_teach_back(ctx) -> dict:
    from .. import scheduler
    return scheduler.maybe_teach_back(ctx)


def _fn_build_sft(ctx) -> dict:
    from .. import scheduler
    return scheduler.maybe_build_sft(ctx)


def _fn_train_qlora(ctx) -> dict:
    from .. import scheduler
    return scheduler.maybe_train_qlora(ctx)


def _fn_rotate_logs(ctx) -> dict:
    from ..monitor.rotate import rotate_all
    return rotate_all(str(ctx.workspace))


def _fn_alert_scan(ctx) -> dict:
    """Daily threshold alerting (audit item 6): evaluate metrics stats
    against configured thresholds, toast + notify on breach."""
    from ..monitor import alerts
    return alerts.check_thresholds(ctx)


def _fn_skill_gate(ctx) -> dict:
    """J2: gate candidate skills (structural check + bounded eval probe)."""
    from ..evals import skillgate
    return skillgate.gate_candidates(ctx)


def _fn_model_gate(ctx) -> dict:
    """J3: model-upgrade quality gate (candidate vs recorded baseline)."""
    from ..evals import gate
    return gate.model_quality_gate(ctx)


def _redact(text: str) -> str:
    """PII/secret redaction for anything persisted as job telemetry."""
    try:
        from .. import privacy
        s, _n = privacy.redact(str(text or ""))
        return s
    except Exception:
        return str(text or "")


FUNCTIONS: dict[str, Callable] = {
    "bee.scheduler.consolidate": _fn_consolidate,
    "bee.scheduler.rebuild_vectors": _fn_rebuild_vectors,
    "bee.scheduler.flush_memory_index": _fn_flush_memory_index,
    "bee.scheduler.maybe_train_router": _fn_train_router,
    "bee.scheduler.maybe_teach_back": _fn_teach_back,
    "bee.scheduler.maybe_build_sft": _fn_build_sft,
    "bee.scheduler.maybe_train_qlora": _fn_train_qlora,
    "bee.monitor.rotate_all": _fn_rotate_logs,
    "bee.monitor.alert_scan": _fn_alert_scan,
    "bee.skills.gate_candidates": _fn_skill_gate,
    "bee.evals.model_gate": _fn_model_gate,
}


# --------------------------------------------------------------------- worker
class JobWorker:
    def __init__(self, ctx, kernel, store: JobStore, bus: EventBus | None = None,
                 policy: ProactivePolicy | None = None,
                 clock: Callable[[], datetime] | None = None,
                 max_parallel: int = 1,
                 miss_grace_seconds: int = DEFAULT_MISS_GRACE,
                 tick_seconds: float = 5.0,
                 default_timezone: str = "Asia/Kolkata",
                 on_notify: Callable[[Notification], None] | None = None):
        self.ctx = ctx
        self.kernel = kernel
        self.store = store
        self.bus = bus or EventBus()
        self.policy = policy
        self.clock = clock or (lambda: datetime.now().astimezone())
        self.queue = JobQueue(max_parallel)
        self.miss_grace = miss_grace_seconds
        self.tick_seconds = tick_seconds
        self.default_timezone = default_timezone
        self.on_notify = on_notify
        self._threads: set = set()
        self._threads_lock = threading.RLock()
        # Deterministic idle signal (N7): wait_idle() used to SAMPLE thread
        # liveness in a 0.05 s poll, so under load the last job thread could be
        # observed alive past the deadline and the wait would fail even though
        # everything had finished. Threads now announce their own exit.
        self._idle = threading.Event()
        self._idle.set()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.restore_report: dict = {}

    # ------------------------------------------------------------- lifecycle
    def start(self) -> dict:
        report = self.restore()
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, daemon=True,
                                            name="BeeJobWorker")
            self._thread.start()
        return report

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        # event sources are attached by scheduler.start_automation(); stopping
        # them here means no poller outlives the worker it feeds
        for src in getattr(self, "event_sources", ()) or ():
            try:
                src.stop()
            except Exception:
                pass
        self.event_sources = []

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:
                log.warning("job worker tick failed: %s", e)
            self._stop.wait(self.tick_seconds)

    def now(self) -> datetime:
        return self.clock()

    def wait_idle(self, timeout: float = 30.0) -> bool:
        """Block until no job thread is running (or timeout). Test/teardown
        helper — production uses the tick loop, not this."""
        self._idle.wait(timeout)
        with self._threads_lock:
            alive = [t for t in self._threads if t.is_alive()]
        if not alive:
            self._idle.set()
            return True
        # the event was set too eagerly (a job started between wake and check):
        # fall back to a bounded join sweep so the answer is still exact
        end = time.time() + max(0.0, timeout - 0.01)
        while time.time() < end:
            for t in alive:
                t.join(0.05)
            with self._threads_lock:
                alive = [t for t in self._threads if t.is_alive()]
            if not alive:
                self._idle.set()
                return True
        return False

    # -------------------------------------------------------------- restore
    def restore(self) -> dict:
        """Restart recovery: load jobs, repair crash state, recompute
        next_run, handle missed windows. Returns a report."""
        now = self.now()
        jobs = self.store.load_all_jobs()
        report = {"restored": len(jobs), "repaired_running": 0,
                  "catchup": 0, "missed": 0, "skipped_recurring": 0}

        # crash repair: a job persisted RUNNING was killed mid-execution.
        # Its execution row already exists (the dup guard) — append a
        # terminal 'interrupted' row for it (store dedupes by execution id,
        # last row wins) and re-queue the job only per its retry budget
        # (never a blind replay).
        open_execs = {ex.job_id: ex for ex in self.store.executions().entries
                      if ex.status == "running"}
        repaired_ids: set[str] = set()
        for job in jobs:
            if job.state == RUNNING:
                ex = open_execs.get(job.id)
                if ex is not None:
                    ex.status = "interrupted"
                    ex.finished_at = iso(now)
                    self.store.append_execution(ex)
                max_attempts = effective_max_attempts(job)
                if ex is not None and ex.attempt >= max_attempts:
                    job.state = FAILED
                    job.next_run = ""
                    self._notify("failure", job,
                                 f"job interrupted by restart and retry budget "
                                 f"exhausted ({ex.attempt}/{max_attempts}) — "
                                 f"{job.description!r}")
                else:
                    job.state = PENDING
                    job.next_run = iso(now)      # re-queue once per retry budget
                report["repaired_running"] += 1
                repaired_ids.add(job.id)

        for job in jobs:
            if job.id in repaired_ids:
                self.store.save_job(job)        # already re-queued above
                continue
            if not job.enabled or job.state in (CANCELLED, COMPLETED):
                self.store.save_job(job)
                continue
            if job.state == FAILED:
                # failed permanently — stays failed (user re-enables)
                self.store.save_job(job)
                continue
            nr = self._next_after(job, now)

            if job.trigger.kind == "one_time":
                if job.last_run:
                    job.state = COMPLETED
                    job.next_run = ""
                    self.store.save_job(job)
                    continue
                ref = parse_dt(job.next_run) or parse_dt(job.trigger.at)
                if ref is None or nr is not None:
                    # still in the future (or no parsable reference) — schedule as-is
                    if nr is not None:
                        job.next_run = iso(nr)
                    job.state = PENDING
                    self.store.save_job(job)
                    continue
                lag = (now - ref).total_seconds()
                if lag <= self.miss_grace:
                    job.state = PENDING
                    job.next_run = iso(now)     # catch up EXACTLY once
                    report["catchup"] += 1
                else:
                    job.state = MISSED
                    job.next_run = ""
                    self._notify("missed", job,
                                 f"missed one-time job (window passed): "
                                 f"{job.description!r}")
                    report["missed"] += 1
                self.store.save_job(job)
                continue

            if nr is None:
                # recurring with no future occurrence
                if job.trigger.kind == "calendar":
                    job.state = PENDING     # wait for new calendar events
                else:
                    job.state = FAILED
                    self._notify("failure", job,
                                 f"job has no valid schedule: {job.description!r}")
                self.store.save_job(job)
                continue
            # missed occurrences while offline: skip + notify, don't backfill
            prev = parse_dt(job.next_run)
            if prev is not None and prev <= now and job.trigger.kind != "interval":
                n_missed = self._count_missed(job, prev, now)
                if n_missed:
                    self._notify("missed", job,
                                 f"missed {n_missed} occurrence(s) while offline; "
                                 f"resuming with next: {iso(nr)}")
                    report["skipped_recurring"] += n_missed
            job.next_run = iso(nr)
            job.state = PENDING
            self.store.save_job(job)
        # proactive rules: rebuild the policy from the store (user-authorized)
        if self.policy is None:
            self.policy = ProactivePolicy(self.store.load_rules())
        else:
            self.policy.rules = self.store.load_rules()
        # (re)attach the policy gate exactly once per bus
        self.bus.unsubscribe("*", self._on_proactive)
        self.bus.subscribe("*", self._on_proactive)
        return report

    def _next_after(self, job: Job, now: datetime) -> Optional[datetime]:
        anchor = parse_dt(job.created_at) or now
        return compute_next_run(job.trigger, job.timezone or self.default_timezone,
                                now, anchor=anchor)

    @staticmethod
    def _count_missed(job: Job, prev: datetime, now: datetime) -> int:
        n = 0
        cur = prev
        while cur < now:
            cur = compute_next_run(job.trigger, job.timezone or "UTC", cur)
            if cur is None or cur > now:
                break
            n += 1
        return max(0, n)

    # ----------------------------------------------------------------- tick
    def tick(self) -> list[str]:
        """One scheduler pass (driven by the loop, or directly by tests).
        Each due job that passes BOTH guards (in-memory queue + file claim)
        runs in its own thread, bounded by max_parallel. Returns the ids of
        jobs that started executing."""
        now = self.now()
        self.store.clear_stale_claims(self.claim_ttl(None) + CLAIM_GRACE)
        started: list[str] = []
        jobs = sorted(self.store.load_all_jobs(), key=lambda j: j.next_run or "")
        for job in jobs:
            if not job.enabled or job.state != PENDING:
                continue
            if job.trigger.kind == "calendar" and not job.next_run:
                # calendar jobs re-evaluate the ICS every tick (new events
                # can appear at any time); nothing else changes here
                nr = self._next_after(job, now)
                if nr:
                    job.next_run = iso(nr)
                    self.store.save_job(job)
                continue
            if not job.next_run:
                continue
            due = parse_dt(job.next_run)
            if due is None or due.astimezone() > now:
                continue
            if not self.queue.claim(job):
                if self.queue.size >= self.queue.max_parallel:
                    break                      # concurrency cap — stays PENDING
                continue                       # already inflight — never twice
            t = threading.Thread(target=self._job_thread, args=(job,),
                                 daemon=True, name=f"BeeJob-{job.id[-8:]}")
            with self._threads_lock:
                self._threads.add(t)
            self._idle.clear()            # busy from here; the thread announces exit
            t.start()
            started.append(job.id)
        return started

    def claim_ttl(self, job: Optional[Job]) -> float:
        return (job.max_runtime if job else 600.0) + CLAIM_GRACE

    def _job_thread(self, job: Job) -> None:
        try:
            self._run_job(job)
        except Exception as e:
            log.warning("job %s crashed: %s", job.id, e)
        finally:
            self.queue.release(job.id)
            with self._threads_lock:
                # this thread removes itself first, so the remaining set is
                # exactly the other in-flight jobs
                self._threads.discard(threading.current_thread())
                if not any(th.is_alive() for th in self._threads):
                    self._idle.set()

    # ------------------------------------------------------------- execution
    def _run_job(self, job: Job) -> None:
        now = self.now()
        # cross-process duplicate guard (file claim, TTL = max_runtime + grace)
        if not self.store.try_claim(job.id, self.claim_ttl(job)):
            # Retried every tick until the holder's TTL lapses (crash takeover).
            # One INFO per streak, then DEBUG: a crashed holder is a normal
            # situation and this tick loop produced ~215 identical lines in
            # 18 minutes of web-server logs.
            skipped = getattr(self, "_claim_skips", None)
            if skipped is None:
                skipped = self._claim_skips = set()
            if job.id in skipped:
                log.debug("job %s still claimed by another process — skipping", job.id)
            else:
                skipped.add(job.id)
                log.info("job %s claimed by another process — skipping until its TTL lapses", job.id)
            return
        skipped = getattr(self, "_claim_skips", None)
        if skipped:
            skipped.discard(job.id)
        job.state = RUNNING
        self.store.save_job(job)           # persisted BEFORE the run (dup guard)
        ex = JobExecution(job_id=job.id, attempt=job.attempts + 1,
                          started_at=iso(now))
        self.store.append_execution(ex)    # row exists before any work starts
        t0 = time.time()
        status, err, task_id, preview = "succeeded", "", "", ""
        try:
            status, err, task_id, preview = self._execute(job)
        except Exception as e:
            status, err = "failed", f"{type(e).__name__}: {e}"
        finally:
            dt = time.time() - t0
            self.store.release_claim(job.id)
        ex.finished_at = iso(self.now())
        ex.status = status
        ex.task_id = task_id
        # retention contract: execution history is telemetry, not a content
        # store — redact before persisting (audit 2026-10-06)
        ex.error = _redact(err)
        ex.output_preview = _redact(preview)
        self.store.append_execution(ex)
        job.last_run = ex.finished_at
        job.attempts = ex.attempt

        if status == "succeeded":
            self._notify("success", job,
                         f"job succeeded: {job.description!r} ({dt:.1f}s)")
            self._advance(job, success=True)
        else:
            self._handle_failure(job, ex, err, status, dt)

    def _execute(self, job: Job) -> tuple[str, str, str, str]:
        """Run the structured action. Returns (status, error, task_id, preview).
        agent_task runs through the SAME kernel as interactive requests."""
        act = job.action or {}
        kind = act.get("type")
        if kind == "agent_task":
            text = act.get("task") or job.description
            session_id = job.owner if job.owner else "job"
            result = self._run_agent_with_timeout(job, text, session_id)
            if result is None:
                return "timeout", f"max_runtime {job.max_runtime:.0f}s exceeded (cancelled)", "", ""
            task_id = getattr(getattr(result, "task", None), "id", "") or ""
            if getattr(result, "cancelled", False):
                return "timeout", "cancelled (max_runtime)", task_id, ""
            if getattr(result, "ok", False):
                return "succeeded", "", task_id, (getattr(result, "output", "") or "")[:160]
            return "failed", str(getattr(result, "error", "") or "task failed"), task_id, ""
        if kind == "notify":
            msg = act.get("message") or job.description
            self._notify("job_event", job, msg)
            return "succeeded", "", "", ""
        if kind == "function":
            fn = FUNCTIONS.get(act.get("fn", ""))
            if fn is None:
                return "failed", f"unknown registered function {act.get('fn')!r}", "", ""
            box: dict = {}

            def _run():
                try:
                    box["res"] = fn(self.ctx)
                except Exception as e:
                    box["err"] = f"{type(e).__name__}: {e}"
            t = threading.Thread(target=_run, daemon=True, name="BeeJobFn")
            t.start()
            t.join(job.max_runtime)
            if t.is_alive():
                # function jobs have no cancel path — abandon the daemon
                # thread (documented; max_runtime is a safety net, not a kill)
                return "timeout", f"max_runtime {job.max_runtime:.0f}s exceeded (thread abandoned)", "", ""
            if "err" in box:
                raise RuntimeError(box["err"])
            return "succeeded", "", "", str(box.get("res"))[:160]
        return "failed", f"unknown action type {kind!r}", "", ""

    def _run_agent_with_timeout(self, job: Job, text: str, session_id: str):
        """kernel.run inline on the job thread (serialized by the kernel's
        own run-lock); a watchdog enforces max_runtime by setting a
        JOB-SCOPED cancel event — the loop checks it every iteration, and a
        job timeout can never cancel interactive user work. The approver is
        swapped for the run to a fail-closed policy: only the job's
        explicitly preapproved capabilities pass; everything that asks is
        denied (jobs are unattended by design)."""
        kernel = self.kernel
        pre = set((job.permissions or {}).get("preapproved_capabilities") or [])

        def _job_approver(tool, args, reason) -> bool:
            t = str(tool or "")
            if t.startswith("capability:") and t[len("capability:"):] in pre:
                return True
            return False

        old_event = getattr(self.ctx, "cancel_event", None)
        old_approver = kernel.approver
        job_event = threading.Event()
        self.ctx.cancel_event = job_event        # loop.py captures it at start
        kernel.approver = _job_approver
        wd_stop = threading.Event()

        def _watchdog():
            if not wd_stop.wait(job.max_runtime):
                job_event.set()                   # timeout -> first-class cancel
        wd = threading.Thread(target=_watchdog, daemon=True, name="BeeJobWatchdog")
        wd.start()
        try:
            return kernel.run(text, session_id=session_id)
        finally:
            wd_stop.set()
            kernel.approver = old_approver
            self.ctx.cancel_event = old_event
            try:
                wd.join(1.0)
            except Exception:
                pass

    # ------------------------------------------------------------- outcomes
    def _advance(self, job: Job, success: bool) -> None:
        now = self.now()
        if job.trigger.kind == "one_time":
            job.state = COMPLETED
            job.next_run = ""
        else:
            nr = self._next_after(job, now)
            job.next_run = iso(nr) if nr else ""
            job.state = PENDING if nr else (COMPLETED if job.trigger.kind == "calendar" else PENDING)
        self.store.save_job(job)

    def _handle_failure(self, job: Job, ex: JobExecution, err: str,
                        status: str, dt: float) -> None:
        rp = job.retry_policy or {}
        # agent_task jobs: no BLIND retry by default (side-effecting work) —
        # see effective_max_attempts. function/notify jobs keep their budget.
        max_attempts = effective_max_attempts(job)
        backoff = float(rp.get("backoff_seconds", 60))
        now = self.now()
        recurring = job.trigger.kind in ("daily", "weekly", "calendar")
        if not recurring and ex.attempt < max_attempts:
            # bounded retry: re-queue after backoff (history keeps the attempt)
            job.state = PENDING
            job.next_run = iso(now + timedelta(seconds=backoff * ex.attempt))
            self.store.save_job(job)
            self._notify("failure", job,
                         f"attempt {ex.attempt}/{max_attempts} failed ({status}): "
                         f"{err[:120]} — retrying in {backoff * ex.attempt:.0f}s")
            return
        if recurring:
            # recurring: don't wedge the schedule — next occurrence still comes
            nr = self._next_after(job, now)
            job.state = PENDING
            job.next_run = iso(nr) if nr else ""
            self.store.save_job(job)
            self._notify("failure", job,
                         f"job failed this occurrence ({status}): {err[:150]} — "
                         f"next run {job.next_run or 'none'}")
        else:
            job.state = FAILED
            job.next_run = ""
            self.store.save_job(job)
            self._notify("failure", job,
                         f"job FAILED after {ex.attempt} attempt(s) ({status}): "
                         f"{err[:200]}")

    # ------------------------------------------------------------- proactive
    def _on_proactive(self, ev: BusEvent) -> None:
        """Policy gate: default-deny. Only user-authorized, matching,
        rate-limit-allowed rules may act."""
        if self.policy is None:
            return
        allowed = self.policy.check(ev, now=time.time())
        for rule, action in allowed:
            try:
                self._run_proactive_action(ev, action)
            except Exception as e:
                log.warning("proactive action failed: %s", e)

    def _run_proactive_action(self, ev: BusEvent, action: dict) -> None:
        kind = action.get("type")
        if kind == "notify":
            self._notify("proactive", None,
                         action.get("message", "") or f"event: {ev.name}",
                         extra=f" (event {ev.name}; rule-authorized)")
        elif kind == "agent_task":
            text = action.get("task", "") or ""
            if not text:
                return
            # proactive tasks run unattended through the kernel (same gates)
            try:
                self.kernel.run(text, session_id="proactive")
            except Exception:
                pass
        else:
            return   # unknown action types are denied (default-deny)

    # ------------------------------------------------------------- notify
    def _notify(self, kind: str, job: Optional[Job], message: str,
                extra: str = "") -> None:
        n = Notification(kind=kind, message=_redact(message + extra)[:500],
                         job_id=job.id if job else "")
        self.store.add_notification(n)
        # OS-level toast, gated by cfg.alerts.enabled, best-effort, never raises.
        # The gate used to be ONLY failure/missed, which meant a `notify` job —
        # i.e. every /remind — "succeeded" into the store and the log while the
        # user waited for something to appear. Proactive notifications are
        # already past policy.check (authorization + rate limit + quiet hours),
        # so they are meant to be seen too.
        action = (job.action or {}) if job is not None else {}
        wants_toast = (kind in ("failure", "missed") or kind == "proactive"
                       or (kind == "job_event" and action.get("critical") is True))
        if wants_toast:
            try:
                from ..monitor import alerts
                acfg = getattr(getattr(self.ctx, "cfg", None), "alerts", None)
                if acfg is not None and getattr(acfg, "enabled", True):
                    title = ("BEE reminder" if action.get("critical") is True
                             else "BEE" if kind == "proactive"
                             else f"BEE job {kind}")
                    alerts.os_notify(title, n.message)
            except Exception:
                pass
        if self.on_notify:
            try:
                self.on_notify(n)
            except Exception:
                pass
        else:
            log.info("[notify:%s] %s", kind, n.message)

    # -------------------------------------------------------------- control
    def jobs(self) -> list[Job]:
        return self.store.load_all_jobs()

    def reschedule(self, job: Job, trigger) -> Job:
        """Move a PENDING job to a new trigger time (Phase 8 follow-up
        resolution: 'Tomorrow.' -> 'Actually at 10 AM.' updates the SAME
        durable job instead of creating a duplicate). next_run is computed
        with the SAME rules as create_job (missed one-time -> catch up once)."""
        job.trigger = trigger
        now = self.now()
        nr = self._next_after(job, now)
        if nr is not None:
            job.next_run = iso(nr)
        elif job.trigger.kind == "one_time":
            job.next_run = iso(now)
        else:
            job.next_run = ""
        self.store.save_job(job)
        return job

    def create_job(self, job: Job) -> Job:
        now = self.now()
        job.state = PENDING
        nr = self._next_after(job, now)
        if nr is None and job.trigger.kind == "one_time":
            at = parse_dt(job.trigger.at)
            if at is not None:
                lag = (now - at.astimezone()).total_seconds()
                if 0 <= lag <= self.miss_grace:
                    job.next_run = iso(now)   # catch up EXACTLY once
                else:
                    job.state = MISSED
                    job.next_run = ""
                    self.store.save_job(job)
                    self._notify("missed", job,
                                 f"one-time job created already past: {job.description!r}")
                    return job
        else:
            job.next_run = iso(nr) if nr else ""
        self.store.save_job(job)
        return job

    def disable_job(self, job_id: str) -> bool:
        job = self.store.load_job(job_id)
        if job is None:
            return False
        job.enabled = False
        job.state = DISABLED
        job.next_run = ""
        self.store.save_job(job)
        return True

    def enable_job(self, job_id: str) -> bool:
        job = self.store.load_job(job_id)
        if job is None:
            return False
        job.enabled = True
        if job.state in (DISABLED, FAILED):
            job.state = PENDING
        nr = self._next_after(job, self.now())
        job.next_run = iso(nr) if nr else ""
        self.store.save_job(job)
        return True

    def cancel_job(self, job_id: str) -> bool:
        job = self.store.load_job(self._resolve(job_id))
        return False if job is None else self._cancel(job)

    def _resolve(self, job_id: str) -> str:
        for j in self.store.load_all_jobs():
            if j.id == job_id or j.id.endswith(job_id) or job_id in j.description:
                return j.id
        return job_id

    def _cancel(self, job: Job) -> bool:
        job.enabled = False
        job.state = CANCELLED
        job.next_run = ""
        self.store.save_job(job)
        self._notify("job_event", job, f"job cancelled: {job.description!r}")
        return True

    def delete_job(self, job_id: str) -> bool:
        job = self.store.load_job(self._resolve(job_id))
        if job is None:
            return False
        self.store.delete_job(job.id)
        return True

    def history(self, job_id: str, n: int = 10) -> list[dict]:
        return [e.to_dict() for e in self.store.executions()
                .last(self._resolve(job_id), n)][::-1]

    def notifications(self, unread_only: bool = False) -> list[dict]:
        rows = self.store.load_notifications()
        return [n.to_dict() for n in rows if not unread_only or not n.read]

    def mark_notifications_read(self) -> int:
        rows = self.store.load_notifications()
        n = 0
        for r in rows:
            if not r.read:
                r.read = True
                n += 1
        self.store.save_notifications(rows)
        return n
