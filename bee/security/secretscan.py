"""Lightweight secret detection for source / generated-file audits.

Usage:
    python -m bee.security.secretscan [path]     # CLI scan (default: project root)
    from bee.security.secretscan import scan_repo, mask

Guarantees:
  - values are NEVER printed: findings carry a masked form only
    (first 4 chars + length), which is safe for logs and commit gates
  - deterministic: pure regex + Shannon entropy, no network
  - `.env` is excluded by design — that is where secrets SHOULD live.
    Everything else in the project (source, docs, config, generated
    code) must be clean.
"""
from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# (kind, pattern) — high-recognition prefixes of real-world credentials.
# Kept intentionally narrow: these are near-zero-false-positive shapes.
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("openai_key",      re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")),
    ("openrouter_key",  re.compile(r"\bsk-or-[A-Za-z0-9_\-]{20,}\b")),
    ("anthropic_key",   re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("aws_access_key",  re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token",    re.compile(r"\b(ghp|gho|ghs|ghr)_[A-Za-z0-9]{20,}\b")),
    ("github_pat",      re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("slack_token",     re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b")),
    ("google_api_key",  re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b")),
    ("jwt",             re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}\b")),
    ("private_key",     re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("livekit_api_key", re.compile(r"\bAPIK[A-Za-z0-9]{16,}\b")),
    ("livekit_secret",  re.compile(r"\bAPIS[A-Za-z0-9]{20,}\b")),
]

# `name = "value"` assignments to secret-looking identifiers with a
# high-entropy value (catches custom-named keys without known prefixes).
_ASSIGN = re.compile(
    r"(?i)\b(api[_-]?key|apikey|secret|token|passwd|password|access[_-]?key|auth[_-]?key)\b"
    r"\s*[=:]\s*['\"]?([A-Za-z0-9+/=_\-]{20,})['\"]?")

# Never scan these (data dirs / VCS internals / sync caches).
EXCLUDE_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules", ".hf",
    "models", "train", "metrics", "temp", "memory", ".pytest_cache",
}
EXCLUDE_FILES = {".env", ".env.example"}
EXCLUDE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp3", ".wav",
                    ".onnx", ".bin", ".pt", ".safetensors", ".joblib", ".dll", ".exe"}


@dataclass
class Finding:
    path: str
    line: int
    kind: str
    masked: str  # NEVER the raw value

    def __str__(self) -> str:
        return f"{self.path}:{self.line} [{self.kind}] {self.masked}"


def mask(value: str) -> str:
    """Safe form of a credential for logs: prefix + length only."""
    v = (value or "").strip()
    if not v:
        return "<empty>"
    return f"{v[:4]}…(len {len(v)})"


def _shannon(s: str) -> float:
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def scan_text(text: str, path: str = "<memory>") -> list[Finding]:
    out: list[Finding] = []
    for ln_no, line in enumerate(text.splitlines(), 1):
        seen_spans: list[tuple[int, int]] = []  # per-line only (line offsets)
        def overlaps(a: int, b: int) -> bool:
            return any(not (b <= s or a >= e) for s, e in seen_spans)
        for kind, pat in PATTERNS:
            for m in pat.finditer(line):
                if not overlaps(m.start(), m.end()):
                    out.append(Finding(path, ln_no, kind, mask(m.group(0))))
                    seen_spans.append((m.start(), m.end()))
        for m in _ASSIGN.finditer(line):
            name, value = m.group(1), m.group(2)
            if overlaps(m.start(2), m.end(2)):
                continue
            if value.upper() in ("REPLACEME", "CHANGEME", "XXXX", "YOUR", "TBD") or "PLACEHOLDER" in value.upper():
                continue
            if len(value) >= 24 and _shannon(value) > 4.0:
                out.append(Finding(path, ln_no, f"high_entropy_{name.lower()}", mask(value)))
                seen_spans.append((m.start(2), m.end(2)))
    return out


def _is_binary(p: Path) -> bool:
    try:
        with p.open("rb") as f:
            return b"\x00" in f.read(8192)
    except OSError:
        return True


def scan_repo(root: str | Path | None = None) -> list[Finding]:
    """Scan the project tree (excluding .env and data dirs). Sorted, stable."""
    if root is None:
        from .. import paths
        root = paths.PROJECT_ROOT
    root = Path(root)
    findings: list[Finding] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.name in EXCLUDE_FILES:
            continue
        if p.suffix.lower() in EXCLUDE_SUFFIXES:
            continue
        parts = set(p.relative_to(root).parts)
        if parts & EXCLUDE_DIRS:
            continue
        if _is_binary(p):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        rel = p.relative_to(root).as_posix()
        findings.extend(scan_text(text, path=rel))
    return findings


def main(argv: list[str] | None = None) -> int:
    from .. import paths
    root = Path(argv[1]) if argv and len(argv) > 1 else paths.PROJECT_ROOT
    findings = scan_repo(root)
    # The repo gate (tests/test_secretscan.py) allows synthetic fixtures only
    # inside tests/ and evals/ — that is where redaction tests live by design.
    # Findings outside that zone are treated as real leaks.
    real = [f for f in findings
            if not f.path.startswith(("tests/", "evals/"))]
    fixture = [f for f in findings
               if f.path.startswith(("tests/", "evals/"))]
    if not real:
        print(f"secret scan: CLEAN — no real credentials under {root}"
              + (f" ({len(fixture)} expected synthetic findings in the "
                 f"tests/evals fixture zone)" if fixture else ""))
        return 0
    print(f"secret scan: {len(real)} REAL FINDING(S) under {root}:")
    for f in real:
        print(f"  {f}")
    if fixture:
        print(f"(+{len(fixture)} expected synthetic findings in tests/evals)")
    print("Move real values to .env (git-ignored) and ROTATE any exposed credential.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
