"""A54 — /plan owns a JSON task store, and three ways to lose the user's tasks.

The store is read with `except: return []` and written with a truncate-then-write,
so one unreadable read + one `/plan add` replaced the whole list with the single
new task. Ids came from `len(tasks) + 1`, which repeats after a prune.
"""
from __future__ import annotations

import json
import os

import pytest

from bee import paths
from bee.commands import plan as plan_mod


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "WORKSPACE", tmp_path)
    return tmp_path / "plans" / "tasks.json"


def _plan(arg):
    return plan_mod.plan(None, arg)


def test_an_unreadable_store_is_kept_not_erased(store):
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text('[{"id": "t1", "title": "pay tax', encoding="utf-8")   # truncated file
    out = _plan("add ship the report")
    assert "unreadable" in out, out
    kept = list(store.parent.glob("tasks.corrupt-*.json"))
    assert len(kept) == 1, kept
    assert "pay tax" in kept[0].read_text(encoding="utf-8")     # the bytes survived
    assert len(json.loads(store.read_text(encoding="utf-8"))) == 1


def test_ids_do_not_repeat_after_a_prune(store):
    for title in ("alpha", "beta", "gamma"):
        _plan(f"add {title}")
    assert _plan("done t2").startswith("Marked 1 done")
    _plan("clear-done")
    out = _plan("add delta")
    ids = [t["id"] for t in json.loads(store.read_text(encoding="utf-8"))]
    assert len(ids) == len(set(ids)), f"duplicate task ids: {ids}"
    assert "t3" not in out, out          # t3 is still in the store


def test_a_save_never_leaves_a_partial_file(store, monkeypatch):
    """The write goes to a sibling temp file and is renamed over the store, so a
    reader — or a crash between truncate and write — can never see half a list."""
    store.parent.mkdir(parents=True, exist_ok=True)
    calls: list[tuple] = []
    real_replace = os.replace

    def spy(src, dst, *a, **kw):
        calls.append((str(src), str(dst)))
        # at rename time the payload is already complete on disk
        assert len(json.loads(open(src, encoding="utf-8").read())) == 500
        return real_replace(src, dst, *a, **kw)

    monkeypatch.setattr(os, "replace", spy)
    plan_mod._save([{"id": f"t{i}", "title": "x" * 200, "priority": "P2",
                     "status": "todo"} for i in range(500)])
    assert calls and calls[0][0] != calls[0][1]
    assert calls[0][0].endswith(".tmp")
    assert not list(store.parent.glob(".*.tmp"))     # nothing left behind


def test_the_store_round_trips_what_it_wrote(store):
    _plan("add renew passport due 2026-11-01 P1")
    rows = json.loads(store.read_text(encoding="utf-8"))
    assert rows[0]["due"] == "2026-11-01" and rows[0]["priority"] == "P1"
    assert "| t1 |" in _plan("list")


def test_unknown_subcommand_is_reported_not_raised(store):
    assert "unknown subcommand" in _plan("frobnicate")
