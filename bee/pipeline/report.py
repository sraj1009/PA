"""Pipeline report → train/PIPELINE_REPORT.md (data flywheel health)."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from .. import paths
from .build_sft import load_episodes
from . import validate


def build_report(workspace: Path | None = None) -> str:
    rows = load_episodes()
    out = []
    out.append("# BEE Data Pipeline Report\n")
    out.append(f"- episodes on disk: **{len(rows)}** (`train/episodes/`)\n")
    if not rows:
        out.append("_No episodes yet — use BEE; every task logs one._")
        return "\n".join(out)
    v = Counter()
    t = Counter()
    m = Counter()
    verdicts = []
    for r in rows:
        res = validate.validate(r, workspace)
        v[res["verdict"]] += 1
        t[res["type"]] += 1
        m[r.get("model", "?")] += 1
        verdicts.append((r.get("date"), r.get("task", "")[:60], res["verdict"], res["why"][:40]))
    out.append("## Validation (SFT eligibility)\n")
    out.append("| verdict | count | meaning |")
    out.append("|---|---|---|")
    out.append(f"| pass | {v.get('pass',0)} | verified success — trainable |")
    out.append(f"| unknown | {v.get('unknown',0)} | succeeded, no cheap check (--loose) |")
    out.append(f"| fail | {v.get('fail',0)} | excluded from training |")
    out.append(f"\n## Task types\n" + "\n".join(f"- {k}: {n}" for k, n in t.most_common()))
    out.append(f"\n## Models\n" + "\n".join(f"- {k}: {n}" for k, n in m.most_common()))
    out.append("\n## Recent episodes\n")
    out.append("| date | task | verdict | why |")
    out.append("|---|---|---|---|")
    for d, task, vd, why in verdicts[-15:]:
        out.append(f"| {d} | {task} | {vd} | {why} |")
    rep = paths.TRAIN_DIR / "router_cv_report.json"
    if rep.exists():
        out.append("\n## ML router\n" + rep.read_text(encoding="utf-8"))
    sft = paths.TRAIN_DIR / "sft_v1.jsonl"
    if sft.exists():
        n = sum(1 for _ in sft.open(encoding="utf-8"))
        out.append(f"\n## SFT dataset\n- {n} samples in `{sft}`")
    return "\n".join(out)


def main():
    from ..config import load_config
    cfg = load_config()
    md = build_report(cfg.workspace)
    paths.TRAIN_DIR.mkdir(parents=True, exist_ok=True)
    p = paths.TRAIN_DIR / "PIPELINE_REPORT.md"
    p.write_text(md, encoding="utf-8")
    print(md)
    print(f"\nwrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
