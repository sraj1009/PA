"""Episodes + cloud goldens → SFT dataset (Qwen3 chat format, loss-masked, PII-scrubbed).

Pipeline: load episodes → validate → keep pass (or --loose: pass+unknown)
→ merge cloud_golden.jsonl (successful cloud answers — curated by construction,
so they bypass the strict deterministic verdict: the cloud is the teacher)
→ dedupe by task (keep most-recent) → scrub → emit train/sft_v1.jsonl + stats.

Run:  python -m bee.pipeline.build_sft [--loose] [--out train/sft_v1.jsonl]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .. import paths
from . import sanitize, validate


def load_episodes() -> list[dict]:
    rows = []
    for f in sorted(paths.EPISODES_DIR.glob("*.jsonl")):
        for ln in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not ln.strip():
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue
    return rows


def load_golden() -> list[dict]:
    """Successful cloud answers (teach-back). {'task','response','model','ts'}."""
    f = paths.TRAIN_DIR / "golden" / "cloud_golden.jsonl"
    if not f.exists():
        return []
    rows = []
    for ln in f.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not ln.strip():
            continue
        try:
            rows.append(json.loads(ln))
        except Exception:
            continue
    return rows


def quality_score(row: dict) -> float:
    """Heuristic 0..1 estimate of SFT sample quality (no LLM call).

    Rewards a substantive verified response + non-trivial task + real tool usage;
    penalizes near-empty output and error-looking text. Used to filter/augment.
    """
    out = (row.get("output") or "").strip()
    task = (row.get("task") or "").strip()
    s = 0.5
    s += min(0.2, len(out) / 2000.0)
    if len(task) >= 8:
        s += 0.05
    if len(task) >= 40:
        s += 0.05
    if row.get("events"):
        s += 0.1
    if out.lower().startswith(("error", "traceback", "failed", "i cannot",
                               "i'm sorry i can't", "i can't")):
        s -= 0.3
    return round(max(0.0, min(1.0, s)), 3)


def _no_tool_single_turn(row: dict) -> bool:
    return bool(row.get("ok")) and not (row.get("events") or []) \
        and (row.get("output") or "").strip() and (row.get("task") or "").strip()


def paraphrase_augment(rows: list[dict], n: int, gen_fn) -> list[dict]:
    """Opt-in data augmentation: the cloud teacher rewrites each no-tool task in
    `n` natural variants; each variant is paired with the SAME verified response.
    This is a real way to 'train more' from the same high-quality examples — it
    teaches the local model robustness to varied phrasing without inventing answers.
    gen_fn(task) -> list[str].
    """
    out = []
    for row in rows:
        if n <= 0 or not _no_tool_single_turn(row):
            continue
        try:
            paras = gen_fn(row["task"]) or []
        except Exception:
            continue
        for p in list(paras)[:n]:
            p = (p or "").strip().lstrip("-•* \t")
            if len(p) < 8 or p.lower() == row["task"].strip().lower():
                continue
            out.append({"task": p, "output": row["output"], "ok": True, "events": [],
                        "model": row.get("model", "cloud"), "date": row.get("date"),
                        "augmented": True})
    return out


def row_to_messages(row: dict) -> list[dict] | None:
    """Chat messages with `loss` flags from a stored episode row."""
    if not row.get("ok") or not (row.get("output") or "").strip():
        return None
    msgs = [{"role": "user", "content": row["task"], "loss": False}]
    for ev in row.get("events", []):
        msgs.append({"role": "assistant", "content": "",
                     "tool_calls": [{"function": {"name": ev.get("tool"), "arguments": ev.get("args", "{}")}}],
                     "loss": True})
        msgs.append({"role": "tool", "name": ev.get("tool"),
                     "content": (ev.get("result") or "")[:2000], "loss": False})
    msgs.append({"role": "assistant", "content": row["output"], "loss": True})
    return msgs


def build(keep_unknown: bool = False, workspace: Path | None = None,
          out: Path | None = None, min_quality: float = 0.0,
          n_paraphrase: int = 0, gen_fn=None) -> dict:
    rows = load_episodes()
    golden = load_golden()
    out = out or (paths.TRAIN_DIR / "sft_v1.jsonl")
    seen: dict[str, dict] = {}
    stats = {"episodes": len(rows), "golden": len(golden), "golden_in": 0,
             "by_verdict": {}, "dropped_dup": 0, "redactions": 0,
             "dropped_low_quality": 0, "paraphrases": 0, "quality_dist": {}}
    for row in rows:
        v = validate.validate(row, workspace)
        stats["by_verdict"][v["verdict"]] = stats["by_verdict"].get(v["verdict"], 0) + 1
        if v["verdict"] == "fail":
            continue
        if v["verdict"] == "unknown" and not keep_unknown:
            continue
        key = row.get("task", "")[:500]
        if key in seen:
            stats["dropped_dup"] += 1
            continue
        seen[key] = row
    # Cloud goldens: successful cloud answers are curated by construction, so
    # they are included directly (deduped against episodes, still PII-scrubbed)
    # — this is how the local model learns what the cloud already answered well.
    for row in golden:
        key = (row.get("task") or "").strip()[:500]
        if not key or not (row.get("response") or "").strip():
            continue
        if key in seen:
            stats["dropped_dup"] += 1
            continue
        seen[key] = {"task": key, "output": row["response"][:4000], "ok": True,
                     "events": [], "model": row.get("model", "cloud"),
                     "date": (row.get("ts") or "")[:10]}
        stats["golden_in"] += 1
    # Opt-in cloud-teacher paraphrase augmentation (robustness to phrasing).
    if n_paraphrase > 0 and gen_fn is not None:
        base = [r for r in seen.values() if not r.get("augmented")]
        for pr in paraphrase_augment(base, n_paraphrase, gen_fn):
            key = pr["task"][:500]
            if key not in seen:
                seen[key] = pr
                stats["paraphrases"] += 1

    n_out = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for row in seen.values():
            # scrub FIRST, then build messages from the scrubbed row so no PII
            # (email/phone/card/keys/Aadhaar) reaches the training dataset.
            aug = bool(row.get("augmented"))
            clean, n_red = sanitize.scrub_episode(row)
            stats["redactions"] += n_red
            msgs = row_to_messages(clean)
            if not msgs:
                continue
            q = quality_score(clean)
            if q < min_quality:
                stats["dropped_low_quality"] += 1
                continue
            bucket = f"{int(q * 10) / 10:.1f}"
            stats["quality_dist"][bucket] = stats["quality_dist"].get(bucket, 0) + 1
            f.write(json.dumps({
                "messages": msgs,
                "metadata": {"date": clean.get("date"), "model": clean.get("model"),
                             "n_tools": clean.get("n_tools"), "redactions": n_red,
                             "quality": q, "augmented": aug,
                             "type": validate.detect_type(clean.get("task", ""), clean.get("events", []))},
            }, ensure_ascii=False) + "\n")
            n_out += 1
    stats["samples_out"] = n_out
    stats["unique_tasks"] = len(seen)
    stats["out"] = str(out)
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loose", action="store_true", help="include unknown-verdict episodes")
    ap.add_argument("--out", default=None)
    ap.add_argument("--min-quality", type=float, default=0.0,
                    help="drop SFT samples scoring below this quality (0..1)")
    ap.add_argument("--paraphrase", type=int, default=0,
                    help="cloud-teacher paraphrase augmentation: N variants per "
                         "no-tool task (0 = off; costs N cloud calls per example)")
    args = ap.parse_args()
    from ..config import load_config
    cfg = load_config()
    gen_fn = None
    if args.paraphrase > 0:
        from ..agent.client import LLMClient
        client = LLMClient(cfg)

        def _gen(task: str):
            res = client.chat(
                "cloud",
                [{"role": "user",
                  "content": "Rewrite this assistant task in %d different natural ways, "
                              "one per line, keeping the exact same intent. Do not add "
                              "or remove meaning.\nTask: %s" % (args.paraphrase, task[:500])}],
                max_retries=1)
            content = res.get("content") or ""
            return [ln.strip(" \t-•·") for ln in content.splitlines() if ln.strip()][:args.paraphrase]

        gen_fn = _gen
    stats = build(keep_unknown=args.loose, workspace=cfg.workspace,
                  out=Path(args.out) if args.out else None,
                  min_quality=args.min_quality, n_paraphrase=args.paraphrase, gen_fn=gen_fn)
    print(json.dumps(stats, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
