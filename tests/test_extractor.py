"""Unit tests for the text tool-call extractor (handles JSONL/fenced/array + escape safety)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bee.agent.loop import _extract_text_tool_calls as x  # noqa: E402

JSONL = (
    '{"name": "calculator", "arguments": {"expression": "127*43+15"}}\n'
    '{"name": "file_write", "arguments": {"path": "a.txt", "content": "x"}}\n'
    '{"name": "file_read", "arguments": {"path": "a.txt"}}'
)

def test_jsonl():
    r = x(JSONL)
    assert len(r) == 3, r
    assert r[0]["name"] == "calculator"
    assert r[0]["arguments"] == {"expression": "127*43+15"}
    assert r[2]["arguments"] == {"path": "a.txt"}

def test_array():
    r = x('[{"name": "shell", "arguments": {"command": "echo hi"}}]')
    assert len(r) == 1 and r[0]["name"] == "shell"

def test_fenced():
    r = x('Sure:\n```json\n{"name": "web_fetch", "arguments": {"url": "https://x.com"}}\n```')
    assert len(r) == 1 and r[0]["name"] == "web_fetch"

def test_not_hijacked():
    assert x('{"total": 5, "items": [1,2]}') == []
    assert x("Here is your JSON answer:\n```json\n{\"a\": 1}\n```\nDone.") == []

def test_escapes():
    tricky = '{"name": "code_run", "arguments": {"code": "print(\\"{a: b}\\")"}}'
    r = x(tricky)
    assert len(r) == 1, r
    assert "print" in r[0]["arguments"]["code"]

def test_args_as_string():
    r = x('{"name": "shell", "arguments": "{\\"command\\": \\"ls\\"}"}')
    assert r and r[0]["arguments"] == {"command": "ls"}

def test_empty():
    assert x("") == []
    assert x("just plain text, no json") == []

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
