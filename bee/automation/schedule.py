"""Trigger math (Phase 6) — pure, tz-aware, deterministic.

next_run(trigger, tz, now) -> aware datetime | None
  one_time : the fixed instant (None once passed)
  daily    : next HH:MM in the job timezone (today if still ahead)
  weekly   : next occurrence on one of the given weekdays (0=Mon..6=Sun)
  interval : anchored to the reference instant (created_at/last_run), the
             first multiple strictly after `now`
  calendar : next event from the supported source (ICS file) minus the
             reminder offset — "where supported" = .ics files; other
             sources are a documented non-claim

All functions take `now` explicitly — the worker injects its clock, so the
entire scheduler is testable without sleeping.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from .models import JobTrigger


def get_tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def worker_now(worker, tz_name: str = "") -> datetime:
    """'Now' exactly as the SCHEDULER sees it, expressed in the job's timezone.

    Anything that turns words ('in 20 min', 'tomorrow 9am') or a bare 'HH:MM'
    into an instant must use this and never `datetime.now()`: JobWorker's tick
    compares next_run against its OWN clock, so a second clock source means the
    creation side and the firing side disagree — and the layer cannot be tested
    without sleeping. Falls back to the wall clock for a worker with no clock
    (a bare/stub worker), which is what the older call sites expected."""
    now = None
    fn = getattr(worker, "now", None)
    if callable(fn):
        try:
            now = fn()
        except Exception:
            now = None
    if now is None:
        now = datetime.now()
    if now.tzinfo is None:                      # a naive 'now' would be a lie
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(get_tz(tz_name)) if tz_name else now


def _parse_local(s: str, tz: ZoneInfo) -> Optional[datetime]:
    """Parse an ISO datetime; naive values are taken IN THE JOB TIMEZONE."""
    try:
        dt = datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt


def _parse_hhmm(s: str) -> Optional[tuple[int, int]]:
    m = re.match(r"^(\d{1,2}):(\d{2})$", (s or "").strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return h, mi


# --------------------------------------------------------------------- ICS
def parse_ics(path: str) -> list[dict]:
    """Minimal ICS reader: VEVENTs with DTSTART (+ optional SUMMARY).
    Supports the common subset; malformed files yield what parses, not an
    exception. (Calendar-derived triggers 'where supported'.)"""
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return []
    events: list[dict] = []
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    # unfold (RFC5545): newline+space continues the previous line
    text = re.sub(r"\r?\n[ \t]", "", text)
    cur: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("BEGIN:VEVENT"):
            cur = {}
        elif line.upper().startswith("END:VEVENT"):
            if cur.get("dt"):
                events.append(cur)
            cur = {}
        elif ":" in line:
            key, _, val = line.partition(":")
            key = key.split(";")[0].upper()
            if key == "DTSTART":
                cur["dt"] = val
            elif key == "SUMMARY":
                cur["summary"] = val
    out = []
    for e in events:
        dt = _parse_ics_dt(e.get("dt", ""))
        if dt:
            out.append({"dt": dt, "summary": e.get("summary", "")})
    # naive (local) and aware (UTC) datetimes cannot compare directly — the
    # sort axis assumes UTC for naive values; the CALLER assigns the job tz
    # to naive values later (job-local semantics are unchanged)
    def _axis(dt):
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=ZoneInfo("UTC"))
    return sorted(out, key=lambda e: _axis(e["dt"]))


def _parse_ics_dt(val: str) -> Optional[datetime]:
    """DTSTART values: YYYYMMDDTHHMMSS[Z|+HH:MM] / YYYYMMDD / ISO.

    The compact form is the ICS standard; a 'Z' or offset suffix means the
    value is UTC/offset-aware and must NOT be reinterpreted as local time.
    """
    v = (val or "").strip()
    # compact form with an offset or Z (RFC5545): 20261006T160000Z / +0530
    m = re.match(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z|[+-]\d{2}:?\d{2})?$", v)
    if m:
        y, mo, d, h, mi, s = (int(m.group(i)) for i in range(1, 7))
        off = m.group(7)
        try:
            if off in (None, "Z"):
                return datetime(y, mo, d, h, mi, s, tzinfo=ZoneInfo("UTC") if off else None)
            if ":" not in off:
                off = off[:3] + ":" + off[3:]
            return datetime.fromisoformat(f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:{s:02d}{off}")
        except (ValueError, TypeError):
            return None
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        pass
    m = re.match(r"^(\d{4})(\d{2})(\d{2})T?(\d{2})?(\d{2})?(\d{2})?$", v)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    h = int(m.group(4) or 0)
    mi = int(m.group(5) or 0)
    s = int(m.group(6) or 0)
    return datetime(y, mo, d, h, mi, s)   # naive = local (job tz applied by caller)


# ----------------------------------------------------------------- next_run
def next_run(trigger: JobTrigger, tz: str, now: datetime,
             anchor: Optional[datetime] = None) -> Optional[datetime]:
    """Next fire time strictly after `now` (aware, in the job timezone)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=get_tz(tz))
    z = get_tz(tz)
    now = now.astimezone(z)
    k = trigger.kind

    if k == "one_time":
        dt = _parse_local(trigger.at, z)
        if dt is None:
            return None
        dt = dt.astimezone(z)
        return dt if dt > now else None

    if k == "daily":
        hm = _parse_hhmm(trigger.time)
        if hm is None:
            return None
        for day_off in range(0, 2):
            cand = (now + timedelta(days=day_off)).replace(
                hour=hm[0], minute=hm[1], second=0, microsecond=0)
            if cand > now:
                return cand
        return None

    if k == "weekly":
        hm = _parse_hhmm(trigger.time)
        days = sorted({int(d) % 7 for d in trigger.days}) if trigger.days else [now.isoweekday() - 1]
        if hm is None:
            return None
        for day_off in range(0, 8):
            cand_day = now + timedelta(days=day_off)
            if (cand_day.isoweekday() - 1) in days:
                cand = cand_day.replace(hour=hm[0], minute=hm[1], second=0,
                                        microsecond=0)
                if cand > now:
                    return cand
        return None

    if k == "interval":
        if trigger.every_seconds <= 0:
            return None
        base = anchor or now
        if base.tzinfo is None:
            base = base.replace(tzinfo=z)
        base = base.astimezone(z)
        step = timedelta(seconds=trigger.every_seconds)
        # first base + n*step strictly after now
        delta = now - base
        n = int(delta.total_seconds() // trigger.every_seconds) + 1
        if n < 0:
            n = 0
        return base + n * step

    if k == "calendar":
        src = (trigger.calendar or "").strip()
        if not src.lower().startswith("ics:"):
            return None                      # only ICS supported (documented)
        offset = timedelta(minutes=trigger.reminder_offset_minutes)
        best: Optional[datetime] = None
        for ev in parse_ics(src[4:]):
            dt = ev["dt"]
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=z)
            fire = dt - offset
            if fire > now and (best is None or fire < best):
                best = fire
        return best

    return None
