"""Show latest eval status per task id from results.jsonl."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
rows = []
for ln in (ROOT / "evals" / "results.jsonl").read_text(encoding="utf-8").splitlines():
    if ln.strip():
        try:
            rows.append(json.loads(ln))
        except Exception:
            pass
latest: dict[str, dict] = {}
order = []
for r in rows:
    tid = r.get("id", "?")
    if tid not in latest:
        order.append(tid)
        latest[tid] = r
    elif latest[tid].get("ts", "") <= r.get("ts", ""):
        latest[tid] = r
print(f"{len(rows)} rows total; latest-per-id: {sum(1 for r in latest.values() if r.get('ok'))}/{len(latest)}")
for tid in order:
    r = latest[tid]
    print(f"  {tid:20s} ok={str(r.get('ok')):5s} ts={r.get('ts')} sec={r.get('seconds')}")
# tasks still missing from the full 21
import yaml  # noqa: E402
tasks = yaml.safe_load((ROOT / "evals" / "tasks.yaml").read_text(encoding="utf-8"))["tasks"]
all_ids = [t.get("id", f"task{i+1}") for i, t in enumerate(tasks)]
missing = [i for i in all_ids if i not in latest]
print("missing:", missing)
