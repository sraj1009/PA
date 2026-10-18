"""`python -m bee.cli doctor` / `/doctor` — one-shot, read-only system report.

Report sections: python/platform/workspace (+ free disk), config load +
precedence summary, guard mode + capability inventory, Ollama reachability and
the required models (cfg.ollama.model + cfg.ollama.embed_model), cloud provider
configured (yes/no only — key material is never printed), memory vector-index
age + dirty queue, last eval summary path.

Design constraints:
  - never starts a service — the CLI dispatches doctor BEFORE the native
    telemetry daemon and the Ollama autostart (see bee/cli.py:main);
  - every probe is individually guarded, so one broken subsystem degrades one
    section of the report, not the report;
  - no secrets: env-var NAMES may appear in probe errors, values never. The
    cloud check renders as yes/no only.

Exit codes (CLI mode): 0 = healthy, 1 = local core unavailable (Ollama
unreachable, or a required model missing), 2 = config could not be loaded.
"""
from __future__ import annotations

import platform
import re
import shutil
import sys
import time
from pathlib import Path

from .. import paths
from ..agent import providers
from ..config import load_config
from ..security import capabilities as caps


def _human_age(seconds: float) -> str:
    if seconds < 120:
        return f"{int(seconds)} s"
    if seconds < 7200:
        return f"{seconds / 60:.1f} m"
    if seconds < 48 * 3600:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} d"


def _scrub(s: object, limit: int = 200) -> str:
    """Error text may echo a broken config line: strip token-shaped runs and
    truncate. Doctor output must never carry credential material."""
    s = re.sub(r"[A-Za-z0-9_\-]{24,}", "[redacted]", str(s))
    return s[:limit]


# ------------------------------------------------------------------- probes
def _probe_ollama(cfg) -> dict:
    base = str(getattr(getattr(cfg, "ollama", None), "base_url", "") or
               "http://localhost:11434").rstrip("/")
    out = {"up": False, "base_url": base, "models": [], "error": ""}
    try:
        import httpx
        r = httpx.get(base + "/api/tags", timeout=4.0)
        out["up"] = r.status_code == 200
        if out["up"]:
            out["models"] = [str(m.get("name", "")) for m in (r.json().get("models") or [])]
        else:
            out["error"] = f"HTTP {r.status_code}"
    except Exception as e:                      # connect refused, DNS, timeout…
        out["error"] = f"{type(e).__name__}: {_scrub(e, 120)}"
    return out


def _has_model(models: list[str], want: str) -> bool:
    def norm(x: str) -> str:
        return x.strip().lower().split(":")[0]
    return any(norm(m) == norm(want) for m in models)


def _cloud_configured(cfg) -> bool:
    try:
        ok, _reason = providers.cloud_available(cfg)
        return bool(ok)          # reason is env-var-name-level; still not rendered
    except Exception:
        return False


def _memory_status() -> dict:
    out = {"dir": str(paths.VECTOR_DIR), "index_age_s": None, "dirty": None}
    try:
        if paths.VECTOR_DIR.exists():
            newest = max((p.stat().st_mtime for p in paths.VECTOR_DIR.iterdir()),
                         default=None)
            if newest is not None:
                out["index_age_s"] = max(0.0, time.time() - newest)
    except Exception:
        pass
    try:
        from ..memory import search
        out["dirty"] = len(search.pending_paths())
    except Exception:
        pass
    return out


def _last_eval_summary() -> dict:
    for cand in (paths.EVALS_DIR / "REPORT.md", paths.EVAL_RESULTS):
        try:
            if cand.exists():
                return {"path": str(cand), "mtime": cand.stat().st_mtime}
        except Exception:
            continue
    return {"path": None, "mtime": None}


# ------------------------------------------------------------------- report
def collect(cfg, config_path=None) -> dict:
    """Gather every fact the report needs. All probes guarded; no secrets."""
    cp = Path(config_path) if config_path else paths.CONFIG_YAML
    try:
        cp_found = cp.exists()
    except Exception:
        cp_found = False

    ws = Path(getattr(cfg, "workspace", paths.WORKSPACE))
    try:
        free_gb = round(shutil.disk_usage(str(ws)).free / 1e9, 1)
    except Exception:
        free_gb = -1.0

    prec = dict(getattr(cfg, "precedence", None) or {})
    guard = getattr(cfg, "guard", None)

    oll = _probe_ollama(cfg)
    needs: list[str] = []
    for m in (getattr(getattr(cfg, "ollama", None), "model", ""),
              getattr(getattr(cfg, "ollama", None), "embed_model", "")):
        m = str(m or "")
        if m and m not in needs:
            needs.append(m)
    oll["required"] = needs
    oll["missing"] = [m for m in needs if not _has_model(oll["models"], m)]

    return {
        "system": {
            "python": sys.version.split()[0],
            "impl": platform.python_implementation(),
            "platform": platform.platform(),
            "workspace": str(ws),
            "free_gb": free_gb,
        },
        "config": {"path": str(cp), "found": cp_found, "precedence": prec},
        "guard": {
            "mode": str(getattr(guard, "mode", "?") or "?"),
            "capabilities": len(caps.CAPABILITIES),
            "default_deny": sum(1 for c in caps.CAPABILITIES.values()
                                if c.default_policy == caps.DENY),
        },
        "ollama": oll,
        "cloud": {"configured": _cloud_configured(cfg)},
        "memory": _memory_status(),
        "evals": _last_eval_summary(),
    }


