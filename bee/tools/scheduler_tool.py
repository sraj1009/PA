"""scheduler tool — ADAPTER over the durable automation system (2026-10-08).

Historically this tool backed its own APScheduler instance and restored
persisted jobs as `_noop` markers (a log line, no work) — exactly the
fake-execution behavior the scheduling unification removes. The legacy
backend is GONE. This file now keeps the OLD tool name and arguments
(`action` add|list|remove, `cron`, `note`) for backwards compatibility, but
every operation maps onto the ONE real scheduling architecture:

    user "schedule" -> adapter -> durable Job (bee/automation)
        -> JobWorker -> AgentKernel -> Task -> Permission -> Tools
        -> Verification -> Receipt -> Notification

* `add`    parses the cron expression (supported subset, below) into a
           JobTrigger and creates a REAL durable job (agent_task) that
           survives restarts and executes real work through the kernel.
* `list`   lists the durable jobs (id, description, trigger, next run,
           state) from the persisted store.
* `remove` cancels a durable job by id (persisted).

If automation is not running in this context the tool says so honestly —
it never falls back to a silent no-op.

Supported cron subset (5 fields):
  M H * * *        -> daily at H:MM
  M H * * D        -> weekly on day D (0/7=Sun..6=Sat), e.g. '30 8 * * 1-5'
  M H * * D1,D2    -> weekly on several days
  M * * * *        -> every hour at minute M   (interval 3600)
  */N * * * *      -> every N minutes           (interval N*60)
Anything else: the tool returns a precise error pointing at the
`automation_job` tool (full trigger control: one_time/daily/weekly/
interval/calendar, tz, retry, max_runtime).
"""
from __future__ import annotations

import re

from .base import T


def _cron_to_trigger(cron: str):
    """Return (JobTrigger, note) or raise ValueError with the reason."""
    from ..automation.models import JobTrigger
    parts = (cron or "").split()
    if len(parts) != 5:
        raise ValueError("expected a 5-field cron expression 'M H dom mon dow'")
    mi, hh, dom, mon, dow = parts
    if dom != "*" or mon != "*":
        raise ValueError("only daily/weekly/every-N-minute crons are supported "
                         "(dom/mon must be '*') — use the automation_job tool for "
                         "full control")
    # every-N-minute:  */N * * * *
    m = re.fullmatch(r"\*/(\d+)", mi)
    if m and hh == "*":
        n = int(m.group(1))
        if not (1 <= n <= 59):
            raise ValueError(f"bad interval */{n} (1..59)")
        return JobTrigger(kind="interval", every_seconds=n * 60), f"every {n} min"
    if hh == "*":
        if not mi.isdigit() or not (0 <= int(mi) <= 59):
            raise ValueError(f"bad minute {mi!r}")
        return JobTrigger(kind="interval", every_seconds=3600), f"every hour at :{int(mi):02d}"
    if not (mi.isdigit() and hh.isdigit()):
        raise ValueError(f"bad time '{mi} {hh}' (need integers)")
    mm, hh_i = int(mi), int(hh)
    if hh_i > 23 or mm > 59:
        raise ValueError(f"time out of range: {hh_i}:{mm}")
    time = f"{hh_i:02d}:{mm:02d}"
    if dow == "*":
        return JobTrigger(kind="daily", time=time), f"daily at {time}"
    days = []
    for tok in dow.split(","):
        tok = tok.strip()
        lo_s, _, hi_s = tok.partition("-")
        if not (lo_s.isdigit() and (hi_s == "" or hi_s.isdigit())):
            raise ValueError(f"bad day-of-week {dow!r} (0/7=Sun..6=Sat, ranges ok)")
        lo = int(lo_s)
        hi = int(hi_s) if hi_s else lo
        if lo > hi:
            raise ValueError(f"bad day-of-week range {tok!r}")
        for d in range(lo, hi + 1):
            if d not in (0, 7) and not (1 <= d <= 6):
                raise ValueError(f"day-of-week {d} out of range (0/7=Sun..6=Sat)")
            days.append((d - 1) % 7)    # cron 0=Sun -> our 0=Mon
    days = sorted(set(days))
    return JobTrigger(kind="weekly", time=time, days=days), f"weekly {time} on day(s) {days}"


