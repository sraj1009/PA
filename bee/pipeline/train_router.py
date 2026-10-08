"""Episodes → ML route classifier (TF-IDF + LogisticRegression).

Labels derived from outcomes (only unambiguous episodes label anything):
  det   — task is a pure math expression
  cloud — episode escalated to cloud and succeeded
  local — succeeded on local without escalation
Failed episodes are skipped (label is ambiguous).

Run:  python -m bee.pipeline.train_router [--min 50]
Out:  train/router_model.joblib + train/router_cv_report.json

REPRODUCIBILITY (Program Phase 7, 2026-10-08):
  - The report is NOT a single accuracy number. Per-class precision/recall/F1,
    the confusion matrix, probability calibration (confidence bins vs empirical
    accuracy + macro-Brier), and the dataset-imbalance audit are all recorded,
    on a held-out split whenever the data allows it (flagged when in-sample).
  - The artifact carries a `meta` block (model format/version, training date,
    dataset version fingerprint, Python/numpy/scipy/scikit-learn/joblib
    versions) so load-time compatibility is checkable with a clear message.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from .. import paths
from ..brain.mlrouter import features, save_bundle, make_mlp, default_meta
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


def dataset_version(pairs: list[tuple[str, str]]) -> str:
    """Stable fingerprint of the labeled dataset (order-insensitive). Recorded
    into the artifact meta so any load environment can say WHICH data produced
    the model (Phase 7 reproducibility)."""
    lines = sorted(f"{(t or '')[:120]}|{l}" for t, l in pairs)
    return hashlib.sha1("\n".join(lines).encode("utf-8")).hexdigest()[:16]


def imbalance_report(pairs: list[tuple[str, str]]) -> dict:
    """Class-imbalance audit (Phase 7): routing classes are rarely balanced,
    and overall accuracy hides a majority-class guesser."""
    counts = {k: sum(1 for _t, l in pairs if l == k) for k in ("local", "cloud", "det")}
    vals = [v for v in counts.values() if v > 0]
    ratio = round(max(vals) / min(vals), 2) if vals else None
    return {"counts": counts, "max_to_min_ratio": ratio,
            "flag": bool(ratio and ratio >= 10) or (not vals)}


def evaluate_classifier(make_clf, X, y, labels=None, test_size: float = 0.25,
                        seed: int = 42) -> dict:
    """Honest per-class evaluation (Phase 7): precision/recall/F1 per class,
    confusion matrix, probability calibration (confidence bins vs empirical
    accuracy + macro-Brier), and holdout accuracy.

    Held-out split whenever the data allows (n>=40 and every class >=3);
    otherwise IN-SAMPLE, honestly flagged — never a fake holdout. Overall
    accuracy is reported but is NOT the headline metric.
    """
    from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

    labels = [str(l) for l in (labels or sorted(set(y)))]
    y = [str(v) for v in y]
    X = np.asarray(X)
    n = len(y)
    min_class = min((y.count(l) for l in labels), default=0)
    in_sample = n < 40 or min_class < 3
    if in_sample:
        Xtr, Xte, ytr, yte = X, X, list(y), list(y)
    else:
        from sklearn.model_selection import train_test_split
        try:
            Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=test_size,
                                                  stratify=y, random_state=seed)
        except ValueError:  # a class too rare to stratify — plain split
            Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=test_size,
                                                  random_state=seed)
    clf = make_clf()
    clf.fit(Xtr, ytr)
    pred = [str(p) for p in clf.predict(Xte)]
    proba = clf.predict_proba(Xte)
    col = {str(c): j for j, c in enumerate(clf.classes_)}

    cm = confusion_matrix(yte, pred, labels=labels)
    p, r, f, sup = precision_recall_fscore_support(yte, pred, labels=labels,
                                                    zero_division=0)
    per_class = {}
    for i, l in enumerate(labels):
        per_class[l] = {"precision": round(float(p[i]), 4),
                        "recall": round(float(r[i]), 4),
                        "f1": round(float(f[i]), 4),
                        "support": int(sup[i])}

    # calibration: binned confidence (of the chosen class) vs empirical accuracy
    n_te = len(yte)
    conf = proba.max(axis=1)
    nb = 5
    bins = []
    for bi in range(nb):
        lo, hi = bi / nb, (bi + 1) / nb
        idx = [i for i in range(n_te)
               if conf[i] >= lo and (conf[i] < hi or bi == nb - 1)]
        if idx:
            acc = sum(1 for i in idx if yte[i] == pred[i]) / len(idx)
            avg_conf = sum(conf[i] for i in idx) / len(idx)
            bins.append({"bin": f"[{lo:.2f},{hi:.2f})", "n": len(idx),
                         "avg_confidence": round(avg_conf, 4),
                         "empirical_accuracy": round(acc, 4)})
        else:
            bins.append({"bin": f"[{lo:.2f},{hi:.2f})", "n": 0,
                         "avg_confidence": None, "empirical_accuracy": None})

    # macro-Brier over the classes present in the model
    brier_terms = []
    for l in labels:
        if l in col:
            j = col[l]
            sq = sum((proba[t, j] - (1.0 if yte[t] == l else 0.0)) ** 2
                     for t in range(n_te))
            brier_terms.append(sq / n_te if n_te else 0.0)
    brier = round(sum(brier_terms) / len(brier_terms), 4) if brier_terms else None

    acc = round(sum(1 for a, b in zip(yte, pred) if a == b) / n_te, 4) if n_te else 0.0
    return {"in_sample": in_sample, "n_total": n, "n_train": int(len(ytr)),
            "n_test": int(len(yte)), "accuracy": acc, "per_class": per_class,
            "confusion": {"labels": labels, "matrix": cm.tolist()},
            "calibration": {"bins": bins, "brier_macro": brier}}


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
              "label_counts": {k: sum(1 for _t, l in pairs if l == k) for k in ("local", "cloud", "det")},
              "imbalance": imbalance_report(pairs)}

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

    # Phase 7: record the dataset fingerprint + environment metadata INTO the
    # artifact, and evaluate per-class on a holdout (not a single accuracy).
    ds_version = dataset_version(pairs)
    meta = default_meta(dataset_version=ds_version, n_train=len(pairs),
                        model_type=best_name)
    classes = [str(c) for c in sorted(set(labels))]
    save_bundle(tfidf, clf, n_train=len(pairs), cv_acc=scores[best_name],
                model_type=best_name, meta=meta)
    try:
        evalrep = evaluate_classifier(lambda: _mk(best_name), X, labels,
                                      labels=classes)
    except Exception as e:
        evalrep = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    report.update({"status": "trained", "model": best_name,
                   "cv_acc_mean": scores[best_name], "cv_acc_std": stds.get(best_name, 0.0),
                   "candidates": scores, "classes": classes,
                   "dataset_version": ds_version, "metadata": meta,
                   "eval": evalrep})
    _write(report)
    print(json.dumps(report, indent=1))
    if isinstance(evalrep, dict) and "per_class" in evalrep:
        hdr = "holdout" if not evalrep["in_sample"] else "in-sample"
        print(f"per-class ({hdr}, n={evalrep['n_test']}):")
        for l, m in evalrep["per_class"].items():
            print(f"  {l:8s} P={m['precision']:.3f} R={m['recall']:.3f} "
                  f"F1={m['f1']:.3f} support={m['support']}")
        cal = evalrep["calibration"]
        print(f"  brier_macro={cal['brier_macro']} "
              f"accuracy={evalrep['accuracy']} (NOT the headline metric)")
    print(f"model -> {paths.ROUTER_MODEL}  ({best_name}, cv_acc={scores[best_name]}, "
          f"dataset={ds_version})")
    return 0


def _write(report: dict):
    p = paths.TRAIN_DIR / "router_cv_report.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
