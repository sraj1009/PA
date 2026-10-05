"""Episodes → ML route classifier (TF-IDF + LogisticRegression).

Labels derived from outcomes (only unambiguous episodes label anything):
  det   — task is a pure math expression
  cloud — episode escalated to cloud and succeeded
  local — succeeded on local without escalation
Failed episodes are skipped (label is ambiguous).

Run:  python -m bee.pipeline.train_router [--min 50]
Out:  train/router_model.joblib + train/router_cv_report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from .. import paths
from ..brain.mlrouter import features, save_bundle, make_mlp
from .build_sft import load_episodes

DET_EXPR = __import__("re").compile(r"^[\d\s\+\-\*/%\.\(\),eE]+$")
DET_OP = __import__("re").compile(r"[+\-\*/]|\*\*")


# Candidate classifiers for the route model: classical ML (LogReg) + a neural net
# (MLPClassifier). "auto" picks whichever cross-validates best.
_MODEL_NAMES = ("logreg", "logreg_C10", "mlp", "mlp_deep")


def label_row(row: dict) -> str | None:
    task = (row.get("task") or "").strip()
    if not row.get("ok"):
        return None
    if DET_EXPR.match(task.replace("^", "")) and DET_OP.search(task) and len(task) < 200:
        return "det"
    return "cloud" if row.get("escalated") else "local"


def main(argv: list[str] | None = None, min_samples: int | None = None):
    """`argv`/`min_samples` allow in-process callers (scheduler) to set the
    sample floor WITHOUT mutating sys.argv (Phase 1: no global argv hacks)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=50, help="min samples to actually fit a model")
    ap.add_argument("--model", default="auto", choices=["auto", *_MODEL_NAMES],
                    help="classifier to use (auto = pick best by cross-validation)")
    args = ap.parse_args(argv)
    if min_samples is not None:
        args.min = min_samples

    from ..config import load_config
    cfg = load_config()
    rows = load_episodes()
    pairs = []
    for r in rows:
        lab = label_row(r)
        if lab:
            pairs.append((r.get("task", ""), lab))
    report = {"episodes": len(rows), "labeled": len(pairs),
              "label_counts": {k: sum(1 for _t, l in pairs if l == k) for k in ("local", "cloud", "det")}}

    if len(pairs) < 10:
        report["status"] = "too few labeled episodes — nothing trained (collect more usage first)"
        _write(report)
        print(json.dumps(report, indent=1))
        return 0

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score, StratifiedKFold
    texts = [t for t, _ in pairs]
    labels = [l for _t, l in pairs]
    tfidf = TfidfVectorizer(max_features=4000, ngram_range=(1, 2), min_df=2,
                            sublinear_tf=True, strip_accents="unicode")
    Xt = tfidf.fit_transform(texts)
    Xn = np.array([[float(v) for v in features(t)[1].values()] for t in texts])
    import scipy.sparse as sp
    # Dense: the DL candidates run a StandardScaler (centers the big numeric
    # features); data is small (hundreds of tasks) so densifying is cheap.
    X = sp.hstack([Xt, sp.csr_matrix(Xn)], format="csr").toarray()

    if len(set(labels)) < 2 or len(pairs) < args.min:
        report["status"] = f"not enough data/variety to fit (n={len(pairs)}, classes={len(set(labels))}) — shadow data accumulating"
        _write(report)
        print(json.dumps(report, indent=1))
        return 0

    def _mk(name: str):
        if name == "logreg":
            return LogisticRegression(max_iter=3000, C=1.0)
        if name == "logreg_C10":
            return LogisticRegression(max_iter=3000, C=10.0)
        if name == "mlp":
            return make_mlp(deep=False)
        return make_mlp(deep=True)

    candidates = list(_MODEL_NAMES) if args.model == "auto" else [args.model]
    min_class = min(labels.count(l) for l in set(labels))
    k = min(5, min_class)
    scores, stds = {}, {}
    if k >= 2:
        cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=42)
        for name in candidates:
            try:
                s = cross_val_score(_mk(name), X, labels, cv=cv, scoring="accuracy")
                scores[name], stds[name] = round(float(s.mean()), 4), round(float(s.std()), 4)
            except Exception as e:
                scores[name], stds[name] = -1.0, 0.0
                print(f"  [{name}] CV failed: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
    else:
        # Severe class imbalance (a class has <2 samples) → stratified CV infeasible.
        # Use in-sample accuracy as a proxy so selection still works; flag it honestly.
        report["cv_infeasible"] = True
        for name in candidates:
            try:
                m = _mk(name)
                m.fit(X, labels)
                scores[name] = round(float(m.score(X, labels)), 4)
                stds[name] = 0.0
            except Exception as e:
                scores[name], stds[name] = -1.0, 0.0
                print(f"  [{name}] fit failed: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
    best_name = max(scores, key=lambda n: scores[n])
    if scores[best_name] <= 0:  # everything failed — fall back to plain logreg
        best_name, scores["logreg"], stds["logreg"] = "logreg", 0.0, 0.0
    clf = _mk(best_name)
    clf.fit(X, labels)
    save_bundle(tfidf, clf, n_train=len(pairs), cv_acc=scores[best_name], model_type=best_name)
    report.update({"status": "trained", "model": best_name,
                   "cv_acc_mean": scores[best_name], "cv_acc_std": stds.get(best_name, 0.0),
                   "candidates": scores,
                   "classes": [str(c) for c in clf.classes_.tolist()]})
    _write(report)
    print(json.dumps(report, indent=1))
    print(f"model -> {paths.ROUTER_MODEL}  ({best_name}, cv_acc={scores[best_name]})")
    return 0


def _write(report: dict):
    p = paths.TRAIN_DIR / "router_cv_report.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
