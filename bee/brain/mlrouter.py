"""ML route classifier — learns local|cloud routing from BEE's own episodes.

Pipeline:
  train_router (pipeline/train_router.py) → labels from episode outcomes:
    - task was pure math/dsa            -> "det"
    - episode escalated and succeeded   -> "cloud"
    - succeeded locally without         -> "local"
  Features: task text (TF-IDF) + numeric signals (length, code, urls, tool hints,
  complexity cues). LogisticRegression (interpretable, fast, small artifact).

Usage:
  - router fuses ML with heuristics: ML wins only if confidence >= threshold and
    the model was trained on >= min episodes; otherwise heuristics rule.
  - shadow logging: ML predictions are always recorded in metrics ("route_ml"),
    so you can watch it converge before trusting it.

REPRODUCIBILITY (Program Phase 7, 2026-10-08):
  - The ML router is an OPTIONAL optimizer. The deterministic routing tiers
    (math / explicit hints / smalltalk / heuristics) always run without it;
    an unavailable or broken artifact degrades to heuristics, never to "no
    assistant".
  - Every artifact carries a `meta` block: model format/version, Python,
    numpy, scipy, scikit-learn, joblib versions, training date, and dataset
    version. The load environment is pinned in requirements-ml.txt.
  - Load-time compatibility is checked and reported as a CLEAR message
    (load_status()["error"]) instead of a cryptic traceback: a MAJOR
    scikit-learn mismatch refuses the artifact; a minor drift loads with a
    logged warning (sklearn's own guarantee); a missing dependency says
    exactly what to install.
"""
from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from .. import paths

log = logging.getLogger("bee.mlrouter")

try:
    import joblib
except Exception:  # joblib is part of the ML stack (requirements-ml.txt)
    joblib = None

ARTIFACT = paths.ROUTER_MODEL

# sklearn's InconsistentVersionWarning fires once per estimator on every
# unpickle of a cross-version artifact. Suppress it at IMPORT time (process
# baseline): pytest resets per-test warning filters, so a one-shot flag inside
# load() let the warning leak between tests. We do our OWN explicit version
# check in load() and log a clear message instead (Phase 7).
try:
    import warnings as _warnings
    from sklearn.exceptions import InconsistentVersionWarning as _Ivw
    _warnings.filterwarnings("ignore", message="Trying to unpickle estimator",
                             category=_Ivw)
except Exception:
    _Ivw = None

MODEL_FORMAT = "bee-router/v2"      # v1 artifacts (no meta block) still load
MODEL_VERSION = "1"

_NUM_FEATS = ["length", "words", "has_code", "has_url", "has_math", "num_questions",
              "tool_hints", "complex_cues", "has_path", "has_number", "log_len"]

TOOL_HINTS = re.compile(
    r"\b(file|shell|python|code|search|fetch|url|database|docker|git|csv|excel|"
    r"screenshot|browser|schedule|remind|email|sort|graph|algorithm|complexity|"
    r"neural|train|model|api|json)\b", re.I)
COMPLEX_CUES = re.compile(
    r"\b(comprehensive|in[- ]depth|research report|architect|design a system|"
    r"refactor|audit|thesis|proposal|legal|medical|financial analysis|prove|"
    r"first.*then.*then|multi[- ]step|long[- ]form)\b", re.I)
MATH = re.compile(r"[\d\s\+\-\*/%\^\.]{3,}")
FILE_PATH = re.compile(
    r"[\w\-./\\]*\.(?:py|js|ts|tsx|csv|json|txt|md|ipynb|sh|sql|html|css|xml|yml|"
    r"yaml|docx|xlsx|pdf)\b|\b[A-Za-z]:\\", re.I)


def features(task: str) -> tuple[str, dict]:
    t = task or ""
    low = t.lower()
    return t, {
        "length": len(t),
        "words": len(t.split()),
        "has_code": 1 if ("```" in t or "def " in low or "import " in low or ";" in low and " " in low) else 0,
        "has_url": 1 if re.search(r"https?://", t) else 0,
        "has_math": 1 if MATH.search(t) and re.search(r"[+\-\*/\^]", t) else 0,
        "num_questions": low.count("?"),
        "tool_hints": len(set(TOOL_HINTS.findall(low))),
        "complex_cues": len(COMPLEX_CUES.findall(low)),
        "has_path": 1 if FILE_PATH.search(t) else 0,
        "has_number": 1 if re.search(r"\d", t) else 0,
        "log_len": round(math.log1p(len(t)), 3),
    }


def make_mlp(deep: bool = False):
    """The DL route model: a **feature-scaled** neural net.

    Scaling is the crux — TF-IDF features are ~0-1 while numeric features
    (e.g. `length`) run into the thousands. Unscaled, the net is dominated by the
    big features, converges slowly (the old ConvergenceWarnings) and scores worse.
    Returns a sklearn Pipeline so save/predict treat it like any other classifier.
    Callers must pass DENSE input (the scaler centers it).
    """
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    hidden = (128, 64) if deep else (96,)
    return Pipeline([
        ("scale", StandardScaler()),
        ("mlp", MLPClassifier(hidden_layer_sizes=hidden, max_iter=8000, random_state=42,
                              solver="adam", early_stopping=True,
                              validation_fraction=0.15, tol=1e-5,
                              learning_rate_init=0.003)),
    ])


