"""Vector memory search (LanceDB, embedded, no server) with keyword fallback.

If LanceDB or the embedder is unavailable, falls back to memory.md.keyword
search transparently — the tool interface is identical.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .. import paths
from . import md

log = logging.getLogger("bee.mem")

TABLE = "bee_memory"
_cache = None


class _VecStore:
    def __init__(self, cfg, client):
        self.cfg = cfg
        self.client = client
        self.lancedb = None
        import lancedb
        self.conn = lancedb.connect(str(paths.VECTOR_DIR))
        self.lancedb = True

    def _has_table(self) -> bool:
        """lancedb renamed table_names() -> list_tables() (0.39 warns on the
        old spelling); going through the deprecated alias risks a silent break
        when it is removed."""
        return TABLE in self.conn.list_tables().tables

    def _table(self):
        if self._has_table():
            return self.conn.open_table(TABLE)
        return self.conn.create_table(TABLE, schema=self._schema(), mode="overwrite")

    def _schema(self):
        import pyarrow as pa
        return pa.schema([
            pa.field("id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("source", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), 768)),
        ])

    def rebuild(self):
        """Clear-before-add (B2/M12 fix, audit 2026-10-06): the old
        implementation did `t.add(rows)` on top of the EXISTING table, so
        every 12 h rebuild APPENDED a full copy — duplicate rows grew
        without bound and search quality degraded over time. Rebuilding now
        replaces the table atomically; row count is stable across rebuilds."""
        chunks = md.all_chunks()
        if not chunks:
            return 0
        texts = [c for _, c in chunks]
        embs = []
        # batch embed (ollama is fine with small batches)
        for i in range(0, len(texts), 8):
            batch = texts[i:i + 8]
            embs.extend(self.client.embed(batch))
        rows = []
        for (src, ch), e in zip(chunks, embs):
            rows.append({"id": f"{src}#{ch[:60]}", "text": ch[:1000], "source": src, "vector": list(map(float, e))})
        if self._has_table():
            self.conn.drop_table(TABLE)
        t = self.conn.create_table(TABLE, schema=self._schema(), mode="overwrite")
        t.add(rows)
        return len(rows)

    def query(self, text: str, k: int = 6) -> list[dict]:
        e = self.client.embed([text])[0]
        t = self._table()
        if t.count_rows() == 0:
            return []
        res = t.search(list(map(float, e))).limit(k).to_list()
        return [{"score": float(r.get("_distance", 0)), "source": r["source"], "text": r["text"]} for r in res]

    def replace_source(self, src: str, chunks: list[str]) -> int:
        """Re-index ONE memory file: drop its old rows, add the current chunks.

        `rebuild()` re-embeds the whole corpus, which is why a fact written
        minutes ago could not be found semantically for up to 12 h (the interval of
        the only job that refreshed the index). This is the incremental path."""
        texts = [c.strip() for c in chunks if c and c.strip()]
        if not texts:
            return 0
        embs = []
        for i in range(0, len(texts), 8):
            embs.extend(self.client.embed(texts[i:i + 8]))
        t = self._table()
        try:
            # paths come from our own code, but this is a filter expression —
            # quote-escape rather than interpolate blindly
            t.delete("source = '" + str(src).replace("'", "''") + "'")
        except Exception as e:
            log.info("could not drop old rows for %s: %s", src, e)
        t.add([{"id": f"{src}#{c[:60]}", "text": c[:1000], "source": src,
                "vector": list(map(float, e))} for c, e in zip(texts, embs)])
        return len(texts)


def get_store(ctx):
    global _cache
    if _cache is None:
        try:
            _cache = _VecStore(ctx.cfg, ctx.client)
        except Exception as e:
            log.info("vector store unavailable (%s) — keyword search only", e)
            _cache = False
    return _cache



# ------------------------------------------------------- incremental indexing
# Durable across restarts: a fact written just before a crash still gets indexed
# on the next flush, instead of waiting for the 12 h rebuild.
def _dirty_file() -> Path:
    return paths.VECTOR_DIR / "dirty.jsonl"


def mark_dirty(path) -> None:
    """Note that a memory file changed. Deliberately cheap and offline — the
    embedding happens in `flush_dirty`, so nothing on the write path can block on
    Ollama (and tests that never run the worker never reach the network)."""
    try:
        paths.VECTOR_DIR.mkdir(parents=True, exist_ok=True)
        with _dirty_file().open("a", encoding="utf-8") as f:
            f.write(str(path) + "\n")
    except Exception as e:
        log.info("could not mark %s dirty: %s", path, e)


def pending_paths() -> list[str]:
    try:
        lines = _dirty_file().read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        if s and s not in out:
            out.append(s)
    return out


def _unindexed_sources(ctx, cap: int = 40) -> list[str]:
    """Memory files that have no rows in the table at all.

    Without this, an index left stale (the queue is empty, and the only other
    refresher is the 12 h rebuild) stays stale forever: nothing marks those files
    dirty again. Capped so a first run after an upgrade cannot spend minutes
    embedding; the remainder stays queued for the next flush."""
    try:
        store = get_store(ctx)
        if store in (None, False):
            return []
        t = store._table()
        n = t.count_rows()
        files = {src for src, _c in md.all_chunks()}
        if n == 0:
            return sorted(files)[:cap]
        have = {r["source"] for r in t.search().select(["source"]).limit(max(n, 1)).to_list()
                if r.get("source")}
        return sorted(f for f in files if f not in have)[:cap]
    except Exception as e:
        log.info("staleness scan skipped: %s", e)
        return []


def flush_dirty(ctx) -> dict:
    """Index whatever changed since the last flush. Best-effort: an unreachable
    embedder leaves the queue intact so the work is retried, not lost."""
    pend = pending_paths()
    if not pend:
        for s in _unindexed_sources(ctx):
            mark_dirty(s)
        pend = pending_paths()
    if not pend:
        return {"ok": True, "files": 0, "chunks": 0}
    store = get_store(ctx)
    if store in (None, False):
        return {"ok": False, "reason": "vector store unavailable", "files": len(pend)}
    done, chunks, failed = 0, 0, []
    for s in pend:
        try:
            chunks += store.replace_source(s, [c for _src, c in md.chunk_md(Path(s))])
            done += 1
        except Exception as e:
            log.info("index flush failed for %s: %s", s, e)
            failed.append(s)
    try:
        # rewrite the queue with only what could not be indexed
        tmp = _dirty_file().with_suffix(".jsonl.tmp")
        tmp.write_text("".join(p + "\n" for p in failed), encoding="utf-8")
        tmp.replace(_dirty_file())
    except Exception as e:
        log.info("could not trim the dirty queue: %s", e)
    return {"ok": not failed, "files": done, "chunks": chunks, "failed": len(failed)}


def vector_search(ctx, query: str, k: int = 6) -> list[dict] | None:
    """Returns results or None (meaning: not available / empty -> caller falls back)."""
    store = get_store(ctx)
    if store is None or store is False:
        return None
    try:
        res = store.query(query, k=k)
        return res or None
    except Exception as e:
        log.debug("vector search failed: %s", e)
        return None


def memory_search_hybrid(ctx, query: str, k: int = 6) -> list[dict]:
    """Try vectors first; fall back to keyword. Always returns a list."""
    res = vector_search(ctx, query, k)
    if res:
        for r in res:
            r["mode"] = "vector"
        return res
    out = md.memory_search(ctx, query, k)
    for r in out:
        r["mode"] = "keyword"
    return out