def scheduler_tools():
    def h_sched(ctx, action: str, cron: str = "", note: str = ""):
        w = getattr(ctx, "automation_worker", None)
        if w is None:
            return {"error": "durable automation is not running in this context — "
                             "start BEE with the scheduler enabled (automation in "
                             "config.yaml). No jobs were created."}
        action = (action or "").lower()
        if action == "add":
            task = (note or "").strip() or f"run the scheduled job {cron}"
            try:
                trigger, desc = _cron_to_trigger(cron)
            except ValueError as e:
                return {"error": str(e)}
            from ..automation.models import Job
            # idempotent id: same note+cron maps to the same job (like the
            # legacy behavior's replace_existing), no duplicates on re-add
            jid = "cron_" + re.sub(r"[^a-z0-9]+", "_",
                                   f"{(note or cron).lower()}").strip("_")[:40]
            existing = w.store.load_job(jid)
            if existing is not None:
                return {"error": f"job already exists: {existing.id} "
                                 f"({existing.description!r}) — cancel it first "
                                 "or use a different note"}
            job = Job(id=jid, owner="main", description=f"cron {cron}: {task}",
                      action={"type": "agent_task", "task": task},
                      trigger=trigger, timezone=w.default_timezone, enabled=True,
                      # agent_task: single attempt by default (no blind retry
                      # of side-effecting work) — the worker enforces this.
                      retry_policy={"max_attempts": 2, "backoff_seconds": 60},
                      max_runtime=600.0, state="pending")
            w.create_job(job)
            from ..automation.models import display_local
            return {"ok": True, "job": job.id, "cron": cron,
                    "trigger": trigger.describe(),
                    "next_run": display_local(job.next_run, job.timezone),
                    "durable": True,
                    "note": "real durable job — survives restarts, runs through "
                            "the kernel (no no-op). Manage with /jobs or the "
                            "automation_job tool."}
        if action == "list":
            from ..automation.models import display_local
            rows = []
            for j in w.jobs():
                rows.append({"id": j.id, "description": j.description,
                             "trigger": j.trigger.describe(),
                             "next_run": display_local(j.next_run, j.timezone),
                             "state": j.state, "enabled": j.enabled})
            return {"jobs": rows, "source": "durable automation store"}
        if action == "remove":
            jid = (cron or "").strip()
            if not jid:
                return {"error": "remove needs the job id (pass it as 'cron')"}
            if w.cancel_job(jid):
                return {"ok": True, "removed": jid}
            if w.delete_job(jid):
                return {"ok": True, "removed": jid, "note": "job deleted from store"}
            return {"error": f"no job matching {jid!r}"}
        return {"error": f"unknown action: {action} (use add|list|remove)"}

    return [
        T("scheduler", "Schedule recurring work (cron adapter over the durable job system). "
                       "Actions: add (cron expr + note describing what to do), list, "
                       "remove (pass job id as 'cron'). Jobs are DURABLE (survive "
                       "restarts) and execute REAL work through the agent kernel — "
                       "never a no-op. Supported crons: 'M H * * *' (daily), "
                       "'M H * * D' (weekly, 0/7=Sun..6=Sat), 'M * * * *' (hourly), "
                       "'*/N * * * *' (every N minutes). For one-time/custom schedules "
                       "use the automation_job tool.",
          {"type": "object", "properties": {
              "action": {"type": "string", "enum": ["add", "list", "remove"]},
              "cron": {"type": "string"}, "note": {"type": "string"}}, "required": ["action"]}, h_sched),
    ]
