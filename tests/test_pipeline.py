"""Data pipeline — validate / sanitize / build_sft / train_router (offline).
Run: python tests/test_pipeline.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bee.pipeline import validate, sanitize  # noqa: E402
from bee.pipeline.build_sft import row_to_messages  # noqa: E402


def _ev(tool, ok=True, args="{}", result="{}"):
    return {"tool": tool, "ok": ok, "args": args, "result": result, "seconds": 0.1}


def test_validate_math_pass():
    row = {"ok": True, "task": "compute 2+2", "output": "the answer is 4",
           "events": [_ev("calculator", True,
                          json.dumps({"expression": "2+2"}),
                          json.dumps({"result": "4"}))]}
    v = validate.validate(row)
    assert v["verdict"] == "pass" and v["type"] == "math", v


def test_validate_math_fail():
    row = {"ok": True, "task": "compute 2+2", "output": "the answer is 5",
           "events": [_ev("calculator", True,
                          json.dumps({"expression": "2+2"}),
                          json.dumps({"result": "4"}))]}
    v = validate.validate(row)
    assert v["verdict"] == "fail", v


def test_validate_file_missing():
    row = {"ok": True, "task": "write x", "output": "done",
           "events": [_ev("file_write", True,
                          json.dumps({"path": "nope.txt", "content": "c"}), "{}")]}
    v = validate.validate(row, Path(__file__).parent)
    assert v["verdict"] == "fail" and v["type"] == "file", v


def test_validate_failed_episode():
    row = {"ok": False, "task": "x", "output": "", "events": []}
    assert validate.validate(row)["verdict"] == "fail"


def test_detect_types():
    assert validate.detect_type("compute 1+1", [_ev("calculator")]) == "math"
    assert validate.detect_type("write a file", [_ev("file_write")]) == "file"
    assert validate.detect_type("sort this array", [_ev("code_run")]) == "dsa"
    assert validate.detect_type("run the build", [_ev("shell")]) == "shell"
    assert validate.detect_type("look it up", [_ev("web_search")]) == "web"
    assert validate.detect_type("hi", []) == "generic"


def test_sanitize_redacts():
    row = {"ok": True, "task": "email me at john@gmail.com", "output": "done",
           "events": [_ev("shell", True, json.dumps({"command": "echo sk-abcdefghijklmnop1234"}), "{}")]}
    clean, n = sanitize.scrub_episode(row)
    assert n >= 2, n
    assert "john@gmail.com" not in json.dumps(clean)
    assert "sk-abcdefghijklmnop1234" not in json.dumps(clean)
    assert clean["metadata"]["redactions"] == n
    # original untouched
    assert "john@gmail.com" in row["task"]


def test_row_to_messages():
    row = {"ok": True, "task": "do it", "output": "done",
           "events": [_ev("calculator", True, json.dumps({"expression": "1+1"}),
                          json.dumps({"result": "2"}))]}
    # A60b changed the contract to (messages, dropped_bad_events) and build() sums
    # the second value into stats — the assertions below now unpack instead of
    # pretending the tuple is a list.
    msgs, dropped = row_to_messages(row)
    assert dropped == 0
    assert msgs[0]["role"] == "user" and msgs[0]["loss"] is False
    assert msgs[1]["role"] == "assistant" and msgs[1]["loss"] is True
    assert msgs[1]["tool_calls"][0]["function"]["name"] == "calculator"
    assert msgs[2]["role"] == "tool" and msgs[2]["loss"] is False
    assert msgs[3]["role"] == "assistant" and msgs[3]["content"] == "done"
    # failed episode -> no messages at all
    assert row_to_messages({**row, "ok": False, "output": ""}) == (None, 0)
    # a failed/blocked event is skipped AND counted, so the sample teaches the
    # recovery rather than the denied call: user + (assistant,tool) for the one good
    # event + final assistant = 4 messages, and 'rm -rf' appears nowhere.
    msgs, dropped = row_to_messages({**row, "events": [
        _ev("calculator", True, json.dumps({"expression": "1+1"}), json.dumps({"result": "2"})),
        _ev("shell", False, json.dumps({"command": "rm -rf /"}), '{"blocked": true}')]})
    assert dropped == 1 and len(msgs) == 4
    assert "rm -rf" not in json.dumps(msgs)


def test_router_label():
    from bee.pipeline.train_router import label_row
    assert label_row({"ok": True, "task": "2+2*3", "escalated": False}) == "det"
    assert label_row({"ok": True, "task": "write a report", "escalated": True}) == "cloud"
    assert label_row({"ok": True, "task": "write a report", "escalated": False}) == "local"
    assert label_row({"ok": False, "task": "2+2", "escalated": False}) is None  # failed: no label


def test_build_sft_merges_cloud_golden(monkeypatch, tmp_path):
    from bee.pipeline import build_sft
    from bee import paths as p

    ep_dir = tmp_path / "episodes"
    ep_dir.mkdir()
    (ep_dir / "ep.jsonl").write_text(json.dumps(
        {"task": "compute 2+2", "output": "the answer is 4", "ok": True,
         "events": [_ev("calculator", True, json.dumps({"expression": "2+2"}),
                        json.dumps({"result": "4"}))],
         "date": "2026-10-05", "model": "local"}), encoding="utf-8")
    train_dir = tmp_path / "train"
    (train_dir / "golden").mkdir(parents=True)
    (train_dir / "golden" / "cloud_golden.jsonl").write_text(
        json.dumps({"task": "explain photosynthesis", "response": "It is how plants make food.",
                    "model": "cloud", "ts": "2026-10-05T12:00:00"}) + "\n"
        # duplicate task of the episode above -> must be deduped
        + json.dumps({"task": "compute 2+2", "response": "4", "model": "cloud",
                      "ts": "2026-10-05T12:01:00"}) + "\n",
        encoding="utf-8")

    monkeypatch.setattr(p, "EPISODES_DIR", ep_dir)
    monkeypatch.setattr(p, "TRAIN_DIR", train_dir)
    out = tmp_path / "sft.jsonl"
    stats = build_sft.build(workspace=tmp_path, out=out)

    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    tasks = {r["messages"][0]["content"] for r in rows}
    # golden is a 'generic' Q&A (verdict=unknown) — still trained on: cloud is the teacher
    assert stats["golden_in"] == 1, stats
    assert "explain photosynthesis" in tasks
    # dedupe: episode wins, golden dup dropped
    assert "compute 2+2" in tasks and stats["dropped_dup"] == 1
    assert stats["samples_out"] == 2


def test_build_sft_golden_still_scrubs_pii(monkeypatch, tmp_path):
    from bee.pipeline import build_sft
    from bee import paths as p

    ep_dir = tmp_path / "episodes"
    ep_dir.mkdir()
    train_dir = tmp_path / "train"
    (train_dir / "golden").mkdir(parents=True)
    (train_dir / "golden" / "cloud_golden.jsonl").write_text(json.dumps(
        {"task": "what is my email", "response": "Your email is john@gmail.com.",
         "model": "cloud", "ts": "2026-10-05T12:00:00"}), encoding="utf-8")

    monkeypatch.setattr(p, "EPISODES_DIR", ep_dir)
    monkeypatch.setattr(p, "TRAIN_DIR", train_dir)
    out = tmp_path / "sft.jsonl"
    build_sft.build(workspace=tmp_path, out=out)
    text = out.read_text(encoding="utf-8")
    assert "john@gmail.com" not in text


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  [PASS] {fn.__name__}")
        except Exception as e:
            print(f"  [FAIL] {fn.__name__}: {e}")
            failed += 1
    print(f"\n{len(fns) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
