"""SFT data pipeline: quality scoring, cloud-teacher paraphrase augmentation,
and min-quality filtering. All offline (loaders + generator are stubbed)."""
import json
from pathlib import Path

from bee.pipeline import build_sft


def test_quality_score_bounds_and_ordering():
    good = {"task": "write a detailed report on renewable energy trends in 2026 with sources",
            "output": "Here is a comprehensive report...\n" + "x" * 500, "ok": True, "events": []}
    bad = {"task": "hi", "output": "error: failed to do the thing", "ok": True, "events": []}
    g, b = build_sft.quality_score(good), build_sft.quality_score(bad)
    assert 0.0 <= g <= 1.0 and 0.0 <= b <= 1.0
    assert g > b


def test_paraphrase_keeps_same_response_drops_original():
    rows = [{"task": "summarize this article about AI", "output": "Summary: ...",
             "ok": True, "events": [], "model": "cloud"}]

    def gen(task):
        return ["give the gist of the AI piece", "briefly explain the AI article", task]

    aug = build_sft.paraphrase_augment(rows, 3, gen)
    tasks = {r["task"] for r in aug}
    assert "give the gist of the AI piece" in tasks
    assert "briefly explain the AI article" in tasks
    assert "summarize this article about AI" not in tasks  # original not a new variant
    assert all(r["output"] == "Summary: ..." for r in aug)  # same verified answer
    assert all(r["augmented"] is True for r in aug)


def test_paraphrase_skips_tool_call_rows():
    rows = [{"task": "open chrome", "output": "ok", "ok": True,
             "events": [{"tool": "shell", "args": "{}", "result": "x"}], "model": "cloud"}]
    # Tool-calling rows must NOT be paraphrased (the tool args would go stale).
    assert build_sft.paraphrase_augment(rows, 2, lambda t: ["variant a", "variant b"]) == []


def test_build_min_quality_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(build_sft, "load_episodes", lambda: [])
    monkeypatch.setattr(build_sft, "load_golden", lambda: [
        {"task": "a very detailed request that needs a thorough answer with many steps",
         "response": "A complete, well-structured response with enough substance here. " * 5,
         "model": "cloud", "ts": "2026-01-01"},
        {"task": "hi", "response": "error: could not do it", "model": "cloud", "ts": "2026-01-01"},
    ])
    out = tmp_path / "sft.jsonl"
    all_stats = build_sft.build(out=out, min_quality=0.0)
    assert all_stats["samples_out"] == 2
    filt = build_sft.build(out=out, min_quality=0.6)
    assert filt["samples_out"] == 1            # only the good sample survives
    assert filt["dropped_low_quality"] == 1
    # every emitted sample carries a quality score in its metadata
    for line in out.read_text(encoding="utf-8").splitlines():
        md = json.loads(line)["metadata"]
        assert "quality" in md and 0.0 <= md["quality"] <= 1.0


def test_failed_or_blocked_tool_calls_are_not_trained(monkeypatch, tmp_path):
    """A guard-blocked or broken tool call must not become the desired behaviour in
    the SFT dataset — A60. The episode recovers, so validate passes, but the bad
    event is still dropped by the message builder."""
    bad_row = {
        "task": "do the thing", "output": "done", "ok": True, "events": [
            {"tool": "shell", "args": "{}", "ok": True, "result": "ok output"},
            {"tool": "shell", "args": "{}", "ok": False,
             "result": "{\"blocked\": true, \"reason\": \"guard\"}"},
            {"tool": "shell", "args": "{}", "ok": True, "result": "recovered output"},
        ], "model": "local", "date": "2026-10-13",
    }
    monkeypatch.setattr(build_sft, "load_episodes", lambda: [bad_row])
    monkeypatch.setattr(build_sft, "load_golden", lambda: [])
    out = tmp_path / "sft.jsonl"
    stats = build_sft.build(out=out)
    assert stats["dropped_bad_events"] == 1
    sample = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    tool_contents = [m.get("content") for m in sample["messages"] if m["role"] == "tool"]
    assert "ok output" in tool_contents
    assert "recovered output" in tool_contents
    assert "{\"blocked\": true" not in str(tool_contents)


def test_tool_messages_carry_matching_tool_call_ids(monkeypatch, tmp_path):
    row = {"task": "t", "output": "ok", "ok": True, "events": [
        {"tool": "shell", "args": "{}", "ok": True, "result": "r1"},
    ], "model": "local", "date": "2026-10-13"}
    monkeypatch.setattr(build_sft, "load_episodes", lambda: [row])
    monkeypatch.setattr(build_sft, "load_golden", lambda: [])
    out = tmp_path / "sft.jsonl"
    build_sft.build(out=out)
    sample = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assistant = [m for m in sample["messages"] if m["role"] == "assistant" and m.get("tool_calls")][0]
    tool = [m for m in sample["messages"] if m["role"] == "tool"][0]
    assert assistant["tool_calls"][0]["id"] == tool["tool_call_id"]
