"""Markdown memory primitives + keyword search fallback.

Files:
  diary/YYYY-MM-DD.md   episodic, timestamped task notes
  lessons/YYYY-MM-DD.md self-review bullets (worked / failed / next)
  profile.md            user preferences (bullet list)
  longterm.md           durable facts (bullet list)
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .. import paths


def diary_add(message: str, model: str = "", escalated: bool = False) -> Path:
    p = paths.DIARY_DIR / f"{datetime.now():%Y-%m-%d}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    extra = f" [model={model}{'|cloud' if escalated else ''}]" if model else ""
    with p.open("a", encoding="utf-8") as f:
        f.write(f"\n## {datetime.now():%H:%M:%S}{extra}\n{message}\n")
    return p


def chunk_md(p: Path) -> list[tuple[str, str]]:
    """(source, chunk) pairs — chunked at ~400 chars on blank lines."""
    if not p.exists():
        return []
    txt = p.read_text(encoding="utf-8", errors="ignore")
    paras = re.split(r"\n\s*\n", txt)
    chunks, cur = [], ""
    for para in paras:
        para = para.strip()
        if not para:
            continue
        if len(cur) + len(para) + 2 > 400 and cur:
            chunks.append(cur)
            cur = para
        else:
            cur = (cur + "\n\n" + para) if cur else para
    if cur:
        chunks.append(cur)
    return [(str(p), c) for c in chunks if c]


def all_chunks() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for f in sorted(paths.DIARY_DIR.glob("*.md")):
        out.extend(chunk_md(f))
    for f in sorted(paths.LESSONS_DIR.glob("*.md")):
        out.extend(chunk_md(f))
    for f in (paths.PROFILE_MD, paths.LONGTERM_MD):
        out.extend(chunk_md(f))
    return out


_TOKEN = re.compile(r"[a-z0-9_]{3,}")


def _score(query: str, chunk: str) -> float:
    q = set(_TOKEN.findall(query.lower()))
    c = _TOKEN.findall(chunk.lower())
    if not q or not c:
        return 0.0
    counts = {}
    for t in c:
        counts[t] = counts.get(t, 0) + 1
    total = sum(1 for t in q if t in counts)
    if total == 0:
        return 0.0
    boost = sum(counts.get(t, 0) for t in q)
    return total / len(q) + min(boost, 8) * 0.05


def memory_search(ctx, query: str, k: int = 6) -> list[dict]:
    """Keyword-ranked search across all memory (always available; no deps)."""
    chunks = all_chunks()
    scored = sorted(((_score(query, ch), src, ch) for src, ch in chunks), reverse=True)
    out = []
    for score, src, ch in scored[:k]:
        if score <= 0:
            break
        rel = src.replace(str(paths.PROJECT_ROOT), ".", 1)
        out.append({"score": round(float(score), 3), "source": rel, "text": ch[:600]})
    return out
