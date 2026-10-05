"""Hybrid RAG over BEE memory — vector + keyword fused with Reciprocal Rank Fusion.

- retrieve(ctx, query, k): ranked grounded chunks with sources.
- auto_context(ctx, task): returns a compact "MEMORY CONTEXT" block when the task
  contains dangling references ("last time", "remember", "my machine", "continue"...)
  so long-horizon/multi-hour tasks stay grounded in state memory.
- recall_eval(...): deterministic retrieval-quality measurement for the eval suite.
"""
from __future__ import annotations

import re

from ..memory import md
from ..memory.search import vector_search

_RRF_K = 60
_TRIGGER = re.compile(
    r"\b(remember|recall(?:ed|ing)?|last time|yesterday|earlier|previously|continue|resume|"
    r"my (machine|setup|gpu|project|preference|notes)|what (did|do) i (tell|ask|say))\b", re.I)


def retrieve(ctx, query: str, k: int = 5) -> list[dict]:
    """RRF fusion of vector (when available) and keyword rankings."""
    kw = md.memory_search(ctx, query, k=max(k, 4))
    vec = vector_search(ctx, query, k=max(k, 4)) or []
    ranked: dict[str, float] = {}
    for rank, item in enumerate(kw):
        key = item["text"][:200]
        ranked[key] = ranked.get(key, 0.0) + 1.0 / (_RRF_K + rank + 1)
    for rank, item in enumerate(vec):
        key = item["text"][:200]
        ranked[key] = ranked.get(key, 0.0) + 1.0 / (_RRF_K + rank + 1)
    items = {}
    for item in kw:
        items[item["text"][:200]] = {**item, "mode": "keyword"}
    for item in vec:
        items.setdefault(item["text"][:200], {**item, "mode": "vector"})
    out = []
    for key, score in sorted(ranked.items(), key=lambda kv: -kv[1])[:k]:
        out.append({**items[key], "rrf": round(float(score), 5)})
    return out


def needs_context(task: str) -> bool:
    return bool(_TRIGGER.search(task or ""))


def auto_context(ctx, task: str, k: int = 4) -> str:
    """Markdown context block for the system/user message, or '' if not needed."""
    if not needs_context(task):
        return ""
    res = retrieve(ctx, task, k=k)
    if not res:
        return ""
    lines = ["## MEMORY CONTEXT (grounded, from your memory — verify before relying)"]
    for r in res:
        src = r.get("source", "?").replace(str(ctx.cfg.workspace), ".", 1)
        lines.append(f"- [{src}] {r['text'][:300]}")
    return "\n".join(lines)


# ------------------------------------------------------- retrieval eval
def recall_eval(chunks: list[tuple[str, str]], questions: list[tuple[str, str]], k: int = 5) -> dict:
    """Deterministic recall@k: for each (question, answer_key), did a chunk
    containing answer_key make the top-k keyword ranking?
    chunks: (source, text); questions: (question, key-substring-in-gold-chunk)."""
    hits, total = 0, 0
    per = []
    for q, key in questions:
        total += 1
        scored = sorted(((md._score(q, c), s, c) for s, c in chunks), reverse=True)[:k]
        ok = any(key.lower() in c.lower() for _s, c in [ (s, c) for _sc, s, c in scored ])
        hits += 1 if ok else 0
        per.append({"q": q[:80], "hit": ok})
    return {"recall_at_k": round(hits / total, 4) if total else None, "k": k,
            "n": total, "hits": hits, "per": per}
