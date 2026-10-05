"""Secret scan: detection shapes, masking, .env exclusion, repo gate.

Repo gate rule (CI): findings are ONLY allowed inside the test-fixture zone
(tests/ and evals/) where synthetic redaction fixtures live by design.
Anything else — source, docs, config, generated code — must be clean.
"""
from __future__ import annotations

from bee import paths
from bee.security import secretscan as ss


FAKE = "sk-abcdefghijklmnop1234"  # synthetic fixture


def test_detects_known_prefixes():
    out = ss.scan_text(f"key = {FAKE}\nother AIzaSyB1234567890abcdefghijklmnopqrst\n"
                       "-----BEGIN RSA PRIVATE KEY-----\n")
    kinds = {f.kind for f in out}
    assert "openai_key" in kinds and "google_api_key" in kinds and "private_key" in kinds


def test_detects_high_entropy_assignment():
    entropy = "a3B9xK2mQ7pL4vN8cR5tY1wZ6dF0gHjKe"  # 32 chars, high entropy
    out = ss.scan_text(f"api_key = '{entropy}'")
    assert any(f.kind.startswith("high_entropy") for f in out)
    # low-entropy / placeholder values pass
    assert ss.scan_text("api_key = ''") == []
    assert ss.scan_text("api_key = REPLACEME") == []
    assert ss.scan_text("token = aaaaaaaabbbbbbbbccccccccdddddddd") == []  # low entropy


def test_mask_never_returns_value():
    m = ss.mask(FAKE)
    assert FAKE not in m and m != FAKE
    assert m.startswith(FAKE[:4]) and "len" in m


def test_scan_repo_excludes_env_file(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / ".env").write_text(f"LIVEKIT_API_KEY={FAKE}\n", encoding="utf-8")
    (tmp_path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    assert ss.scan_repo(tmp_path) == []  # .env is the sanctioned location


def test_scan_repo_catches_secret_in_source(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(f"KEY = '{FAKE}'\n", encoding="utf-8")
    findings = ss.scan_repo(tmp_path)
    assert len(findings) == 1 and findings[0].path == "src/app.py"
    assert FAKE not in str(findings[0])  # masked in the finding itself


def test_project_repo_gate():
    """The actual repo: clean everywhere except the synthetic fixture zone."""
    findings = ss.scan_repo(paths.PROJECT_ROOT)
    fixture_zone = ("tests/", "evals/")
    bad = [f for f in findings if not f.path.startswith(fixture_zone)]
    assert bad == [], [str(f) for f in bad]
    # high-entropy hits are the most likely real leaks — never tolerated
    ent = [f for f in findings if f.kind.startswith("high_entropy")]
    assert ent == [], [str(f) for f in ent]
