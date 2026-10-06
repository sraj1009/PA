"""automation_job tool (Phase 6) — user-facing automation management.

The user creates automation EXPLICITLY, either by talking to BEE
("Every weekday at 8 AM, tell me my schedule") or via REPL commands
(/jobs, /auto). Either way the job lands in the durable store and runs
through the kernel. This tool is gated by the `automation.manage`
capability (R3, ASK) — BEE cannot automate things the user did not
authorize.

Operations:
  create  {kind, at|time|days|every, task|message, timezone?, owner?,
           max_runtime?, max_attempts?}
  list | disable <id> | enable <id> | cancel <id> | history <id>
  rules  {op: list|add|disable, kind, match?, action?, message?, task?}
"""
from __future__ import annotations

from datetime import datetime

from ..tools.base import T
from .events import ProactiveRule
from .models import COMPLETED, CANCELLED, DISABLED, Job, JobTrigger, RUNNING, PENDING
from .worker import JobWorker


def _worker(ctx) -> JobWorker | None:
    return getattr(ctx, "automation_worker", None)


def _trigger_from(args: dict) -> JobTrigger:
    kind = (args.get("kind") or "one_time").lower()
    return JobTrigger(
        kind=kind,
        at=args.get("at") or "",
        time=args.get("time") or "",
        days=list(args.get("days") or []),
        every_seconds=int(args.get("every_seconds") or 0),
        calendar=args.get("calendar") or "",
        reminder_offset_minutes=int(args.get("reminder_offset_minutes") or 0),
    )


def automation_job(ctx, op: str = "list", **kw):
    w = _worker(ctx)
    if w is None:
        return {"error": "automation is not running in this context "
                         "(start the REPL/web with the scheduler enabled)"}
    op = (op or "list").lower()
    now = w.now()

    if op == "create":
        task = kw.get("task") or ""
        message = kw.get("message") or ""
        if not task and not message:
            return {"error": "create needs 'task' (agent task) or 'message' (notify)"}
        trigger = _trigger_from(kw)
        job = Job(
            owner=kw.get("owner") or "main",
            description=kw.get("description") or task or message,
            action=({"type": "agent_task", "task": task} if task
                    else {"type": "notify", "message": message}),
            trigger=trigger,
            timezone=kw.get("timezone") or w.default_timezone,
            enabled=True,
            retry_policy={"max_attempts": int(kw.get("max_attempts") or 2),
                          "backoff_seconds": 60},
            max_runtime=float(kw.get("max_runtime") or 600.0),
        )
        w.create_job(job)
        return {"created": job.id, "description": job.description,
                "trigger": trigger.describe(), "next_run": job.next_run,
                "note": "authorized automation — manage with /jobs"}

    if op == "list":
        return {"jobs": [j.summary() for j in w.jobs()],
                "rules": [r.to_dict() for r in w.policy.rules] if w.policy else []}

    if op in ("disable", "enable", "cancel", "delete", "history"):
        jid = kw.get("id") or ""
        if not jid:
            return {"error": f"{op} needs 'id'"}
        if op == "disable":
            return {"ok": w.disable_job(jid)}
        if op == "enable":
            return {"ok": w.enable_job(jid)}
        if op == "cancel":
            return {"ok": w.cancel_job(jid)}
        if op == "delete":
            return {"ok": w.delete_job(jid)}
        return {"history": w.history(jid)}

    if op == "rules":
        if w.policy is None:
            from .events import ProactivePolicy
            w.policy = ProactivePolicy(w.store.load_rules())
        sub = (kw.get("rule_op") or "list").lower()
        if sub == "list":
            return {"rules": [r.to_dict() for r in w.policy.rules]}
        if sub == "add":
            action = {"type": "notify", "message": kw.get("message") or ""}
            if kw.get("task"):
                action = {"type": "agent_task", "task": kw.get("task")}
            rule = ProactiveRule(kind=kw.get("kind") or "timer",
                                 match=dict(kw.get("match") or {}),
                                 action=action,
                                 description=kw.get("description") or "",
                                 max_per_hour=int(kw.get("max_per_hour") or 6),
                                 created_by="user")     # explicit authorization
            w.policy.add_rule(rule)
            w.store.save_rules(w.policy.rules)
            return {"created": rule.id, "rule": rule.to_dict()}
        if sub == "disable":
            ok = w.policy.remove_rule(kw.get("id") or "")
            if ok:
                w.store.save_rules(w.policy.rules)
            return {"ok": ok}
        return {"error": "rules needs rule_op one of list|add|disable"}

    return {"error": f"unknown op {op!r} (create|list|disable|enable|cancel|history|rules)"}


def automation_tools() -> list[T]:
    return [
        T(name="automation_job",
          description="Manage durable automations (user-authorized): create jobs "
                      "(one_time/daily/weekly/interval: kind + at/time/days/every_seconds; "
                      "task = agent task, message = plain notification), list, disable, "
                      "enable, cancel, history; and proactive rules (event -> notify/task, "
                      "rate-limited). Jobs survive restarts and run through the kernel.",
          parameters={"type": "object",
                      "properties": {
                          "op": {"type": "string",
                                 "enum": ["create", "list", "disable", "enable",
                                          "cancel", "delete", "history", "rules"]},
                          "kind": {"type": "string", "enum": ["one_time", "daily", "weekly", "interval"]},
                          "at": {"type": "string", "description": "one_time: ISO datetime (job tz)"},
                          "time": {"type": "string", "description": "daily/weekly: HH:MM"},
                          "days": {"type": "array", "items": {"type": "integer"},
                                   "description": "weekly: 0=Mon..6=Sun"},
                          "every_seconds": {"type": "integer"},
                          "task": {"type": "string"}, "message": {"type": "string"},
                          "description": {"type": "string"}, "id": {"type": "string"},
                          "timezone": {"type": "string"}, "owner": {"type": "string"},
                          "max_runtime": {"type": "number"}, "max_attempts": {"type": "integer"},
                          "rule_op": {"type": "string", "enum": ["list", "add", "disable"]},
                          "match": {"type": "object"}, "max_per_hour": {"type": "integer"}},
                      "required": ["op"]},
          handler=automation_job, risk="medium",
          capabilities=("automation.manage",)),
    ]
