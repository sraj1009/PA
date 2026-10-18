"""Self-contained monitoring dashboard → metrics/dashboard.html.

Reads metrics.jsonl + evals/results.jsonl + episodes, plus the training
flywheel sources (train/golden/cloud_golden.jsonl, memory/ratings.db,
train/sft_v1.jsonl, evals/baselines.json). No external assets — dark
cinematic theme with electric lime (#D7FF00).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from .. import paths
from . import metrics

BG, PANEL, LINE, TXT, DIM, ACC, ERR, BLU = (
    "#0b0d10", "#12161c", "#1f2630", "#e8edf2", "#8b98a5", "#d7ff00", "#ff5c7c", "#4da3ff")


def _series_by_day(rows, key_event, n_days=14) -> list[tuple[str, int]]:
    days = defaultdict(int)
    today = datetime.now().date()
    for i in range(n_days):
        d = (today.toordinal() - i)
        days[d] = 0
    for r in rows:
        if r.get("event") != key_event:
            continue
        try:
            d = datetime.fromtimestamp(r["ts"]).date().toordinal()
        except Exception:
            continue
        if d in days:
            days[d] += 1
    return [(datetime.fromordinal(d).strftime("%m-%d"), c) for d, c in sorted(days.items(), reverse=True)]


def _bars(pairs: list[tuple[str, int]], color: str) -> str:
    if not pairs:
        return "<div class='empty'>no data yet</div>"
    mx = max(v for _k, v in pairs) or 1
    cells = []
    for k, v in pairs:
        h = max(2, int(v / mx * 120))
        cells.append(f"<div class='col' title='{k}: {v}'><div class='bar' style='height:{h}px;background:{color}'></div><div class='lbl'>{k}</div></div>")
    return "<div class='bars'>" + "".join(cells) + "</div>"


def _kpi(label: str, value: str, sub: str = "", tone: str = "") -> str:
    return (f"<div class='kpi'><div class='kpi-v {tone}'>{value}</div>"
            f"<div class='kpi-l'>{label}</div><div class='kpi-s'>{sub}</div></div>")


# ------------------------------------------------------- training flywheel
# P1-8: the flywheel's four ledgers, rendered as cards. Every helper is
# tolerant by contract — a missing/corrupt source renders as an empty state,
# never an error, and nothing here may CREATE the source it reads.

def _golden_series(n_days: int = 14) -> tuple[list[tuple[str, int]], int]:
    """Cloud-golden rows/day (teach-back corpus) + total rows on disk.

    `train/golden/cloud_golden.jsonl` is the corpus the nightly SFT build
    eats; its growth rate is the flywheel's feed rate. Rows carry
    `ts: YYYY-MM-DDTHH:MM:SS` (see `agent.episode_metrics.golden`)."""
    f = paths.TRAIN_DIR / "golden" / "cloud_golden.jsonl"
    days = {datetime.now().date().toordinal() - i: 0 for i in range(n_days)}
    total = 0
    try:
        with f.open(encoding="utf-8", errors="ignore") as fh:
            for ln in fh:
                try:
                    row = json.loads(ln)
                except Exception:
                    continue
                total += 1
                try:
                    d = datetime.strptime(
                        str(row.get("ts") or "")[:10], "%Y-%m-%d").date().toordinal()
                except Exception:
                    continue
                if d in days:
                    days[d] += 1
    except OSError:
        return [], 0
    return ([(datetime.fromordinal(d).strftime("%m-%d"), c)
             for d, c in sorted(days.items(), reverse=True)], total)


def _pairs_summary() -> dict:
    """Preference-pair corpus (memory/ratings.db): totals + per-source counts.

    Reuses bee.memory.ratings with an explicit path; the store must already
    exist (rendering must never create the DB). Any failure = zeros."""
    out: dict = {"total": 0, "by_source": {}, "up": 0, "down": 0, "corrections": 0}
    db = paths.MEMORY_DIR / "ratings.db"
    if not db.exists():
        return out
    try:
        from ..memory import ratings
        st = ratings.stats(db=db)
        rows = ratings.pairs(db=db)
        out.update(up=st.get("up", 0), down=st.get("down", 0),
                   corrections=st.get("corrections", 0),
                   total=st.get("pairs", len(rows)),
                   by_source=dict(Counter((r.get("source") or "?")
                                          for r in rows).most_common()))
    except Exception:
        pass
    return out


def _sft_mix() -> dict:
    """SFT dataset composition from the nightly build (train/sft_v1.jsonl):
    per-sample `metadata.type` distribution + the practice share (P1-6 rows
    are model-generated, not user work). Missing file = empty state."""
    out: dict = {"total": 0, "types": {}, "practice": 0}
    types: Counter = Counter()
    try:
        with (paths.TRAIN_DIR / "sft_v1.jsonl").open(encoding="utf-8",
                                                     errors="ignore") as fh:
            for ln in fh:
                try:
                    md = (json.loads(ln).get("metadata") or {})
                except Exception:
                    continue
                out["total"] += 1
                types[str(md.get("type") or "?")] += 1
                if md.get("practice"):
                    out["practice"] += 1
    except OSError:
        return out
    out["types"] = dict(types.most_common())
    return out


def _gate_lineage() -> dict:
    """Adapter → eval-score lineage, straight from the gate's own ledgers:
    every scored model in evals/baselines.json, its promotions, the pending
    queue (train/gate_candidate.json) and the current override (models.yaml)."""
    out: dict = {"models": [], "promotions": [], "pending": "", "current": ""}
    try:
        data = json.loads((paths.EVALS_DIR / "baselines.json").read_text(encoding="utf-8"))
    except Exception:
        data = {}
    try:
        models = data.get("models") or {}
        out["models"] = sorted(
            [{"model": str(k), "score": str(v.get("score") or "?"),
              "ts": str(v.get("ts") or "")[:10]}
             for k, v in models.items() if isinstance(v, dict)],
            key=lambda m: m["ts"])
        out["promotions"] = [
            {"ts": str(p.get("ts") or "")[:10], "from": str(p.get("from") or "?"),
             "to": str(p.get("to") or "?"), "before": str(p.get("before") or "?"),
             "after": str(p.get("after") or "?")}
            for p in (data.get("promotions") or []) if isinstance(p, dict)][-5:]
    except Exception:
        pass
    try:
        q = json.loads((paths.TRAIN_DIR / "gate_candidate.json").read_text(encoding="utf-8"))
        out["pending"] = str(q.get("model") or "")
    except Exception:
        pass
    try:
        import yaml
        my = paths.MODELS_YAML
        if my.exists():
            out["current"] = str((yaml.safe_load(my.read_text(encoding="utf-8")) or {})
                                 .get("local_model") or "")
    except Exception:
        pass
    return out


def render(refresh_seconds: int = 0) -> str:
    """The dashboard as HTML. `refresh_seconds` > 0 makes the page reload itself,
    which is what the live web route uses; the written file stays a snapshot."""
    st = metrics.stats()
    rows = metrics.load_all()
    tasks = [r for r in rows if r.get("event") == "task"]
    by_day = _series_by_day(rows, "task")
    models = dict(Counter(t.get("model") for t in tasks))
    tools = dict(Counter(r.get("tool") for r in rows if r.get("event") == "tool"))
    tool_fail = dict(Counter(r.get("tool") for r in rows if r.get("event") == "tool" and not r.get("ok")))
    routes = dict(Counter(r.get("source") for r in rows if r.get("event") == "route"))

    # eval history
    evals = []
    if paths.EVAL_RESULTS.exists():
        for ln in paths.EVAL_RESULTS.read_text(encoding="utf-8").splitlines():
            try:
                evals.append(json.loads(ln))
            except Exception:
                pass
    runs = defaultdict(lambda: [0, 0])
    for e in evals:
        ts = e.get("ts", "")[:16]
        runs[ts][1] += 1
        if e.get("ok"):
            runs[ts][0] += 1
    eval_series = [(k, f"{v[0]}/{v[1]}") for k, v in list(runs.items())[-14:]]

    def _eval_bar(k: str, v: str):
        parts = k.replace("T", " ").split()
        label = (parts[0][5:] + " " + parts[1][:2]) if len(parts) == 2 else k[:11]
        try:
            int(v.split("/")[1])  # total must be non-zero
            ok = int(v.split("/")[0])
        except (ValueError, IndexError):
            ok = 0
        return label, ok

    eval_bars = [_eval_bar(k, v) for k, v in eval_series] if eval_series else []

    ep_count = 0
    for f in paths.EPISODES_DIR.glob("*.jsonl"):
        ep_count += sum(1 for _ in f.open(encoding="utf-8", errors="ignore"))

    # P1-8: the training flywheel — feed rate, pairs, dataset mix, model lineage
    golden_bars, golden_total = _golden_series()
    pairs_info = _pairs_summary()
    sft = _sft_mix()
    lineage = _gate_lineage()
    sft_bars = _bars([(k, v) for k, v in sft["types"].items()], BLU)
    sft_pct = int(round(100 * sft["practice"] / sft["total"])) if sft["total"] else 0
    pairs_rows = ("".join(f"<tr><td>{k}</td><td>{v}</td></tr>"
                          for k, v in pairs_info["by_source"].items())
                  or "<tr><td colspan=2>no pairs yet</td></tr>")
    lineage_rows = "".join(
        f"<tr><td>{m['model']}</td><td>{m['score']}</td><td>{m['ts']}</td></tr>"
        for m in lineage["models"])
    promo_rows = "".join(
        f"<tr><td>{p['from']} → {p['to']}</td>"
        f"<td>{p['before']} → {p['after']}</td><td>{p['ts']}</td></tr>"
        for p in lineage["promotions"])
    promo_table = f"<table>{promo_rows}</table>" if promo_rows else ""
    gate_state = []
    if lineage["pending"]:
        gate_state.append(f"pending gate candidate: {lineage['pending']}")
    if lineage["current"]:
        gate_state.append(f"current override: {lineage['current']}")
    gate_line = " · ".join(gate_state) or "no promotion recorded yet"

    success = st.get("success_rate")
    success_txt = f"{success * 100:.1f}%" if success is not None else "—"
    kpis = "".join([
        _kpi("tasks (7d)", str(st.get("total_tasks", 0)), f"{st.get('tasks_ok', 0)} ok"),
        _kpi("success rate", success_txt, "deterministic + LLM", "acc" if (success or 0) >= 0.9 else ""),
        _kpi("avg latency", f"{st.get('avg_seconds', 0)}s", f"avg iters {st.get('avg_iters', 0)}"),
        _kpi("escalations", str(st.get("escalations", 0)), "local→cloud"),
        _kpi("guard denials", str(st.get("guard_denied", 0)), f"{st.get('guard_asks', 0)} approvals asked"),
        _kpi("PII redactions", str(st.get("redactions", 0)), "before cloud"),
        _kpi("episodes stored", str(ep_count), "data flywheel fuel"),
        _kpi("verify fails", str(st.get("verify_fail", 0)), "bounded fix rounds"),
    ])

    model_rows = "".join(f"<tr><td>{k or '?'}</td><td>{v}</td></tr>"
                         for k, v in sorted(models.items(), key=lambda kv: -kv[1]))
    tool_rows = "".join(f"<tr><td>{k or '?'}</td><td>{v}</td><td>{tool_fail.get(k, 0)}</td></tr>"
                        for k, v in sorted(tools.items(), key=lambda kv: -kv[1])[:12])
    route_rows = "".join(f"<tr><td>{k or '?'}</td><td>{v}</td></tr>"
                         for k, v in sorted(routes.items(), key=lambda kv: -kv[1]))

    refresh_meta = (f'<meta http-equiv="refresh" content="{int(refresh_seconds)}">'
                    if refresh_seconds else "")
    sub_line = (f"generated {datetime.now():%Y-%m-%d %H:%M:%S} · live view, "
                f"reload every {int(refresh_seconds)} s · data: metrics/metrics.jsonl"
                if refresh_seconds else
                f"generated {datetime.now():%Y-%m-%d %H:%M:%S} · "
                f"refresh: python -m bee.cli dashboard · data: metrics/metrics.jsonl")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>BEE — monitoring</title>
<style>
 body {{ background:{BG}; color:{TXT}; font:14px/1.5 "Segoe UI",system-ui,sans-serif; margin:0; }}
 .wrap {{ max-width:1100px; margin:0 auto; padding:24px; }}
 h1 {{ font-size:20px; letter-spacing:2px; }} h1 span {{ color:{ACC}; }}
 .sub {{ color:{DIM}; font-size:12px; margin-bottom:20px; }}
 .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:20px; }}
 .kpi {{ background:{PANEL}; border:1px solid {LINE}; border-radius:10px; padding:14px; }}
 .kpi-v {{ font-size:26px; font-weight:700; }} .kpi-v.acc {{ color:{ACC}; }}
 .kpi-l {{ color:{DIM}; font-size:12px; margin-top:4px; }} .kpi-s {{ font-size:11px; color:{DIM}; }}
 .grid {{ display:grid; grid-template-columns:1.4fr 1fr; gap:16px; }}
 .card {{ background:{PANEL}; border:1px solid {LINE}; border-radius:10px; padding:16px; margin-bottom:16px; }}
 .card h3 {{ margin:0 0 12px; font-size:13px; color:{DIM}; text-transform:uppercase; letter-spacing:1px; }}
 .bars {{ display:flex; align-items:flex-end; gap:6px; height:150px; }}
 .col {{ flex:1; display:flex; flex-direction:column; justify-content:flex-end; align-items:center; height:100%; }}
 .bar {{ width:70%; border-radius:3px 3px 0 0; }}
 .lbl {{ font-size:9px; color:{DIM}; margin-top:4px; }}
 .empty {{ color:{DIM}; font-size:12px; padding:20px 0; text-align:center; }}
 table {{ width:100%; border-collapse:collapse; font-size:13px; }}
 td {{ padding:5px 8px; border-bottom:1px solid {LINE}; }} td:last-child {{ color:{DIM}; }}
 .sect {{ color:{ACC}; font-size:12px; letter-spacing:2px; text-transform:uppercase; margin:30px 0 12px; }}
 .sect span {{ color:{DIM}; text-transform:none; letter-spacing:0; margin-left:8px; }}
 .note {{ color:{DIM}; font-size:11px; margin-top:8px; }}
 .foot {{ color:{DIM}; font-size:11px; margin-top:24px; }}
</style>{refresh_meta}</head><body><div class="wrap">
<h1>BEE <span>//</span> MONITORING</h1>
<div class="sub">{sub_line}</div>
<div class="kpis">{kpis}</div>
<div class="grid">
 <div>
  <div class="card"><h3>tasks — last 14 days</h3>{_bars(by_day, ACC)}</div>
  <div class="card"><h3>eval runs (pass/total)</h3>{_bars(eval_bars, BLU)}</div>
  <div class="card"><h3>tool usage (7d) — calls / failures</h3>
    <table><tr><td>tool</td><td>calls</td><td>failures</td></tr>{tool_rows}</table></div>
 </div>
 <div>
  <div class="card"><h3>models</h3><table>{model_rows or '<tr><td colspan=2>no tasks yet</td></tr>'}</table></div>
  <div class="card"><h3>route sources</h3><table>{route_rows or '<tr><td colspan=2>no routes yet</td></tr>'}</table></div>
 </div>
</div>
<div class="sect">training flywheel<span>goldens → pairs → sft → gate</span></div>
<div class="grid">
 <div>
  <div class="card"><h3>cloud goldens — last 14 days · {golden_total} total</h3>{_bars(golden_bars, ACC)}</div>
  <div class="card"><h3>SFT type-mix — train/sft_v1.jsonl · {sft['total']} samples</h3>{sft_bars}
   <div class="note">practice share: {sft_pct}% ({sft['practice']} of {sft['total']} rows are model-generated, not user work)</div></div>
 </div>
 <div>
  <div class="card"><h3>preference pairs · {pairs_info['total']}</h3>
   <table><tr><td>source</td><td>pairs</td></tr>{pairs_rows}</table>
   <div class="note">ratings +1/−1 {pairs_info['up']}/{pairs_info['down']} · corrections {pairs_info['corrections']}</div></div>
  <div class="card"><h3>model lineage — adapter → gate score</h3>
   <table><tr><td>model</td><td>score</td><td>scored</td></tr>{lineage_rows or '<tr><td colspan=3>no gate runs yet</td></tr>'}</table>
   {promo_table}
   <div class="note">{gate_line}</div></div>
 </div>
</div>
<div class="foot">BEE local-first agent · episodes: train/episodes/ · eval history: evals/results.jsonl · flywheel: train/golden/ · memory/ratings.db · train/sft_v1.jsonl · evals/baselines.json · pipeline report: python -m bee.pipeline.report</div>
</div></body></html>"""
    return html


def build() -> Path:
    """Snapshot the dashboard to metrics/dashboard.html (the `/dashboard` command).
    The web app serves `render(refresh_seconds=…)` live instead — this file is a
    point-in-time copy, so opening it later shows the data as of this run."""
    html = render()
    p = paths.METRICS_DIR / "dashboard.html"
    p.write_text(html, encoding="utf-8")
    return p
