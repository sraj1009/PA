"""Structured memory store (Phase 3, Parts C/D).

Five conceptual stores are exposed as ONE structured store with typed items:
  fact / preference / event / workflow / entity  (+ working-memory notes)

Governance rules (enforced in code, not convention):
- every item carries: type, source, confidence, created_at, updated_at,
  importance, expiry (optional), provenance, tags
- source is one of: user | tool | web | model_inference
- model inferences are confidence-capped (<=0.5) and can NEVER be silently
  promoted to a user fact: an update may set source="user" only with
  asserted_by_user=True (an explicit user re-statement)
- web-derived content is never trusted policy (trusted_policy=False always)
- content is privacy-redacted on store (secrets never persist here)
- nothing is auto-saved: items appear only via remember()/explicit facts
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .. import privacy

log = logging.getLogger("bee.memory")

VALID_TYPES = {"fact", "preference", "event", "workflow", "entity", "working"}
VALID_SOURCES = {"user", "tool", "web", "model_inference"}
_CONF_FLOOR = {"user": 0.95, "tool": 0.8, "web": 0.5, "model_inference": 0.5}
_CONF_CAP = {"model_inference": 0.5, "web": 0.5}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class MemoryItem:
    id: str
    type: str                      # fact | preference | event | workflow | entity
    content: str
    source: str                    # user | tool | web | model_inference
    confidence: float
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    importance: int = 3            # 1..5
    expiry: str | None = None      # ISO datetime; None = no expiry
    provenance: str = ""           # where it came from ("user message 2026-10-05")
    key: str = ""                  # upsert key, e.g. "project.name"
    subject: str = ""              # entity name for entity items
    tags: list[str] = field(default_factory=list)
    trusted_policy: bool = False   # web-derived is NEVER trusted policy
    superseded_by: str = ""        # set when a conflicting item replaced this
    deleted: bool = False

    def expired(self) -> bool:
        """Timezone-safe expiry check (fixed 2026-10-08): expiries are stored
        UTC-canonical ('+00:00' suffix), so comparing them to NAIVE
        datetime.now() raised TypeError -> silently 'never expired'. Now:
        naive expiry = local time, aware expiry = compared as aware."""
        if not self.expiry:
            return False
        try:
            import datetime as _dt
            exp = _dt.datetime.fromisoformat(self.expiry)
            now = _dt.datetime.now()
            if exp.tzinfo is None:
                return exp <= now
            return exp <= now.astimezone()
        except Exception:
            return False

    def to_dict(self) -> dict:
        return {
            "id": self.id, "type": self.type, "content": self.content,
            "source": self.source, "confidence": self.confidence,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "importance": self.importance, "expiry": self.expiry,
            "provenance": self.provenance, "key": self.key, "subject": self.subject,
            "tags": self.tags, "trusted_policy": self.trusted_policy,
            "superseded_by": self.superseded_by, "deleted": self.deleted,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryItem":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


class StructuredMemory:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        # RLock: forget(query=...) re-enters through recall() while holding it
        self._lock = threading.RLock()
        self._items: dict[str, MemoryItem] = {}
        if self.path and self.path.exists():
            # Corrupt-file resilience (Phase 12 reliability): a totally
            # unreadable file degrades to an EMPTY store (never crashes);
            # a file with a few bad rows salvages the good rows instead of
            # losing everything.
            rows: list = []
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    rows = data.get("items", []) or []
                elif isinstance(data, list):
                    rows = data
            except Exception:
                rows = []
            skipped = 0
            for row in rows:
                try:
                    it = MemoryItem.from_dict(row)
                    self._items[it.id] = it
                except Exception:
                    skipped += 1
            if skipped:
                log.warning("memory store: skipped %d corrupt row(s), "
                            "salvaged %d", skipped, len(self._items))

    # ---------------------------------------------------------- remember
    def remember(self, content: str, type: str = "fact", source: str = "user",
                 confidence: float | None = None, importance: int = 3,
                 expiry: str | None = None, provenance: str = "",
                 key: str = "", subject: str = "", tags: list[str] | None = None) -> MemoryItem:
        if source not in VALID_SOURCES:
            raise ValueError(f"invalid memory source: {source}")
        if type not in VALID_TYPES:
            raise ValueError(f"invalid memory type: {type}")
        content = str(content or "").strip()
        if not content:
            raise ValueError("cannot remember an empty statement")
        # privacy boundary: secrets never persist into memory
        content, _n = privacy.redact(content)
        # confidence governance
        if confidence is None:
            confidence = _CONF_FLOOR[source]
        cap = _CONF_CAP.get(source)
        if cap is not None:
            confidence = min(confidence, cap)
        if source == "user":
            confidence = max(confidence, 0.9)   # explicit user statements are high-confidence
        trusted = False                          # web/tool inference never becomes policy
        with self._lock:
            new_id = f"mem_{uuid.uuid4().hex[:10]}"
            item = MemoryItem(id=new_id, type=type, content=content, source=source,
                              confidence=round(float(confidence), 3),
                              importance=max(1, min(5, int(importance))),
                              expiry=expiry, provenance=provenance or f"{source} {_now()}",
                              key=key, subject=subject, tags=tags or [],
                              trusted_policy=trusted)
            if key:
                for i in self._items.values():
                    if i.key == key and not i.deleted and i.id != new_id:
                        i.superseded_by = new_id
                        i.deleted = True        # tombstone, kept for audit
            self._items[new_id] = item
            self._persist_locked()
            return item

    # ------------------------------------------------------------- recall
    def recall(self, query: str, k: int = 5, include_expired: bool = False) -> list[MemoryItem]:
        q = [w for w in re.split(r"\W+", (query or "").lower()) if len(w) > 2]
        scored = []
        with self._lock:
            for it in self._items.values():
                if it.deleted:
                    continue
                if not include_expired and it.expired():
                    continue
                text = f"{it.key} {it.subject} {it.content} {' '.join(it.tags)}".lower()
                score = 0
                for w in q:
                    if w in text:
                        score += 2
                    if w == it.key.lower() or w == it.subject.lower():
                        score += 5
                if it.key and it.key.lower() in [x for x in q]:
                    score += 5
                if score:
                    scored.append((score, it.importance, it.confidence, it.updated_at, it))
        scored.sort(key=lambda t: (t[0], t[1], t[2], t[3]), reverse=True)
        return [s[4] for s in scored[:k]]

    def recall_by_key(self, key: str) -> MemoryItem | None:
        with self._lock:
            for it in self._items.values():
                if it.key == key and not it.deleted and not it.expired():
                    return it
        return None

    # ------------------------------------------------------------- update
    def update(self, item_id: str, content: str | None = None, confidence: float | None = None,
               importance: int | None = None, expiry: str | None = None,
               source: str | None = None, asserted_by_user: bool = False,
               tags: list[str] | None = None) -> MemoryItem:
        with self._lock:
            it = self._items.get(item_id)
            if it is None or it.deleted:
                raise KeyError(f"no such memory: {item_id}")
            # governance: a non-user item can only become 'user' via an
            # EXPLICIT user re-statement (asserted_by_user=True)
            if source is not None:
                if source != it.source and source == "user" and it.source != "user" \
                        and not asserted_by_user:
                    raise PermissionError(
                        "cannot promote a model inference / web / tool memory to a user "
                        "fact without an explicit user statement (asserted_by_user=True)")
                if source not in VALID_SOURCES:
                    raise ValueError(f"invalid memory source: {source}")
                it.source = source
                if source in _CONF_CAP and confidence is None:
                    it.confidence = min(it.confidence, _CONF_CAP[source])
                elif source == "user" and asserted_by_user and confidence is None:
                    # an explicit user re-statement restores user-level confidence
                    it.confidence = max(it.confidence, _CONF_FLOOR["user"])
            if content is not None:
                c, _ = privacy.redact(str(content).strip())
                it.content = c
            if confidence is not None:
                it.confidence = round(float(confidence), 3)
                cap = _CONF_CAP.get(it.source)
                if cap is not None:
                    it.confidence = min(it.confidence, cap)
            if importance is not None:
                it.importance = max(1, min(5, int(importance)))
            if expiry is not None:
                it.expiry = expiry
            if tags is not None:
                it.tags = list(tags)
            it.updated_at = _now()
            self._persist_locked()
            return it

    # ------------------------------------------------------------- forget
    def forget(self, item_id: str | None = None, query: str | None = None) -> list[str]:
        """Delete by id, or (for 'Forget that.') the LAST matched item when a
        query is given; returns the ids removed."""
        removed: list[str] = []
        with self._lock:
            if item_id:
                it = self._items.get(item_id)
                if it and not it.deleted:
                    it.deleted = True
                    it.updated_at = _now()
                    removed.append(it.id)
            elif query:
                matches = self.recall(query, k=1)
                if matches:
                    m = matches[0]
                    m.deleted = True
                    m.updated_at = _now()
                    removed.append(m.id)
            if removed:
                self._persist_locked()
        return removed

    # ---------------------------------------------------------- summarize
    def summarize(self, limit: int = 12) -> str:
        """Compact, source-labeled digest for context injection."""
        with self._lock:
            live = [i for i in self._items.values() if not i.deleted and not i.expired()]
        live.sort(key=lambda i: (i.importance, i.confidence), reverse=True)
        if not live:
            return ""
        L = ["Known memories (source-labeled):"]
        for i in live[:limit]:
            src = f"from {i.source}" + (f", conf {i.confidence:.2f}" if i.source != "user" else "")
            sub = f" [{i.subject}]" if i.subject else ""
            L.append(f"- ({i.type}{sub}) {i.content[:120]}  {src}")
        return "\n".join(L)

    # ------------------------------------------------------------- expire
    def expire(self) -> int:
        """Purge expired + long-tombstoned items; returns count removed."""
        with self._lock:
            n = 0
            for it in list(self._items.values()):
                if it.expired():
                    del self._items[it.id]
                    n += 1
                elif it.deleted and it.updated_at < time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400 * 14)):
                    del self._items[it.id]
                    n += 1
            if n:
                self._persist_locked()
            return n

    # -------------------------------------------------------------- misc
    def all(self, include_deleted: bool = False) -> list[MemoryItem]:
        with self._lock:
            return [i for i in self._items.values() if include_deleted or not i.deleted]

    def _persist_locked(self):
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"updated": _now(),
                       "items": [i.to_dict() for i in self._items.values()]}
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:
            pass  # memory persistence is best-effort
