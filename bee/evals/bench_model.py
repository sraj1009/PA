"""Local model throughput/latency benchmark → evals/bench_model.json.

Run:  python -m bee.evals.bench_model [--model qwen3:8b] [--n 5]
Pure Ollama /api/generate calls — no agent loop, no tools.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import httpx


def _bench_gen(base: str, model: str, n: int, max_tokens: int = 256) -> dict:
    latencies, tps = [], []
    for _ in range(n):
        t0 = time.time()
        r = httpx.post(f"{base}/api/generate", json={
            "model": model,
            "prompt": "Explain the quicksort algorithm in exactly one sentence.",
            "stream": False, "options": {"num_ctx": 8192, "num_predict": max_tokens, "temperature": 0},
        }, timeout=600)
        r.raise_for_status()
        j = r.json()
        dt = time.time() - t0
        ntok = j.get("eval_count", 0)
        latencies.append(dt * 1000)
        if ntok:
            tps.append(ntok / (j.get("eval_duration", 1) / 1e9))
    return {
        "n": n, "max_tokens": max_tokens,
        "mean_ms": round(statistics.mean(latencies), 1),
        "p50_ms": round(statistics.median(latencies), 1),
        "min_ms": round(min(latencies), 1),
        "max_ms": round(max(latencies), 1),
        "mean_tokens_per_s": round(statistics.mean(tps), 1) if tps else None,
    }


def _bench_embed(base: str, model: str, n: int) -> dict:
    lat = []
    for _ in range(n):
        t0 = time.time()
        r = httpx.post(f"{base}/api/embeddings",
                       json={"model": model, "prompt": "embedding latency probe"}, timeout=120)
        r.raise_for_status()
        lat.append((time.time() - t0) * 1000)
    return {"n": n, "mean_ms": round(statistics.mean(lat), 1),
            "p50_ms": round(statistics.median(lat), 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--n", type=int, default=5)
    args = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from bee.config import load_config
    cfg = load_config()
    out = {"ts": time.time(), "machine": "RTX 3050 8GB / Windows", "results": {}}
    try:
        out["results"]["generation"] = _bench_gen(cfg.ollama.base_url, args.model or cfg.ollama.model, args.n)
    except Exception as e:
        out["results"]["generation"] = {"error": str(e)[:200]}
    try:
        out["results"]["embedding"] = _bench_embed(cfg.ollama.base_url, cfg.ollama.embed_model, args.n)
    except Exception as e:
        out["results"]["embedding"] = {"error": str(e)[:200]}
    p = Path(__file__).resolve().parent.parent.parent / "evals" / "bench_model.json"
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