_CACHE = {"key": None, "bundle": None, "error": "", "compatible": True,
          "checked": False}
_ivw_filtered = [False]  # one-shot: global sklearn unpickle filter set


def default_meta(dataset_version: str = "", n_train: int = 0,
                 model_type: str = "") -> dict:
    """Training-time environment metadata recorded INTO the artifact (Phase 7).

    Keys: model format/version, training date (UTC), dataset version,
    sample count, model type, and the Python + ML-stack versions used to
    TRAIN the model. Compare against the load environment at load time.
    """
    def _ver(mod):
        try:
            import importlib
            return importlib.import_module(mod).__version__
        except Exception:
            return "n/a"
    import sys as _sys
    return {
        "model_format": MODEL_FORMAT,
        "model_version": MODEL_VERSION,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": _sys.version.split()[0],
        "numpy": _ver("numpy"),
        "scipy": _ver("scipy"),
        "sklearn": _ver("sklearn"),
        "joblib": _ver("joblib"),
        "dataset_version": dataset_version,
        "n_train": int(n_train),
        "model_type": model_type,
    }


def _sklearn_ver() -> str:
    try:
        import sklearn
        return sklearn.__version__
    except Exception:
        return ""


def _compat_issue(meta: dict) -> str:
    """'' when compatible; otherwise a clear, actionable message (Phase 7).

    MAJOR scikit-learn drift  -> refuse (artifact may be structurally incompatible)
    MINOR/PATCH drift         -> tolerated with a warning (sklearn's own
                                 unpickle guarantee; retrain for exactness)
    Missing ML stack          -> say exactly what to install
    """
    if joblib is None:
        return ("joblib is not installed — the ML router artifact cannot be loaded. "
                "Install the pinned ML stack: pip install -r requirements-ml.txt "
                "(the deterministic routing tiers are unaffected)")
    trained = str(meta.get("sklearn") or "")
    have = _sklearn_ver()
    if not trained:
        return ""  # v1 artifact (no meta) — nothing to check
    if not have:
        return ("scikit-learn is not installed but the router artifact "
                f"was trained with {trained}. Install the pinned ML stack: "
                "pip install -r requirements-ml.txt (deterministic routing "
                "tiers are unaffected)")
    t, h = trained.split(".")[0], have.split(".")[0]
    if t != h:
        return (f"scikit-learn MAJOR version mismatch: artifact trained with "
                f"{trained}, this environment has {have}. The artifact is "
                "refusing to load (unpickled estimators across major versions "
                "may be silently wrong). Re-train in THIS environment: "
                "python -m bee.pipeline.train_router, or install the pinned "
                "stack: pip install -r requirements-ml.txt")
    return ""


def load():
    """Returns bundle dict or None.

    Cached by (path, mtime): predict() runs on EVERY task, and joblib.load()
    re-unpickles the 4000-feature TF-IDF + classifier from disk each time — a real
    hot-path cost. We load once and only reload when the artifact actually changes
    (i.e. after a retrain), so repeated routing decisions are in-memory only.

    Phase 7: any failure is captured as a CLEAR message in load_status()["error"]
    (never a cryptic traceback into the router), and a major-version incompatible
    artifact is refused, not loaded.
    """
    if not ARTIFACT.exists():
        if _CACHE["bundle"] is not None:
            _CACHE["bundle"], _CACHE["key"] = None, None
        _CACHE["error"], _CACHE["compatible"], _CACHE["checked"] = "", True, True
        return None
    if joblib is None:
        msg = ("the ML stack (joblib) is not installed — the router artifact "
               f"exists at {ARTIFACT} but cannot be loaded. Install the pinned "
               "ML stack: pip install -r requirements-ml.txt (the "
               "deterministic routing tiers are unaffected)")
        _CACHE.update(bundle=None, key=None, error=msg, compatible=False,
                      checked=True)
        log.warning("ML router unavailable: %s", msg)
        return None
    key = (str(ARTIFACT), ARTIFACT.stat().st_mtime)
    if _CACHE["bundle"] is not None and _CACHE["key"] == key:
        return _CACHE["bundle"]
    import warnings as _warnings
    try:
        from sklearn.exceptions import InconsistentVersionWarning as _Ivw
    except Exception:
        _Ivw = None
    # sklearn's own InconsistentVersionWarning is suppressed globally (a scoped
    # catch_warnings races between the main thread and the auto-learn thread);
    # we do our OWN version check instead and log a clear message (Phase 7).
    if _Ivw is not None and not _ivw_filtered[0]:
        _warnings.filterwarnings("ignore", message="Trying to unpickle estimator",
                                 category=_Ivw)
        _ivw_filtered[0] = True
    try:
        b = joblib.load(ARTIFACT)
    except Exception as e:
        msg = (f"failed to load router artifact {ARTIFACT}: "
               f"{type(e).__name__}: {str(e)[:200]} — the ML router is "
               "UNAVAILABLE (this is an optional optimizer; deterministic "
               "routing continues). Delete or re-train the artifact "
               "(python -m bee.pipeline.train_router).")
        _CACHE.update(bundle=None, key=None, error=msg, compatible=False,
                      checked=True)
        log.warning("ML router load failed: %s", msg)
        return None
    if not isinstance(b, dict) or "tfidf" not in b or "clf" not in b:
        msg = (f"router artifact {ARTIFACT} is not a valid bundle (missing "
               "'tfidf'/'clf'). It may be corrupted — re-train: "
               "python -m bee.pipeline.train_router")
        _CACHE.update(bundle=None, key=None, error=msg, compatible=False,
                      checked=True)
        log.warning("ML router load failed: %s", msg)
        return None
    issue = _compat_issue(b.get("meta") or {})
    if issue:
        _CACHE.update(bundle=None, key=None, error=issue, compatible=False,
                      checked=True)
        log.warning("ML router REFUSED: %s", issue)
        return None
    if (b.get("meta") or {}).get("sklearn") and \
            str(b["meta"]["sklearn"]).split(".")[:2] != _sklearn_ver().split(".")[:2]:
        log.warning("ML router: artifact trained with scikit-learn %s, loading "
                    "with %s (minor drift — sklearn-safe, but re-train for "
                    "exactness: python -m bee.pipeline.train_router)",
                    b["meta"]["sklearn"], _sklearn_ver())
    _CACHE.update(bundle=b, key=key, error="", compatible=True, checked=True)
    return b


