"""Offline deterministic fallback. Run: python tests/test_offline.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bee.agent import offline  # noqa: E402

ws = Path(tempfile.mkdtemp())
(ws / "alpha.txt").write_text("a", encoding="utf-8")
(ws / "beta").mkdir()


def test_math():
    out = offline.run_offline("127*43+15", ws)
    assert "5476" in out, out


def test_math_caret():
    out = offline.run_offline("2^10", ws)
    assert "1024" in out, out


def test_not_math():
    assert offline._try_math("hello world") is None
    assert offline._try_math("100") is None


def test_math_phrased():
    assert "391" in offline.run_offline("what is 17*23?", ws)
    assert "20.0" in offline.run_offline("calculate 10% of 200", ws)
    assert offline._try_math("what is the capital of France?") is None


def test_sort():
    out = offline.run_offline("sort [5,3,1,4,2] ascending", ws)
    assert "[1, 2, 3, 4, 5]" in out, out
    out = offline.run_offline("sort [5,3,1] in descending order", ws)
    assert "[5, 3, 1]" in out, out


def test_list():
    out = offline.run_offline("list files in the workspace", ws)
    assert "alpha.txt" in out and "beta/" in out, out


def test_time_and_identity():
    assert "offline" in offline.run_offline("what time is it", ws)
    assert "BEE" in offline.run_offline("who are you", ws)


def test_fallback_message():
    out = offline.run_offline("write me a poem about clouds", ws)
    assert "deterministic" in out or "offline" in out
    assert "math" in out.lower()


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
