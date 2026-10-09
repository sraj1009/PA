"""Scheduling unification (2026-10-08) — ONE architecture, no no-op.

Pins the program requirements:
  * timestamps stored CANONICALLY IN UTC; the user tz stored separately and
    used for scheduling/display (never host-local persistence);
  * the legacy `_noop` APScheduler restoration is GONE — the `scheduler`
    tool is now an ADAPTER that creates real durable jobs;
  * `memory.temporal.schedule` creates a real job (no diary-only no-op) when
    automation is running;
  * agent_task jobs are NOT blindly retried (side-effecting work); function
    jobs keep their retry budget;
  * restart recovery / duplicate prevention / failure notification /
    cancellation / permission denial / real side-effect — all verified
    against the durable store.

Run:  python -m pytest tests/test_scheduling_unified.py -q
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from bee.automation import (Job, JobStore, JobTrigger, JobWorker, EventBus,
                            parse_dt)
from bee.automation import worker as wmod
from bee.automation.models import display_local
from bee.automation.worker import effective_max_attempts

TZ = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc
BASE = datetime(2026, 10, 8, 12, 0, 0, tzinfo=TZ)


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
    def __init__(self, ctx, behavior="ok", side_effect=None):
        self.ctx = ctx
        self.behavior = behavior
        self.calls = []
        self.side_effect = side_effect      # fn(text) -> side-effect marker
        self.approver = lambda tool, args, reason: False

    def run(self, text, session_id="repl", **kw):
        self.calls.append((text, session_id))
        if self.side_effect:
            self.side_effect(text)
        if self.behavior == "fail":
            return FakeResult(ok=False, error="boom (scripted failure)")
        if self.behavior == "denied":
            return FakeResult(ok=False, error="capability denied (unattended)")
        return FakeResult()

    def cancel(self):
        ev = getattr(self.ctx, "cancel_event", None)
        if ev is not None and hasattr(ev, "set"):
            ev.set()


class Ctx:
    def __init__(self, workspace):
        self.cancel_event = threading.Event()
        self.workspace = workspace
        self.cfg = None
        self.automation_worker = None


class FakeClock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now = self.now + timedelta(**kw)


def make_worker(tmp_path, kernel, clock, store_dir=None, ctx=None):
    store = JobStore(store_dir or (tmp_path / "automation"))
    ctx = ctx or Ctx(tmp_path)
    w = JobWorker(ctx, kernel, store, bus=EventBus(), clock=clock,
                  max_parallel=2, miss_grace_seconds=900, tick_seconds=5.0)
    ctx.automation_worker = w
    return w


def due_one_time(task="the task", at=None, owner="main"):
    at = at or (BASE - timedelta(seconds=1)).isoformat()
    return Job(owner=owner, description="due job",
               action={"type": "agent_task", "task": task},
               trigger=JobTrigger(kind="one_time", at=at),
               timezone="Asia/Kolkata")


# ========================================================== UTC-canonical
def test_persisted_timestamps_are_utc(tmp_path):
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(tmp_path))
    w = make_worker(tmp_path, kernel, clock)
    job = due_one_time()
    w.create_job(job)
    stored = w.store.load_job(job.id)
    assert stored.next_run.endswith("+00:00"), \
        f"next_run must be stored UTC-canonical, got {stored.next_run}"
    # execution rows + created_at too
    started = w.tick()
    assert started
    w.wait_idle(5)
    ex = w.store.executions().for_job(job.id)[-1]
    assert ex.started_at.endswith("+00:00") and ex.finished_at.endswith("+00:00")
    assert stored.created_at.endswith("+00:00")


def test_timezone_conversion_stored_utc_displayed_local(tmp_path):
    # user says "09:00" in Asia/Kolkata -> the INSTANT is 03:30 UTC
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(tmp_path))
    w = make_worker(tmp_path, kernel, clock)
    job = Job(owner="main", description="morning brief",
              action={"type": "agent_task", "task": "brief me"},
              trigger=JobTrigger(kind="daily", time="09:00"),
              timezone="Asia/Kolkata")
    w.create_job(job)
    stored = w.store.load_job(job.id)
    dt = parse_dt(stored.next_run)
    assert dt.astimezone(UTC).hour == 3 and dt.astimezone(UTC).minute == 30
    # display uses the USER's timezone
    shown = display_local(stored.next_run, stored.timezone)
    assert "09:00" in shown and "Asia/Kolkata" in shown
    # same instant, another user tz -> correct wall clock.
    # 09:00 IST (UTC+5:30) == 03:30 UTC == 12:30 JST (UTC+9)
    shown_tokyo = display_local(stored.next_run, "Asia/Tokyo")
    assert "12:30" in shown_tokyo and "Asia/Tokyo" in shown_tokyo
    shown_utc = display_local(stored.next_run, "UTC")
    assert "03:30" in shown_utc


def test_one_time_naive_at_is_job_tz_then_utc(tmp_path):
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(tmp_path))
    w = make_worker(tmp_path, kernel, clock)
    job = Job(owner="main", description="tomorrow 18:00 IST",
              action={"type": "notify", "message": "hi"},
              trigger=JobTrigger(kind="one_time", at="2026-10-09T18:00"),
              timezone="Asia/Kolkata")
    w.create_job(job)
    stored = w.store.load_job(job.id)
    dt = parse_dt(stored.next_run)
    assert dt.astimezone(UTC) == datetime(2026, 10, 9, 12, 30, tzinfo=UTC)
    assert display_local(stored.next_run, "Asia/Kolkata").startswith(
        "2026-10-09 18:00")


def test_utc_storage_is_host_tz_independent(tmp_path, monkeypatch):
    """The same wall-clock trigger stored from two different HOST timezones
    must yield the same persisted instant."""
    results = []
    for host_tz in ("UTC", "America/New_York"):
        # (documented: the stored instant must not depend on the host tz;
        #  Python reads TZ at process start, so this also pins determinism
        #  of the fixed-clock path)
        monkeypatch.setenv("TZ", host_tz)
        clock = FakeClock(datetime(2026, 10, 8, 12, 0, tzinfo=TZ))
        kernel = FakeKernel(Ctx(tmp_path))
        w = make_worker(tmp_path, kernel, clock,
                        store_dir=tmp_path / f"auto_{host_tz.replace('/', '_')}")
        job = Job(owner="main", description="tz test",
                  action={"type": "notify", "message": "x"},
                  trigger=JobTrigger(kind="daily", time="09:00"),
                  timezone="Asia/Kolkata")
        w.create_job(job)
        results.append(w.store.load_job(job.id).next_run)
    assert results[0] == results[1], \
        f"persistence depends on host tz: {results}"


# ======================================================= no-blind agent retry
def test_agent_task_not_blindly_retried(tmp_path):
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(tmp_path), behavior="fail")
    w = make_worker(tmp_path, kernel, clock)
    job = due_one_time(task="send the invoice to the client")
    job.retry_policy = {"max_attempts": 5, "backoff_seconds": 10}
    w.create_job(job)
    w.tick()
    w.wait_idle(5)
    stored = w.store.load_job(job.id)
    # side-effecting LLM work: ONE attempt, then FAILED — never a blind replay
    assert stored.state == "failed"
    assert stored.attempts == 1
    assert len(w.store.executions().for_job(job.id)) == 1
    assert kernel.calls.count(("send the invoice to the client", "main")) == 1


def test_agent_task_retry_is_explicit_opt_in(tmp_path):
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(tmp_path), behavior="fail")
    w = make_worker(tmp_path, kernel, clock)
    job = due_one_time(task="idempotent thing")
    job.retry_policy = {"max_attempts": 2, "backoff_seconds": 10,
                        "retry_agent_task": True}
    assert effective_max_attempts(job) == 2
    w.create_job(job)
    w.tick()
    w.wait_idle(5)
    # retried after backoff (budget 2)
    clock.advance(seconds=25)
    w.tick()
    w.wait_idle(5)
    assert w.store.load_job(job.id).state == "failed"
    assert len(kernel.calls) == 2


def test_function_jobs_keep_retry_budget(tmp_path):
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(tmp_path))
    w = make_worker(tmp_path, kernel, clock)
    job = Job(owner="system", description="flaky fn",
              action={"type": "function", "fn": "bee.scheduler._definitely_missing"},
              trigger=JobTrigger(kind="one_time",
                                 at=(BASE - timedelta(seconds=1)).isoformat()),
              timezone="UTC",
              retry_policy={"max_attempts": 2, "backoff_seconds": 10})
    w.create_job(job)
    w.tick()
    w.wait_idle(5)
    assert w.store.load_job(job.id).state == "pending"   # re-queued (attempt 1)
    clock.advance(seconds=25)
    w.tick()
    w.wait_idle(5)
    assert w.store.load_job(job.id).state == "failed"    # budget exhausted
    assert len(w.store.executions().for_job(job.id)) == 2


# ===================================================== restart + duplicate
def test_restart_recovery_with_utc_store(tmp_path):
    side = tmp_path / "side_effect.txt"
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(tmp_path),
                        side_effect=lambda t: side.write_text(t, encoding="utf-8"))
    w = make_worker(tmp_path, kernel, clock)
    job = due_one_time(task=f"touch {side.name}")
    w.create_job(job)
    w.tick()
    w.wait_idle(5)
    assert side.exists()                                # real side effect
    first_state = w.store.load_job(job.id).state
    assert first_state == "completed"

    # ---- RESTART: fresh worker, same store, later clock ----
    clock2 = FakeClock(BASE + timedelta(hours=2))
    kernel2 = FakeKernel(Ctx(tmp_path))
    w2 = make_worker(tmp_path, kernel2, clock2)
    report = w2.restore()
    assert report["restored"] >= 1
    again = w2.store.load_job(job.id)
    assert again.state == "completed" and again.next_run == ""
    w2.tick()
    w2.wait_idle(5)
    assert kernel2.calls == []                          # NEVER re-executed


def test_no_duplicate_execution_same_tick(tmp_path):
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(tmp_path))
    w = make_worker(tmp_path, kernel, clock)
    job = due_one_time()
    w.create_job(job)
    started = w.tick()
    assert started == [job.id]
    # tick again while still in-flight: single-flight per job
    started2 = w.tick()
    assert job.id not in started2
    w.wait_idle(5)
    assert len(w.store.executions().for_job(job.id)) == 1


# ======================================================= failure / cancel
def test_failure_notifies_and_job_failed(tmp_path):
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(tmp_path), behavior="fail")
    w = make_worker(tmp_path, kernel, clock)
    job = due_one_time()
    w.create_job(job)
    w.tick()
    w.wait_idle(5)
    kinds = [n.kind for n in w.store.load_notifications()]
    assert "failure" in kinds
    assert w.store.load_job(job.id).state == "failed"


def test_permission_denial_records_failure_without_side_effect(tmp_path):
    side = tmp_path / "should_not_exist.txt"
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(tmp_path), behavior="denied",
                        side_effect=lambda t: None)   # nothing executed
    w = make_worker(tmp_path, kernel, clock)
    job = due_one_time(task="delete the backups")
    w.create_job(job)
    w.tick()
    w.wait_idle(5)
    assert not side.exists()
    assert w.store.load_job(job.id).state == "failed"
    ex = w.store.executions().for_job(job.id)[-1]
    assert "denied" in ex.error
    kinds = [n.kind for n in w.store.load_notifications()]
    assert "failure" in kinds


def test_cancellation_prevents_execution(tmp_path):
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(tmp_path))
    w = make_worker(tmp_path, kernel, clock)
    job = due_one_time(at=(BASE + timedelta(minutes=30)).isoformat())
    w.create_job(job)
    assert w.cancel_job(job.id)
    stored = w.store.load_job(job.id)
    assert stored.state == "cancelled" and stored.next_run == ""
    # time passes — a cancelled job must never fire
    clock.advance(hours=3)
    assert w.tick() == []
    assert kernel.calls == []


# ================================================== legacy tool is an adapter
def test_scheduler_tool_is_a_real_adapter(tmp_path):
    from bee.tools.scheduler_tool import scheduler_tools, _cron_to_trigger
    tools = {t.name: t.handler for t in scheduler_tools()}
    assert "scheduler" in tools

    # cron -> trigger subset
    tr, _ = _cron_to_trigger("30 8 * * *")
    assert tr.kind == "daily" and tr.time == "08:30"
    tr, _ = _cron_to_trigger("30 8 * * 1-5")
    assert tr.kind == "weekly" and tr.days == [0, 1, 2, 3, 4]
    tr, _ = _cron_to_trigger("15 * * * *")
    assert tr.kind == "interval" and tr.every_seconds == 3600
    tr, _ = _cron_to_trigger("*/5 * * * *")
    assert tr.kind == "interval" and tr.every_seconds == 300
    with pytest.raises(ValueError):
        _cron_to_trigger("0 0 1 * *")          # monthly unsupported -> honest error
    with pytest.raises(ValueError):
        _cron_to_trigger("bad")

    # add -> REAL durable job in the store (restart-surviving, kernel-runnable)
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(tmp_path))
    ctx = Ctx(tmp_path)
    w = make_worker(tmp_path, kernel, clock, ctx=ctx)
    r = tools["scheduler"](ctx, action="add", cron="0 9 * * *",
                           note="morning briefing")
    assert r["ok"] and r["durable"] is True
    stored = w.store.load_job(r["job"])
    assert stored is not None
    assert stored.action["type"] == "agent_task"
    assert stored.next_run.endswith("+00:00")
    # it actually EXECUTES real work when due
    clock2 = FakeClock(datetime(2026, 10, 9, 9, 0, 0, tzinfo=TZ) + timedelta(seconds=1))
    clock.now = clock2.now
    started = w.tick()
    assert r["job"] in started
    w.wait_idle(5)
    assert any(t == "morning briefing" for t, _ in kernel.calls)

    # list reflects the durable store; remove cancels it
    lst = tools["scheduler"](ctx, action="list")
    assert any(j["id"] == r["job"] for j in lst["jobs"])
    assert tools["scheduler"](ctx, action="remove", cron=r["job"])["ok"]
    assert w.store.load_job(r["job"]).state == "cancelled"

    # honest failure when automation is not running (never a silent no-op)
    ctx2 = Ctx(tmp_path)
    r2 = tools["scheduler"](ctx2, action="add", cron="0 9 * * *", note="x")
    assert "error" in r2 and "no jobs were created" in r2["error"].lower()


def test_noop_backend_is_gone(tmp_path):
    import inspect
    from bee.tools import scheduler_tool
    src = inspect.getsource(scheduler_tool)
    # the legacy no-op function and backend are gone (mentions in prose are
    # fine; a DEFINITION or an apscheduler/jobs.json reference is not)
    assert "def _noop" not in src
    assert "from apscheduler" not in src and "import apscheduler" not in src
    assert "jobs.json" not in src


def test_temporal_schedule_creates_real_job(tmp_path):
    from bee.kernel.memory_if import MemoryStack
    clock = FakeClock(BASE)
    kernel = FakeKernel(Ctx(tmp_path))
    ctx = Ctx(tmp_path)
    w = make_worker(tmp_path, kernel, clock, ctx=ctx)
    # diary writes to the REAL project — keep the test hermetic
    import bee.memory.md as md
    orig = md.diary_add
    md.diary_add = lambda s: None
    try:
        stack = MemoryStack(structured_path=tmp_path / "store.json",
                            worker_ref=lambda: ctx.automation_worker)
        r = stack.temporal.schedule("send the invoice", "17:30")
        assert r["ok"] and "job" in r, r
        stored = w.store.load_job(r["job"])
        assert stored is not None and stored.action["type"] == "agent_task"
        assert stored.next_run.endswith("+00:00")
        assert any(j["id"] == r["job"] for j in stack.temporal.list())
        # past time -> rejected honestly, no job. Derived from the WORKER'S clock
        # (the FakeClock below), which is the instant the code compares against;
        # the wall clock here made the test pass for the wrong reason.
        past = (clock.now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        r2 = stack.temporal.schedule("x", past)
        assert not r2["ok"] and "past" in r2["note"]
        # unparseable -> honest error
        r2b = stack.temporal.schedule("x", "whenever")
        assert not r2b["ok"]
    finally:
        md.diary_add = orig
    # without automation: honest no-job, diary note only
    ctx2 = Ctx(tmp_path)
    stack2 = MemoryStack(structured_path=tmp_path / "store2.json",
                         worker_ref=lambda: None)
    r3 = stack2.temporal.schedule("x", "17:30")
    assert not r3["ok"] and "no job created" in r3["note"]


def test_temporal_schedule_speaks_the_same_grammar_as_remind(tmp_path, monkeypatch):
    """The memory/planner surface and /remind must understand the same words and
    must decide 'today or tomorrow' from the SCHEDULER'S clock. Before this, a
    spoken 'tomorrow 9am' was rejected ('could not parse') and a bare '17:30'
    rolled over against datetime.now() — an instant the tick never uses."""
    from bee.kernel.memory_if import MemoryStack
    import bee.memory.md as md
    monkeypatch.setattr(md, "diary_add", lambda s: None)   # keep the test hermetic

    clock = FakeClock(BASE)                            # 2026-10-08 12:00 IST
    ctx = Ctx(tmp_path)
    w = make_worker(tmp_path, FakeKernel(Ctx(tmp_path)), clock, ctx=ctx)
    stack = MemoryStack(structured_path=tmp_path / "store.json",
                        worker_ref=lambda: ctx.automation_worker)

    r = stack.temporal.schedule("send the invoice", "tomorrow 9am")
    assert r["ok"], r
    assert w.store.load_job(r["job"]).next_run == "2026-10-09T03:30:00+00:00"

    r2 = stack.temporal.schedule("stretch", "in 20 min")
    assert r2["ok"], r2
    assert w.store.load_job(r2["job"]).next_run == "2026-10-08T06:50:00+00:00"

    # a bare clock time still means TODAY when it has not passed yet (12:00 IST)
    r3 = stack.temporal.schedule("call the dentist", "17:30")
    assert r3["ok"], r3
    assert w.store.load_job(r3["job"]).next_run == "2026-10-08T12:00:00+00:00"

    # unparseable stays an honest refusal — never a guessed date
    r4 = stack.temporal.schedule("x", "whenever")
    assert not r4["ok"] and "tomorrow 9am" in r4["note"]


def test_temporal_list_reports_upcoming_not_already_fired(tmp_path, monkeypatch):
    """A one_time job keeps enabled=True after it fires, so a naive listing tells
    the model a reminder the user already received is still coming up."""
    from bee.kernel.memory_if import MemoryStack
    import bee.memory.md as md
    monkeypatch.setattr(md, "diary_add", lambda s: None)

    clock = FakeClock(BASE)                            # 2026-10-08 12:00 IST
    ctx = Ctx(tmp_path)
    w = make_worker(tmp_path, FakeKernel(Ctx(tmp_path)), clock, ctx=ctx)
    stack = MemoryStack(structured_path=tmp_path / "store.json",
                        worker_ref=lambda: ctx.automation_worker)

    from bee.automation.models import Job, JobTrigger, PENDING
    w.create_job(Job(owner="reminder", description="Reminder: stretch",
                     action={"type": "notify", "message": "Reminder: stretch",
                             "critical": True},
                     trigger=JobTrigger(kind="one_time",
                                        at=(clock.now + timedelta(minutes=5)).isoformat()),
                     timezone="Asia/Kolkata", enabled=True, state=PENDING))
    assert len(stack.temporal.list()) == 1

    clock.advance(minutes=6)
    w.tick()
    assert w.wait_idle(5.0)
    j = w.jobs()[0]
    assert j.state == "completed" and j.enabled          # the store's truth
    assert stack.temporal.list() == []                   # but it is no longer 'upcoming'
