"""Eval resumer — runs every eval task that hasn't PASSED yet, then stops.

Idempotent and kill-tolerant (designed for scheduled overnight runs):
- reads evals/tasks.yaml + the latest per-task row in evals/results.jsonl
- skips tasks whose latest result is ok=true (including repeat tasks)
- re-runs failures (latest ok=false) so a new row supersedes the old one
- lightest-first ordering (measured seconds, unknowns last) to maximize
  completions inside any runtime window
- each task is persisted immediately by the runner, so a killed run simply
  resumes from the next invocation

Usage:  python eval_resume.py [task-id ...]     (no args = everything pending)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def latest_results() -> dict:
    p = ROOT / "evals" / "results.jsonl"
    latest: dict = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            latest[row["id"]] = row
    return latest


def main() -> int:
    tasks = yaml.safe_load((ROOT / "evals" / "tasks.yaml").read_text(encoding="utf-8"))["tasks"]
    latest = latest_results()
    only = sys.argv[1:]
    todo = []
    for t in tasks:
        tid = t["id"]
        if only and tid not in only:
            continue
        row = latest.get(tid)
        if row is not None and row.get("ok"):
            print(f"[skip] {tid} (already passed)")
            continue
        todo.append(t)
    # lightest first: measured seconds ascending, never-measured last
    todo.sort(key=lambda t: latest.get(t["id"], {}).get("seconds", 10**6))
    if not todo:
        print("nothing to do - all eval tasks green")
        return 0
    print("pending:", ", ".join(t["id"] for t in todo))

    from bee.agent.client import LLMClient  # noqa: E402
    from bee.agent.context import Context  # noqa: E402
    from bee.config import load_config  # noqa: E402
    from bee.evals import runner  # noqa: E402

    cfg = load_config()
    ctx = Context(cfg, workspace=cfg.workspace, name="BEE")
    ctx.client = LLMClient(cfg)
    ctx.guard_mode = cfg.guard.mode
    runner.run_suite(ctx, only=[t["id"] for t in todo])
    return 0


if __name__ == "__main__":
    sys.exit(main())
