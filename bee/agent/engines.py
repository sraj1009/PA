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
import logging

from .. import paths

log = logging.getLogger("bee.engines")

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
    """The persisted engine choice, through `paths` so the test suite can
    redirect it (A41a: an unredirectable path meant any launch of `web`/`voice`
    under a pipe rewrote the USER's settings.json)."""
    return paths.SETTINGS_JSON


def load_engine() -> str | None:
    try:
        data = json.loads(settings_file().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as e:
        log.warning("settings.json is unreadable (%s) — using the hybrid default", e)
        return None
    e = data.get("engine") if isinstance(data, dict) else None
    if e is not None and e not in ENGINES:
        log.warning("settings.json names unknown engine %r — using hybrid routing", e)
        return None
    return e


def save_engine(engine: str) -> bool:
    """Persist the choice. Returns whether it actually happened: the caller may
    not be able to do anything about it, but silently losing the user's explicit
    `/engine` selection is how a config file becomes a lie (A41b)."""
    if engine not in ENGINES:
        return False
    try:
        data = {}
        try:
            data = json.loads(settings_file().read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except FileNotFoundError:
            pass
        except Exception as e:
            log.info("starting settings.json fresh (previous contents unreadable: %s)", e)
        data["engine"] = engine
        settings_file().write_text(json.dumps(data, indent=1), encoding="utf-8")
        return True
    except Exception as e:
        log.warning("could not persist engine %r: %s — this session keeps it, "
                    "the next launch will not", engine, e)
        return False


def override_for(engine: str | None) -> str | None:
    """Session model override for an engine (None = normal hybrid routing)."""
    if engine in ENGINES:
        return ENGINES[engine]["override"]
    return None


def engine_labels(cfg=None) -> dict[str, str]:
    """Human-facing engine labels. The api-cloud label reflects the ACTUAL
    configured cloud model from config (no hard-coded provider assumption)."""
    labels = {k: v["label"] for k, v in ENGINES.items()}
    if cfg is not None and getattr(cfg.cloud, "llm", ""):
        labels["api-cloud"] = f"API Cloud — {cfg.cloud.llm} (direct API, fastest)"
    return labels


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
