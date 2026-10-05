"""Engine selection: which brain does BEE use by default?

Asked once at first launch (REPL), persisted in settings.json, switchable with
/engine. Web and voice use the persisted choice. A per-task prefix
('cloud: ...' / 'local: ...') and the fast/deterministic tiers always win.

    hybrid        — local bee4b first, auto-escalation to cloud        (default)
   local         — local model only (bee4b, offline, fast)
  ollama-cloud  — Ollama-hosted cloud model via the local Ollama API (fast)
  api-cloud     — direct API model via env key (fastest)
"""
from __future__ import annotations

import json

from .. import paths

ENGINES: dict[str, dict] = {
    "hybrid": {
        "n": 1,
        "label": "Hybrid — local bee4b first, cloud auto-escalation (recommended, works offline)",
        "override": None,
    },
    "local": {
        "n": 2,
        "label": "Local only — bee4b (3B base, fits 4 GB GPU VRAM, fast), fully offline",
        "override": "local",
    },
    "ollama-cloud": {
        "n": 3,
        "label": "Ollama Cloud — glm-5.2:cloud, remote & fast (needs Ollama login)",
        "override": "glm-5.2:cloud",
    },
    "api-cloud": {
        "n": 4,
        "label": "API Cloud — gemini-3-flash-preview, fastest (needs internet + key)",
        "override": "cloud",
    },
}


def settings_file():
    return paths.PROJECT_ROOT / "settings.json"


def load_engine() -> str | None:
    try:
        data = json.loads(settings_file().read_text(encoding="utf-8"))
        e = data.get("engine")
        return e if e in ENGINES else None
    except Exception:
        return None


def save_engine(engine: str) -> None:
    if engine not in ENGINES:
        return
    try:
        data = {}
        try:
            data = json.loads(settings_file().read_text(encoding="utf-8"))
        except Exception:
            pass
        data["engine"] = engine
        settings_file().write_text(json.dumps(data, indent=1), encoding="utf-8")
    except Exception:
        pass


def override_for(engine: str | None) -> str | None:
    """Session model override for an engine (None = normal hybrid routing)."""
    if engine in ENGINES:
        return ENGINES[engine]["override"]
    return None


def ask_engine(print_info: "callable | None" = None) -> str:
    """First-launch prompt. Non-interactive stdins (pipes/tests) default to hybrid."""
    saved = load_engine()
    if saved:
        return saved
    import sys
    if not sys.stdin.isatty():
        save_engine("hybrid")
        return "hybrid"
    print_info = print_info or (lambda s: print(s))
    print_info("\n  First launch — pick BEE's default brain:")
    for meta in ENGINES.values():
        print_info(f"   [{meta['n']}] {meta['label']}")
    while True:
        try:
            choice = input("  choice [1-4] (1 = hybrid, recommended): ").strip() or "1"
        except (EOFError, KeyboardInterrupt):
            choice = "1"
        if choice in ("1", "2", "3", "4") or choice in ENGINES:
            break
        print_info("  (enter 1-4)")
    engine = [k for k, v in ENGINES.items() if v["n"] == int(choice)][0] \
        if choice in ("1", "2", "3", "4") else choice
    save_engine(engine)
    return engine
