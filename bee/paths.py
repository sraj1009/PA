"""Canonical paths for BEE. Everything memory-related lives under PROJECT_ROOT."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _workspace_from_env() -> Path:
    """BEE_WORKSPACE from the process env, else from .env, else the repo root.

    This module is imported before `config.load_config()` runs `_load_dotenv()`,
    so reading only os.environ split the workspace in two: cfg.workspace (and
    with it memory/, automation/, the sandbox mount) followed a .env setting
    while plans/, drafts/, codeout/ and the STT cache stayed at PROJECT_ROOT.
    """
    raw = os.environ.get("BEE_WORKSPACE")
    if not raw:
        dotenv = PROJECT_ROOT / ".env"
        try:
            for line in dotenv.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("BEE_WORKSPACE="):
                    raw = line.split("=", 1)[1].strip().strip("'\"")
                    break
        except OSError:
            pass
    base = Path(raw).expanduser() if raw else PROJECT_ROOT
    return base.resolve()


# Workspace = where BEE reads/writes files and runs shell/code
WORKSPACE = _workspace_from_env()

MEMORY_DIR = PROJECT_ROOT / "memory"
DIARY_DIR = MEMORY_DIR / "diary"
LESSONS_DIR = MEMORY_DIR / "lessons"
PROFILE_MD = MEMORY_DIR / "profile.md"
LONGTERM_MD = MEMORY_DIR / "longterm.md"
SYSTEM_MD = MEMORY_DIR / "system.md"

SKILLS_DIR = PROJECT_ROOT / "skills"
MODELS_YAML = PROJECT_ROOT / "models.yaml"

CONFIG_YAML = PROJECT_ROOT / "config.yaml"
JOBS_JSON = PROJECT_ROOT / "jobs.json"
JOBS_LOG = PROJECT_ROOT / "jobs.log"
EVALS_DIR = PROJECT_ROOT / "evals"
EVAL_RESULTS = EVALS_DIR / "results.jsonl"

VECTOR_DIR = MEMORY_DIR / "vectors"
SANDBOX_DIR = PROJECT_ROOT / "sandbox"
DOCS_DIR = PROJECT_ROOT / "docs"

METRICS_DIR = PROJECT_ROOT / "metrics"
METRICS_FILE = METRICS_DIR / "metrics.jsonl"
TRAIN_DIR = PROJECT_ROOT / "train"
EPISODES_DIR = TRAIN_DIR / "episodes"
ROUTER_MODEL = TRAIN_DIR / "router_model.joblib"

PY = sys.executable


def ensure_core_dirs() -> None:
    for d in (
        MEMORY_DIR,
        DIARY_DIR,
        LESSONS_DIR,
        SKILLS_DIR,
        VECTOR_DIR,
        EVALS_DIR,
        SANDBOX_DIR,
        METRICS_DIR,
        TRAIN_DIR,
        EPISODES_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
    for f in (PROFILE_MD, LONGTERM_MD):
        if not f.exists():
            f.touch()