def _precedence_summary(prec: dict) -> str:
    buckets: dict[str, int] = {}
    for v in prec.values():
        v = str(v).lower()
        if v.startswith("default"):
            k = "default"
        elif v.startswith("config.yaml"):
            k = "config.yaml"
        elif v.startswith(".env"):
            k = ".env"
        elif v.startswith("process-env"):
            k = "process-env"
        elif v.startswith("models.yaml"):
            k = "models.yaml"
        else:
            k = "other"
        buckets[k] = buckets.get(k, 0) + 1
    order = ["config.yaml", "models.yaml", ".env", "process-env", "default", "other"]
    return " · ".join(f"{k} {buckets[k]}" for k in order if buckets.get(k)) or "n/a"


def _verdict(rep: dict) -> tuple[str, str]:
    oll = rep.get("ollama") or {}
    if not oll.get("up"):
        return "DEGRADED", "Ollama unreachable — the local model tier is unavailable"
    if oll.get("missing"):
        return "DEGRADED", "missing Ollama model(s): " + ", ".join(oll["missing"])
    return "OK", "core is healthy"


def exit_code(rep: dict) -> int:
    return 0 if _verdict(rep)[0] == "OK" else 1


def _fmt_ts(ts) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(ts)))
    except Exception:
        return ""


def render(rep: dict) -> str:
    s = rep.get("system") or {}
    c = rep.get("config") or {}
    g = rep.get("guard") or {}
    o = rep.get("ollama") or {}
    m = rep.get("memory") or {}
    ev = rep.get("evals") or {}
    verdict, why = _verdict(rep)

    def row(label: str, val: str) -> str:
        return f"  {label:<14}{val}"

    free = s.get("free_gb", -1.0)
    free_s = (f"free {free} GB"
              if isinstance(free, (int, float)) and free >= 0 else "free disk n/a")

    lines = ["== BEE doctor ==", "", "system"]
    lines.append(row("python", f"{s.get('python', '?')} ({s.get('impl', '?')})"))
    lines.append(row("platform", str(s.get("platform", "?"))))
    lines.append(row("workspace", f"{s.get('workspace', '?')}  ({free_s})"))

    lines.append("config")
    lines.append(row("file", f"{c.get('path', '?')} [{'found' if c.get('found') else 'MISSING'}]"))
    lines.append(row("precedence", _precedence_summary(c.get("precedence") or {})))
    lines.append(row("guard mode", str(g.get("mode", "?"))))
    lines.append(row("gate", f"kernel-owned — {g.get('capabilities', 0)} capabilities "
                             f"({g.get('default_deny', 0)} default-deny)"))

    lines.append("services")
    if o.get("up"):
        lines.append(row("ollama", f"UP {o.get('base_url', '')} — "
                                   f"{len(o.get('models') or [])} model(s)"))
    else:
        lines.append(row("ollama", f"DOWN {o.get('base_url', '')} — "
                                   f"{o.get('error') or 'no response'}"))
    req = o.get("required") or []
    if req:
        miss = set(o.get("missing") or [])
        lines.append(row("models", " · ".join(
            f"{r} {'OK' if r not in miss else 'MISSING'}" for r in req)))
    lines.append(row("cloud", f"configured: {'yes' if (rep.get('cloud') or {}).get('configured') else 'no'}"))

    lines.append("memory")
    age = m.get("index_age_s")
    age_s = f"{_human_age(age)} old" if isinstance(age, (int, float)) else "n/a"
    lines.append(row("vector index", f"{age_s}  ({m.get('dir', '?')})"))
    dq = m.get("dirty")
    dq_s = f"{dq} file(s) pending embed" if isinstance(dq, (int, float)) else "n/a"
    lines.append(row("dirty queue", dq_s))

    lines.append("evals")
    if ev.get("path"):
        ts = _fmt_ts(ev.get("mtime"))
        lines.append(row("last summary", f"{ev['path']} ({ts})" if ts else str(ev["path"])))
    else:
        lines.append(row("last summary", "none"))

    lines.append("")
    lines.append(f"verdict: {verdict} — {why}")
    return "\n".join(lines)


# ------------------------------------------------------------------- entry
def cli_report(cfg) -> None:
    """REPL `/doctor` — same report, no exit-code semantics."""
    print(render(collect(cfg)))


def run(config_path=None) -> int:
    """CLI `python -m bee.cli doctor`. Loads config itself so a broken file
    is REPORTED (exit 2) instead of crashing before the report."""
    try:
        cfg = load_config(config_path)
    except Exception as e:
        print("== BEE doctor ==")
        print("")
        print("config        FAILED to load — the agent cannot start")
        print(f"  error       {type(e).__name__}: {_scrub(e)}")
        print("")
        print("verdict: BROKEN — fix the configuration and re-run")
        return 2
    rep = collect(cfg, config_path)
    print(render(rep))
    return exit_code(rep)
