"""Episodes ledger + cloud goldens → derived preference pairs (RLAIF stage 2).

Close the data loop (2026-10-17, P0-4): the preference corpus sat at 0 because
pairs only came from hand-typed /correct rows. Two machine-derived rules feed it
now, both conservative on purpose — a bad pair poisons the preference tune:

  A. cloud teaches local — for a task whose cloud answer was captured as a
     golden (train/golden/cloud_golden.jsonl; `_golden` on cloud-served
     successes) and whose local run failed, the pair is (chosen=cloud answer,
     rejected=failed output). This is the "everything the cloud does gets
     taught to the local model" loop, taken from the ledger.
  B. verifier-fixed — on the same task, an episode the verifier FAILED
     (verdict "fail") followed by a run the verifier PASSED is (chosen=passed
     output, rejected=failed output). The deterministic check marks both sides,
     so the direction is not the model's opinion of itself.

Both sides must be REAL MODEL text: the loop's status sentinels ("(stopped: …)")
and the fallbacks it writes for empty/wrap-stopped episodes are excluded from
both sides. Plumbing talk is excluded from the CHOSEN side only — a meta-ramble
is never a good answer, but on the rejected side ("prefer the answer over the
ramble about tool calls") it is exactly the lesson. Measured 2026-10-17:
without these gates a first dry run offered 24 "pairs", every one a meta-ramble
preferred over "(stopped: max iterations reached)".

  - the user blocklist (rating -1) wins: those tasks label nothing
  - idempotent: pairs dedupe by (task, chosen, rejected) hash in ratings.db

Run:    python -m bee.pipeline.derive_prefs [--dry-run] [--max-per-task 2]
Writes: memory/ratings.db (pairs table) — consumed by
        training/dpo/export_prefs.py → train/prefs.jsonl → train_dpo.py.
"""
from __future__ import annotations

import argparse
import json
import re

from .. import paths
from ..agent.loop import _META_RAMBLE_RE
from ..memory import ratings

# The loop's own status sentinels — "(stopped: max iterations reached)" etc.
# harness text, not model text: neither a good nor a bad "answer".
_PLUMBING = re.compile(r"^\s*\((?:stopped|scripted|no reply|nothing)", re.I)
# The "excuse" family the loop's wrap/grounded passes already fight at ship
# time ("…budget has been exhausted", "previous calls have exceeded…"). The
# loop's _META_RAMBLE_RE covers the "no function calls were…" branch.
_PLUMBING_EXTRA = re.compile(
    r"it seems like there might have been an error"
    r"|\b(?:tool|function)\s*calls?\b[^.\n]{0,44}\b(?:budget|exceeded|exhausted|limit)\b"
    r"|\b(?:budget|exceeded|exhausted)\b[^.\n]{0,44}\b(?:tool|function)\s*calls?\b", re.I)


def _is_plumbing(text: str) -> bool:
    return bool(_PLUMBING.match(text) or _META_RAMBLE_RE.search(text)
                or _PLUMBING_EXTRA.search(text))


# Errors whose episode OUTPUT was written by the harness, not the model: an
# "empty answer" episode ships the grounded fallback; a wrap-stop ships the
# sentinel. Preferring anything over harness text teaches styles, not answers —
# measured 2026-10-17: the one surviving rule-B pair on the real ledger was
# "prefer narration over the honest fallback" of an empty-answer episode.
_HARNESS_ERRORS = {"empty answer", "max iterations", "cancelled",
                   "no answer after wrap"}
# Model-authored ERROR explanations ("the function does not accept keyword
# arguments…", "misunderstanding…") are never a good "chosen": a golden with
# that text is a captured defect, not a lesson. As the rejected side they are
# ordinary negatives and stay allowed.
_ERROR_TEXT = re.compile(
    r"does not accept|unexpected keyword|no module named|importerror"
    r"|traceback|misunderstanding", re.I)


def _bad_chosen(text: str) -> bool:
    return _is_plumbing(text) or bool(_ERROR_TEXT.search(text))


def _is_model_failure(row: dict, out: str, min_chars: int) -> bool:
    """True when `out` is a MODEL-AUTHORED answer the harness judged defective.

    Meta-ramble talk is ALLOWED here (only the chosen side bans it): "prefer
    the shipped answer over the ramble about tool calls" is the lesson."""
    if len(out) < min_chars or _PLUMBING.match(out):
        return False
    err = (row.get("error") or "").strip().lower()
    if err.startswith("llm error") or err in _HARNESS_ERRORS:
        return False
    verdict = ((row.get("verify") or {}).get("verdict") or "")
    return verdict == "fail" or err == "unverified action claim"


def _load_episodes(episodes_dir=None) -> list[dict]:
    rows: list[dict] = []
    d = episodes_dir or paths.EPISODES_DIR
    for f in sorted(d.glob("*.jsonl")):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for ln in text.splitlines():
            if not ln.strip():
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue
    return rows


