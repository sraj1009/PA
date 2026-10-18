"""Nightly recall-regression probe for the memory stack (P1-5).

Read-only: samples rows out of the LIVE vector index, quotes a distinctive
slice of each row's own text, and asks the production hybrid retriever
(`rag.retrieve` -> keyword + vector RRF) to find that row back. Records
recall@k, index stats and vector-path liveness to the metrics stream,
compares against its own trailing baseline, and RAISES on a real drop or a
broken vector path - a failing durable job is this repo's existing alert
surface.

Why this exists: A28a (an index four days stale, nobody noticed) and A38a
(the vector half dying silently into keyword-only, suite green) both went
unobserved because nothing measures retrieval quality on the live index.

Design rules:
  * no writes to user memory; the only artifacts are metrics rows;
  * a self-calibrating corpus (sampled from the live index), so the probe
    cannot rot when memory changes;
  * the baseline is empirical - the median of the last few runs - and the
    first runs verdict `baseline` instead of guessing a threshold.
"""
from __future__ import annotations

import json
import logging
from statistics import median

from .. import paths
from ..brain import rag
from ..monitor import metrics
from . import md, search

log = logging.getLogger("bee.mem")

EVENT = "recall_guard"
PROBES = 8            # rows sampled per run
TOP_K = 8             # top-k the retriever gets to return the source row
TOLERANCE = 0.15      # absolute recall@k drop vs the trailing median
MIN_BASELINE = 3      # runs before a `regressed` verdict is allowed
BASELINE_N = 7        # trailing runs the median is taken over
_ROW_CAP = 5000       # never page more index rows than this


def _src_key(src) -> str:
    """One name for one file across both halves of the stack: md relays
    sources relativized to PROJECT_ROOT (`./memory/...`), the vector store
    keeps the absolute path it was told to index."""
    s = str(src).replace("\\", "/")
    root = str(paths.PROJECT_ROOT).replace("\\", "/")
    if s.startswith(root):
        s = s[len(root):]
    return s.lstrip("/.").lower()


def _quote(text: str) -> str:
    """A distinctive slice of the row's own text - the thing a user would
    half-remember. The middle of the chunk, not the head: heads are often
    headers/bullets shared across rows."""
    words = (text or "").split()
    if not words:
        return ""
    if len(words) <= 12:
        return " ".join(words)
    start = len(words) // 3
    return " ".join(words[start:start + 10])


def _sample_rows(store, n: int = PROBES):
    """Deterministic stride sample of the live table. Returns (rows, total)."""
    t = store._table()
    total = int(t.count_rows())
    if total <= 0:
        return [], 0
    rows = t.search().select(["source", "text"]).limit(min(total, _ROW_CAP)).to_list()
    stride = max(1, len(rows) // n)
    return rows[::stride][:n], total


def _measure(ctx, rows) -> dict:
    ok = vec_share = 0
    per = []
    for i, row in enumerate(rows):
        q = _quote(row.get("text", ""))
        got = []
        if q:
            try:
                got = rag.retrieve(ctx, q, k=TOP_K) or []
            except Exception as e:     # a raising retriever is a miss, not a crash
                log.info("recall probe %d failed: %s", i, e)
        want = _src_key(row.get("source", ""))
        hit = any(_src_key(h.get("source", "")) == want for h in got)
        vec = any(h.get("mode") == "vector" for h in got)
        ok += 1 if hit else 0
        vec_share += 1 if vec else 0
        per.append({"s": want[-40:], "hit": bool(hit), "vec": bool(vec)})
    n = len(per)
    return {"n": n, "hits": ok,
            "recall_at_k": round(ok / n, 4) if n else None,
            # informational: how often the vector half changed the ranking
            # (can legitimately be 0 when vector matches mirror keyword ones)
            "vector_share": round(vec_share / n, 4) if n else None,
            "per": per}


def _baseline() -> list[dict]:
    rows = [r for r in metrics.load_all()
            if r.get("event") == EVENT and isinstance(r.get("recall_at_k"), (int, float))]
    return rows[-BASELINE_N:]


def _verdict(rec, *, base, n_rows: int, corpus: bool, vector_alive: bool) -> str:
    if n_rows and not vector_alive:
        return "vector_dead"          # A38a's species: the silent downgrade
    if corpus and not n_rows:
        return "index_empty"          # rows all gone while files remain
    if not corpus and not n_rows:
        return "empty"                # fresh install - nothing to measure yet
    vals = [b["recall_at_k"] for b in base
            if isinstance(b.get("recall_at_k"), (int, float))]
    if len(vals) < MIN_BASELINE:
        return "baseline"
    if rec is not None and rec < median(vals) - TOLERANCE:
        return "regressed"
    return "ok"


def run(ctx) -> dict:
    """Durable-job entry (registered as `recall_guard` in bee.scheduler)."""
    store = search.get_store(ctx)
    corpus = [src for src, _c in md.all_chunks()]
    rows, total = [], 0
    if store not in (None, False):
        try:
            rows, total = _sample_rows(store)
        except Exception as e:
            log.info("recall guard could not read the index: %s", e)
    vector_alive = False
    if total:
        try:
            vector_alive = bool(search.vector_search(
                ctx, "recall guard liveness probe", k=2))
        except Exception as e:
            log.info("recall guard liveness call failed: %s", e)
    m = (_measure(ctx, rows) if rows
         else {"n": 0, "hits": 0, "recall_at_k": None, "vector_share": None, "per": []})
    base = _baseline()
    verdict = _verdict(m["recall_at_k"], base=base, n_rows=total,
                       corpus=bool(corpus), vector_alive=vector_alive)
    out = {"ok": verdict in ("ok", "baseline", "empty"),
           "verdict": verdict, "n": m["n"], "k": TOP_K,
           "recall_at_k": m["recall_at_k"], "vector_share": m["vector_share"],
           "vector_alive": vector_alive, "indexed_rows": total,
           "disk_chunks": len(corpus), "baseline_runs": len(base),
           "baseline_median": (median([b["recall_at_k"] for b in base])
                               if base else None),
           "tolerance": TOLERANCE,
           "misses": [p["s"] for p in m["per"] if not p["hit"]][:5]}
    # record first: a regression that raises must still be visible as data
    metrics.record(EVENT, **out)
    if not out["ok"]:
        raise RuntimeError("recall_guard: " + json.dumps(out, ensure_ascii=False))
    return out
