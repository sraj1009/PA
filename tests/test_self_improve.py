"""Self-improving bee4b: self-critique loop, SQLite ratings (RLAIF input),
success-digest recall, and their SFT integration. All offline."""
from __future__ import annotations

import json
import types

import pytest

from bee.agent import critique
from bee.config import load_config
from bee.memory import ratings


class _Chat:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def chat(self, _engine, messages):
        self.calls.append(messages)
        return {"content": self.text}


def _ctx(client):
    cfg = load_config()
    return types.SimpleNamespace(cfg=cfg, client=client)


# ---------------------------------------------------------- layer 1: critique
def test_critique_ok_keeps_draft():
    ctx = _ctx(_Chat("OK"))
    draft = "The answer is 42. " * 20
    # should_critique needs a real LLMClient; stub clients must NOT pass the
    # gate (otherwise scripted test sequences would shift by one call).
    assert critique.should_critique(ctx, "task", draft) is False
    assert critique.critique_answer(ctx, draft, "task") == draft


def test_critique_gate_real_client_only():
    from bee.agent.client import LLMClient
    cfg = load_config()
    real = types.SimpleNamespace(cfg=cfg, client=LLMClient(cfg))
    draft = "A long enough draft answer. " * 20
    assert critique.should_critique(real, "task", draft) is True
    cfg.learning.self_critique = False
    assert critique.should_critique(real, "task", draft) is False
    cfg.learning.self_critique = True
    assert critique.should_critique(real, "task", "short") is False


def test_critique_applies_bounded_rewrite():
    ctx = _ctx(_Chat("Corrected full answer here. " * 20))
    draft = "Original draft answer here. " * 20
    out = critique.critique_answer(ctx, draft, "task")
    assert out.startswith("Corrected full answer")


def test_critique_rejects_absurd_rewrite():
    ctx = _ctx(_Chat("x" * 10000))
    draft = "Original draft answer here. " * 20
    assert critique.critique_answer(ctx, draft, "task") == draft
    ctx2 = _ctx(_Chat(""))
    assert critique.critique_answer(ctx2, draft, "task") == draft


# ------------------------------------------------- layer 3: ratings (SQLite)
def test_ratings_record_get_stats(tmp_path):
    db = tmp_path / "r.db"
    ratings.record("do math", "4", +1, model="bee4b", db=db)
    got = ratings.get("do math", db=db)
    assert got and got["rating"] == 1 and got["model"] == "bee4b"
    ratings.record("do math", "5", -1, correction="it's 4", db=db)
    got2 = ratings.get("do math", db=db)
    assert got2["rating"] == -1 and got2["correction"] == "it's 4"
    st = ratings.stats(db=db)
    assert st == {"up": 0, "down": 1, "corrections": 1, "pairs": 0}
    assert ratings.blocklisted(db=db) == {ratings.task_key("do math")}
    corr = ratings.corrections(db=db)
    assert len(corr) == 1 and corr[0]["correction"] == "it's 4"


def test_ratings_rejects_bad_input(tmp_path):
    db = tmp_path / "r.db"
    with pytest.raises(ValueError):
        ratings.record("t", "o", 0, db=db)
    with pytest.raises(ValueError):
        ratings.record("", "o", +1, db=db)
    assert ratings.stats(db=db) == {"up": 0, "down": 0, "corrections": 0, "pairs": 0}
    assert ratings.blocklisted(db=db) == set()


def test_ratings_pairs_roundtrip_and_dedupe(tmp_path):
    db = tmp_path / "r.db"
    assert ratings.record_pair("a task asked often", "the good answer text",
                               "the bad answer text", source="critique",
                               model="local", db=db)
    # same triple again: one row (pair_key dedupe), not two
    ratings.record_pair("a task asked often", "the good answer text",
                        "the bad answer text", source="critique",
                        model="local", db=db)
    ratings.record_pair("another task here", "better answer text",
                        "worse answer text", source="episode-derive",
                        model="cloud", db=db)
    rows = ratings.pairs(db=db)
    assert len(rows) == 2, rows
    by_src = {r["source"]: r for r in rows}
    assert by_src["critique"]["chosen"] == "the good answer text"
    assert by_src["episode-derive"]["model"] == "cloud"
    # one-sided / degenerate pairs are skipped, not stored
    assert ratings.record_pair("t", "same", "same", db=db) is None
    assert ratings.record_pair("t", "", "x", db=db) is None
    assert ratings.record_pair("", "a", "b", db=db) is None
    assert ratings.stats(db=db)["pairs"] == 2


