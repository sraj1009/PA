"""Benchmark + correctness harness for the DSA library.

run_bench(fn, *args, warmup=1, repeats=5, **kwargs) -> timing dict
check(actual, expected, label) -> AssertionError on mismatch
report(rows, path) -> writes JSON report next to evals/
"""
from __future__ import annotations

import json
import time
from pathlib import Path


def time_once(fn, *args, **kwargs):
    t0 = time.perf_counter()
    out = fn(*args, **kwargs)
    return out, (time.perf_counter() - t0) * 1000.0


def run_bench(fn, label: str = "", *args, warmup: int = 1, repeats: int = 5, **kwargs) -> dict:
    label = label or getattr(fn, "__name__", "fn")
    if warmup:
        for _ in range(warmup):
            fn(*args, **kwargs)
    best, total = float("inf"), 0.0
    for _ in range(max(1, repeats)):
        _, ms = time_once(fn, *args, **kwargs)
        best = min(best, ms)
        total += ms
    return {"name": label, "best_ms": round(best, 3), "mean_ms": round(total / max(1, repeats), 3),
            "repeats": repeats}


def check(actual, expected, label: str = "") -> None:
    a = list(actual) if hasattr(actual, "__iter__") and not isinstance(actual, (str, bytes)) else actual
    e = list(expected) if hasattr(expected, "__iter__") and not isinstance(expected, (str, bytes)) else expected
    if a != e:
        raise AssertionError(f"check failed [{label}]: expected {str(e)[:200]}, got {str(a)[:200]}")


def compare_sorts(n: int = 2000, seed: int = 7, repeats: int = 3) -> list[dict]:
    """Benchmark all sorting implementations on the same random input; verify against timsort."""
    import random
    from . import sorting
    rng = random.Random(seed)
    data = [rng.randint(0, n * 10) for _ in range(n)]
    expected = sorted(data)
    rows = []
    for name, fn in sorting.ALL.items():
        if name == "timsort":
            continue
        check(fn(data), expected, label=f"{name} correctness n={n}")
        rows.append(run_bench(fn, name, data, warmup=1, repeats=repeats))
    rows.append(run_bench(sorting.timsort_reference, "timsort", data, warmup=1, repeats=repeats))
    return rows


def report(rows: list[dict], path: Path | str | None = None) -> Path:
    path = Path(path) if path else Path(__file__).resolve().parent.parent.parent / "evals" / "dsa_bench.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return path


if __name__ == "__main__":
    import sys
    rows = compare_sorts(n=int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
    for r in rows:
        print(f"{r['name']:10s} best={r['best_ms']:10.3f} ms  mean={r['mean_ms']:10.3f} ms")
    p = report(rows)
    print(f"report -> {p}")
