"""Deterministic memory requests (Phase 3, Part C).

'Remember that my project is called BEE.' / 'What do you remember about this
project?' / 'Forget that.' — handled by the kernel BEFORE any LLM call:
fast, offline, and verifiable (the kernel checks the store actually changed).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_REMEMBER_RE = re.compile(
    r"^\s*(?:please\s+)?remember\s+(?:that\s+)?(?P<text>.+)$", re.I | re.S)
_RECALL_RE = re.compile(
    r"^\s*(?:what do you (?:remember|know) about|what do you recall about|"
    r"do you remember|recall|tell me (?:what you (?:remember|know))\s+about)\s+"
    r"(?P<q>.+)?\s*$", re.I | re.S)
_FORGET_RE = re.compile(
    r"^\s*(?:please\s+)?forget\s+(?:that\s+|this\s+)?(?P<q>.+?)\s*\.?\s*$", re.I | re.S)
_KEY_VALUE_RE = re.compile(
    r"^\s*(?:my\s+|the\s+)?(?P<subj>[\w -]{2,24}?)(?:\s+(?:is|are|was|called|named|'s|"
    r"equals|=\s*))\s+(?P<val>.+)$", re.I)


@dataclass
class MemoryRequest:
    kind: str            # remember | recall | forget
    text: str = ""       # raw content / query
    key: str = ""        # extracted subject.value key (remember)
    subject: str = ""
    query: str = ""      # normalized recall query
    last: bool = False   # forget 'that' -> most recent item


def parse(text: str) -> MemoryRequest | None:
    t = (text or "").strip()
    m = _REMEMBER_RE.match(t)
    if m:
        content = m.group("text").strip()
        req = MemoryRequest(kind="remember", text=content)
        kv = _KEY_VALUE_RE.match(content)
        if kv:
            subj = re.sub(r"\s+", " ", kv.group("subj").strip().lower())
            subj = subj.removeprefix("my ")
            req.key = subj
            req.subject = subj
            req.text = kv.group("val").strip()
        return req
    m = _RECALL_RE.match(t)
    if m:
        q = (m.group("q") or "").strip().rstrip(".?")
        q = re.sub(r"^(this|that|my|the)\s+", "", q, flags=re.I)
        return MemoryRequest(kind="recall", query=q or "anything", text=t)
    m = _FORGET_RE.match(t)
    if m:
        q = (m.group("q") or "").strip()
        if q in ("", "that", "this", "it", "it."):
            return MemoryRequest(kind="forget", last=True)
        return MemoryRequest(kind="forget", query=q)
    return None