def test_export_prefs_merges_user_and_derived(tmp_path):
    """The DPO corpus builder now merges hand-typed corrections with the
    machine-derived pairs table (critique / verify-fix / episode-derive)."""
    import importlib.util
    from pathlib import Path as _Path
    script = _Path(__file__).resolve().parents[1] / "training" / "dpo" / "export_prefs.py"
    spec = importlib.util.spec_from_file_location("_export_prefs", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    db = tmp_path / "r.db"
    ratings.record("user task here with detail", "bad original answer", -1,
                   correction="the corrected version", db=db)
    ratings.record_pair("derived task here with detail", "cloud answer text wins",
                        "local failed answer text", source="episode-derive", db=db)
    out = tmp_path / "prefs.jsonl"
    st = mod.export(db=db, out=out)
    assert st["pairs"] == 2, st
    assert st["by_source"] == {"user": 1, "episode-derive": 1}, st
    text = out.read_text(encoding="utf-8")
    assert "the corrected version" in text and "cloud answer text wins" in text


def test_build_honors_blocklist_and_corrections(tmp_path, monkeypatch):
    from bee.pipeline import build_sft
    import bee.memory.ratings as _rr
    db = tmp_path / "r.db"
    _rr.record("hated task explained thoroughly here", "bad answer", -1, db=db)
    _rr.record("corrected task with sufficient detail", "bad answer", -1,
               correction="the corrected wording here", db=db)
    # isolate from the real memory/ratings.db: no-arg calls read the tmp db
    _orig_b, _orig_c = _rr.blocklisted, _rr.corrections
    monkeypatch.setattr(_rr, "blocklisted", lambda db=None: _orig_b(tmp_path / "r.db"))
    monkeypatch.setattr(_rr, "corrections", lambda db=None: _orig_c(tmp_path / "r.db"))
    monkeypatch.setattr(build_sft, "load_episodes", lambda: [
        {"task": "hated task explained thoroughly here",
         "output": "A detailed bad answer. " * 20, "ok": True, "events": [], "model": "cloud"},
        {"task": "loved task with enough detail", "output": "A good answer. " * 20,
         "ok": True, "events": [], "model": "cloud"},
    ])
    monkeypatch.setattr(build_sft, "load_golden", lambda: [])
    out = tmp_path / "sft.jsonl"
    stats = build_sft.build(out=out, keep_unknown=True, min_quality=0.0)
    assert stats["dropped_disliked"] == 1, stats
    assert stats["corrections_in"] == 1, stats
    texts = out.read_text(encoding="utf-8")
    assert "the corrected wording here" in texts
    assert "A detailed bad answer" not in texts


# --------------------------------------- layer 2: wins + skills in the index
def test_record_win_writes_caps_and_dedupes(tmp_path, monkeypatch):
    from bee.memory import md
    from bee import paths
    monkeypatch.setattr(paths, "MEMORY_DIR", tmp_path)
    assert md.record_win("run backup", "backup completed ok") is True
    assert md.record_win("run backup", "backup completed ok") is False  # dup
    assert md.record_win("", "x") is False
    assert md.record_win("t", "") is False
    lines = (tmp_path / "wins.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and lines[0].startswith("- run backup => backup completed")


def test_all_chunks_covers_skills_and_wins(tmp_path, monkeypatch):
    from bee.memory import md
    from bee import paths
    monkeypatch.setattr(paths, "MEMORY_DIR", tmp_path)
    monkeypatch.setattr(paths, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(paths, "DIARY_DIR", tmp_path / "diary")
    monkeypatch.setattr(paths, "LESSONS_DIR", tmp_path / "lessons")
    monkeypatch.setattr(paths, "PROFILE_MD", tmp_path / "profile.md")
    monkeypatch.setattr(paths, "LONGTERM_MD", tmp_path / "longterm.md")
    (tmp_path / "skills" / "demo").mkdir(parents=True)
    (tmp_path / "skills" / "demo" / "SKILL.md").write_text(
        "# demo\nDoes zzz-unique-workflow things.\n", encoding="utf-8")
    (tmp_path / "wins.md").write_text("- fixed zzz-unique router bug => patched\n",
                                      encoding="utf-8")
    srcs = [s for s, _c in md.all_chunks()]
    assert any(str(s).endswith("SKILL.md") for s in srcs)
    assert any(str(s).endswith("wins.md") for s in srcs)


# --------------------------------------- constrained tool-call validation
def _meta():
    import types
    return {
        "shell": types.SimpleNamespace(
            parameters={"type": "object", "required": ["command"],
                          "properties": {"command": {"type": "string"}}}),
        "calculator": types.SimpleNamespace(
            parameters={"type": "object", "required": ["expression"],
                          "properties": {"expression": {"type": "string"}}}),
    }


def test_validate_call_accepts_good_call():
    from bee.agent.loop import _validate_call
    assert _validate_call("shell", {"command": "dir"}, _meta()) == ""


def test_validate_call_unknown_name_suggests():
    from bee.agent.loop import _validate_call
    msg = _validate_call("shel", {"command": "dir"}, _meta())
    assert "unknown tool" in msg and "shell" in msg


def test_validate_call_missing_required():
    from bee.agent.loop import _validate_call
    msg = _validate_call("calculator", {}, _meta())
    assert "missing required" in msg and "expression" in msg


def test_validate_call_non_dict_args():
    from bee.agent.loop import _validate_call
    msg = _validate_call("shell", "dir", _meta())
    assert "must be a JSON object" in msg
