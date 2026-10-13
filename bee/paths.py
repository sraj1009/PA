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
# The kernel's two append-only audit streams. Module-level (not `PROJECT_ROOT /
# "memory" / ...` written out at each call site) because a hardcoded path cannot
# be redirected: every scored eval run rebuilt its kernel inside `_isolated_memory()`
# expecting sessions + receipts to follow, and they did not — 1568 of 1571 rows in
# the user's receipts.jsonl and 23 eval-*.json files in memory/sessions/ came from
# eval runs (measured 2026-10-13).
SESSIONS_DIR = MEMORY_DIR / "sessions"
RECEIPTS_FILE = MEMORY_DIR / "receipts.jsonl"
# Same reason, different stream: bee.security.audit.audit_path() used to build
# `PROJECT_ROOT / "audit.jsonl"` inline. PROJECT_ROOT is the checkout and is never
# redirected, so neither the suite nor the eval could move it and every scored run's
# tool rows appended to the user's audit file (3142 rows measured 2026-10-13, with no
# session field in the row — so the residue was not even removable afterwards).
AUDIT_FILE = PROJECT_ROOT / "audit.jsonl"

SKILLS_DIR = PROJECT_ROOT / "skills"
MODELS_YAML = PROJECT_ROOT / "models.yaml"

CONFIG_YAML = PROJECT_ROOT / "config.yaml"
# The persisted engine choice. A module-level path (not `PROJECT_ROOT / ...`
# inside the caller) so the test suite can redirect it — an unredirectable path
# is what let the suite write user state before (A25b, A27f).
SETTINGS_JSON = PROJECT_ROOT / "settings.json"
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
        SESSIONS_DIR,
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
