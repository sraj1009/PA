"""Environment + service health check: `python -m bee.cli health` / `/health`."""
from __future__ import annotations

import importlib.util
import shutil
import sys

import httpx
import shutil as _sh
from pathlib import Path


def _disk_free_gb(p: Path) -> float:
    try:
        return round(_sh.disk_usage(str(p)).free / 1e9, 1)
    except Exception:
        return -1.0


def run_checks(cfg) -> list[dict]:
    out = []

    def add(ok, name, note=""):
        out.append({"ok": bool(ok), "name": name, "note": note})

    add(sys.version_info >= (3, 10), f"python {sys.version.split()[0]}", "need >= 3.10")
    for mod, label in [
        ("litellm", "litellm (LLM gateway)"), ("lancedb", "lancedb (vector memory)"),
        ("apscheduler", "apscheduler (nightly jobs)"), ("fastapi", "fastapi (web UI)"),
        ("sklearn", "scikit-learn (ML router)"), ("joblib", "joblib (router artifact)"),
        ("faster_whisper", "faster-whisper (voice in)"), ("sounddevice", "sounddevice (mic)"),
        ("pyttsx3", "pyttsx3 (voice out)"),
    ]:
        ok = importlib.util.find_spec(mod) is not None
        add(ok, label, "" if ok else "missing — pip install -r requirements.txt / -voice.txt")

    try:
        r = httpx.get(f"{cfg.ollama.base_url}/api/tags", timeout=4)
        models = [m["name"] for m in r.json().get("models", [])]
        add(bool(models), "ollama", ", ".join(models[:6]) or "no models")
        need = {cfg.ollama.model, cfg.ollama.embed_model}
        missing = [m for m in need if not any(m == x or m.split(":")[0] == x.split(":")[0] for x in models)]
        if missing:
            add(False, "required models", "missing: " + ", ".join(missing) + " — ollama pull <name>")
    except Exception as e:
        # A60: BEE can start this server itself, so the advice depends on whether it
        # tried and what happened — a plain "start Ollama" was wrong half the time.
        from ..agent import localserver
        add(False, "ollama", f"OFFLINE ({str(e)[:40]}) — {localserver.offline_hint(cfg)}")

    has_key = bool(cfg.cloud.api_key)
    add(bool(cfg.cloud.enabled and cfg.cloud.llm and has_key),
        f"cloud ({cfg.cloud.llm or 'not set'})",
        "" if has_key else "set OPENROUTER_API_KEY / OPENAI_API_KEY or cloud.api_key")

    try:
        r = subprocess_docker_version()
        add(r is not None, "docker", r or "unreachable — start Docker Desktop")
        if r:
            has_img = docker_has_image(cfg.sandbox.image)
            add(has_img, "sandbox image", cfg.sandbox.image if has_img else
                f"{cfg.sandbox.image} not built — docker build -t {cfg.sandbox.image} .\\sandbox")
    except Exception as e:
        add(False, "docker", str(e)[:80])

    free = _disk_free_gb(Path(cfg.workspace))
    add(free > 10, f"disk free {free} GB", "keep > 10 GB for models/venvs" if free <= 10 else "")
    return out


def subprocess_docker_version():
    import subprocess
    try:
        r = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                           capture_output=True, text=True, timeout=8)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except Exception:
        return None


def docker_has_image(name: str) -> bool:
    import subprocess
    try:
        r = subprocess.run(["docker", "image", "inspect", name], capture_output=True,
                           text=True, timeout=8)
        return r.returncode == 0
    except Exception:
        return False


def cli_report(cfg) -> None:
    checks = run_checks(cfg)
    from . import metrics
    st = metrics.stats()
    print("\n== BEE health ==")
    for c in checks:
        print(f"  [{'OK ' if c['ok'] else '!! '}] {c['name']:36s} {c['note']}")
    if st.get("total_tasks"):
        print(f"\n  activity (7d): {st['total_tasks']} tasks, "
              f"{(st.get('success_rate') or 0) * 100:.1f}% ok, "
              f"avg {st.get('avg_seconds')}s, {st['escalations']} escalations, "
              f"{st['redactions']} redactions, {st['guard_denied']} guard denials")
    print()
