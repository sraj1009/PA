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
    r"do you remember|recall|tell me (?:what you (?:remember|know))\s+about|"
    # 'Search your memory for X' / 'check my memory about X' — the eval asked
    # this in exactly those words and the model answered from thin air instead
    # ("I do not have direct access to hardware information"), because only the
    # 'what do you remember' phrasings reached the deterministic recall path.
    r"search(?:ing)?\s+(?:my|your|the)\s+memor(?:y|ies)\s+(?:for|about|on)|"
    r"(?:check|query)\s+(?:my|your|the)\s+memor(?:y|ies)\s+(?:for|about|on)|"
    r"memor(?:y|ies)\s+search\s+(?:for|about|on)|"
    r"look\s+(?:it\s+|that\s+)?up\s+in\s+(?:my|your|the)\s+memor(?:y|ies))\s*"
    r"(?P<q>.+?)?\s*$", re.I | re.S)
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


_QUESTION_LEAD = re.compile(
    r"^\s*(?:who|what|when|where|which|how|why|whether|do\s+i|did\s+i|is|are|was|were|"
    r"can|could|should|tell)\b", re.I)

# A recall about the box itself is answerable without any stored fact: the CIM
# inventory is authoritative and always current. 'Search your memory for
# "hardware" and tell me what you know about this machine's GPU' used to return
# "I don't have anything stored about 'hardware' yet" — true but useless, since
# the assistant was sitting on the machine it was asked about.
_HW_QUERY_RE = re.compile(
    r"\b(?:gpu|graphics|vram|cuda|cpu|processor|chipset|ram|memory\s+(?:stick|card|size|"
    r"modules?)|ssd|nvme|hard\s*drive|laptop|desktop|notebook|workstation|pc|"
    r"computer|machine(?!s?\s+learning)|hardware|spec(?:s|ification)?s?|motherboard)\b",
    re.I)


def is_hardware_query(text: str) -> bool:
    return bool(_HW_QUERY_RE.search(text or ""))


def _as_recall(content: str, raw: str) -> MemoryRequest:
    """'Remember my GPU from last time?' is a RECALL request.

    `_REMEMBER_RE` used to win for every 'remember …' sentence, so a question
    became a stored fact: the assistant 'remembered' that it had been asked
    something and never answered it (the rag_gpu_memory eval task failed exactly
    this way — output was `Remembered: my GPU from last time? Tell me which one
    this machine has.`)."""
    q = (content or "").split("?")[0]
    q = re.sub(r"\bremember\b\s*(?:that\s+)?", "", q, flags=re.I)
    q = re.sub(r"^(?:do\s+you|can\s+you)\s+", "", q, flags=re.I)
    q = re.sub(r"\b(from\s+last\s+time|again|that\s+you\s+saved)\b", "", q, flags=re.I)
    q = re.sub(r"^(?:my|the|this|that)\s+", "", q.strip(), flags=re.I)
    q = re.sub(r"[.!;,]\s*$", "", q).strip()
    return MemoryRequest(kind="recall", query=q or "anything", text=raw)


def parse(text: str) -> MemoryRequest | None:
    t = (text or "").strip()
    m = _REMEMBER_RE.match(t)
    if m:
        content = m.group("text").strip()
        if "?" in content or _QUESTION_LEAD.match(content):
            return _as_recall(content, t)
        req = MemoryRequest(kind="remember", text=content)
        kv = _KEY_VALUE_RE.match(content)
        if kv:
            subj = re.sub(r"\s+", " ", kv.group("subj").strip().lower())
            subj = subj.removeprefix("my ")
            req.key = subj
            req.subject = subj
            # Stop the value at the sentence the user actually meant.
            # 'Remember that my favorite editor is Neovim. Use the profile memory
            # tool.' stored "Neovim. Use the profile memory tool." — the trailing
            # instruction became part of the fact, and every eval run appended
            # that fragment to the user's memory.
            val = re.split(r"(?<=[.!?])\s+(?=[A-Z])", kv.group("val").strip(), 1)[0]
            req.text = val.strip().rstrip(".!?")
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
