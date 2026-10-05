"""Verifier — deterministic claim checks against episode events + disk. Run: python tests/test_verifier.py"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bee.brain import verifier  # noqa: E402


def _calc(expr, stated):
    return {"tool": "calculator", "ok": True, "args": json.dumps({"expression": expr}),
            "result": json.dumps({"expression": expr, "result": stated})}


def test_math_fail():
    events = [_calc("2+2", "5")]
    v = verifier.verify("t", "the answer is 5", Path(tempfile.gettempdir()), events)
    assert v["verdict"] == "fail" and v["findings"][0]["check"] == "math", v


def test_math_pass():
    events = [_calc("2+2", "4")]
    v = verifier.verify("t", "the answer is 4", Path(tempfile.gettempdir()), events)
    assert v["verdict"] == "pass", v


def test_file_missing():
    ws = Path(tempfile.mkdtemp())
    events = [{"tool": "file_write", "ok": True,
               "args": json.dumps({"path": "nope.txt", "content": "x"}),
               "result": json.dumps({"path": "nope.txt"})}]
    v = verifier.verify("t", "I wrote nope.txt", ws, events)
    assert v["verdict"] == "fail" and v["findings"][0]["check"] == "file", v


def test_file_present():
    ws = Path(tempfile.mkdtemp())
    (ws / "ok.txt").write_text("hello BEE", encoding="utf-8")
    events = [{"tool": "file_write", "ok": True,
               "args": json.dumps({"path": "ok.txt", "content": "hello BEE"}),
               "result": json.dumps({"path": "ok.txt"})}]
    v = verifier.verify("t", "done", ws, events)
    assert v["verdict"] == "pass", v


def test_url_unfetched_warn():
    events = []
    v = verifier.verify("t", "see https://never-fetched.example.com/page for details",
                        Path(tempfile.gettempdir()), events)
    assert v["verdict"] == "warn" and v["findings"][0]["check"] == "url", v


def test_url_fetched_pass():
    events = [{"tool": "web_fetch", "ok": True,
               "args": json.dumps({"url": "https://ok.example.com/page"}),
               "result": "{}"}]
    v = verifier.verify("t", "from https://ok.example.com/page: fact",
                        Path(tempfile.gettempdir()), events)
    assert v["verdict"] == "pass", v


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
