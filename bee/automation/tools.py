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


def _num(args: dict, key: str, default, cast=int):
    """Cast a model-supplied number with a message that names the field and the
    accepted shape. A bare `int(args['every_seconds'])` let a small model's "1h"
    escape the tool as `ValueError: invalid literal for int() with base 10: '1h'`
    — a Python internals message the model cannot act on (A43b)."""
    raw = args.get(key)
    if raw in (None, ""):
        return default
    try:
        return cast(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a number, got {raw!r}")


_DAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
         "saturday": 5, "sunday": 6}


def _days_from(raw):
    """Accept the integers the schema documents and the day names a small model
    writes anyway (`["mon","tue"]`), rejecting anything else instead of silently
    scheduling on the wrong day."""
    out = []
    for d in list(raw or []):
        if isinstance(d, bool):
            raise ValueError(f"days must be integers 0=Mon..6=Sun, got {d!r}")
        if isinstance(d, int):
            out.append(d % 7)
            continue
        s = str(d).strip().lower()
        if s.isdigit():
            out.append(int(s) % 7)
            continue
        full = _DAYS.get(s)
        if full is None:
            for k, v in _DAYS.items():
                if k.startswith(s[:3]):
                    full = v
                    break
        if full is None:
            raise ValueError(f"days must be 0=Mon..6=Sun or a day name, got {d!r}")
        out.append(full)
    return sorted(set(out))


def _trigger_from(args: dict) -> JobTrigger:
    kind = (args.get("kind") or "one_time").lower()
    if kind not in ("one_time", "daily", "weekly", "interval", "calendar"):
        raise ValueError(f"unknown trigger kind {kind!r} "
                         "(use one_time | daily | weekly | interval | calendar)")
    return JobTrigger(
        kind=kind,
        at=args.get("at") or "",
        time=args.get("time") or "",
        days=_days_from(args.get("days")),
        every_seconds=_num(args, "every_seconds", 0, int),
        calendar=args.get("calendar") or "",
        reminder_offset_minutes=_num(args, "reminder_offset_minutes", 0, int),
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
        try:
            trigger = _trigger_from(kw)
            max_attempts = _num(kw, "max_attempts", 2, int)
            max_runtime = _num(kw, "max_runtime", 600.0, float)
        except ValueError as e:
            return {"error": str(e)}
        # A43a: a trigger whose next fire time cannot be computed used to be
        # stored anyway as PENDING with `next_run=""` — enabled, never scheduled,
        # and the tool answered {"created": ..., "next_run": ""} with the note
        # "authorized automation". Live probe, 2026-10-09: five such jobs
        # ("at": "tomorrow 9am", daily with no time, weekly with no time) landed
        # in the durable store while every caller was told it succeeded. This is
        # A24b one layer down: the user waits for a reminder that cannot fire.
        from .schedule import next_run as _next_run
        try:
            tzname = kw.get("timezone") or w.default_timezone
            fires_at = _next_run(trigger, tzname, now)
        except Exception as e:
            return {"error": f"could not schedule this trigger: {e}"}
        if fires_at is None:
            hint = {
                "one_time": "pass 'at' as an ISO datetime, e.g. \"2026-10-10T09:00\" "
                            f"(got {trigger.at!r})",
                "daily": "pass 'time' as HH:MM, e.g. \"08:00\" (got {t!r})".format(t=trigger.time),
                "weekly": "pass 'time' as HH:MM and 'days' as 0=Mon..6=Sun "
                          f"(got time={trigger.time!r}, days={trigger.days!r})",
                "interval": "pass 'every_seconds' as a whole number of seconds, e.g. 3600 "
                            f"(got {kw.get('every_seconds')!r})",
                "calendar": "pass 'calendar' as \"ics:<path>\" — only ICS calendars are "
                            f"supported (got {trigger.calendar!r})",
            }.get(trigger.kind, "check 'kind' against the accepted shapes")
            return {"error": f"this job can never fire: {hint}"}
        job = Job(
            owner=kw.get("owner") or "main",
            description=kw.get("description") or task or message,
            action=({"type": "agent_task", "task": task} if task
                    else {"type": "notify", "message": message}),
            trigger=trigger,
            timezone=tzname,
            enabled=True,
            retry_policy={"max_attempts": max_attempts,
                          "backoff_seconds": 60},
            max_runtime=max_runtime,
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
            try:
                per_hour = _num(kw, "max_per_hour", 6, int)
                match = dict(kw.get("match") or {})
            except (TypeError, ValueError) as e:
                return {"error": str(e) if str(e) else "match must be an object"}
            rule = ProactiveRule(kind=kw.get("kind") or "timer",
                                 match=match,
                                 action=action,
                                 description=kw.get("description") or "",
                                 max_per_hour=per_hour,
                                 # Provenance is a fact, not a courtesy: the
                                 # field's documented meaning is "explicit user
                                 # authorization", and a rule the MODEL composed
                                 # does not qualify even when the user approved
                                 # the tool call. The approval lives in the
                                 # permission receipt; stamping "user" here made
                                 # a model-authored deferred action look
                                 # human-authorized in the record and in /auto.
                                 created_by="model")
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
