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
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import joblib

from .. import paths

ARTIFACT = paths.ROUTER_MODEL

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


_CACHE = {"key": None, "bundle": None}
_ivw_filtered = [False]  # one-shot: global sklearn unpickle filter set


def load():
    """Returns bundle dict or None.

    Cached by (path, mtime): predict() runs on EVERY task, and joblib.load()
    re-unpickles the 4000-feature TF-IDF + classifier from disk each time — a real
    hot-path cost. We load once and only reload when the artifact actually changes
    (i.e. after a retrain), so repeated routing decisions are in-memory only.
    """
    try:
        if not ARTIFACT.exists():
            return None
        key = (str(ARTIFACT), ARTIFACT.stat().st_mtime)
        if _CACHE["bundle"] is not None and _CACHE["key"] == key:
            return _CACHE["bundle"]
        import warnings as _warnings
        try:
            from sklearn.exceptions import InconsistentVersionWarning as _Ivw
        except Exception:
            _Ivw = None
        # patch-level sklearn drift (1.9.1 -> 1.9.0 across venvs) is safe to
        # load; targeted GLOBAL filter (a scoped catch_warnings races between
        # the main thread and the auto-learn thread and lets the warning leak)
        if _Ivw is not None and not _ivw_filtered[0]:
            _warnings.filterwarnings("ignore", message="Trying to unpickle estimator",
                                     category=_Ivw)
            _ivw_filtered[0] = True
        b = joblib.load(ARTIFACT)
        _CACHE["bundle"], _CACHE["key"] = b, key
        return b
    except Exception:
        return None


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


def save_bundle(tfidf, clf, n_train: int, cv_acc: float, model_type: str = "logreg") -> Path:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"tfidf": tfidf, "clf": clf, "n_train": n_train,
                 "cv_acc": round(cv_acc, 4), "model_type": model_type,
                 "num_feats": _NUM_FEAT_NAMES()}, ARTIFACT)
    return ARTIFACT


def _NUM_FEAT_NAMES():
    return _NUM_FEATS


def summarize() -> dict:
    b = load()
    if not b:
        return {"trained": False}
    return {"trained": True, "n_train": b.get("n_train"), "cv_acc": b.get("cv_acc"),
            "model_type": b.get("model_type", "logreg"), "artifact": str(ARTIFACT)}
