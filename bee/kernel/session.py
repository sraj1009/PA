"""AgentSession (Phase 2) — persistent conversation state.

Follow-ups ("Tomorrow." / "Actually make it 10 AM.") must resolve against
the ACTIVE task, not be treated as unrelated prompts. Resolution is a
deterministic kernel decision (heuristics below) — the LLM only ever sees
the MERGED text.

Persisted as JSON under memory/sessions/<id>.json (git-ignored data dir).
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .models import new_id

STOP_WORDS = {"stop", "stop it", "cancel", "cancel it", "abort", "never mind",
              "nevermind", "forget it", "drop it", "halt"}

TIME_RE = re.compile(
    r"\b(tomorrow|tonight|today|later|eod|noon|midnight|next (?:week|month)|"
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"\d{1,2}(:\d{2})?\s*(?:am|pm)?|in \d+ (?:min|minute|hour|day)s?)\b", re.I)
_REVISE_RE = re.compile(
    r"^(actually|change|make it|instead|update|fix|no wait|wait|no,|but)\b", re.I)
_REFS_RE = re.compile(r"\b(that|the (?:task|one|above|folder|file|draft|invoice|email|reminder))\b", re.I)

MAX_TURNS = 40
MAX_RECENT = 6


@dataclass
class AgentSession:
    id: str = field(default_factory=lambda: new_id("sess"))
    created: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    updated: str = ""
    turns: list[dict] = field(default_factory=list)          # {role, text, ts}
    active_task_id: str = ""
    active_task_text: str = ""
    last_output: str = ""
    entities: dict = field(default_factory=dict)             # referenced entities
    pending_confirmation: str = ""                            # open question/permission
    recent_results: list[dict] = field(default_factory=list) # last tool outcomes
    last_time_hint: str = ""
    last_memory_id: str = ""          # Phase 3: target of a bare 'Forget that.'

    # ------------------------------------------------------------ helpers
    def _touch(self):
        self.updated = time.strftime("%Y-%m-%dT%H:%M:%S")

    def add_turn(self, role: str, text: str):
        self.turns.append({"role": role, "text": text[:1000],
                           "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
        if len(self.turns) > MAX_TURNS:
            del self.turns[: len(self.turns) - MAX_TURNS]
        self._touch()

    def note_result(self, tool: str, ok: bool, preview: str):
        self.recent_results.append({"tool": tool, "ok": ok, "preview": preview[:200],
                                    "ts": time.strftime("%H:%M:%S")})
        if len(self.recent_results) > MAX_RECENT:
            del self.recent_results[: len(self.recent_results) - MAX_RECENT]
        m = re.search(r"(?:path|file|folder|dir)[\"\':=\s]+([\w./\\ -]+)", preview, re.I)
        if m:
            self.entities["last_path"] = m.group(1).strip()
        self._touch()

    def record_task(self, task, output: str, ok: bool):
        self.active_task_id = task.id
        self.active_task_text = task.text[:600]
        self.last_output = (output or "")[:1000]
        for o in task.observations[-MAX_RECENT:]:
            self.note_result(o.tool, o.ok, o.result_text[:200])
        self.add_turn("bee", output or task.error or "")
        self._touch()

    # --------------------------------------------------- follow-up resolve
    def resolve_followup(self, text: str) -> tuple[str, str]:
        """Returns one of:
        ('cancel', <active task text or ''>)   — user wants to stop
        ('continue', <merged task text>)        — resolve against active task
        ('new', <text>)                          — unrelated, start fresh
        """
        t = (text or "").strip()
        low = t.lower().strip(" .!?")
        if low in STOP_WORDS:
            return ("cancel", self.active_task_text)
        if not t or not self.active_task_text:
            return ("new", t)
        # short message that references time / a revision / the prior object
        short = len(t) <= 90
        is_time = bool(TIME_RE.search(t))
        is_revise = bool(_REVISE_RE.match(t))
        is_ref = bool(_REFS_RE.search(t))
        if short and (is_time or is_revise or is_ref or len(t.split()) <= 4):
            merged = f"{self.active_task_text} — follow-up: {t}"
            if is_time:
                self.last_time_hint = t
            return ("continue", merged)
        # a time-only nudge ("Tomorrow.") even if longer
        if is_time and len(t) <= 40:
            self.last_time_hint = t
            return ("continue", f"{self.active_task_text} — follow-up: {t}")
        return ("new", t)

    def context_block(self) -> str:
        """Compact state block the kernel can inject so the model has the
        conversation frame (the kernel owns state; the model reads it)."""
        if not (self.active_task_text or self.entities or self.pending_confirmation):
            return ""
        L = ["## Conversation state (resolved by the kernel, for context)"]
        if self.active_task_text:
            L.append(f"- Active task: {self.active_task_text[:300]}")
        if self.last_time_hint:
            L.append(f"- Last time instruction: {self.last_time_hint}")
        if self.pending_confirmation:
            L.append(f"- Pending confirmation: {self.pending_confirmation[:200]}")
        if self.entities:
            L.append("- Entities: " + ", ".join(f"{k}={v}" for k, v in list(self.entities.items())[:8]))
        if self.recent_results:
            L.append("- Recent tool results: " + "; ".join(
                f"{r['tool']}({'ok' if r['ok'] else 'FAIL'}) {r['preview'][:80]}"
                for r in self.recent_results[-3:]))
        return "\n".join(L)

    # ---------------------------------------------------------- persistence
    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("id", "created", "updated", "turns", "active_task_id",
                 "active_task_text", "last_output", "entities",
                 "pending_confirmation", "recent_results", "last_time_hint",
                 "last_memory_id")}

    @classmethod
    def from_dict(cls, d: dict) -> "AgentSession":
        s = cls(id=d.get("id") or new_id("sess"))
        for k, v in d.items():
            if hasattr(s, k):
                setattr(s, k, v)
        return s

    def save(self, dirpath: str | Path) -> Path:
        p = Path(dirpath)
        p.mkdir(parents=True, exist_ok=True)
        f = p / f"{self.id}.json"
        f.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1),
                     encoding="utf-8")
        return f

    @classmethod
    def load(cls, dirpath: str | Path, sid: str) -> "AgentSession | None":
        f = Path(dirpath) / f"{sid}.json"
        if not f.exists():
            return None
        try:
            return cls.from_dict(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            return None
