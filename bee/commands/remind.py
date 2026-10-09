"""/remind — natural-language reminders on the durable job store.

Usage:
  /remind <what> <when>      create (when: "tomorrow 9am", "in 20 min",
                             "monday 7:30", "2026-10-12 07:30", "18:00")
  /remind list               upcoming reminders, soonest first
  /remind cancel <id|last|all>

A reminder is ONE durable `notify` job (owner="reminder") in
<workspace>/automation — it therefore survives restarts, is repaired by
`worker.restore()` after a crash, fires through the same JobWorker as every
other job, and lands in the notification store + OS toast. No second scheduler.

Fully deterministic: time parsing is regex + calendar math, so this works with
no model reachable and never costs an LLM call (the contract in
bee/commands/__init__.py). Repeated text is preserved verbatim as the message.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from . import register

_UNIT = {"m": "minutes", "min": "minutes", "mins": "minutes", "minute": "minutes",
         "minutes": "minutes", "h": "hours", "hr": "hours", "hrs": "hours",
         "hour": "hours", "hours": "hours", "d": "days", "day": "days",
         "days": "days", "w": "weeks", "week": "weeks", "weeks": "weeks"}
_REL = re.compile(r"\bin\s+(\d+)\s*([a-z]+)\b", re.I)
_DAYWORD = re.compile(r"\b(day after tomorrow|tomorrow|tonight|today|"
                      r"next\s+(?:week\s+)?(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*|"
                      r"mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|"
                      r"fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b", re.I)
_CLOCK = re.compile(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*([ap])m\b", re.I)
_CLOCK24 = re.compile(r"\b(?:at\s+)?([01]?\d|2[0-3]):([0-5]\d)\b")
_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MONTH = re.compile(r"\b(\d{1,2})\.?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|"
                    r"oct|nov|dec)[a-z]*\.?(?:\s+(\d{4}))?\b", re.I)
_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
           "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
_TONIGHT = re.compile("tonight", re.I)
_WD = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

USAGE = ('give me a time — e.g. /remind call the bank tomorrow 9am, '
         '/remind pay the client in 20 min, /remind water the plants 18:00, '
         '/remind file the taxes 2026-10-12 07:30')


def _clock(m1: str, m2: str | None, ap: str | None) -> tuple[int, int]:
    h, minute = int(m1), int(m2 or 0)
    if ap and ap.lower() == "p" and h < 12:
        h += 12
    elif ap and ap.lower() == "a" and h == 12:
        h = 0
    return min(h, 23), min(minute, 59)


def _strip(match: re.Match, text: str) -> str:
    """Remove a matched time phrase from the reminder text, tidying leftovers."""
    out = (text[:match.start()] + " " + text[match.end():])
    return re.sub(r"\s+(?:at|on|by|for)\s*$", " ", out).strip(" .,;:-\t")


def parse_when(text: str, now: datetime) -> tuple[datetime | None, str]:
    """Return (aware target datetime | None, remaining text).

    Order matters: an explicit relative span wins over a day word, which wins
    over a bare clock. Anything unparseable returns None so the caller can show
    the usage line instead of silently guessing a date."""
    rest = text
    day = None
    tonight = bool(_TONIGHT.search(text, re.I))
    when_date: tuple[int, int, int] | None = None

    m = _DATE.search(text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        when_date = (y, mo, d)
        rest = _strip(m, rest)
    m = _MONTH.search(text)
    if when_date is None and m:
        key = m.group(2).lower()
        mon = _MONTHS[key if key in _MONTHS else key[:3]]
        d = int(m.group(1))
        year = int(m.group(3)) if m.group(3) else now.year
        when_date = (year, mon, d)
        rest = _strip(m, rest)

    md = _REL.search(rest)
    if md:
        unit = _UNIT.get(md.group(2).lower())
        if unit:
            rest = _strip(md, rest)
            return now + timedelta(**{unit: int(md.group(1))}), rest

    dm = _DAYWORD.search(rest)
    if dm:
        w = dm.group(1).lower()
        rest = _strip(dm, rest)
        if "after tomorrow" in w:
            day = now.date() + timedelta(days=2)
        elif w.startswith("tomorrow"):
            day = now.date() + timedelta(days=1)
        elif w == "tonight":
            day = now.date()
        elif w == "today":
            day = now.date()
        else:
            key = w.replace("next ", "")[:3]
            want = _WD.get(key)
            if want is None:
                return None, text
            ahead = (want - now.weekday()) % 7
            if ahead == 0:
                ahead = 7 if "next" in w else 0
            elif "next" in w:
                ahead += 7
            day = now.date() + timedelta(days=ahead)

    cm = _CLOCK.search(rest) or _CLOCK24.search(rest)
    hour = minute = None
    if cm:
        g = cm.groups()
        if len(g) == 3:
            hour, minute = _clock(g[0], g[1], g[2])
        else:
            hour, minute = int(g[0]), int(g[1])
        rest = _strip(cm, rest)

    if when_date is not None:
        y, mo, d = when_date
        return now.replace(year=y, month=mo, day=d,
                           hour=hour or 9, minute=minute or 0,
                           second=0, microsecond=0), rest.strip()
    if day is None and hour is None:
        return None, text
    if day is None:
        day = now.date()
    if hour is None:
        hour = 20 if tonight else 9      # "tonight" means ~8 PM, not tomorrow morning
    dt = now.replace(year=day.year, month=day.month, day=day.day,
                     hour=hour if hour is not None else 9,
                     minute=minute if minute is not None else 0,
                     second=0, microsecond=0)
    if minute is None and dt <= now and day == now.date():
        dt = dt.replace(hour=hour, minute=0) + timedelta(days=1)
    if dt <= now and day == now.date():
        dt += timedelta(days=1)                      # "18:00" at 19:00 = tomorrow
    return dt, re.sub(r"\s+", " ", rest).strip(" .,;:-\t")


def _worker(ctx):
    return getattr(ctx, "automation_worker", None)


@register("remind", "/remind <what> <when> | list | cancel <id|last|all>",
          "durable reminders (notify job + toast), e.g. /remind pay the client tomorrow 9am")
def remind(ctx, arg: str) -> str:
    from ..automation.models import Job, JobTrigger, PENDING, display_local, iso

    w = _worker(ctx)
    if w is None:
        return ("ERROR: automation is not running, so reminders cannot be "
                "scheduled. Start BEE normally (automation.enabled in config.yaml) "
                "or set a task instead with /plan add.")
    body = (arg or "").strip()
    if not body:
        return f"ERROR: {USAGE}"

    low = body.lower()
    if low in ("list", "ls", ""):
        return _list(ctx, w)
    if low.startswith("cancel "):
        return _cancel(ctx, w, body[7:].strip())

    # The job's timezone is the one the scheduler itself uses (same convention as
    # bee/scheduler.py) so the wall clock the user spoke in, the instant that gets
    # stored, and the time /remind list renders are all one coherent story.
    tzname = getattr(w, "default_timezone", "") or "Asia/Kolkata"
    from ..automation.schedule import worker_now
    now = worker_now(w, tzname)

    what = body
    when, remainder = None, body
    try:
        when, remainder = parse_when(body, now)
    except Exception:
        when = None
    if when is None:
        return f"ERROR: I could not read a time in {body!r}. {USAGE}"
    what = (remainder or "").strip()
    if not what:
        return f"ERROR: what should I remind you about? {USAGE}"

    job = Job(owner="reminder",
              description=f"Reminder: {what}",
              action={"type": "notify", "message": f"Reminder: {what}",
                      "critical": True},
              trigger=JobTrigger(kind="one_time", at=iso(when)),
              timezone=tzname,
              enabled=True,
              permissions={"guard_mode": "unattended", "preapproved_capabilities": []},
              retry_policy={"max_attempts": 2, "backoff_seconds": 60},
              max_runtime=600.0, state=PENDING)
    w.create_job(job)
    return (f"⏰ Reminder set: **{what}**\n- when: "
            f"{display_local(job.next_run or iso(when), job.timezone)}\n"
            f"- job: `{job.id}` (survives restarts; "
            f"`/remind cancel {job.id}` removes it)")


def _list(ctx, w) -> str:
    from ..automation.models import display_local
    rows = [j for j in w.jobs() if j.owner == "reminder" and j.enabled
            and j.state in ("pending", "running")]
    if not rows:
        return "No reminders scheduled. Add one: /remind call the bank tomorrow 9am"
    rows.sort(key=lambda j: j.next_run or "9999")
    lines = ["| when (local) | reminder | id |", "|---|---|---|"]
    for j in rows[:20]:
        msg = j.action.get("message") or j.description
        lines.append(f"| {display_local(j.next_run, j.timezone)} | {msg[:60]} | `{j.id}` |")
    return "\n".join(lines)


def _cancel(ctx, w, ident: str) -> str:
    if not ident:
        return "ERROR: /remind cancel <id|last|all>"
    rows = [j for j in w.jobs() if j.owner == "reminder"]
    if ident.lower() == "all":
        gone = [j.id for j in rows if j.enabled and j.state in ("pending", "running")]
        done = [jid for jid in gone if w.cancel_job(jid)]
        return (f"Cancelled {len(done)} reminder(s)." if done
                else "No pending reminders to cancel.")
    if ident.lower() == "last":
        pend = sorted((j for j in rows if j.enabled), key=lambda j: j.next_run or "")
        if not pend:
            return "No reminders to cancel."
        ident = pend[-1].id
    hit = next((j for j in rows if j.id == ident or j.id.endswith(ident)), None)
    if hit is None:
        return f"ERROR: no reminder with id {ident!r} (see /remind list)"
    return (f"Cancelled reminder `{hit.id}` — {hit.description}"
            if w.cancel_job(hit.id) else f"ERROR: could not cancel {hit.id}")
