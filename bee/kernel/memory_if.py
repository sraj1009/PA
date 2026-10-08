"""Memory interfaces (Phase 2) — clean contracts over the EXISTING systems.

The memory system itself is NOT redesigned here. These are the five
conceptual stores as protocols, plus MemoryStack: a thin adapter that wires
the current implementations (episodes, memory search/RAG, memory.md,
skills, scheduler/diary) behind those interfaces so the kernel only ever
talks to abstractions.
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable


@runtime_checkable
class WorkingMemory(Protocol):
    """Short-horizon state for the active session (kernel-owned, in-process)."""
    def context_block(self) -> str: ...
    def note(self, key: str, value: str) -> None: ...


@runtime_checkable
class EpisodicMemory(Protocol):
    """What happened, when (tasks, tool calls, outcomes)."""
    def record(self, task: str, ok: bool, output: str, error: str = "") -> None: ...
    def search(self, query: str, k: int = 5) -> list[dict]: ...


@runtime_checkable
class SemanticMemory(Protocol):
    """Durable facts: profile, long-term notes, RAG corpus."""
    def add(self, text: str, kind: str = "longterm") -> None: ...
    def search(self, query: str, k: int = 5) -> list[dict]: ...


@runtime_checkable
class ProceduralMemory(Protocol):
    """How to do things: skills distilled from novel successes."""
    def list(self) -> list[str]: ...
    def get(self, name: str) -> str: ...
    def add(self, name: str, body: str) -> None: ...


@runtime_checkable
class TemporalMemory(Protocol):
    """Time-indexed: diary entries, scheduled reminders, time-bound facts."""
    def schedule(self, task: str, when: str) -> dict: ...
    def list(self) -> list[dict]: ...
    def diary(self, text: str) -> None: ...


@runtime_checkable
class EntityMemory(Protocol):
    """Entities: people, projects, devices, applications, locations."""
    def remember_entity(self, name: str, kind: str, **attrs) -> object: ...
    def recall_entity(self, name: str) -> list: ...


class _Working:
    """Kernel's in-memory working set, scoped by task (global notes use "")."""
    def __init__(self):
        self._notes: dict[tuple[str, str], str] = {}

    def note(self, key: str, value: str = "", task_id: str = "") -> None:
        # note(key, value) — global; note(key, value, task_id) — task-scoped
        self._notes[(task_id, key)] = str(value)

    def context_block(self, task_id: str = "") -> str:
        entries = [(k, v) for (tid, k), v in self._notes.items() if tid in ("", task_id)]
        if not entries:
            return ""
        return "Working memory:\n" + "\n".join(f"- {k}: {v}" for k, v in entries[-8:])


class _Episodic:
    def record(self, task: str, ok: bool, output: str, error: str = "") -> None:
        # Episodes are already recorded inside run_agent (bee.episodes.logger)
        # — the kernel must not double-record. This adapter exists so future
        # episodic stores slot in without kernel changes.
        pass

    def search(self, query: str, k: int = 5) -> list[dict]:
        try:
            from ..pipeline.build_sft import load_episodes
            rows = load_episodes()
            out = []
            ql = [w for w in query.lower().split() if len(w) > 3]
            for r in reversed(rows[-200:]):
                t = (r.get("task") or "").lower()
                if ql and any(w in t for w in ql):
                    out.append({"task": r.get("task", ""), "ok": r.get("ok"),
                                "ts": r.get("ts", "")})
                if len(out) >= k:
                    break
            return out
        except Exception:
            return []


class _Semantic:
    """Long-term markdown memory. Phase 8: entries carry PROVENANCE inline
    (source label) so a future reader — or the model itself — can tell what
    is user-asserted vs tool-derived vs model-inferred. (The canonical
    provenance+confidence records live in the structured store; this is the
    human-readable mirror.)"""

    def add(self, text: str, kind: str = "longterm", source: str = "user",
            provenance: str = "") -> None:
        from .. import paths
        t = str(text or "").strip()
        if not t:
            return
        src = f" [source: {source}{': ' + provenance if provenance else ''}]" \
            if source and source != "user" else ""
        line = f"- {t}{src}"
        p = paths.PROFILE_MD if kind == "profile" else paths.LONGTERM_MD
        if p.exists():
            p.write_text(p.read_text(encoding="utf-8").rstrip() + f"\n\n{line}\n",
                         encoding="utf-8")
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"# {'Profile' if kind == 'profile' else 'Long-term memory'}\n\n{line}\n",
                         encoding="utf-8")

    def search(self, query: str, k: int = 5) -> list[dict]:
        try:
            from ..brain.rag import retrieve
            return list(retrieve(query, k=k) or [])
        except Exception:
            return []


class _Procedural:
    def list(self) -> list[str]:
        from .. import paths
        return sorted(p.parent.name for p in paths.SKILLS_DIR.glob("*/SKILL.md"))

    def get(self, name: str) -> str:
        from .. import paths
        f = paths.SKILLS_DIR / name / "SKILL.md"
        return f.read_text(encoding="utf-8", errors="replace") if f.exists() else ""

    def add(self, name: str, body: str) -> None:
        from .. import paths
        d = paths.SKILLS_DIR / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(body, encoding="utf-8")


