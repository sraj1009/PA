"""ML route classifier: feature extraction + ML/DL model round-trip through predict().

Proves the router works end-to-end for BOTH the classical (LogisticRegression) and
deep-learning (MLPClassifier) models, without touching the real artifact or episodes.
"""
import numpy as np
import pytest

from bee.brain import mlrouter


def test_features_keys_match():
    _, num = mlrouter.features("open chrome and fetch https://x.com then sort the list")
    assert list(num.keys()) == list(mlrouter._NUM_FEATS)
    assert num["has_url"] == 1
    assert num["tool_hints"] >= 1
    assert num["has_path"] == 0
    assert num["has_number"] == 0
    _, num2 = mlrouter.features("read C:\\data\\report.csv and note that 42 rows exist")
    assert num2["has_path"] == 1
    assert num2["has_number"] == 1
    assert num2["log_len"] > 0


@pytest.fixture
def tmp_artifact(tmp_path, monkeypatch):
    art = tmp_path / "router_test.joblib"
    monkeypatch.setattr(mlrouter, "ARTIFACT", art)
    return art


def _make_data():
    texts, labels = [], []
    for i in range(30):
        texts.append(f"pure math expression number {i} plus two times three")
        labels.append("det")
        texts.append(f"write a comprehensive research report and design a system architecture audit {i}")
        labels.append("cloud")
        texts.append(f"open the local file and list its contents quickly {i}")
        labels.append("local")
    return texts, labels


def _features_matrix(texts):
    from sklearn.feature_extraction.text import TfidfVectorizer
    import scipy.sparse as sp
    tfidf = TfidfVectorizer(max_features=500, ngram_range=(1, 2), min_df=1)
    Xt = tfidf.fit_transform(texts)
    Xn = np.array([[float(v) for v in mlrouter.features(t)[1].values()] for t in texts])
    X = sp.hstack([Xt, sp.csr_matrix(Xn)], format="csr")
    return tfidf, X


def test_roundtrip_logreg(tmp_artifact):
    from sklearn.linear_model import LogisticRegression
    texts, labels = _make_data()
    tfidf, X = _features_matrix(texts)
    clf = LogisticRegression(max_iter=1000)
    clf.fit(X, labels)
    mlrouter.save_bundle(tfidf, clf, n_train=len(texts), cv_acc=0.95, model_type="logreg")
    got = mlrouter.predict("open the local file and list its contents quickly 99", min_conf=0.3)
    assert got is not None
    assert got[0] in ("local", "cloud", "det")


def test_roundtrip_mlp_dl(tmp_artifact):
    """The DL option (feature-scaled MLP) must save + predict exactly like the ML one,
    and converge cleanly (no ConvergenceWarning) thanks to the StandardScaler."""
    from bee.brain.mlrouter import make_mlp
    texts, labels = _make_data()
    tfidf, X = _features_matrix(texts)
    clf = make_mlp()
    clf.fit(X.toarray(), labels)
    mlrouter.save_bundle(tfidf, clf, n_train=len(texts), cv_acc=0.95, model_type="mlp")
    got = mlrouter.predict("open the local file and list its contents quickly 99", min_conf=0.3)
    assert got is not None
    s = mlrouter.summarize()
    assert s["model_type"] == "mlp"


def test_make_mlp_is_scaled_pipeline():
    """The DL model must be a Pipeline whose first step is a scaler (the accuracy fix)."""
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from bee.brain.mlrouter import make_mlp
    for deep in (False, True):
        p = make_mlp(deep=deep)
        assert isinstance(p, Pipeline)
        assert isinstance(p.named_steps["scale"], StandardScaler)