def load_goldens() -> dict[str, dict]:
    """task_key -> {"task","response","model"} from the cloud teach-back corpus."""
    f = paths.TRAIN_DIR / "golden" / "cloud_golden.jsonl"
    out: dict[str, dict] = {}
    if not f.exists():
        return out
    for ln in f.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except Exception:
            continue
        task = (row.get("task") or "").strip()
        resp = (row.get("response") or "").strip()
        if task and resp:
            out[ratings.task_key(task)] = {"task": task, "response": resp,
                                           "model": row.get("model") or "cloud"}
    return out


def derive_candidates(rows: list[dict], goldens: dict | None = None, db=None,
                      max_per_task: int = 2, min_chars: int = 24
                      ) -> tuple[list[tuple[str, str, str, str]], dict]:
    """Select candidate pairs (no writes). Returns (pairs, stats).

    Pair tuples are (task, chosen, rejected, chosen_model)."""
    if goldens is None:
        goldens = load_goldens()
    blocked = ratings.blocklisted(db=db)
    groups: dict[str, list[dict]] = {}
    for r in rows:
        t = (r.get("task") or "").strip()
        if t:
            groups.setdefault(ratings.task_key(t), []).append(r)
    stats = {"episodes": len(rows), "tasks": len(groups), "skipped_blocked": 0,
             "skipped_no_sides": 0}
    pairs: list[tuple[str, str, str, str]] = []
    for key, members in groups.items():
        if key in blocked:
            stats["skipped_blocked"] += 1
            continue
        members.sort(key=lambda r: r.get("ts") or 0)
        failed: list[tuple[str, str]] = []      # (output, verdict)
        passes: list[tuple[str, str]] = []      # (output, model)
        task_text = ""
        for r in members:
            out = (r.get("output") or "").strip()
            verdict = ((r.get("verify") or {}).get("verdict") or "")
            t = (r.get("task") or "").strip()
            if (r.get("ok") and verdict == "pass" and len(out) >= min_chars
                    and not _bad_chosen(out)):
                passes.append((out, str(r.get("model") or "")))
            elif _is_model_failure(r, out, min_chars):
                failed.append((out, verdict))
            else:
                continue
            task_text = task_text or t
        if not failed:
            stats["skipped_no_sides"] += 1
            continue
        gold = goldens.get(key) or {}
        gold_resp = (gold.get("response") or "").strip()
        # a golden that is itself meta-ramble or an error text must never be
        # the "chosen" side
        if len(gold_resp) < min_chars or _bad_chosen(gold_resp):
            gold_resp = ""
        if gold_resp:
            chosen, chosen_model = gold_resp, (gold.get("model") or "cloud")
            task_text = gold.get("task") or task_text
            rejections = [o for o, _v in failed]
        else:
            # rule B needs the verifier's own verdicts on both sides
            chosen, chosen_model = (passes[-1] if passes else (None, ""))
            chosen_model = chosen_model or "local"
            rejections = [o for o, v in failed if v == "fail"]
        if not chosen or not rejections:
            stats["skipped_no_sides"] += 1
            continue
        picked: list[str] = []
        for bad in reversed(rejections):        # most recent failures first
            if bad == chosen or bad in picked:
                continue
            picked.append(bad)
            pairs.append((task_text, chosen, bad, chosen_model))
            if len(picked) >= max_per_task:
                break
        if not picked:
            stats["skipped_no_sides"] += 1
    return pairs, stats


def derive(episodes_dir=None, db=None, max_per_task: int = 2,
           min_chars: int = 24, dry_run: bool = False,
           goldens: dict | None = None) -> dict:
    """Derive candidate pairs and (unless dry_run) store them in ratings.db."""
    rows = _load_episodes(episodes_dir)
    pairs, stats = derive_candidates(rows, goldens=goldens, db=db,
                                     max_per_task=max_per_task,
                                     min_chars=min_chars)
    stats = dict(stats)
    stats.update({"pairs": 0, "candidates": len(pairs)})
    for task, chosen, bad, cmodel in pairs:
        if dry_run:
            stats["pairs"] += 1
            continue
        got = ratings.record_pair(task, chosen, bad, source="episode-derive",
                                  model=cmodel, db=db)
        if got:
            stats["pairs"] += 1
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="count candidates, write nothing")
    ap.add_argument("--max-per-task", type=int, default=2)
    ap.add_argument("--min-chars", type=int, default=24)
    args = ap.parse_args(argv)
    st = derive(max_per_task=args.max_per_task, min_chars=args.min_chars,
                dry_run=args.dry_run)
    mode = "would record" if args.dry_run else "recorded"
    print(f"derive_prefs: {st['tasks']} tasks from {st['episodes']} episodes — "
          f"{mode} {st['pairs']} pairs (candidates {st['candidates']}, "
          f"blocked {st['skipped_blocked']}, one-sided {st['skipped_no_sides']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
