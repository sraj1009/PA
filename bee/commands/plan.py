"""/plan — itineraries with time-boxing + Eisenhower matrix, and a small task store.

Usage:
  /plan                          today's itinerary (time-boxed)
  /plan daily | weekly | monthly generate the itinerary for that horizon
  /plan add <title> [due YYYY-MM-DD] [P1..P4] [needs a,b]   add a task
  /plan list                     all open tasks by quadrant
  /plan done <id...>             mark tasks done
  /plan clear-done               prune finished tasks

Tasks persist in plans/tasks.json; itineraries in plans/itineraries/.
Priority = Eisenhower: P1 urgent+important, P2 important, P3 urgent, P4 neither.
LLM polishes the schedule when reachable; the deterministic engine is the floor.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

from . import register

URGENT_RE = re.compile(r"\b(today|tonight|urgent|asap|immediately|now|emergency|overdue)\b", re.I)
DUE_TOMORROW_RE = re.compile(r"due (by )?(today|tomorrow)\b", re.I)
IMPORTANT_RE = re.compile(
    r"\b(important|critical|deadline|due|review|sign|approve|pay|payment|submit|deadline|boss|"
    r"client|revenue|contract|launch|health|doctor|family|tax|visa|passport)\b", re.I)

WORK_START, WORK_END = dtime(9, 0), dtime(18, 0)
BREAKS = [(dtime(12, 30), dtime(14, 0)), (dtime(16, 0), dtime(16, 15))]
BLOCK_MIN = {"P1": 45, "P2": 30, "P3": 20, "P4": 15}


def _paths():
    from .. import paths
    d = Path(paths.WORKSPACE) / "plans"
    it = d / "itineraries"
    d.mkdir(parents=True, exist_ok=True)
    it.mkdir(parents=True, exist_ok=True)
    return d, it


def _load() -> list[dict]:
    f = _paths()[0] / "tasks.json"
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(tasks: list[dict]):
    (_paths()[0] / "tasks.json").write_text(json.dumps(tasks, indent=1), encoding="utf-8")


def classify(title: str, due: str = "") -> str:
    """Eisenhower quadrant → P1..P4 (pure heuristic, no LLM)."""
    urgent = bool(URGENT_RE.search(title) or DUE_TOMORROW_RE.search(title))
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    if due in (today, tomorrow):
        urgent = True
    important = bool(IMPORTANT_RE.search(title))
    if urgent and important:
        return "P1"
    if important:
        return "P2"
    if urgent:
        return "P3"
    return "P4"


def _open(tasks: list[dict]) -> list[dict]:
    return [t for t in tasks if t.get("status") == "todo"]


def _llm(ctx, prompt: str, max_tokens: int = 700) -> str | None:
    # Phase 2: commands execute LLM work through the SAME kernel as main tasks
    # (provider routing, receipts, events, telemetry). The fallback keeps bare
    # ctx objects working (tests without a kernel).
    kernel = getattr(ctx, "kernel", None)
    if kernel is not None:
        try:
            return kernel.direct("plan", prompt, max_tokens=max_tokens)
        except Exception:
            pass
    if ctx is None or ctx.client is None:
        return None
    try:
        out = ctx.client.chat("local", [{"role": "user", "content": prompt}], max_tokens=max_tokens)
        c = (out.get("content") or "").strip()
        return c or None
    except Exception:
        return None


# ------------------------------------------------------------ deterministic
def _daily_blocks(tasks: list[dict]) -> list[tuple[str, str, dict]]:
    tod = date.today()
    blocks: list[tuple[str, str, dict]] = []
    done = {t["id"] for t in tasks if t.get("status") == "done"}
    order = sorted(_open(tasks), key=lambda t: (t["priority"], t.get("due") or "9999", t["id"]))
    t = WORK_START
    for task in order:
        deps = [d for d in task.get("deps", []) if d not in done]
        if deps:
            blocks.append((f"later ({dtime(17, 30)}–{dtime(18, 0)})", f"{task['id']} {task['title']} — waiting on {', '.join(deps)}", task))
            continue
        dur = BLOCK_MIN[task["priority"]]
        start = t
        end = start
        # walk past breaks
        while True:
            end = min(datetime.combine(tod, start) + timedelta(minutes=dur), datetime.combine(tod, WORK_END)).time()
            if end <= start:
                end = start
            if not any(bs <= start < be for bs, be in BREAKS):
                break
            start = be
        blocks.append((f"{start:%H:%M}–{end:%H:%M}", f"{task['id']} {task['title']}  [{task['priority']}] "
                    + (f"due {task['due']}" if task.get("due") else ""), task))
        t = end
        if t >= WORK_END:
            break
    if not blocks:
        blocks.append((f"{WORK_START:%H:%M}–{WORK_END:%H:%M}", "no open tasks — /plan add <title> to start", {}))
    return blocks


def _weekly_split(tasks: list[dict]) -> dict[date, list[dict]]:
    """Greedy: each open task lands on the earliest weekday >= today and <= due (or today+)."""
    days: dict[date, list[dict]] = {}
    today = date.today()
    for task in sorted(_open(tasks), key=lambda t: (t["priority"], t.get("due") or "9999", t["id"])):
        due = None
        if task.get("due"):
            try:
                due = datetime.strptime(task["due"][:10], "%Y-%m-%d").date()
            except ValueError:
                due = None
        start = max(today, due - timedelta(days=2)) if due else today
        day = start
        while day.weekday() >= 5:  # push weekends to Monday
            day += timedelta(days=1)
        if due and day > due:
            day = due if due.weekday() < 5 else due - timedelta(days=due.weekday() - 4)
        days.setdefault(day, []).append(task)
    return dict(sorted(days.items()))


# ------------------------------------------------------------- render/save
def _render_daily(blocks) -> str:
    tod = date.today().isoformat()
    L = [f"## BEE — daily itinerary · {tod}", ""]
    for span, line, _t in blocks:
        L.append(f"- **{span}** — {line}")
    L.append("")
    L.append("_Time-boxed: P1 45′ · P2 30′ · P3 20′ · P4 15′ — breaks 12:30–14:00, 16:00–16:15. "
             "Eisenhower: P1 do now · P2 schedule · P3 delegate · P4 drop._")
    return "\n".join(L)


def _render_weekly(days) -> str:
    L = ["## BEE — weekly plan", ""]
    for d, ts in days.items():
        L.append(f"### {d:%a %Y-%m-%d}")
        for t in ts:
            L.append(f"- [{t['priority']}] {t['id']} {t['title']}" + (f" — due {t['due']}" if t.get("due") else ""))
        L.append("")
    return "\n".join(L)


def _render_monthly(days) -> str:
    by_week: dict[int, list[dict]] = {}
    for d, ts in days.items():
        by_week.setdefault(d.isocalendar()[1], []).extend(ts)
    L = ["## BEE — monthly outlook (4-week buckets)", ""]
    for w in sorted(by_week):
        L.append(f"### Week {w}")
        for t in by_week[w]:
            L.append(f"- [{t['priority']}] {t['id']} {t['title']}")
        L.append("")
    return "\n".join(L)


def _persist(kind: str, text: str):
    d, it = _paths()
    f = it / f"{date.today().isoformat()}-{kind}.md"
    f.write_text(text, encoding="utf-8")
    return f.name


@register("plan", "/plan [add|list|done|daily|weekly|monthly|clear-done]",
          "time-boxed itineraries (Eisenhower P1–P4) + task store with deadlines/dependencies/status")
def plan(ctx, arg: str) -> str:
    arg = arg.strip()
    try:
        tasks = _load()
        if not arg or arg.lower() in ("daily", "today"):
            blocks = _daily_blocks(tasks)
            llm = _llm(ctx, "You are an executive scheduler. Convert this task list into a realistic "
                            "time-boxed workday (09:00-18:00, breaks 12:30-14:00 and 16:00-16:15). "
                            "Keep task ids and priorities. Markdown bullet list, no preamble.\n" +
                            "\n".join(f"{i['id']} [{i['priority']}] {i['title']}" for i in
                                      (b[2] for b in blocks if b[2])))
            text = llm or _render_daily(blocks)
            return _persist("daily", text) + "\n\n" + text
        if arg.lower() == "weekly":
            days = _weekly_split(tasks)
            text = _render_weekly(days)
            return _persist("weekly", text) + "\n\n" + text
        if arg.lower() == "monthly":
            days = _weekly_split(tasks)
            text = _render_monthly(days)
            return _persist("monthly", text) + "\n\n" + text
        if arg.lower().startswith("add "):
            rest = arg[4:].strip()
            m = re.match(r"^(?P<title>.+?)(?:\s+due\s+(?P<due>\d{4}-\d{2}-\d{2}))?"
                         r"(?:\s+(?P<p>p[1-4]))?(?:\s+needs\s+(?P<deps>[a-z0-9,]+))?$",
                         rest, re.I)
            if not m:
                return "ERROR: /plan add <title> [due YYYY-MM-DD] [P1..P4] [needs a,b]"
            title = m.group("title").strip()
            due = (m.group("due") or "").lower()
            pri = (m.group("p") or "").upper() or classify(title, due)
            tid = f"t{len(tasks) + 1}"
            tasks.append({"id": tid, "title": title, "due": due, "priority": pri,
                          "deps": [d.strip() for d in (m.group("deps") or "").split(",") if d.strip()],
                          "status": "todo", "created": date.today().isoformat()})
            _save(tasks)
            return f"Added **{tid}** [{pri}] {title}" + (f" — due {due}" if due else "")
        if arg.lower() == "list":
            open_t = _open(tasks)
            if not open_t:
                return "No open tasks. /plan add <title> [due YYYY-MM-DD] [P1..P4]"
            L = ["| id | priority | title | due | deps | status |", "|---|---|---|---|---|---|"]
            for t in sorted(open_t, key=lambda x: (x["priority"], x.get("due") or "9999")):
                L.append(f"| {t['id']} | {t['priority']} | {t['title']} | {t.get('due') or '—'} | "
                         f"{', '.join(t.get('deps', [])) or '—'} | {t.get('status', 'todo')} |")
            return "\n".join(L)
        if arg.lower().startswith("done "):
            ids = set(arg[5:].split())
            n = 0
            for t in tasks:
                if t["id"] in ids and t.get("status") != "done":
                    t["status"] = "done"
                    n += 1
            _save(tasks)
            return f"Marked {n} done." if n else "ERROR: no such open task id(s) — /plan list"
        if arg.lower() == "clear-done":
            before = len(tasks)
            tasks[:] = [t for t in tasks if t.get("status") != "done"]
            _save(tasks)
            return f"Pruned {before - len(tasks)} finished task(s)."
        return "ERROR: unknown subcommand — /plan | add | list | done | daily | weekly | monthly | clear-done"
    except Exception as e:
        return f"ERROR: /plan failed safely: {type(e).__name__}: {e}"
