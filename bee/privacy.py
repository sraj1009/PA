"""Privacy controls — PII detection + redaction for cloud-bound payloads.

Policy (config: privacy):
  - Cloud calls carry REDACTED text; local calls are never redacted (privacy floor).
  - Redaction events are counted in metrics so leakage risk is observable.
  - Detection is deterministic regex (no ML) — auditable, offline, no false
    sense of precision. Precision over recall: we only redact high-confidence
    patterns (Luhn-validated cards, key prefixes, 12-digit Aadhaar w/ spaces).
"""
from __future__ import annotations

import re

# (type, pattern, replacement token)
_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("api_key", re.compile(
        r"(?i)\b(sk-[A-Za-z0-9_\-]{16,}|sk-or-[A-Za-z0-9_\-]{16,}|sk-ant-[A-Za-z0-9_\-]{16,}"
        r"|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
        r"|xox[baprs]-[A-Za-z0-9\-]{10,}|AIza[0-9A-Za-z_\-]{30,}|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,})"),
     "[REDACTED:API_KEY]"),
    # PEM header starts with '-' (non-word char) — a leading \b can never match, so it
    # gets its own pattern outside the word-boundary-gated api_key alternation
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "[REDACTED:PRIVATE_KEY]"),
    ("credit_card", re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[REDACTED:CC]"),  # Luhn-filtered in code
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[REDACTED:EMAIL]"),
    # (?!\s\d): don't fire when the 12 digits are the head of a longer card number
    ("aadhaar", re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b(?!\s\d)"), "[REDACTED:AADHAAR]"),
    ("phone_in", re.compile(r"(?<!\d)(?:\+91[- ]?)?\b[6-9]\d{4}[- ]?\d{5}\b(?!\d)"), "[REDACTED:PHONE]"),
    ("phone_us", re.compile(r"(?<!\d)(?:\+1[- ]?)?\b\d{3}[- .]\d{3}[- .]\d{4}\b(?!\d)"), "[REDACTED:PHONE]"),
    ("secret_assign", re.compile(
        r"(?i)\b(password|passwd|pwd|secret|api_?key|access_?token|auth_?token)\b\s*[=:]\s*([^\s,;'\"]{6,})"),
        r"\1=[REDACTED:SECRET]"),
]


def luhn_ok(digits: str) -> bool:
    s, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        s += d
        alt = not alt
    return s % 10 == 0


# by NAME, not index — list order must never matter
_CC_PATTERN = next(p for n, p, _t in _PATTERNS if n == "credit_card")


def _cc_replace(text: str, log: list | None = None) -> str:
    """CC pattern + Luhn validation so random digit runs pass through."""
    def repl(m):
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        if 13 <= len(digits) <= 19 and luhn_ok(digits):
            if log is not None:
                log.append(("credit_card", m.start(), m.end()))
            return "[REDACTED:CC]"
        return raw
    return _CC_PATTERN.sub(repl, text)


def _run_digits(text: str, s: int, e: int) -> int:
    """Length (in digits) of the maximal digit(+single separator) run covering [s,e)."""
    lo, hi, n = s, e, len(text)
    while lo > 0:
        c = text[lo - 1]
        if c.isdigit():
            lo -= 1
        elif c in " -" and lo >= 2 and text[lo - 2].isdigit():
            lo -= 2
        else:
            break
    while hi < n:
        c = text[hi]
        if c.isdigit():
            hi += 1
        elif c in " -" and hi + 1 < n and text[hi + 1].isdigit():
            hi += 2
        else:
            break
    return len(re.sub(r"\D", "", text[lo:hi]))


def detect(text: str) -> list[tuple[str, int, int]]:
    """Returns (type, start, end) spans found in text (for tests/audits)."""
    spans: list[tuple[str, int, int]] = []
    consumed: list[tuple[int, int]] = []

    def overlaps(span, consumed_list):
        s1, s2 = span
        return any(not (s2 <= s or s1 >= e) for s, e in consumed_list)

    # credit cards first — they consume the span so shorter ID patterns can't eat their head
    for m in _CC_PATTERN.finditer(text):
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        if 13 <= len(digits) <= 19 and luhn_ok(digits) and not overlaps((m.start(), m.end()), consumed):
            spans.append(("credit_card", m.start(), m.end()))
            consumed.append((m.start(), m.end()))
    for name, pat, _tok in _PATTERNS:
        if name == "credit_card":
            continue
        for m in pat.finditer(text):
            if overlaps((m.start(), m.end()), consumed):
                continue
            if name == "aadhaar" and _run_digits(text, m.start(), m.end()) != 12:
                continue  # head/tail of a longer card-style number, not a 12-digit ID
            spans.append((name, m.start(), m.end()))
            consumed.append((m.start(), m.end()))
    return sorted(spans, key=lambda s: s[1])


def redact(text: str) -> tuple[str, int]:
    """Returns (redacted_text, n_redactions). Order: API keys → secrets → CC → email → ids."""
    n = 0
    before = text.count("[REDACTED:CC]")
    text = _cc_replace(text)  # cards first, so ID patterns can't eat their head
    n += text.count("[REDACTED:CC]") - before
    for name, pat, tok in _PATTERNS:
        if name == "credit_card":
            continue
        if name == "aadhaar":
            changed = []

            def _aad_repl(m, _t=text, _ch=changed):
                if _run_digits(_t, m.start(), m.end()) != 12:
                    return m.group(0)  # part of a longer card-style run — leave it
                _ch.append(1)
                return tok
            text, _c = pat.subn(_aad_repl, text)
            n += len(changed)  # subn's count includes no-op replacements — count real ones
        else:
            text, c = pat.subn(tok if name != "secret_assign" else r"\1=[REDACTED:SECRET]", text)
            n += c
    return text, n


def is_clean(text: str) -> bool:
    return len(detect(text)) == 0
