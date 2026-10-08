"""ML router report (Program Phase 7, 2026-10-08).

One place to answer "how is the OPTIONAL ML optimizer doing?" with the
metrics the program requires — NOT overall accuracy alone:

  * artifact state     — trained? loadable? environment-compatible? metadata
                         (model version, Python/numpy/scipy/sklearn versions,
                         training date, dataset version)
  * training report    — per-class precision/recall/F1, confusion matrix,
                         calibration (bins + macro-Brier), dataset imbalance
                         (from train/router_cv_report.json)
  * runtime telemetry  — fallback rate + fallback reasons + prediction
                         latency percentiles (from the metrics JSONL stream)

Everything here is a read of persisted data — no model load side effects,
no network. Safe to call from any surface (CLI, web, cron).
"""
from __future__ import annotations

import json
import time

from .. import paths


def _pctl(sorted_vals: list[float], q: float) -> float | None:
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return round(sorted_vals[idx], 1)


def runtime_report(window_hours: float = 24 * 7) -> dict:
    """Fallback rate + latency percentiles over the last `window_hours`."""
    from ..monitor import metrics
    rows = metrics.load_all()
    cutoff = time.time() - window_hours * 3600
    rows = [r for r in rows if r.get("ts", 0) >= cutoff]
    used = [r for r in rows if r.get("event") == "route_ml" and r.get("used")]
    falls = [r for r in rows if r.get("event") == "route_ml_fallback"]
    lat = sorted(r["ms"] for r in used if isinstance(r.get("ms"), (int, float)))
    reasons: dict[str, int] = {}
    for r in falls:
        reason = str(r.get("reason") or "unknown").split(":", 1)[0]
        reasons[reason] = reasons.get(reason, 0) + 1
    pred_counts: dict[str, int] = {}
    for r in used:
        p = str(r.get("pred") or "?")
        pred_counts[p] = pred_counts.get(p, 0) + 1
    total = len(used) + len(falls)
    return {
        "window_hours": window_hours,
        "ml_decisions": len(used),
        "fallbacks": len(falls),
        "fallback_rate": round(len(falls) / total, 4) if total else None,
        "fallback_reasons": reasons,
        "prediction_counts": pred_counts,
        "latency_ms": {"p50": _pctl(lat, 0.50), "p95": _pctl(lat, 0.95),
                       "max": _pctl(lat, 1.0)},
    }


def training_report() -> dict:
    """The last training report (per-class metrics etc.), if any."""
    p = paths.TRAIN_DIR / "router_cv_report.json"
    if not p.exists():
        return {"available": False}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"available": False, "error": "unparseable report file"}


def full_report() -> dict:
    """Artifact + training + runtime in one dict (for /health-style output)."""
    from . import mlrouter
    return {
        "artifact": mlrouter.summarize(),
        "load_status": mlrouter.load_status(),
        "training": training_report(),
        "runtime": runtime_report(),
    }


def render(report: dict | None = None) -> str:
    """Human-readable one-screen summary."""
    rep = report or full_report()
    a = rep.get("artifact") or {}
    st = rep.get("load_status") or {}
    tr = rep.get("training") or {}
    rt = rep.get("runtime") or {}
    L = ["ML ROUTER REPORT"]
    if a.get("trained"):
        meta = a.get("meta") or {}
        L.append(f"  artifact : {a.get('artifact')} ({a.get('model_type')}, "
                 f"n_train={a.get('n_train')}, cv_acc={a.get('cv_acc')})")
        if meta:
            L.append(f"  trained  : {meta.get('trained_at')}  "
                     f"dataset={meta.get('dataset_version')}")
            L.append(f"  trainenv : py={meta.get('python')} numpy={meta.get('numpy')} "
                     f"scipy={meta.get('scipy')} sklearn={meta.get('sklearn')} "
                     f"joblib={meta.get('joblib')}")
        L.append(f"  loadenv  : py={st.get('load_env', {}).get('python')} "
                 f"sklearn={st.get('load_env', {}).get('sklearn')}")
        L.append(f"  compat   : {'OK' if st.get('compatible') else 'REFUSED: ' + str(st.get('error'))[:120]}")
    else:
        L.append(f"  artifact : not loaded — {a.get('error') or 'never trained'}")
    if tr.get("available") or "eval" in tr:
        ev = tr.get("eval") or {}
        if isinstance(ev, dict) and "per_class" in ev:
            scope = "in-sample" if ev.get("in_sample") else f"holdout n={ev.get('n_test')}"
            L.append(f"  training : {tr.get('model')}, {scope}, "
                     f"accuracy={ev.get('accuracy')} (not the headline metric)")
            for cls, m in ev.get("per_class", {}).items():
                L.append(f"    {cls:8s} P={m['precision']:.3f} R={m['recall']:.3f} "
                         f"F1={m['f1']:.3f} support={m.get('support')}")
            cal = ev.get("calibration") or {}
            L.append(f"    brier_macro={cal.get('brier_macro')}")
        imb = tr.get("imbalance") or {}
        if imb:
            L.append(f"  imbalance: {imb.get('counts')} "
                     f"max/min={imb.get('max_to_min_ratio')} "
                     f"{'FLAGGED' if imb.get('flag') else 'ok'}")
    if rt:
        L.append(f"  runtime  : {rt.get('ml_decisions')} ML decisions, "
                 f"fallback_rate={rt.get('fallback_rate')} "
                 f"reasons={rt.get('fallback_reasons') or {}}")
        lat = rt.get("latency_ms") or {}
        if lat.get("p50") is not None:
            L.append(f"  latency  : p50={lat['p50']}ms p95={lat['p95']}ms "
                     f"max={lat['max']}ms")
    return "\n".join(L)


if __name__ == "__main__":
    print(render())
