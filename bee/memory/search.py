"""Vector memory search (LanceDB, embedded, no server) with keyword fallback.

If LanceDB or the embedder is unavailable, falls back to memory.md.keyword
search transparently — the tool interface is identical.
"""
from __future__ import annotations

import logging

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

    def _table(self):
        if TABLE in self.conn.table_names():
            return self.conn.open_table(TABLE)
        import pyarrow as pa
        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("source", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), 768)),
        ])
        return self.conn.create_table(TABLE, schema=schema, mode="overwrite")

    def rebuild(self):
        chunks = md.all_chunks()
        if not chunks:
            return 0
        texts = [c for _, c in chunks]
        embs = []
        # batch embed (ollama is fine with small batches)
        for i in range(0, len(texts), 8):
            batch = texts[i:i + 8]
            embs.extend(self.client.embed(batch))
        import pyarrow as pa
        rows = []
        for (src, ch), e in zip(chunks, embs):
            rows.append({"id": f"{src}#{ch[:60]}", "text": ch[:1000], "source": src, "vector": list(map(float, e))})
        t = self._table()
        t.add(rows)
        return len(rows)

    def query(self, text: str, k: int = 6) -> list[dict]:
        e = self.client.embed([text])[0]
        t = self._table()
        if t.count_rows() == 0:
            return []
        res = t.search(list(map(float, e))).limit(k).to_list()
        return [{"score": float(r.get("_distance", 0)), "source": r["source"], "text": r["text"]} for r in res]


def get_store(ctx):
    global _cache
    if _cache is None:
        try:
            _cache = _VecStore(ctx.cfg, ctx.client)
        except Exception as e:
            log.info("vector store unavailable (%s) — keyword search only", e)
            _cache = False
    return _cache


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
