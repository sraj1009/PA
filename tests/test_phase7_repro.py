"""Phase 7 — ROUTING + TEST/CI REPRODUCIBILITY (2026-10-08).

Covers, with evidence rather than claims:
  * artifact metadata (model format/version, training date, dataset version,
    Python/numpy/scipy/sklearn/joblib) is written by save_bundle and read back
  * load-time compatibility: MAJOR sklearn mismatch -> REFUSED with a clear,
    actionable message (no cryptic traceback); minor drift -> loads with a
    warning; v1 artifacts (no meta) -> still load; corrupt bundle -> clear msg
  * training report: per-class precision/recall/F1, confusion matrix,
    calibration (bins + macro-Brier), dataset-imbalance audit, dataset version
  * runtime telemetry: route_ml_fallback reasons + prediction latency (ms)
  * ml_report.runtime_report: fallback rate + p50/p95 latency from metrics
  * requirements-ml.txt pins match the installed ML stack
  * the core/optional classification is honest: every file marked optional is
    importorskip-guarded (Phase 7 rule: never hide a REAL DEFECT behind
    'optional'; never let a MISSING DEP fail the core suite)

Category: ml (sklearn required). The CI 'ml' job installs requirements-ml.txt
pinned, then runs exactly this category.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import sklearn  # noqa: F401  (ml category by definition)

import joblib
from bee import paths
from bee.brain import mlrouter
from bee.pipeline import train_router as tr


def test_default_meta_records_environment():
    meta = mlrouter.default_meta(dataset_version="abc123", n_train=10,
                                 model_type="logreg")
    for k in ("model_format", "model_version", "trained_at", "python",
              "numpy", "scipy", "sklearn", "joblib", "dataset_version",
              "n_train", "model_type"):
        assert k in meta, f"meta missing key: {k}"
    assert meta["dataset_version"] == "abc123"
    assert meta["sklearn"] == sklearn.__version__
    assert meta["n_train"] == 10 and meta["model_type"] == "logreg"


def _tiny_model(tmp, meta=None):
    """A small, fast LogReg bundle on synthetic 3-class data (no episodes)."""
    texts, labels = [], []
    for i in range(20):
        texts.append(f"pure math expression number {i} plus two times three")
        labels.append("det")
        texts.append(f"write a comprehensive research report and design a system architecture audit {i}")
        labels.append("cloud")
        texts.append(f"open the local file and list its contents quickly {i}")
        labels.append("local")
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    import scipy.sparse as sp
    tfidf = TfidfVectorizer(max_features=500, ngram_range=(1, 2), min_df=1)
    Xt = tfidf.fit_transform(texts)
    Xn = np.array([[float(v) for v in mlrouter.features(t)[1].values()] for t in texts])
    X = sp.hstack([Xt, sp.csr_matrix(Xn)], format="csr")
    clf = LogisticRegression(max_iter=2000)
    clf.fit(X, labels)
    art = tmp / "router_p7.joblib"
    mlrouter.save_bundle(tfidf, clf, n_train=len(texts), cv_acc=0.9,
                         model_type="logreg",
                         meta=meta or mlrouter.default_meta(
                             dataset_version="test-ds", n_train=len(texts),
                             model_type="logreg"))
    return art, texts, labels


@pytest.fixture
def p7(monkeypatch, tmp_path):
    """Isolated artifact + metrics + fresh cache for each test."""
    art = tmp_path / "router_p7.joblib"
    monkeypatch.setattr(mlrouter, "ARTIFACT", art)
    monkeypatch.setattr(mlrouter, "_CACHE",
                        {"key": None, "bundle": None, "error": "",
                         "compatible": True, "checked": False})
    metrics_file = tmp_path / "metrics.jsonl"
    monkeypatch.setattr(paths, "METRICS_FILE", metrics_file)
    return art, metrics_file


def test_save_bundle_writes_metadata(p7):
    art, _, _ = _tiny_model(p7[0].parent,
                            meta=mlrouter.default_meta(dataset_version="ds-9",
                                                       n_train=60,
                                                       model_type="logreg"))
    b = mlrouter.load()
    assert b is not None
    assert b["meta"]["dataset_version"] == "ds-9"
    assert b["meta"]["sklearn"] == sklearn.__version__
    st = mlrouter.load_status()
    assert st["loaded"] and st["compatible"] and not st["error"]
    s = mlrouter.summarize()
    assert s["trained"] and s["meta"]["model_format"] == mlrouter.MODEL_FORMAT


def test_major_sklearn_mismatch_refused_with_clear_message(p7):
    art, _, _ = _tiny_model(p7[0].parent)
    b = joblib.load(art)
    b["meta"]["sklearn"] = "0.9.9"          # different MAJOR than installed
    joblib.dump(b, art)
    mlrouter._CACHE.update(key=None, bundle=None, error="", checked=False)
    got = mlrouter.load()
    assert got is None
    st = mlrouter.load_status()
    assert st["loaded"] is False and st["compatible"] is False
    assert "MAJOR version mismatch" in st["error"]
    assert "0.9.9" in st["error"] and sklearn.__version__ in st["error"]
    assert "train_router" in st["error"]    # actionable, not cryptic
    # and predict() degrades to None (router falls back to heuristics)
    assert mlrouter.predict("any task", min_conf=0.1) is None


def test_minor_sklearn_drift_loads(p7):
    art, _, _ = _tiny_model(p7[0].parent)
    b = joblib.load(art)
    major, minor, _ = sklearn.__version__.split(".")[:3]
    b["meta"]["sklearn"] = f"{major}.{max(0, int(minor) - 1)}.0"
    joblib.dump(b, art)
    mlrouter._CACHE.update(key=None, bundle=None, error="", checked=False)
    assert mlrouter.load() is not None      # minor drift = sklearn-safe
    assert mlrouter.load_status()["compatible"] is True


def test_v1_artifact_without_meta_still_loads(p7):
    art, _, _ = _tiny_model(p7[0].parent)
    b = joblib.load(art)
    del b["meta"]                            # pre-Phase-7 artifact
    joblib.dump(b, art)
    mlrouter._CACHE.update(key=None, bundle=None, error="", checked=False)
    assert mlrouter.load() is not None
    assert mlrouter.summarize()["trained"] is True


def test_corrupt_bundle_gives_clear_error(p7):
    art, _, _ = _tiny_model(p7[0].parent)
    art.write_bytes(b"this is not a joblib file")
    mlrouter._CACHE.update(key=None, bundle=None, error="", checked=False)
    assert mlrouter.load() is None
    st = mlrouter.load_status()
    assert st["compatible"] is False
    assert "re-train" in st["error"] and "router artifact" in st["error"]


def test_load_missing_dependency_message(monkeypatch, tmp_path):
    """With joblib absent, load() must say exactly what to install —
    no cryptic traceback (Phase 7: MISSING DEP is reported, not crashed)."""
    tf = tmp_path / "exists.joblib"
    tf.write_bytes(b"x")
    monkeypatch.setattr(mlrouter, "ARTIFACT", tf)
    monkeypatch.setattr(mlrouter, "_CACHE",
                        {"key": None, "bundle": None, "error": "",
                         "compatible": True, "checked": False})
    monkeypatch.setattr(mlrouter, "joblib", None, raising=False)
    assert mlrouter.load() is None
    st = mlrouter.load_status()
    assert st["compatible"] is False
    assert "requirements-ml.txt" in st["error"]


# ---------------------------------------------------------------- training
def test_dataset_version_stable_and_order_insensitive():
    a = [("t1", "local"), ("t2", "cloud"), ("t3", "det")]
    assert tr.dataset_version(a) == tr.dataset_version(list(reversed(a)))
    assert tr.dataset_version(a) != tr.dataset_version([("t1", "local"),
                                                        ("t2", "cloud")])
    assert len(tr.dataset_version(a)) == 16


def test_imbalance_report_flags_skew():
    pairs = [("x", "local")] * 30 + [("y", "cloud")] * 3
    rep = tr.imbalance_report(pairs)
    assert rep["counts"] == {"local": 30, "cloud": 3, "det": 0}
    assert rep["max_to_min_ratio"] == 10.0
    assert rep["flag"] is True
    even = tr.imbalance_report([("x", "local"), ("y", "cloud")])
    assert even["flag"] is False


def test_evaluate_classifier_reports_per_class():
    from sklearn.linear_model import LogisticRegression
    texts, labels = [], []
    for i in range(30):
        texts.append(f"math expression {i} plus two times three")
        labels.append("det")
        texts.append(f"comprehensive research report architecture audit {i}")
        labels.append("cloud")
        texts.append(f"open the local file and list its contents {i}")
        labels.append("local")
    from sklearn.feature_extraction.text import TfidfVectorizer
    import scipy.sparse as sp
    tfidf = TfidfVectorizer(max_features=300, ngram_range=(1, 2), min_df=1)
    Xt = tfidf.fit_transform(texts)
    Xn = np.array([[float(v) for v in mlrouter.features(t)[1].values()] for t in texts])
    X = sp.hstack([Xt, sp.csr_matrix(Xn)], format="csr").toarray()
    ev = tr.evaluate_classifier(lambda: LogisticRegression(max_iter=2000),
                                X, labels, labels=["cloud", "det", "local"])
    assert set(ev["per_class"]) == {"cloud", "det", "local"}
    for m in ev["per_class"].values():
        assert 0.0 <= m["precision"] <= 1.0 and 0.0 <= m["recall"] <= 1.0
        assert 0.0 <= m["f1"] <= 1.0
    cm = ev["confusion"]
    assert cm["labels"] == ["cloud", "det", "local"]
    assert len(cm["matrix"]) == 3 and all(len(r) == 3 for r in cm["matrix"])
    assert sum(map(sum, cm["matrix"])) == ev["n_test"]
    cal = ev["calibration"]
    assert len(cal["bins"]) == 5
    assert cal["brier_macro"] is None or 0.0 <= cal["brier_macro"] <= 1.0
    assert ev["n_test"] > 0 and not ev["in_sample"]
    # tiny data -> honestly flagged in-sample, never a fake holdout
    tiny = tr.evaluate_classifier(lambda: LogisticRegression(max_iter=500),
                                  X[:12], labels[:12],
                                  labels=["cloud", "det", "local"])
    assert tiny["in_sample"] is True


def test_train_main_writes_full_report(p7, monkeypatch):
    """End-to-end: synthetic episodes -> trained artifact + report with
    per-class metrics, confusion, calibration, metadata, dataset version."""
    art, metrics_file = p7
    rows = []
    for i in range(15):
        rows.append({"task": f"23+{i}", "ok": True, "escalated": False})
    for i in range(12):
        rows.append({"task": f"write a comprehensive research report on topic {i} "
                             f"with deep analysis and architecture",
                     "ok": True, "escalated": True})
    for i in range(13):
        rows.append({"task": f"open the local file notes{i}.txt and list its lines",
                     "ok": True, "escalated": False})
    monkeypatch.setattr(tr, "load_episodes", lambda: rows)
    captured = {}
    monkeypatch.setattr(tr, "_write", lambda r: captured.update(r))
    rc = tr.main(argv=["--min", "5"])
    assert rc == 0
    rep = captured
    assert rep["status"] == "trained"
    assert rep["dataset_version"] and len(rep["dataset_version"]) == 16
    assert rep["metadata"]["dataset_version"] == rep["dataset_version"]
    ev = rep["eval"]
    assert "per_class" in ev and "confusion" in ev and "calibration" in ev
    assert set(ev["per_class"]) >= {"local", "cloud", "det"}
    # artifact meta matches the report (load env can verify the provenance)
    b = mlrouter.load()
    assert b["meta"]["dataset_version"] == rep["dataset_version"]
    assert b["meta"]["sklearn"] == sklearn.__version__


# ---------------------------------------------------------------- runtime
def _cfg_p7():
    from bee.config import load_config
    cfg = load_config()
    cfg.cloud.enabled = False
    cfg.router.ml_enabled = True
    cfg.router.ml_confidence = 0.3
    return cfg


def test_router_records_not_trained_fallback(p7):
    from bee.agent import router
    cfg = _cfg_p7()
    r = router.route("explain quantum entanglement in some detail", cfg)
    assert r["source"] == "heuristic"           # ML absent -> deterministic path
    rows = [json.loads(l) for l in p7[1].read_text(encoding="utf-8").splitlines()]
    fb = [x for x in rows if x["event"] == "route_ml_fallback"]
    assert fb and fb[0]["reason"] == "not_trained"


def test_router_records_latency_and_low_confidence_fallback(p7):
    from bee.agent import router
    art, metrics_file = p7
    _tiny_model(art.parent)
    cfg = _cfg_p7()
    # a confident-looking task for the trained bundle -> ML used, ms recorded
    r = router.route("open the local file and list its contents quickly 77", cfg)
    rows = [json.loads(l) for l in metrics_file.read_text(encoding="utf-8").splitlines()]
    used = [x for x in rows if x["event"] == "route_ml" and x.get("used")]
    if used:
        assert isinstance(used[0].get("ms"), (int, float)) and used[0]["ms"] >= 0
        assert r["source"] in ("ml", "complexity")
    else:
        # low confidence on this sample -> the fallback reason must say why
        fb = [x for x in rows if x["event"] == "route_ml_fallback"]
        assert fb and str(fb[0]["reason"]).startswith(("low_confidence",))


def test_ml_report_runtime_percentiles(p7):
    from bee.brain import ml_report
    art, metrics_file = p7
    import time as _t
    now = round(_t.time(), 3)
    rows = ([{"ts": now, "event": "route_ml", "pred": "local", "used": True, "ms": m}
             for m in (1.0, 2.0, 10.0)]
            + [{"ts": now, "event": "route_ml_fallback", "reason": "not_trained"}])
    with metrics_file.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    rep = ml_report.runtime_report(window_hours=1)
    assert rep["ml_decisions"] == 3 and rep["fallbacks"] == 1
    assert rep["fallback_rate"] == 0.25
    assert rep["fallback_reasons"] == {"not_trained": 1}
    assert rep["latency_ms"]["p50"] == 2.0
    assert rep["latency_ms"]["p95"] == 10.0
    assert rep["prediction_counts"] == {"local": 3}
    text = ml_report.render({"artifact": {"trained": False, "error": "x"},
                             "load_status": {"compatible": True,
                                             "load_env": {"python": "3", "sklearn": sklearn.__version__}},
                             "training": {"available": False},
                             "runtime": rep})
    assert "fallback_rate=0.25" in text


# ---------------------------------------------------------------- pins
def test_requirements_ml_pins_match_installed():
    """The pinned ML stack (requirements-ml.txt) must equal the installed
    versions — otherwise artifacts could silently load under a different
    numpy/sklearn than the pins promise (Phase 7)."""
    req = (Path(__file__).resolve().parent.parent / "requirements-ml.txt") \
        .read_text(encoding="utf-8")
    pins = {}
    for line in req.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "==" in line:
            name, ver = line.split("==", 1)
            pins[name.strip()] = ver.strip()
    assert set(pins) >= {"scikit-learn", "numpy", "scipy", "joblib"}
    import importlib.metadata as md
    for name, want in pins.items():
        have = md.version(name)
        assert have == want, (f"requirements-ml.txt pins {name}=={want} but the "
                              f"installed version is {have} — re-pin or "
                              f"re-train the router artifact")


def test_optional_classification_is_honest():
    """Phase 7 rule, enforced: a file is 'optional' ONLY if it is guarded by
    importorskip (MISSING DEP -> skip), and the empirical audit result
    (2026-10-08 blocked-import runs) is exactly {test_livekit}."""
    import importlib.util
    cpath = Path(__file__).resolve().parent / "conftest.py"
    spec = importlib.util.spec_from_file_location("_p7_conftest", cpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert set(mod._OPTIONAL_DEPS) == {"test_livekit"}
    for name in mod._OPTIONAL_DEPS:
        src = (Path(__file__).parent / f"{name}.py").read_text(encoding="utf-8")
        assert "importorskip" in src, (
            f"{name} is classified optional but lacks an importorskip guard — "
            "that would FAIL (not skip) on a bare install")
    # and core must be exactly unit+integration minus the guarded files
    core = set(mod._CORE)
    assert "test_livekit" not in core
    assert "test_computeruse" in core and "test_voice_engine" in core


def test_netguard_suite_is_hermetic():
    """Network security tests must NOT depend on real public DNS: every
    resolver/transport in the netguard suite is injected (Phase 7)."""
    src = (Path(__file__).parent / "test_netguard.py").read_text(encoding="utf-8")
    assert "resolver=" in src and "transport=" in src
    for needle in ("socket", "getaddrinfo", "requests.", "urllib"):
        assert needle not in src, f"test_netguard.py uses real network: {needle}"
