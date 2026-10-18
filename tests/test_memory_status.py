"""`python -m bee.cli memory status` / `/mem status` — read-only memory index
report: source chunk counts, transcript entries dropped, index age + rows,
dirty queue. Hermetic: every memory path points into tmp.

Registered in tests/conftest.py:_UNIT.
"""
from __future__ import annotations

import pytest

from bee import cli as bee_cli
from bee import paths
from bee.memory import status as st


@pytest.fixture
def mem_tree(monkeypatch, tmp_path):
    diary = tmp_path / "diary"
    diary.mkdir()
    (diary / "2026-10-18.md").write_text(
        "# diary\n\n"
        "## 09:12:03\nnote (fast path): the wifi password was rotated to hunter2\n\n"
        "## 10:00:00 [model=local]\ntask: q\nresult: r\n", encoding="utf-8")
    monkeypatch.setattr(paths, "DIARY_DIR", diary)
    monkeypatch.setattr(paths, "LESSONS_DIR", tmp_path / "lessons")
    monkeypatch.setattr(paths, "MEMORY_DIR", tmp_path)
    monkeypatch.setattr(paths, "PROFILE_MD", tmp_path / "profile.md")
    monkeypatch.setattr(paths, "LONGTERM_MD", tmp_path / "longterm.md")
    monkeypatch.setattr(paths, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(paths, "VECTOR_DIR", tmp_path / "vectors")
    return tmp_path


def test_collect_counts_sources_and_dropped_logs(mem_tree):
    s = st.collect()
    assert s["sources"]["diary"]["files"] == 1
    assert s["sources"]["diary"]["chunks"] == 1          # the log entry is excluded
    assert s["dropped_logs"] == 1
    text = st.render(s)
    assert "== memory status ==" in text and "diary" in text
    assert "logs dropped  1" in text
    assert "dirty queue" in text and "vector index" in text


def test_render_shapes_for_missing_env():
    s = {"sources": {}, "dropped_logs": 0, "index_age_s": None,
         "index_rows": None, "dirty": None}
    text = st.render(s)
    assert "vector index  n/a" in text
    assert "dirty queue   n/a" in text


def test_run_status_and_usage(mem_tree, capsys):
    assert st.run(["status"]) == 0
    assert "== memory status ==" in capsys.readouterr().out
    assert st.run(["bogus"]) == 2
    assert "usage" in capsys.readouterr().out


def test_cli_memory_status_mode(mem_tree, capsys):
    assert bee_cli.main(["memory", "status"]) == 0
    assert "== memory status ==" in capsys.readouterr().out
