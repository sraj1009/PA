"""PII detection + redaction — labeled cases. Run: python tests/test_privacy.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bee import privacy  # noqa: E402

CASES_DETECT = [
    # (text, expected types present)
    ("contact me at john.doe+test@gmail.com soon", {"email"}),
    ("my number is +91 98765 43210", {"phone_in"}),
    ("call 415-555-0132 for details", {"phone_us"}),
    ("card 4111 1111 1111 1111 expires next year", {"credit_card"}),
    ("aadhaar 1234 5678 9012 verified", {"aadhaar"}),
    ("token sk-abc123def456ghi789jkl012 use it", {"api_key"}),
    ("aws key AKIAIOSFODNN7EXAMPLE in the bucket", {"api_key"}),
    ("my password=hunter2secret is weak", {"secret_assign"}),
    ("the date is 2026-10-04 and price 1234567 is fine", set()),  # 8-digit run, not PII
    ("order 4111 1111 1111 1112 was rejected (invalid luhn)", set()),  # Luhn-fail
    ("nothing sensitive here at all", set()),
    ("pi is 3.14159 and n is 2026100412345678901", set()),  # 21 digits: too long for CC
]


def test_detect():
    for text, expected in CASES_DETECT:
        found = {t for t, _s, _e in privacy.detect(text)}
        assert expected <= found or expected == set(), (text, found, expected)
        if expected == set():
            assert found == set(), (text, found)


def test_redact():
    t, n = privacy.redact("email john@gmail.com, card 4111 1111 1111 1111, key sk-abcdefghijklmnop1234")
    assert n >= 3, n
    assert "john@gmail.com" not in t and "[REDACTED:EMAIL]" in t
    assert "4111 1111 1111 1111" not in t and "[REDACTED:CC]" in t
    assert "sk-abcdefghijklmnop1234" not in t and "[REDACTED:API_KEY]" in t
    assert privacy.is_clean(t)


def test_luhn():
    assert privacy.luhn_ok("4111111111111111")
    assert not privacy.luhn_ok("4111111111111112")
    assert privacy.luhn_ok("5500005555555559")


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
