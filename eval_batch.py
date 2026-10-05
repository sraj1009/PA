"""Batch driver for the LLM eval suite (background runs must stay < 15 min).

Usage:  python eval_batch.py id1 id2 id3 ...
Appends results to evals/results.jsonl (the verification report aggregates
the latest result per task id, so batches compose).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bee.agent.client import LLMClient  # noqa: E402
from bee.agent.context import Context  # noqa: E402
from bee.config import load_config  # noqa: E402
from bee.evals import runner  # noqa: E402


def main():
    ids = sys.argv[1:]
    if not ids:
        print("usage: python eval_batch.py <task-id> [...]")
        return 2
    cfg = load_config()
    ctx = Context(cfg, workspace=cfg.workspace, name="BEE")
    ctx.client = LLMClient(cfg)
    ctx.guard_mode = cfg.guard.mode
    runner.run_suite(ctx, only=list(ids))
    return 0


if __name__ == "__main__":
    sys.exit(main())