def load_status() -> dict:
    """Clear, machine-readable load report (Phase 7): what happened and why,
    without a traceback. Used by tests, /health-style surfaces, and docs.
    Triggers a load attempt on first call (so it never reports a stale
    'not loaded' for a perfectly good artifact)."""
    if not _CACHE["checked"]:
        load()
    st = {"artifact": str(ARTIFACT), "exists": ARTIFACT.exists(),
          "loaded": _CACHE["bundle"] is not None,
          "compatible": _CACHE["compatible"], "error": _CACHE["error"],
          "meta": (_CACHE["bundle"] or {}).get("meta") if _CACHE["bundle"] else None,
          "load_env": {"python": __import__("sys").version.split()[0],
                       "sklearn": _sklearn_ver() or "not installed",
                       "numpy": _ver_meta("numpy"),
                       "scipy": _ver_meta("scipy"),
                       "joblib": _ver_meta("joblib")}}
    return st


def _ver_meta(mod: str) -> str:
    try:
        import importlib
        return importlib.import_module(mod).__version__
    except Exception:
        return "not installed"


def predict(task: str, min_conf: float = 0.65) -> tuple[str, float] | None:
    """Returns (label, confidence) or None if model unavailable."""
    b = load()
    if not b:
        return None
    text, num = features(task)
    X = b["tfidf"].transform([text])
    import numpy as np
    Xn = np.hstack([X.toarray(), [[float(v) for v in num.values()]]])
    prob = b["clf"].predict_proba(Xn)[0]
    label = b["clf"].classes_[int(prob.argmax())].item()
    conf = float(prob.max())
    if conf < min_conf:
        return None
    return label, round(conf, 4)


def save_bundle(tfidf, clf, n_train: int, cv_acc: float, model_type: str = "logreg",
                meta: dict | None = None, dataset_version: str = "") -> Path:
    """Persist the artifact WITH training metadata (Phase 7). Callers that
    know the dataset version should pass `meta` built by default_meta() —
    otherwise the metadata is filled in automatically (dataset_version="")."""
    if joblib is None:
        raise RuntimeError("joblib not installed — cannot save the router "
                           "artifact (pip install -r requirements-ml.txt)")
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    m = dict(meta or default_meta(dataset_version=dataset_version,
                                  n_train=n_train, model_type=model_type))
    m.setdefault("n_train", int(n_train))
    m.setdefault("model_type", model_type)
    joblib.dump({"tfidf": tfidf, "clf": clf, "n_train": n_train,
                 "cv_acc": round(cv_acc, 4), "model_type": model_type,
                 "num_feats": _NUM_FEAT_NAMES(), "meta": m}, ARTIFACT)
    _CACHE.update(key=None, bundle=None, error="", compatible=True, checked=False)
    return ARTIFACT


def _NUM_FEAT_NAMES():
    return _NUM_FEATS


def summarize() -> dict:
    b = load()
    if not b:
        st = load_status()
        return {"trained": False, "error": st["error"], "artifact": str(ARTIFACT)}
    return {"trained": True, "n_train": b.get("n_train"), "cv_acc": b.get("cv_acc"),
            "model_type": b.get("model_type", "logreg"), "artifact": str(ARTIFACT),
            "meta": b.get("meta") or {}, "compatible": load_status()["compatible"]}
