"""Routing tiers: explicit > deterministic > ML > heuristic. Run: python tests/test_router_tiers.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bee.config import load_config  # noqa: E402
from bee.agent import router  # noqa: E402

cfg = load_config()


def _r(task, model=None):
    return router.route(task, cfg, model)


def test_explicit():
    assert _r("cloud: anything")["name"] == "cloud"
    assert _r("cloud: anything")["source"] == "explicit"
    assert _r("use local for this")["name"] == "local"
    assert _r("plain task", model="cloud")["name"] == "cloud"
    assert _r("use cloud please")["name"] == "cloud"


def test_deterministic():
    assert _r("2+2*3")["name"] == "det"
    assert _r("127*43+15")["name"] == "det"
    assert _r("(100-4)*2^3")["name"] == "det"
    assert _r("12:30")["name"] != "det"        # colon: not an expression
    assert _r("100")["name"] != "det"          # no operator
    assert _r("2+2*3 with explanation")["name"] != "det"  # words: not pure
    assert _r("a" * 300 + "*2")["name"] != "det"  # too long


def test_deterministic_phrased():
    # light phrasing around pure math still routes to the deterministic tier
    r = _r("what is 17*23?")
    assert r["name"] == "det" and r["expr"] == "17*23", r
    assert _r("17*23?")["expr"] == "17*23"
    assert _r("calculate 10% of 200")["expr"] == "10/100*200"
    assert _r("what's 2^10?")["expr"] == "2**10"
    assert _r("5 plus 5")["expr"] == "5 + 5"
    assert _r("6 to the power of 2")["expr"] == "6 ** 2"
    assert _r("17 \u00d7 23")["expr"] == "17 * 23"
    assert _r("how much is 100 minus 37?")["expr"] == "100 - 37"
    # natural language is NEVER the calculator (even when it contains numbers)
    assert _r("what is the capital of France?")["name"] != "det"
    assert _r("what are the odds of rain tomorrow")["name"] != "det"
    assert _r("find the files in my workspace")["name"] != "det"
    assert _r("100% of my salary goes to taxes")["name"] != "det"
    assert _r("tell me 5 fun facts")["name"] != "det"


def test_heuristic():
    simple = _r("what is in my workspace")
    assert simple["name"] == "local" and simple["source"] in ("heuristic", "ml")
    big = ("Write a comprehensive in-depth research report that designs a system; "
           "first gather, then model, then evaluate. " + "x" * 400)
    r = _r(big)
    if cfg.cloud.enabled and cfg.cloud.llm:
        assert r["name"] == "cloud", r
    else:
        assert r["name"] == "local", r


def test_legacy_api():
    assert router.route_task("do this", cfg) == ("local", False)
    assert router.route_task("cloud: analyze", cfg) == ("cloud", True)


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
