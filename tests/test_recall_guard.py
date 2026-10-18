"""P1-5 - the nightly recall-regression probe (`bee.memory.recall_guard`).

Reproduces both silent-failure species the probe exists for: a vector path
that dies into keyword-only without a word (A38a), and an index/recall drop
nobody notices (A28a). Everything is faked - no index, no model, no metrics
file, no network.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from bee.memory import recall_guard as rg


class _Table:
    def __init__(self, rows):
        self._rows = rows

    def count_rows(self):
        return len(self._rows)

    def search(self):
        return self

    def select(self, _cols):
        return self

    def limit(self, n):
        self._n = n
        return self

    def to_list(self):
        return self._rows[:getattr(self, "_n", len(self._rows))]


class _Store:
    def __init__(self, rows):
        self._table_obj = _Table(rows)

    def _table(self):
        return self._table_obj


def _rows(n):
    src = str(rg.paths.PROJECT_ROOT / "memory" / "longterm.md")
    return [{"source": src, "text": " ".join(f"w{i}x{j}" for j in range(20))}
            for i in range(n)]


def _env(monkeypatch, rows, *, hit=True, vector_alive=True, baseline_rows=None):
    captured = {"records": []}
    monkeypatch.setattr(rg.search, "get_store", lambda ctx: _Store(rows))
    monkeypatch.setattr(rg.md, "all_chunks",
                        lambda: [(str(rg.paths.PROJECT_ROOT / "memory" / "longterm.md"), "x")])
    monkeypatch.setattr(rg.search, "vector_search",
                        lambda ctx, q, k=2: ([{"source": "x"}] if vector_alive else None))
    monkeypatch.setattr(rg.rag, "retrieve",
                        lambda ctx, q, k=8: ([{"source": ".\\memory\\longterm.md",
                                               "text": "t", "mode": "keyword"}] if hit else []))
    monkeypatch.setattr(rg.metrics, "record",
                        lambda event, **d: captured["records"].append({"event": event, **d}))
    monkeypatch.setattr(rg.metrics, "load_all", lambda: list(baseline_rows or []))
    return captured


def _baseline(recalls):
    return [{"event": rg.EVENT, "recall_at_k": r} for r in recalls]


def test_src_key_bridges_absolute_and_relativized_paths():
    """md relays keyword sources relativized (`./memory/...`); the vector
    store keeps the absolute path. Equality across the two is the whole
    reason _src_key exists."""
    abs_path = str(rg.paths.PROJECT_ROOT / "memory" / "longterm.md")
    assert rg._src_key(abs_path) == rg._src_key(".\\memory\\longterm.md")
    assert rg._src_key(abs_path) == "memory/longterm.md"


def test_quote_takes_the_middle_not_the_shared_head():
    short = "one two three four"
    assert rg._quote(short) == short
    q = rg._quote(" ".join(f"w{i}" for i in range(30)))
    assert len(q.split()) == 10
    assert q.split()[0] == "w10"          # 30 // 3
    assert "w0" not in q.split()


def test_sampling_is_a_deterministic_stride():
    rows = _rows(20)
    sampled, total = rg._sample_rows(_Store(rows))
    assert total == 20 and len(sampled) == 8
    assert sampled[0]["text"] == rows[0]["text"]
    assert sampled[1]["text"] == rows[2]["text"]    # stride 20 // 8 == 2


def test_first_run_forms_a_baseline_without_a_verdict(monkeypatch):
    captured = _env(monkeypatch, _rows(4))
    out = rg.run(SimpleNamespace(cfg=None, client=None))
    assert out["verdict"] == "baseline" and out["ok"] is True
    assert out["recall_at_k"] == 1.0 and out["indexed_rows"] == 4
    row = captured["records"][0]
    assert row["verdict"] == "baseline" and row["vector_alive"] is True


def test_regression_vs_trailing_median_raises_and_still_records(monkeypatch):
    captured = _env(monkeypatch, _rows(4), hit=False,
                    baseline_rows=_baseline([1.0, 1.0, 1.0]))
    with pytest.raises(RuntimeError) as e:
        rg.run(SimpleNamespace(cfg=None, client=None))
    assert "regressed" in str(e.value)
    row = captured["records"][0]
    assert row["verdict"] == "regressed", "recorded before the raise"
    assert row["recall_at_k"] == 0.0
    assert row["baseline_median"] == 1.0


def test_dead_vector_path_is_infra_not_silence(monkeypatch):
    """A38a's species: the vector half gone, keyword still answers, nothing
    says a word. The probe must fail loudly even though recall itself is
    unchanged."""
    captured = _env(monkeypatch, _rows(4), vector_alive=False)
    with pytest.raises(RuntimeError) as e:
        rg.run(SimpleNamespace(cfg=None, client=None))
    assert "vector_dead" in str(e.value)
    assert captured["records"][0]["vector_alive"] is False


def test_index_lost_while_files_remain_is_flagged(monkeypatch):
    _env(monkeypatch, [])
    with pytest.raises(RuntimeError) as e:
        rg.run(SimpleNamespace(cfg=None, client=None))
    assert "index_empty" in str(e.value)


def test_fresh_install_is_empty_and_ok(monkeypatch):
    captured = _env(monkeypatch, [])
    monkeypatch.setattr(rg.md, "all_chunks", lambda: [])
    out = rg.run(SimpleNamespace(cfg=None, client=None))
    assert out["verdict"] == "empty" and out["ok"] is True
    assert captured["records"][0]["verdict"] == "empty"


def test_recall_guard_is_a_registered_system_job():
    from bee import scheduler
    assert "recall_guard" in scheduler._SYSTEM_JOB_IDS
    import bee.memory.recall_guard as mod
    assert callable(mod.run)
    # the parity pin in tests/test_audit_fixes.py proves this list matches
    # the specs actually registered by _register_nightly_jobs - so the id
    # cannot drift from the wiring in either direction.
