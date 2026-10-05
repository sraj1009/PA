"""Memory interfaces (Phase 2) — clean contracts over the EXISTING systems.

The memory system itself is NOT redesigned here. These are the five
conceptual stores as protocols, plus MemoryStack: a thin adapter that wires
the current implementations (episodes, memory search/RAG, memory.md,
skills, scheduler/diary) behind those interfaces so the kernel only ever
talks to abstractions.
"""
from __future__ import annotations

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
    def add(self, text: str, kind: str = "longterm") -> None:
        from .. import paths
        t = str(text or "").strip()
        if not t:
            return
        p = paths.PROFILE_MD if kind == "profile" else paths.LONGTERM_MD
        if p.exists():
            p.write_text(p.read_text(encoding="utf-8").rstrip() + f"\n\n- {t}\n",
                         encoding="utf-8")
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"# {'Profile' if kind == 'profile' else 'Long-term memory'}\n\n- {t}\n",
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
    def schedule(self, task: str, when: str) -> dict:
        # User cron jobs are a documented no-op until the scheduling phase —
        # the adapter records intent in the diary and says so honestly.
        self.diary(f"schedule (not yet active): {when} — {task}")
        return {"ok": False, "note": "scheduling not active yet; intent noted in diary"}

    def list(self) -> list[dict]:
        return []

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
    def __init__(self, structured_path=None):
        self.working: WorkingMemory = _Working()
        self.episodic: EpisodicMemory = _Episodic()
        self.semantic: SemanticMemory = _Semantic()
        self.procedural: ProceduralMemory = _Procedural()
        self.temporal: TemporalMemory = _Temporal()
        from .. import paths
        from ..memory.store import StructuredMemory
        self.structured = StructuredMemory(structured_path or
                                           paths.PROJECT_ROOT / "memory" / "store.json")
        self.entities: EntityMemory = _Entity(self.structured)
