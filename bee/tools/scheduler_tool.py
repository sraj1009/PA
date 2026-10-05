"""scheduler — APScheduler-backed cron/one-shot jobs (persisted in jobs.json).

Used by the memory consolidation loop (docs/consolidation.py) and by the agent
for recurring tasks the user requests ("remind me daily at 9", "run X every hour").
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass

from .. import paths


@dataclass
class T:
    name: str
    description: str
    parameters: dict
    handler: object

_sched = None
_lock = threading.Lock()


def _ensure():
    global _sched
    with _lock:
        if _sched is None:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
            s = BackgroundScheduler(timezone="Asia/Kolkata")
            # restore persisted jobs
            if paths.JOBS_JSON.exists():
                try:
                    jobs = json.loads(paths.JOBS_JSON.read_text(encoding="utf-8"))
                    for j in jobs:
                        try:
                            s.add_job(_noop, CronTrigger.from_crontab(j["cron"]), id=j["id"],
                                      replace_existing=True, kwargs={"note": j.get("note")})
                        except Exception:
                            pass
                except Exception:
                    pass
            s.start()
            _sched = s
        return _sched


def _noop(note=None):
    """Placeholder for restored jobs; live jobs get real callables when added this process."""
    try:
        with paths.JOBS_LOG.open("a", encoding="utf-8") as f:
            from datetime import datetime
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} job fired (restored, no live callable) note={note}\n")
    except Exception:
        pass


def _persist():
    if _sched is None:
        return
    jobs = []
    for j in _sched.get_jobs():
        jobs.append({"id": j.id, "cron": getattr(j.trigger, "str", lambda: str(j.trigger))(), "note": j.name})
    paths.JOBS_JSON.write_text(json.dumps(jobs, indent=1), encoding="utf-8")


def scheduler_tools():
    def h_sched(ctx, action: str, cron: str = "", note: str = ""):
        try:
            s = _ensure()
        except ImportError:
            return {"error": "apscheduler not installed — pip install apscheduler"}
        action = (action or "").lower()
        if action == "add":
            if not cron:
                return {"error": "add needs cron expr, e.g. '0 9 * * *'"}
            try:
                from apscheduler.triggers.cron import CronTrigger
                jid = note.replace(" ", "_")[:40] or f"job{len(s.get_jobs()) + 1}"
                s.add_job(_noop, CronTrigger.from_crontab(cron), id=jid, name=note or jid, replace_existing=True)
                _persist()
                return {"ok": True, "job": jid, "cron": cron}
            except Exception as e:
                return {"error": f"bad cron: {e}"}
        if action == "list":
            return {"jobs": [{"id": j.id, "next_run": str(j.next_run_time or ""), "note": j.name} for j in s.get_jobs()]}
        if action == "remove":
            jid = cron  # reuse 'cron' arg as job id for remove
            try:
                s.remove_job(jid)
                _persist()
                return {"ok": True, "removed": jid}
            except Exception as e:
                return {"error": str(e)}
        return {"error": f"unknown action: {action} (use add|list|remove)"}

    return [
        T("scheduler", "Manage recurring jobs (cron). Actions: add (cron expr + note), list, remove (pass job id as 'cron'). "
                       "Example add: action=add, cron='0 9 * * *', note='morning briefing'. "
                       "Note: jobs restore as no-op markers across restarts; wire real callables in code for critical automation.",
          {"type": "object", "properties": {
              "action": {"type": "string", "enum": ["add", "list", "remove"]},
              "cron": {"type": "string"}, "note": {"type": "string"}}, "required": ["action"]}, h_sched),
    ]
