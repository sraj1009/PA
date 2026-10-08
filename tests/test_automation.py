"""Durable automation + proactive agent tests (Phase 6).

Covers the required scenarios:
  * trigger math: one_time / daily / weekly / interval / calendar (ICS)
  * persistence: job round-trip, execution history, cross-process claims
  * restart recovery: restore + recompute next_run + NEVER re-run finished
    work + crash repair honoring the retry budget + missed-job handling
  * concurrency: single-flight per job, global max_parallel cap
  * max_runtime: watchdog cancels the JOB (job-scoped cancel event), never
    interactive user work
  * retry with backoff, failure notification, disable/enable/cancel/delete
  * proactive events: default-deny without rules, user-authorized rules
    fire, rate limiting, rules persist across restart
  * the SAME KERNEL: agent_task jobs and the automation_job tool run
    through the real AgentKernel (sessions, receipts, capability gate)

Run:  python -m pytest tests/test_automation.py -q
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from bee.automation import (Job, JobStore, JobTrigger, JobWorker,
                            ProactiveRule, BusEvent, EventBus, next_run,
                            parse_ics)
from bee.automation import worker as wmod
from bee.automation.models import JobExecution

TZ = ZoneInfo("Asia/Kolkata")
BASE = datetime(2026, 10, 6, 12, 0, 0, tzinfo=TZ)   # fake "now"


# ------------------------------------------------------------------ stand-ins
class FakeTask:
    def __init__(self, tid="fake-task"):
        self.id = tid


class FakeResult:
    def __init__(self, ok=True, error="", output="done", cancelled=False,
                 task_id="fake-task"):
        self.ok = ok
        self.error = error
        self.output = output
        self.cancelled = cancelled
        self.task = FakeTask(task_id)


class FakeKernel:
    """Kernel stand-in mirroring the pieces the worker touches:
    run(text, session_id), cancel(), approver, and honoring
    ctx.cancel_event like the real loop does (checked at start)."""

    def __init__(self, ctx, behavior="ok"):
        self.ctx = ctx
        self.behavior = behavior
        self.calls: list[tuple] = []
        self.approver = lambda tool, args, reason: False

    def run(self, text, session_id="repl", **kw):
        self.calls.append((text, session_id))
        if self.behavior == "fail":
            return FakeResult(ok=False, error="boom (scripted failure)")
        if self.behavior == "block_until_cancel":
            ev = getattr(self.ctx, "cancel_event", None)
            if ev is not None and hasattr(ev, "wait"):
                ev.wait(5.0)
            if ev is not None and ev.is_set():
                return FakeResult(ok=False, error="cancelled", cancelled=True)
            return FakeResult()
        if self.behavior == "fail_once":
            if not getattr(self, "_failed", False):
                self._failed = True
                return FakeResult(ok=False, error="first attempt failed")
            return FakeResult()
        return FakeResult()

    def cancel(self):
        ev = getattr(self.ctx, "cancel_event", None)
        if ev is not None and hasattr(ev, "set"):
            ev.set()


class Ctx:
    def __init__(self):
        self.cancel_event = threading.Event()
        self.automation_worker = None


class FakeClock:
    def __init__(self, start: datetime):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now = self.now + timedelta(**kw)


def make_worker(tmp_path, kernel, clock, max_parallel=2, store_dir=None,
                miss_grace=900, on_notify=None, ctx=None):
    store = JobStore(store_dir or (tmp_path / "automation"))
    ctx = ctx or Ctx()
    w = JobWorker(ctx, kernel, store, bus=EventBus(), clock=clock,
                  max_parallel=max_parallel, miss_grace_seconds=miss_grace,
                  on_notify=on_notify)
    ctx.automation_worker = w
    return w


def due_one_time(desc="due job", task="the task", at=None, owner="main"):
    at = at or (BASE - timedelta(seconds=1)).isoformat()
    return Job(owner=owner, description=desc,
               action={"type": "agent_task", "task": task},
               trigger=JobTrigger(kind="one_time", at=at),
               timezone="Asia/Kolkata")


def notif_kinds(store):
    return [n.kind for n in store.load_notifications()]


# ============================================================ trigger math
def test_trigger_math_one_time_naive_and_aware():
    tr = JobTrigger(kind="one_time", at="2026-10-06T13:00:00")  # naive = job tz
    nr = next_run(tr, "Asia/Kolkata", BASE)
    assert nr is not None and nr.astimezone(TZ).hour == 13 and nr.tzinfo is not None
    assert next_run(tr, "Asia/Kolkata", BASE + timedelta(hours=2)) is None  # passed
    tr2 = JobTrigger(kind="one_time", at="2026-10-06T07:30:00-07:00")  # aware (UTC-7)
    nr2 = next_run(tr2, "Asia/Kolkata", BASE)
    # 07:30 -07:00 = 14:30 UTC = 20:00 +05:30
    assert nr2.astimezone(TZ).hour == 20 and nr2.astimezone(TZ).minute == 0


def test_trigger_math_daily():
    tr = JobTrigger(kind="daily", time="14:00")
    assert next_run(tr, "Asia/Kolkata", BASE).astimezone(TZ).hour == 14  # today
    assert next_run(tr, "Asia/Kolkata", BASE.replace(hour=15, minute=0)).astimezone(TZ).day == 7
    tr_bad = JobTrigger(kind="daily", time="25:99")
    assert next_run(tr_bad, "Asia/Kolkata", BASE) is None


def test_trigger_math_weekly():
    # BASE 2026-10-06 is a Tuesday. days 0=Mon .. 4=Fri
    tr = JobTrigger(kind="weekly", time="08:00", days=[0, 4])
    nr = next_run(tr, "Asia/Kolkata", BASE)
    assert nr.astimezone(TZ).isoweekday() == 5      # next Friday
    tr_sun = JobTrigger(kind="weekly", time="08:00", days=[6])
    nr_sun = next_run(tr_sun, "Asia/Kolkata", BASE)
    assert nr_sun.astimezone(TZ).isoweekday() == 7  # Sunday


def test_trigger_math_interval_anchor():
    anchor = BASE - timedelta(hours=1)
    tr = JobTrigger(kind="interval", every_seconds=60)
    nr = next_run(tr, "Asia/Kolkata", BASE, anchor=anchor)
    assert (nr - BASE) == timedelta(minutes=1)      # strictly after now
    nr2 = next_run(tr, "Asia/Kolkata", BASE + timedelta(seconds=59), anchor=anchor)
    assert (nr2 - (BASE + timedelta(seconds=59))) == timedelta(seconds=1)


def test_trigger_math_calendar_ics(tmp_path):
    ics = tmp_path / "cal.ics"
    ics.write_text(
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
        "BEGIN:VEVENT\r\nDTSTART:20261006T130000\r\nSUMMARY:Team standup\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\nDTSTART:20261006T160000Z\r\nSUMMARY:UTC sync\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n", encoding="utf-8")
    tr = JobTrigger(kind="calendar", calendar=f"ics:{ics}",
                    reminder_offset_minutes=30)
    nr = next_run(tr, "Asia/Kolkata", BASE)
    assert nr.astimezone(TZ) == datetime(2026, 10, 6, 12, 30, tzinfo=TZ)  # 13:00 IST - 30m
    # after 12:30 -> next is the UTC event (16:00Z = 21:30 IST) - 30m
    nr2 = next_run(tr, "Asia/Kolkata", BASE + timedelta(hours=1))
    assert nr2.astimezone(TZ) == datetime(2026, 10, 6, 21, 0, tzinfo=TZ)
    # no offset -> exact event times
    tr0 = JobTrigger(kind="calendar", calendar=f"ics:{ics}")
    assert next_run(tr0, "Asia/Kolkata", BASE).astimezone(TZ).hour == 13
    # unsupported source kind is a clean non-claim
    assert next_run(JobTrigger(kind="calendar", calendar="exchange:"),
                    "Asia/Kolkata", BASE) is None


def test_ics_parse_missing_and_malformed(tmp_path):
    assert parse_ics(str(tmp_path / "nope.ics")) == []
    bad = tmp_path / "bad.ics"
    bad.write_text("garbage\r\n:missing:colon\r\nBEGIN:VEVENT\r\nDTSTART:20261006T100000\r\nEND:VEVENT\r\n",
                   encoding="utf-8")
    evs = parse_ics(str(bad))
    assert len(evs) == 1 and evs[0]["dt"].hour == 10


# ============================================================ persistence
def test_job_roundtrip_and_history_dedupe(tmp_path):
    job = Job(owner="main", description="durable",
              action={"type": "agent_task", "task": "t"},
              trigger=JobTrigger(kind="weekly", time="09:00", days=[1, 3]),
              timezone="Asia/Kolkata", enabled=True,
              permissions={"guard_mode": "unattended", "preapproved_capabilities": ["files.write"]},
              retry_policy={"max_attempts": 3, "backoff_seconds": 30},
              max_runtime=120.0, next_run="2026-10-07T09:00:00+05:30",
              last_run="2026-10-06T09:00:00+05:30", state="pending", attempts=2)
    store = JobStore(tmp_path / "aut")
    store.save_job(job)
    j2 = store.load_job(job.id)
    assert j2.to_dict() == job.to_dict()
    assert j2.trigger.days == [1, 3] and j2.permissions["preapproved_capabilities"] == ["files.write"]

    ex1 = JobExecution(job_id=job.id, attempt=1, status="running")
    ex2 = JobExecution(job_id=job.id, attempt=2, status="running")
    store.append_execution(ex1)
    store.append_execution(ex2)
    # crash-repair style terminal row for ex1 (same id, later status)
    ex1t = JobExecution(id=ex1.id, job_id=job.id, attempt=1, status="interrupted")
    store.append_execution(ex1t)
    hist = store.executions()
    by_status = {e.id: e.status for e in hist.entries}
    assert by_status[ex1.id] == "interrupted"     # last row per id wins
    assert by_status[ex2.id] == "running"
    assert hist.count(job.id, "interrupted") == 1
    assert len(hist.entries) == 2                 # deduped by execution id


def test_store_cross_process_claims(tmp_path):
    store = JobStore(tmp_path / "aut")
    assert store.try_claim("job_x", ttl_seconds=600) is True
    # second "process" (same dir) is blocked while the claim is live
    store2 = JobStore(tmp_path / "aut")
    assert store2.try_claim("job_x", ttl_seconds=600) is False
    # but a different job is claimable
    assert store2.try_claim("job_y", ttl_seconds=600) is True
    store.release_claim("job_x")
    assert store2.try_claim("job_x", ttl_seconds=600) is True
    # stale claim (crash) is taken over after TTL
    p = store2._claim_path("job_y")
    old = time.time() - 700
    os.utime(p, (old, old))
    assert store.try_claim("job_y", ttl_seconds=600) is True
    # housekeeping: stale claims are swept, fresh ones kept
    os.utime(store._claim_path("job_x"), (old, old))
    assert store.clear_stale_claims(600) == 1


# ============================================================ worker: one-time
def test_one_time_lifecycle_and_restart_never_reruns(tmp_path):
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(), "ok")
    w = make_worker(tmp_path, kernel, clock)
    job = w.create_job(due_one_time(desc="once"))
    assert job.next_run  # catch-up: created 1s past its due instant
    started = w.tick()
    assert started == [job.id]
    assert w.wait_idle(5)
    j = w.store.load_job(job.id)
    assert j.state == "completed" and j.attempts == 1
    execs = w.store.executions().entries
    assert len(execs) == 1 and execs[0].status == "succeeded" and execs[0].task_id
    assert kernel.calls == [(job.action["task"], "main")]
    assert "success" in notif_kinds(w.store)

    # RESTART (same store): the finished job must not run again
    clock2 = FakeClock(BASE + timedelta(hours=2))
    w2 = make_worker(tmp_path, FakeKernel(Ctx(), "ok"), clock2, store_dir=tmp_path / "automation")
    report = w2.restore()
    assert report["restored"] == 1 and report["catchup"] == 0
    assert w2.tick() == []
    assert w2.store.executions().entries == execs     # identical history


# ============================================================ worker: crash repair
def _force_running(store, job_id, attempt, max_attempts=2):
    job = store.load_job(job_id)
    job.state = "running"
    # 2026-10-08 scheduling unification: agent_task jobs are NOT retried
    # blindly by default (side-effecting work). These tests verify the
    # crash-repair/REQUEUE MECHANISM, so they opt in explicitly.
    job.retry_policy = {"max_attempts": max_attempts, "backoff_seconds": 60,
                        "retry_agent_task": True}
    store.save_job(job)
    store.append_execution(JobExecution(job_id=job_id, attempt=attempt,
                                        status="running"))


def test_crash_repair_requeues_within_budget(tmp_path):
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(), "ok")
    w = make_worker(tmp_path, kernel, clock)
    job = w.create_job(due_one_time(desc="flaky"))
    # simulate a crash mid-run: job RUNNING with an open attempt-1 row
    _force_running(w.store, job.id, attempt=1, max_attempts=2)
    w2 = make_worker(tmp_path, kernel, FakeClock(BASE + timedelta(minutes=1)),
                     store_dir=tmp_path / "automation")
    report = w2.restore()
    assert report["repaired_running"] == 1
    j = w2.store.load_job(job.id)
    assert j.state == "pending" and j.next_run  # re-queued per budget
    assert w2.tick() and w2.wait_idle(5)
    hist = w2.store.executions()
    assert hist.count(job.id, "interrupted") == 1
    assert hist.count(job.id, "succeeded") == 1
    assert w2.store.load_job(job.id).state == "completed"


def test_crash_repair_exhausted_budget_fails(tmp_path):
    clock = FakeClock(BASE)
    w = make_worker(tmp_path, FakeKernel(Ctx(), "ok"), clock)
    job = w.create_job(due_one_time(desc="doomed"))
    _force_running(w.store, job.id, attempt=2, max_attempts=2)   # budget spent
    w2 = make_worker(tmp_path, FakeKernel(Ctx(), "ok"), FakeClock(BASE + timedelta(minutes=1)),
                     store_dir=tmp_path / "automation")
    w2.restore()
    j = w2.store.load_job(job.id)
    assert j.state == "failed" and j.next_run == ""
    assert w2.tick() == []
    assert "failure" in notif_kinds(w2.store)


# ============================================================ worker: missed
def test_one_time_missed_grace_catchup(tmp_path):
    w = make_worker(tmp_path, FakeKernel(Ctx(), "ok"), FakeClock(BASE))
    job = w.create_job(due_one_time(desc="graceful", at=BASE.isoformat()))
    # restart 10 minutes after the due instant (grace = 15 min)
    w2 = make_worker(tmp_path, FakeKernel(Ctx(), "ok"),
                     FakeClock(BASE + timedelta(minutes=10)),
                     store_dir=tmp_path / "automation", miss_grace=900)
    report = w2.restore()
    assert report["catchup"] == 1
    assert w2.tick() and w2.wait_idle(5)
    assert w2.store.load_job(job.id).state == "completed"
    # and exactly once
    assert len(w2.store.executions().entries) == 1


def test_one_time_missed_beyond_grace(tmp_path):
    w = make_worker(tmp_path, FakeKernel(Ctx(), "ok"), FakeClock(BASE))
    job = w.create_job(due_one_time(desc="too late", at=BASE.isoformat()))
    w2 = make_worker(tmp_path, FakeKernel(Ctx(), "ok"),
                     FakeClock(BASE + timedelta(minutes=30)),
                     store_dir=tmp_path / "automation", miss_grace=900)
    report = w2.restore()
    assert report["missed"] == 1
    j = w2.store.load_job(job.id)
    assert j.state == "missed" and j.next_run == ""
    assert w2.tick() == []
    assert "missed" in notif_kinds(w2.store)


def test_recurring_miss_skips_and_notifies(tmp_path):
    clock = FakeClock(BASE)
    w = make_worker(tmp_path, FakeKernel(Ctx(), "ok"), clock)
    job = Job(owner="main", description="daily digest",
              action={"type": "notify", "message": "daily"},
              trigger=JobTrigger(kind="daily", time="12:30"), timezone="Asia/Kolkata")
    # pretend it last fired today 12:30 and next_run was persisted today
    job.next_run = BASE.replace(hour=12, minute=30).isoformat()
    job.state = "pending"
    w.store.save_job(job)
    # restart THREE days later (missed: day 7 12:30 and day 8 12:30 —
    # day 9's 12:30 is still in the future at restore time day 9 12:00)
    w2 = make_worker(tmp_path, FakeKernel(Ctx(), "ok"),
                     FakeClock(BASE + timedelta(days=3)),
                     store_dir=tmp_path / "automation")
    report = w2.restore()
    assert report["skipped_recurring"] == 2
    j = w2.store.load_job(job.id)
    assert j.state == "pending"
    # stored UTC-canonical (2026-10-08); compare the INSTANT in the job tz
    nxt = datetime.fromisoformat(j.next_run)
    local = nxt.astimezone(TZ)
    assert local.day == 9 and local.hour == 12 and local.minute == 30  # next future
    assert w2.tick() == []              # nothing backfilled
    assert "missed" in notif_kinds(w2.store)


# ============================================================ worker: retry
def test_retry_backoff_then_success(tmp_path):
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(), "fail_once")
    w = make_worker(tmp_path, kernel, clock)
    job = w.create_job(due_one_time(desc="retry me"))
    # agent_task retries are opt-in since 2026-10-08 (no blind retry of
    # side-effecting work); this test verifies the backoff MECHANISM, so it
    # opts in explicitly.
    job.retry_policy = {"max_attempts": 2, "backoff_seconds": 60,
                        "retry_agent_task": True}
    w.store.save_job(job)
    w.tick(); assert w.wait_idle(5)
    j = w.store.load_job(job.id)
    assert j.state == "pending" and j.attempts == 1
    from bee.automation.models import parse_dt
    assert parse_dt(j.next_run) == BASE + timedelta(seconds=60)  # backoff (UTC-stored)
    assert any("retrying" in n.message for n in w.store.load_notifications()
               if n.kind == "failure")
    # advance past the backoff -> attempt 2 succeeds
    clock.advance(seconds=61)
    assert w.tick() and w.wait_idle(5)
    j2 = w.store.load_job(job.id)
    assert j2.state == "completed" and j2.attempts == 2
    assert w.store.executions().count(job.id, "failed") == 1
    assert w.store.executions().count(job.id, "succeeded") == 1


def test_failure_terminal_and_notification(tmp_path):
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(), "fail")
    w = make_worker(tmp_path, kernel, clock)
    job = w.create_job(due_one_time(desc="always fails"))
    job.retry_policy = {"max_attempts": 1, "backoff_seconds": 60}
    w.store.save_job(job)
    w.tick(); assert w.wait_idle(5)
    j = w.store.load_job(job.id)
    assert j.state == "failed" and j.next_run == ""
    fails = [n for n in w.store.load_notifications() if n.kind == "failure"]
    assert fails and "boom" in fails[-1].message
    # a recurring job that fails does NOT wedge its schedule
    w2j = Job(owner="main", description="daily frag",
              action={"type": "agent_task", "task": "frag"},
              trigger=JobTrigger(kind="daily", time="23:00"), timezone="Asia/Kolkata",
              retry_policy={"max_attempts": 1, "backoff_seconds": 60})
    w.create_job(w2j)
    clock2 = FakeClock(datetime(2026, 10, 6, 23, 5, 0, tzinfo=TZ))
    w3 = make_worker(tmp_path, kernel, clock2, store_dir=tmp_path / "automation")
    assert w3.tick() and w3.wait_idle(5)
    j3 = w3.store.load_job(w2j.id)
    assert j3.state == "pending" and j3.next_run            # tomorrow's occurrence kept


# ============================================================ worker: control
def test_disable_enable_cancel_delete(tmp_path):
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(), "ok")
    w = make_worker(tmp_path, kernel, clock)
    future = BASE + timedelta(hours=1)
    job = Job(owner="main", description="toggle me",
              action={"type": "agent_task", "task": "toggle task"},
              trigger=JobTrigger(kind="one_time", at=future.isoformat()),
              timezone="Asia/Kolkata")
    from bee.automation.models import parse_dt
    w.create_job(job)
    # next_run is stored UTC-canonical — compare instants, not tz-local strings
    assert parse_dt(job.next_run) == future

    assert w.disable_job(job.id)
    clock.advance(minutes=59)
    assert w.tick() == [] and kernel.calls == []            # disabled: no run
    assert w.enable_job(job.id)
    j = w.store.load_job(job.id)
    assert j.state == "pending" and parse_dt(j.next_run) == future
    clock.advance(minutes=1)                                # reach the due instant
    assert w.tick() and w.wait_idle(5)                      # now it runs
    assert kernel.calls == [("toggle task", "main")]

    job2 = Job(owner="main", description="cancel me",
               action={"type": "agent_task", "task": "never"},
               trigger=JobTrigger(kind="one_time",
                                  at=(BASE + timedelta(hours=2)).isoformat()),
               timezone="Asia/Kolkata")
    w.create_job(job2)
    assert w.cancel_job(job2.id)
    j2 = w.store.load_job(job2.id)
    assert j2.state == "cancelled" and not j2.enabled
    clock.advance(minutes=60)
    assert w.tick() == []                                   # cancelled: no run
    assert any(n.kind == "job_event" and "cancelled" in n.message
               for n in w.store.load_notifications())
    assert w.delete_job(job2.id)
    assert w.store.load_job(job2.id) is None
    assert w.disable_job("nope") is False


# ============================================================ worker: concurrency
def test_concurrency_cap_and_single_flight(tmp_path):
    peak = {"cur": 0, "max": 0}
    lk = threading.Lock()

    def slow(ctx):
        with lk:
            peak["cur"] += 1
            peak["max"] = max(peak["max"], peak["cur"])
        time.sleep(0.4)
        with lk:
            peak["cur"] -= 1
        return {"ok": True}

    old = wmod.FUNCTIONS.get("test.slow")
    wmod.FUNCTIONS["test.slow"] = slow
    try:
        # cap = 1: two due jobs, but at most one at a time
        clock = FakeClock(BASE)
        w = make_worker(tmp_path, FakeKernel(Ctx(), "ok"), clock, max_parallel=1)
        for d in ("job a", "job b"):
            j = Job(owner="main", description=d,
                    action={"type": "function", "fn": "test.slow"},
                    trigger=JobTrigger(kind="one_time",
                                       at=(BASE - timedelta(seconds=1)).isoformat()),
                    timezone="Asia/Kolkata")
            w.create_job(j)
        assert len(w.tick()) == 1          # cap: only ONE starts this pass
        assert w.wait_idle(10)
        assert len(w.tick()) == 1          # next pass takes the second
        assert w.wait_idle(10)
        assert peak["max"] == 1            # never two at once
        assert all(w.store.load_job(j.id).state == "completed" for j in w.jobs())

        # cap = 2: true parallelism
        peak.update(cur=0, max=0)
        tmp2 = tmp_path / "second"
        w2 = make_worker(tmp_path, FakeKernel(Ctx(), "ok"), FakeClock(BASE),
                         max_parallel=2, store_dir=tmp2)
        for d in ("job c", "job d"):
            j = Job(owner="main", description=d,
                    action={"type": "function", "fn": "test.slow"},
                    trigger=JobTrigger(kind="one_time",
                                       at=(BASE - timedelta(seconds=1)).isoformat()),
                    timezone="Asia/Kolkata")
            w2.create_job(j)
        w2.tick()
        assert w2.wait_idle(10)
        assert peak["max"] == 2

        # single-flight: a due job ticks while inflight must not start twice
        tmp3 = tmp_path / "third"
        w3 = make_worker(tmp_path, FakeKernel(Ctx(), "ok"), FakeClock(BASE), store_dir=tmp3)
        j3 = Job(owner="main", description="solo",
                 action={"type": "function", "fn": "test.slow"},
                 trigger=JobTrigger(kind="one_time",
                                    at=(BASE - timedelta(seconds=1)).isoformat()),
                 timezone="Asia/Kolkata")
        w3.create_job(j3)
        s1 = w3.tick()
        s2 = w3.tick()                       # still inflight
        assert s1 == [j3.id] and s2 == []
        assert w3.wait_idle(10)
        assert len(w3.store.executions().entries) == 1
    finally:
        if old is None:
            wmod.FUNCTIONS.pop("test.slow", None)
        else:
            wmod.FUNCTIONS["test.slow"] = old


# ============================================================ worker: max_runtime
def test_max_runtime_cancels_job_not_user_work(tmp_path):
    clock = FakeClock(BASE)
    ctx = Ctx()
    user_event = threading.Event()           # the user's live task cancel event
    ctx.cancel_event = user_event
    kernel = FakeKernel(ctx, "block_until_cancel")
    w = make_worker(tmp_path, kernel, clock)
    w.ctx = ctx
    job = w.create_job(due_one_time(desc="long job"))
    job.max_runtime = 0.4
    w.store.save_job(job)
    t0 = time.time()
    w.tick()
    assert w.wait_idle(15)
    assert time.time() - t0 < 10             # cancelled promptly, not abandoned
    hist = w.store.executions()
    row = hist.last(job.id, 1)[0]
    assert row.status == "timeout"
    assert any(n.kind == "failure" and "max_runtime" in n.message
               for n in w.store.load_notifications())
    assert not user_event.is_set()           # the USER's task was never cancelled
    assert ctx.cancel_event is user_event    # and the event was restored


# ============================================================ worker: functions
def test_function_job_real_registered_work_and_unknown_fails(tmp_path):
    from bee.automation import FUNCTIONS
    # the five nightly functions are registered as REAL scheduler work
    for fn in ("bee.scheduler.consolidate", "bee.scheduler.rebuild_vectors",
               "bee.scheduler.maybe_train_router", "bee.scheduler.maybe_teach_back",
               "bee.scheduler.maybe_build_sft"):
        assert fn in FUNCTIONS

    tmp_ws = tmp_path / "ws"
    tmp_ws.mkdir()
    target = tmp_path / "ws" / "proof.txt"

    old = wmod.FUNCTIONS.get("test.write_proof")
    def write_proof(ctx):
        target.write_text("nightly work actually ran", encoding="utf-8")
        return {"written": str(target.name)}
    wmod.FUNCTIONS["test.write_proof"] = write_proof
    try:
        w = make_worker(tmp_path, FakeKernel(Ctx(), "ok"), FakeClock(BASE))
        j1 = Job(owner="system", description="proof job",
                 action={"type": "function", "fn": "test.write_proof"},
                 trigger=JobTrigger(kind="one_time", at=BASE.isoformat()),
                 timezone="Asia/Kolkata")
        w.create_job(j1)
        assert w.tick() and w.wait_idle(5)
        assert target.exists()               # real effect on disk
        row = w.store.executions().last(j1.id, 1)[0]
        assert row.status == "succeeded" and "proof.txt" in row.output_preview

        j2 = Job(owner="system", description="ghost fn",
                 action={"type": "function", "fn": "not.a.real.function"},
                 trigger=JobTrigger(kind="one_time", at=BASE.isoformat()),
                 timezone="Asia/Kolkata")
        w.create_job(j2)
        assert w.tick() and w.wait_idle(5)
        row2 = w.store.executions().last(j2.id, 1)[0]
        assert row2.status == "failed" and "unknown registered function" in row2.error
    finally:
        if old is None:
            wmod.FUNCTIONS.pop("test.write_proof", None)


# ============================================================ proactive
def test_proactive_default_deny_without_rules(tmp_path):
    kernel = FakeKernel(Ctx(), "ok")
    w = make_worker(tmp_path, kernel, FakeClock(BASE))
    w.restore()
    base_notifs = len(w.store.load_notifications())
    for kind in ("timer", "calendar", "email", "file_change", "app_event",
                 "battery", "network", "device_state"):
        w.bus.publish(BusEvent(name="x", kind=kind, payload={}))
    assert len(w.store.load_notifications()) == base_notifs
    assert kernel.calls == []                # no LLM, no action at all


def test_proactive_authorized_rule_fires_and_rate_limits(tmp_path):
    kernel = FakeKernel(Ctx(), "ok")
    w = make_worker(tmp_path, kernel, FakeClock(BASE))
    w.restore()
    rule = ProactiveRule(kind="app_event", match={"app": "downloader"},
                         action={"type": "notify", "message": "download finished"},
                         description="open folder when download finishes",
                         max_per_hour=2, created_by="user")
    w.policy.add_rule(rule)
    w.bus.publish(BusEvent(name="download.finished", kind="app_event",
                           payload={"app": "downloader"}))
    proactive = [n for n in w.store.load_notifications() if n.kind == "proactive"]
    assert len(proactive) == 1 and "download finished" in proactive[0].message
    # rate limit: 2 more identical events -> NO more than the cap
    w.bus.publish(BusEvent(name="download.finished", kind="app_event",
                           payload={"app": "downloader"}))
    w.bus.publish(BusEvent(name="download.finished", kind="app_event",
                           payload={"app": "downloader"}))
    proactive = [n for n in w.store.load_notifications() if n.kind == "proactive"]
    assert len(proactive) == 2
    # non-matching payload does not fire the rule
    w.bus.publish(BusEvent(name="download.finished", kind="app_event",
                           payload={"app": "browser"}))
    assert len([n for n in w.store.load_notifications() if n.kind == "proactive"]) == 2


def test_proactive_agent_task_and_rule_restart(tmp_path):
    kernel = FakeKernel(Ctx(), "ok")
    w = make_worker(tmp_path, kernel, FakeClock(BASE))
    w.restore()
    rule = ProactiveRule(kind="file_change",
                         action={"type": "agent_task",
                                 "task": "Summarize the file that just changed."},
                         created_by="user")
    w.policy.add_rule(rule)
    w.store.save_rules(w.policy.rules)
    w.bus.publish(BusEvent(name="file.changed", kind="file_change",
                           payload={"path": "reports/q3.xlsx"}))
    assert kernel.calls == [("Summarize the file that just changed.", "proactive")]

    # RESTART: rules are user-authorized and must come back from the store
    w2 = make_worker(tmp_path, FakeKernel(Ctx(), "ok"), FakeClock(BASE),
                     store_dir=tmp_path / "automation")
    w2.restore()
    assert [r.id for r in w2.policy.rules] == [rule.id]
    assert w2.policy.rules[0].created_by == "user"


# ============================================================ calendar live
def test_calendar_job_picks_up_new_ics_event(tmp_path):
    ics = tmp_path / "meet.ics"
    ics.write_text("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n"
                   f"DTSTART:{(BASE + timedelta(minutes=40)).strftime('%Y%m%dT%H%M%S')}"
                   "\r\nSUMMARY:1:1\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n", encoding="utf-8")
    w = make_worker(tmp_path, FakeKernel(Ctx(), "ok"), FakeClock(BASE))
    job = Job(owner="main", description="meeting reminder",
              action={"type": "notify", "message": "meeting in 30"},
              trigger=JobTrigger(kind="calendar", calendar=f"ics:{ics}",
                                 reminder_offset_minutes=30),
              timezone="Asia/Kolkata")
    w.create_job(job)
    # the reminder is due 30 min before the meeting = BASE + 10 min
    # (stored UTC-canonical — compare the instant)
    from bee.automation.models import parse_dt
    assert parse_dt(job.next_run) == BASE + timedelta(minutes=10)
    assert w.tick() == []                            # not due yet
    clock = FakeClock(BASE + timedelta(minutes=5))
    w2 = make_worker(tmp_path, FakeKernel(Ctx(), "ok"), clock,
                     store_dir=tmp_path / "automation")
    assert w2.tick() == []                           # still 5 min early
    clock.advance(minutes=6)                         # now 30 min before
    assert w2.tick() and w2.wait_idle(5)
    assert w2.store.load_job(job.id).state == "completed"


# ============================================================ the SAME kernel
def _real_kernel(tmp_path, script, approver=None, client=None):
    from bee.agent.context import Context
    from bee.config import load_config
    from bee.kernel import AgentKernel
    from tests.test_kernel_integration import ScriptedClient, tc
    cfg = load_config()
    cfg.cloud.enabled = False
    cfg.workspace = tmp_path
    client = client or ScriptedClient(script)
    ctx = Context(cfg, workspace=tmp_path, client=client,
                  guard_on=True, guard_mode="unattended",
                  episodes_on=False, rag_on=False,
                  cancel_event=threading.Event())
    k = AgentKernel(ctx, approver=approver if approver is not None
                    else (lambda t, a, r: False),
                    sessions_dir=tmp_path / "sessions",
                    receipts_path=tmp_path / "receipts.jsonl")
    ctx.kernel = k
    return k, ctx, client


def test_agent_task_runs_through_real_kernel(tmp_path):
    """scheduled job -> AgentSession -> Task -> ... -> Receipt -> notification"""
    k, ctx, _ = _real_kernel(tmp_path,
                             ["I checked the calendar; you have two meetings today."])
    w = make_worker(tmp_path, k, FakeClock(BASE), ctx=ctx)
    job = w.create_job(due_one_time(desc="morning briefing", task="Check my calendar today.",
                                    owner="briefing"))
    assert w.tick() and w.wait_idle(10)
    j = w.store.load_job(job.id)
    assert j.state == "completed"
    row = w.store.executions().last(job.id, 1)[0]
    assert row.status == "succeeded" and row.task_id
    # the kernel really ran it: session persisted under the JOB's owner...
    sess = tmp_path / "sessions" / "briefing.json"
    assert sess.exists()
    assert "calendar" in sess.read_text(encoding="utf-8")
    # ...and receipts were written through the same ReceiptLog
    receipts = (tmp_path / "receipts.jsonl").read_text(encoding="utf-8")
    assert '"tool": "agent"' in receipts or '"tool":"agent"' in receipts
    assert "briefing" in receipts
    # and the success notification landed
    assert any(n.kind == "success" for n in w.store.load_notifications())


def test_automation_tool_gates_on_explicit_authorization(tmp_path):
    """'create a job' through the LLM requires the automation.manage grant."""
    from tests.test_kernel_integration import tc
    asks: list[tuple] = []
    future = (BASE + timedelta(hours=1)).isoformat()

    def approver(tool, args, reason):
        asks.append((tool, reason))
        return tool == "capability:automation.manage"   # user authorizes this

    k, ctx, _ = _real_kernel(tmp_path,
                             [tc("c1", "automation_job",
                                 {"op": "create", "kind": "one_time", "at": future,
                                  "task": "evening review"}),
                              "Scheduled. I will run the evening review tomorrow."],
                             approver=approver)
    w = make_worker(tmp_path, k, FakeClock(BASE), ctx=ctx)
    r = k.run("Create a one-time job called evening review for later today.",
              session_id="repl")
    assert r.ok is True
    assert any(t == "capability:automation.manage" for t, _ in asks)
    jobs = w.jobs()
    assert len(jobs) == 1 and jobs[0].action == {"type": "agent_task",
                                                  "task": "evening review"}
    assert jobs[0].state == "pending" and jobs[0].next_run
    # denied variant: the gate fails closed, no job is created
    k2, ctx2, _ = _real_kernel(
        tmp_path,
        [tc("c1", "automation_job",
            {"op": "create", "kind": "one_time", "at": future, "task": "nope"}),
         "I could not create that job."],
        approver=lambda t, a, r: False)
    w2 = make_worker(tmp_path, k2, FakeClock(BASE), store_dir=tmp_path / "aut2",
                     ctx=ctx2)
    k2.run("Create a one-time job that must be denied.", session_id="repl")
    assert w2.jobs() == []


def test_job_run_fails_closed_on_capability_asks(tmp_path):
    """Inside a scheduled run, an ASK capability is DENIED (unattended,
    fail closed) even though the same tool would be asked in interactive use."""
    from tests.test_kernel_integration import tc
    future = (BASE + timedelta(hours=1)).isoformat()
    k, ctx, _ = _real_kernel(tmp_path,
                             [tc("c1", "automation_job",
                                 {"op": "create", "kind": "one_time", "at": future,
                                  "task": "sneaky"}),
                              "The automation could not be created."])
    w = make_worker(tmp_path, k, FakeClock(BASE), ctx=ctx)
    job = w.create_job(due_one_time(desc="job that tries to self-replicate",
                                    task="Create another job using automation tools."))
    job.permissions = {"guard_mode": "unattended", "preapproved_capabilities": []}
    w.store.save_job(job)
    assert w.tick() and w.wait_idle(10)
    assert [j.id for j in w.jobs()] == [job.id]    # no second job was created
    denied = [e for e in k.events.log
              if e.kind.value == "permission_denied"
              and e.data.get("capability") == "automation.manage"]
    assert denied, "the capability gate must have DENIED automation.manage in-job"
