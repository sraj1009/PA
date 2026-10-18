"""Preference pairs -> train/prefs.jsonl (RLAIF stage 2: SFT imitates, preferences tune).

Two sources, merged and deduped:
  1. User corrections (memory/ratings.db): prompt=task, chosen=user correction,
     rejected=the model's original output. Only rows with BOTH sides non-empty
     become pairs — a correction without the original answer teaches nothing.
  2. Machine-derived pairs (memory/ratings.db `pairs` table, see
     bee.memory.ratings.record_pair): `critique` rewrites, `verify-fix` drafts
     the verifier caught and the loop then fixed, and `episode-derive` pairs
     (same task failed on one run, succeeded on another — see
     bee.pipeline.derive_prefs, which fills this table from the episodes
     ledger). Until 2026-10-17 this file read source 1 only, and source 1 was
     empty — the DPO corpus sat at 0 waiting for hand-typed /correct edits.

Emits train/prefs.jsonl: {"prompt","chosen","rejected","source",...}.

Run:  python training/dpo/export_prefs.py [--out train/prefs.jsonl]
Trains with: python training/dpo/train_dpo.py (needs CUDA + trl; --dry-run validates).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Run as a script ("python training/dpo/export_prefs.py") the repo root is not
# on sys.path — add it so the lazy `from bee.memory import ratings` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def export(db=None, out: Path | None = None) -> dict:
    from bee.memory import ratings
    rows = ratings.corrections(db=db)
    out = out or (Path("train") / "prefs.jsonl")
    pairs, skipped = [], 0
    seen: set = set()

    def _add(prompt, chosen, rejected, source, model, ts) -> bool:
        """One pair, deduped against everything already queued."""
        nonlocal skipped
        prompt, chosen = (prompt or "").strip(), (chosen or "").strip()
        rejected = (rejected or "").strip()
        if not prompt or not chosen or not rejected or chosen == rejected:
            skipped += 1
            return False
        key = (prompt, chosen, rejected)
        if key in seen:
            skipped += 1
            return False
        seen.add(key)
        pairs.append({"prompt": prompt, "chosen": chosen, "rejected": rejected,
                      "source": source, "model": model or "", "ts": ts or ""})
        return True

    by_source: dict[str, int] = {}
    for r in rows:
        prompt = (r.get("task") or "").strip()
        full = ratings.get(prompt, db=db) or {}
        if _add(prompt, r.get("correction"), full.get("output"), "user",
                full.get("model"), full.get("ts")):
            by_source["user"] = by_source.get("user", 0) + 1
    for p in ratings.pairs(db=db):
        src = (p.get("source") or "derived").strip() or "derived"
        if _add(p.get("task"), p.get("chosen"), p.get("rejected"), src,
                p.get("model"), p.get("ts")):
            by_source[src] = by_source.get(src, 0) + 1
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    return {"pairs": len(pairs), "skipped": skipped, "by_source": by_source,
            "out": str(out)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    print(json.dumps(export(out=Path(args.out) if args.out else None), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
