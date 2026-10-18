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
    from .. import safeio
    safeio.append_text(p, f"\n## {datetime.now():%H:%M:%S}{extra}\n{message}\n")
    # Queued, not embedded here: the write path must never block on Ollama, and
    # without this a fact stayed semantically unfindable until the 12 h rebuild.
    from . import search as _search
    _search.mark_dirty(p)
    return p


def add_facts(path: Path, text: str) -> dict:
    """Write durable facts (profile.md / longterm.md) without duplicating them.

    Both writers used to do `file.write(old + '\\n- ' + text)` and the model was
    handed multi-line blobs, so the user's profile accumulated the same section
    nine times, structural junk as facts ('- ## Personal Preferences and
    Settings'), the assistant's own task chatter ('- Completed task. Remember to
    save and review the progress in your profile.'), and three contradicting
    '- Hardware: …' lines. Those duplicate bullets are what drowned the real
    answer in the recall measurement — four copies of the software list ranked
    above the one line that says what the project is."""
    lines = []
    for raw in (text or "").splitlines():
        c = _clean_fact(raw)
        # '## Personal Preferences and Settings' is structure the model echoed,
        # not a fact — but '## Time zone: UTC+5.5' still is one.
        if raw.strip().startswith("#") and ":" not in c:
            continue
        if c and not _SELF_TALK.search(c) \
                and c.lower() not in [x.lower() for x in lines]:
            lines.append(c)
    if not lines:
        return {"added": 0, "duplicates": 0, "updated": 0, "file": str(path)}
    rows = (path.read_text(encoding="utf-8").splitlines() if path.exists() else
            [_HEADERS.get(path.stem, f"# {path.stem.replace('_', ' ').title()}")])
    added = dupes = updated = 0
    for c in lines:
        # Compare the FACT, not the line: promotions carry a '[source: model: run
        # 3]' tag that changes every time, so three promotions of one fact were
        # three distinct bullets.
        key = _finger(_fact_core(c))
        bullet = next((i for i, r in enumerate(rows)
                       if _finger(_fact_core(_clean_fact(r))) == key), None)
        if bullet is not None:
            rows[bullet] = f"- {c}"           # keep the freshest provenance
            dupes += 1
            continue
        subj = _subject(c)
        clash = None
        if subj:
            clash = next((i for i, r in enumerate(rows)
                          if r.strip().startswith("-")
                          and _subject(_fact_core(_clean_fact(r))) == subj), None)
        if clash is not None:                     # same subject, new value: update
            rows[clash] = f"- {c}"
            updated += 1
        else:
            rows.append(f"- {c}")
            added += 1
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(rows).rstrip() + "\n", encoding="utf-8")
    tmp.replace(path)
    from . import search as _search
    _search.mark_dirty(path)
    return {"added": added, "duplicates": dupes, "updated": updated, "file": str(path)}


_HEADERS = {"profile": "# User profile", "longterm": "# Long-term memory"}


def _fact_core(s: str) -> str:
    """The fact without its provenance tag: 'BEE runs locally [source: model]'
    and 'BEE runs locally [source: user]' are one fact, stated once."""
    return re.sub(r"\s*\[source:[^\]]*\]\s*$", "", s or "").strip()


def _clean_fact(raw: str) -> str:
    s = re.sub(r"^(?:[-*•]\s*)+", "", (raw or "").strip())
    s = re.sub(r"^#+\s*", "", s).strip()
    return re.sub(r"\s+", " ", s).strip(" .\t")[:300]


# The assistant's own workflow commentary, mistaken for facts about the user.
# 'Completed' and 'Finished' are only rejected when they talk about a task, so
# the real fact 'Completed the data migration on 3 Oct' still saves.
_SELF_TALK = re.compile(
    r"^(?:completed|finished)\b[^\n]{0,60}\b(?:all\s+)?tasks?\b"
    r"|^(?:next steps?|remember to|task is complete|ready to (?:relax|for next)"
    r"|i will|i am going to|i just)\b", re.I)


