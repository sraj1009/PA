"""Manual test runner (no pytest needed): python tests/run_manual.py"""
import sys, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tests.test_dsa as t

fns = [v for k, v in vars(t).items() if k.startswith("test_")]
passed, failed = 0, 0
for fn in fns:
    try:
        fn()
        print(f"  [PASS] {fn.__name__}")
        passed += 1
    except Exception:
        print(f"  [FAIL] {fn.__name__}")
        traceback.print_exc()
        failed += 1
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
