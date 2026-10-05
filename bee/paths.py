"""Canonical paths for BEE. Everything memory-related lives under PROJECT_ROOT."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Workspace = where BEE reads/writes files and runs shell/code
WORKSPACE = Path(os.environ.get("BEE_WORKSPACE", str(PROJECT_ROOT)))

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