class _Temporal:
    """Time-indexed memory. `schedule` creates REAL durable jobs through the
    one scheduling architecture (bee/automation -> JobWorker -> kernel) —
    since the scheduling unification (2026-10-08) there is no no-op path:
    either a job is created, or the call says exactly why it was not."""

    def __init__(self, worker_ref=None):
        self._worker_ref = worker_ref   # callable -> JobWorker | None

    def _worker(self):
        try:
            return self._worker_ref() if self._worker_ref else None
        except Exception:
            return None

    def schedule(self, task: str, when: str) -> dict:
        w = self._worker()
        if w is None:
            self.diary(f"schedule (NOT activated — automation unavailable): {when} — {task}")
            return {"ok": False,
                    "note": "durable automation is not running in this context — "
                            "intent noted in diary, no job created"}
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from ..automation.models import Job, JobTrigger, display_local, iso
        tz = w.default_timezone
        z = ZoneInfo(tz) if tz else None
        when = (when or "").strip()
        trigger = None
        try:
            # "HH:MM" -> one_time today (tomorrow if already past)
            if re.fullmatch(r"\d{1,2}:\d{2}", when):
                h, m = (int(x) for x in when.split(":"))
                if not (h <= 23 and m <= 59):
                    raise ValueError("time out of range")
                base = datetime.now(z).replace(hour=h, minute=m, second=0, microsecond=0)
                if base <= datetime.now(z):
                    from datetime import timedelta
                    base += timedelta(days=1)
                trigger = JobTrigger(kind="one_time", at=base.strftime("%Y-%m-%dT%H:%M"))
            else:
                # ISO datetime (naive = job tz, aware = used as-is)
                dt = datetime.fromisoformat(when)
                if dt.tzinfo is None and z:
                    dt = dt.replace(tzinfo=z)
                if dt <= datetime.now(z):
                    raise ValueError("time is in the past")
                trigger = JobTrigger(kind="one_time", at=dt.astimezone(
                    z or ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M"))
        except (ValueError, TypeError) as e:
            return {"ok": False, "note": f"could not parse when={when!r} ({e}) — "
                                         "use 'HH:MM' or an ISO datetime; for "
                                         "recurring schedules use the automation_job tool"}
        # Phase 8: a follow-up against an EXISTING pending reminder updates
        # THAT job ('Remind me to send the invoice.' -> 'Tomorrow.' ->
        # 'Actually at 10 AM.' = one job whose trigger moves), never a
        # duplicate. Match on owner + description + pending + never run.
        existing = None
        for j in w.jobs():
            if (j.owner == "main" and j.state == "pending" and j.enabled
                    and j.description == f"remind: {task[:120]}"
                    and j.trigger.kind == "one_time" and not j.last_run):
                existing = j
                break
        if existing is not None and hasattr(w, "reschedule"):
            w.reschedule(existing, trigger)
            self.diary(f"rescheduled (durable job {existing.id}): {when} — {task}")
            return {"ok": True, "job": existing.id, "updated": True,
                    "next_run": display_local(existing.next_run, existing.timezone)}
        job = Job(owner="main", description=f"remind: {task[:120]}",
                  action={"type": "agent_task", "task": f"Remind the user: {task}"},
                  trigger=trigger, timezone=tz, enabled=True,
                  retry_policy={"max_attempts": 2, "backoff_seconds": 60},
                  max_runtime=600.0, state="pending")
        w.create_job(job)
        self.diary(f"scheduled (durable job {job.id}): {when} — {task}")
        return {"ok": True, "job": job.id,
                "next_run": display_local(job.next_run, job.timezone)}

    def list(self) -> list[dict]:
        w = self._worker()
        if w is None:
            return []
        from ..automation.models import display_local
        out = []
        for j in w.jobs():
            if (j.owner or "") in ("main",) and j.enabled and j.state not in ("cancelled",):
                out.append({"id": j.id, "description": j.description,
                            "next_run": display_local(j.next_run, j.timezone),
                            "state": j.state})
        return out

    def diary(self, text: str) -> None:
        from ..memory import md
        md.diary_add(text)


class _Entity:
    """Entity memory over the structured store (type='entity')."""
    def __init__(self, structured):
        self._s = structured

    def remember_entity(self, name: str, kind: str, **attrs) -> object:
        content = f"{kind}: {name}" + (f" — {attrs}" if attrs else "")
        return self._s.remember(content, type="entity", source="user",
                                 key=f"entity.{name.lower()}", subject=name,
                                 tags=[kind, name.lower()])

    def recall_entity(self, name: str) -> list:
        return self._s.recall(name, k=5)


class MemoryStack:
    """Facade: memory.<kind> gives the kernel one object per store.

    Phase 3: `structured` is the canonical user-facing store (facts,
    preferences, events, workflows, entities) with provenance + governance;
    the other stores adapt the pre-existing systems."""
    def __init__(self, structured_path=None, worker_ref=None):
        self.working: WorkingMemory = _Working()
        self.episodic: EpisodicMemory = _Episodic()
        self.semantic: SemanticMemory = _Semantic()
        self.procedural: ProceduralMemory = _Procedural()
        # worker_ref: callable -> JobWorker|None — temporal.schedule creates
        # REAL durable jobs through the one scheduling architecture
        self.temporal: TemporalMemory = _Temporal(worker_ref=worker_ref)
        from .. import paths
        from ..memory.store import StructuredMemory
        self.structured = StructuredMemory(structured_path or
                                           paths.PROJECT_ROOT / "memory" / "store.json")
        self.entities: EntityMemory = _Entity(self.structured)
