"""Head-to-head: same tasks on local bee4b vs cloud, judged by the suite rubric.

The judge is check_task itself (substring expects + route/guard/verify/redact
events) — no new rubric to game, no human in the loop. Verdicts per task:
local-win (local passes, cloud fails), cloud-win, tie-pass, tie-fail.

Writes evals/compare_results.jsonl — NEVER the official eval ledger, so
experiment rows cannot inflate suite scores (A52/A62).

Run:  python -m bee.evals.compare [--tasks dsa_sort_check,memory_read,shell_echo]
Cost: 2 engine runs per task. Defaults to 3 quick tasks (~2-4 min).
"""
from __future__ import annotations

import argparse
import json
import sys

DEFAULT_TASKS = ["dsa_sort_check", "memory_read", "shell_echo"]


def compare(task_ids: list[str]) -> dict:
    from .. import paths
    from ..agent.context import create_context
    from ..config import load_config
    from . import runner

    ledger = paths.EVAL_RESULTS
    compare_ledger = ledger.parent / "compare_results.jsonl"
    paths.EVAL_RESULTS = compare_ledger  # redirect the suite ledger for this run
    cfg = load_config()
    sides: dict[str, list[dict]] = {}
    try:
        for engine in ("local", "cloud"):
            ctx = create_context(cfg)
            rows = runner.run_suite(ctx, model=engine, only=task_ids)
            sides[engine] = [r for r in rows if r.get("id") in task_ids]
    finally:
        paths.EVAL_RESULTS = ledger
    table, wins = [], {"local": 0, "cloud": 0, "tie_pass": 0, "tie_fail": 0}
    for tid in task_ids:
        loc = next((r for r in sides.get("local", []) if r.get("id") == tid), {})
        clo = next((r for r in sides.get("cloud", []) if r.get("id") == tid), {})
        lok, cok = bool(loc.get("ok")), bool(clo.get("ok"))
        if lok and not cok:
            verdict, wins["local"] = "local-win", wins["local"] + 1
        elif cok and not lok:
            verdict, wins["cloud"] = "cloud-win", wins["cloud"] + 1
        elif lok:
            verdict, wins["tie_pass"] = "tie-pass", wins["tie_pass"] + 1
        else:
            verdict, wins["tie_fail"] = "tie-fail", wins["tie_fail"] + 1
        table.append({"id": tid, "verdict": verdict,
                      "local": {"ok": lok, "seconds": loc.get("seconds"),
                                "model": loc.get("model")},
                      "cloud": {"ok": cok, "seconds": clo.get("seconds"),
                                "model": clo.get("model")}})
    return {"tasks": table, "wins": wins,
            "ledger": str(compare_ledger)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=",".join(DEFAULT_TASKS),
                    help="comma-separated eval task ids (default: 3 quick tasks)")
    args = ap.parse_args()
    ids = [t.strip() for t in args.tasks.split(",") if t.strip()]
    if not ids:
        print("no tasks given")
        return 2
    out = compare(ids)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
