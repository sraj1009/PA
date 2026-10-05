"""Episode logger + SFT message export. Run: python tests/test_episodes.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bee import paths  # noqa: E402
from bee.episodes.logger import Episode  # noqa: E402


def test_episode_row():
    e = Episode("test task", model="local")
    e.tool("calculator", {"expression": "1+1"}, True, 0.01, {"result": "2"})
    e.finish(True, "answer is 2", verify={"verdict": "pass"}, tokens=123)
    rows = [json.loads(l) for l in paths.EPISODES_DIR.glob("*.jsonl")
            for l in open(l, encoding="utf-8") if "test task" in l]
    assert rows, "episode not persisted"
    r = rows[-1]
    assert r["ok"] is True and r["n_tools"] == 1 and r["tokens"] == 123
    assert r["events"][0]["tool"] == "calculator"
    assert r["verify"]["verdict"] == "pass"


def test_to_messages():
    e = Episode("do the thing", model="local")
    e.tool("file_write", {"path": "a.txt", "content": "x"}, True, 0.05, {"path": "a.txt"})
    e.finish(True, "done, file written")
    msgs = e.to_messages()
    assert msgs is not None
    assert msgs[0]["role"] == "user" and msgs[0]["loss"] is False
    assert msgs[1]["role"] == "assistant" and msgs[1]["loss"] is True
    assert msgs[1]["tool_calls"][0]["function"]["name"] == "file_write"
    assert msgs[2]["role"] == "tool" and msgs[2]["loss"] is False
    assert msgs[3]["role"] == "assistant" and msgs[3]["loss"] is True
    assert msgs[3]["content"] == "done, file written"


def test_failed_episode_not_sft():
    e = Episode("broken", model="local")
    e.finish(False, "", error="boom")
    assert e.to_messages() is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  [PASS] {fn.__name__}")
        except Exception as ex:
            print(f"  [FAIL] {fn.__name__}: {ex}")
            failed += 1
    print(f"\n{len(fns) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
