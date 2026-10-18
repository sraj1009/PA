"""Human feedback store (RLAIF input): explicit +1/-1 ratings and corrections.

Every rating is one row in a local SQLite database (memory/ratings.db — never
leaves the machine). The SFT builder reads it back each nightly run:
  - tasks rated -1 are BLOCKLISTED from training (a disliked answer must not
    become a lesson, even if its episode verified clean), and
  - /correct texts become teacher samples (the user's corrected wording is
    what the local model should have said).

This is feedback-weighted SFT — the honest single-GPU form of "RLAIF". Full
online RL (PPO/GRPO reward modeling) needs the 8-GPU node in
docs/training-plan.md Phase B; this loop captures the same signal (which
answers were good, what the better wording was) into the weights via the
existing QLoRA job instead.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .. import paths


def task_key(task: str) -> str:
    """Stable dedupe key — MUST match bee.pipeline.build_sft._task_key."""
    return hashlib.sha256((task or "").encode()).hexdigest()[:32]


def _db(db: Path | None = None) -> Path:
    return Path(db) if db is not None else (paths.MEMORY_DIR / "ratings.db")


def _conn(db: Path | None = None) -> sqlite3.Connection:
    p = _db(db)
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(p))
    c.execute(
        "CREATE TABLE IF NOT EXISTS ratings ("
        " task_key TEXT PRIMARY KEY, task TEXT NOT NULL, output TEXT NOT NULL,"
        " rating INTEGER NOT NULL, correction TEXT NOT NULL DEFAULT '',"
        " model TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT '',"
        " ts TEXT NOT NULL)")
    c.execute(
        "CREATE TABLE IF NOT EXISTS pairs ("
        " pair_key TEXT PRIMARY KEY, task TEXT NOT NULL, chosen TEXT NOT NULL,"
        " rejected TEXT NOT NULL, source TEXT NOT NULL DEFAULT '',"
        " model TEXT NOT NULL DEFAULT '', ts TEXT NOT NULL)")
    return c


def record(task: str, output: str, rating: int, correction: str = "",
           model: str = "", source: str = "repl",
           db: Path | None = None) -> dict:
    """Store (+1/-1). Re-rating the same task overwrites (latest wins)."""
    if rating not in (+1, -1):
        raise ValueError("rating must be +1 or -1")
    task, output = (task or "")[:2000], (output or "")[:4000]
    if not task.strip() or not output.strip():
        raise ValueError("task and output must be non-empty")
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    c = _conn(db)
    try:
        c.execute(
            "INSERT OR REPLACE INTO ratings "
            "(task_key, task, output, rating, correction, model, source, ts)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_key(task), task, output, int(rating),
             (correction or "")[:4000], model or "", source or "", ts))
        c.commit()
    finally:
        c.close()
    return {"task_key": task_key(task), "rating": int(rating), "ts": ts}


def get(task: str, db: Path | None = None) -> dict | None:
    c = _conn(db)
    try:
        row = c.execute(
            "SELECT task_key, task, output, rating, correction, model, source, ts"
            " FROM ratings WHERE task_key = ?", (task_key(task),)).fetchone()
    finally:
        c.close()
    if not row:
        return None
    keys = ("task_key", "task", "output", "rating", "correction",
            "model", "source", "ts")
    return dict(zip(keys, row))


def blocklisted(db: Path | None = None) -> set[str]:
    """Task keys rated -1 (latest rating wins) — excluded from SFT."""
    c = _conn(db)
    try:
        rows = c.execute("SELECT task_key FROM ratings WHERE rating = -1").fetchall()
    except Exception:
        return set()
    finally:
        try:
            c.close()
        except Exception:
            pass
    return {r[0] for r in rows}


def corrections(db: Path | None = None) -> list[dict]:
    """Rows with a user correction — teacher samples for SFT."""
    c = _conn(db)
    try:
        rows = c.execute(
            "SELECT task, correction, model, ts FROM ratings"
            " WHERE correction <> ''").fetchall()
    except Exception:
        return []
    finally:
        try:
            c.close()
        except Exception:
            pass
    return [{"task": t, "correction": co, "model": m, "ts": ts}
            for t, co, m, ts in rows]


def pair_key(task: str, chosen: str, rejected: str) -> str:
    """Stable dedupe key for a preference pair (idempotent re-derivation)."""
    h = hashlib.sha256()
    for part in (task or "", chosen or "", rejected or ""):
        h.update(part.encode("utf-8", "replace"))
        h.update(b"\x00")
    return h.hexdigest()[:32]


def record_pair(task: str, chosen: str, rejected: str, source: str = "",
                model: str = "", db: Path | None = None) -> dict | None:
    """Store one machine-derived preference pair (chosen > rejected).

    Sources today: `critique` (the self-critique rewrite), `verify-fix` (a
    verifier-FAILED draft the loop then fixed), `episode-derive` (same task
    failed earlier, succeeded later — see bee.pipeline.derive_prefs). The
    point of P0-4: the RLAIF corpus must not sit at 0 waiting for a human to
    rate answers by hand; these are free pairs the system already generates.
    Empty sides are skipped (return None) — a one-sided pair teaches nothing.
    Re-recording the same triple overwrites (idempotent, latest wins)."""
    task, chosen, rejected = (task or "").strip(), (chosen or "").strip(), (rejected or "").strip()
    if not task or not chosen or not rejected or chosen == rejected:
        return None
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    c = _conn(db)
    try:
        c.execute(
            "INSERT OR REPLACE INTO pairs "
            "(pair_key, task, chosen, rejected, source, model, ts)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pair_key(task, chosen, rejected), task[:2000], chosen[:8000],
             rejected[:8000], (source or "")[:40], (model or "")[:80], ts))
        c.commit()
    finally:
        c.close()
    return {"pair_key": pair_key(task, chosen, rejected), "source": source, "ts": ts}


def pairs(db: Path | None = None) -> list[dict]:
    """All stored preference pairs (any source), newest first."""
    c = _conn(db)
    try:
        rows = c.execute(
            "SELECT task, chosen, rejected, source, model, ts FROM pairs"
            " ORDER BY ts DESC").fetchall()
    except Exception:
        return []
    finally:
        try:
            c.close()
        except Exception:
            pass
    return [{"task": t, "chosen": ch, "rejected": rj, "source": s, "model": m, "ts": ts}
            for t, ch, rj, s, m, ts in rows]


def stats(db: Path | None = None) -> dict:
    c = _conn(db)
    try:
        up = c.execute("SELECT COUNT(*) FROM ratings WHERE rating = 1").fetchone()[0]
        down = c.execute("SELECT COUNT(*) FROM ratings WHERE rating = -1").fetchone()[0]
        corr = c.execute("SELECT COUNT(*) FROM ratings WHERE correction <> ''").fetchone()[0]
        prs = c.execute("SELECT COUNT(*) FROM pairs").fetchone()[0]
    except Exception:
        return {"up": 0, "down": 0, "corrections": 0, "pairs": 0}
    finally:
        try:
            c.close()
        except Exception:
            pass
    return {"up": up, "down": down, "corrections": corr, "pairs": prs}