def _finger(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _subject(s: str) -> str:
    """'Hardware: Windows, RTX 3050' -> 'hardware'. '' when not a keyed fact."""
    m = re.match(r"([A-Za-z][A-Za-z0-9 /().+-]{1,28}?):\s+\S", s or "")
    return _finger(m.group(1)) if m else ""


def chunk_md(p: Path) -> list[tuple[str, str]]:
    """(source, chunk) pairs — chunked at ~400 chars on blank lines.

    Logs are dropped PER PARAGRAPH, before the ~400-char merge: filtering the
    merged chunk instead lets one transcript block drag a genuine neighbouring
    note out of memory with it."""
    if not p.exists():
        return []
    txt = p.read_text(encoding="utf-8", errors="ignore")
    paras = [pp.strip() for pp in re.split(r"\n\s*\n", txt)
             if pp.strip() and not is_transcript(pp)]
    chunks, cur = [], ""
    for para in paras:
        if len(cur) + len(para) + 2 > 400 and cur:
            chunks.append(cur)
            cur = para
        else:
            cur = (cur + "\n\n" + para) if cur else para
    if cur:
        chunks.append(cur)
    return [(str(p), c) for c in chunks if c]


# A diary block written by the agent loop is a LOG of one exchange:
# "## 21:41:16 [model=local]\ntask: …\nresult: …". Those blocks are not facts —
# and because they quote the question, they embed very close to the next time the
# user asks the same thing. With ~1,300 of them per day they crowded the actual
# profile facts out of both keyword and vector recall, so the assistant answered
# "I don't have anything stored" while quoting its own past failures at itself.
# Genuine diary notes (`## 09:12:03` + "note (fast path): …") have no [model= tag
# and stay indexed.
TRANSCRIPT_RE = re.compile(r"^##\s*\d{1,2}:\d{2}(?::\d{2})?\s*\[model=", re.M)


def is_transcript(chunk: str) -> bool:
    return bool(TRANSCRIPT_RE.search(chunk or ""))


def all_chunks() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for f in sorted(paths.DIARY_DIR.glob("*.md")):
        out.extend(chunk_md(f))
    for f in sorted(paths.LESSONS_DIR.glob("*.md")):
        out.extend(chunk_md(f))
    for f in (paths.PROFILE_MD, paths.LONGTERM_MD, paths.MEMORY_DIR / "wins.md"):
        out.extend(chunk_md(f))
    # Capability workflows: what each skill does lives in its SKILL.md, so
    # "how do I ..." questions retrieve the workflow, not just the fact that
    # a skill with that name exists (system prompt carries only the index).
    try:
        for f in sorted(paths.SKILLS_DIR.glob("*/SKILL.md")):
            out.extend(chunk_md(f))
    except Exception:
        pass
    return out


def record_win(task: str, output: str, cap: int = 500) -> bool:
    """One-line digest of a SUCCESSFUL tool-using task (task -> outcome).

    Diary transcripts are deliberately unindexed (they crowd out facts), so
    past successes would otherwise be invisible to recall. One line each,
    successes only, capped file — the compact form the anti-crowding lesson
    allows. Returns True when written.
    """
    task, output = (task or "").strip(), (output or "").strip()
    if not task or not output:
        return False
    line = f"- {task[:160]} => {(output[:200]).replace(chr(10), ' ')}"
    try:
        p = paths.MEMORY_DIR / "wins.md"
        lines = []
        if p.exists():
            lines = [ln for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if ln.strip()]
        if lines and lines[-1] == line:
            return False  # already the latest — no dup growth
        lines.append(line)
        p.write_text("\n".join(lines[-cap:]) + "\n", encoding="utf-8")
        try:
            from .search import mark_dirty
            mark_dirty(str(p))
        except Exception:
            pass
        return True
    except Exception:
        return False


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
