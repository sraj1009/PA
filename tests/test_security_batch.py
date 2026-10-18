"""Security batch (2026-10-16): secret-bearing child env, guard.mode=always
refusal, file-jail hardening, golden scrub-at-capture, recursive metrics
scrub. All offline."""
from __future__ import annotations

import json
import os


def test_code_child_env_drops_secrets(monkeypatch):
    from bee.tools import code as code_mod
    monkeypatch.setenv("PROBE_API_KEY", "sk-secret-123")
    monkeypatch.setenv("PROBE_SECRET", "s3cret")
    monkeypatch.setenv("PROBE_AUTH_TOKEN", "tok-abc")
    monkeypatch.setenv("PROBE_PLAIN", "keep-me")
    env = code_mod._child_env()
    assert "PROBE_API_KEY" not in env
    assert "PROBE_SECRET" not in env
    assert "PROBE_AUTH_TOKEN" not in env
    assert env.get("PROBE_PLAIN") == "keep-me"
    assert "PATH" in env and env["PYTHONIOENCODING"] == "utf-8"


def test_guard_always_refused_from_config(tmp_path):
    import yaml
    from bee.config import load_config
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump({"guard": {"mode": "always"}}), encoding="utf-8")
    cfg = load_config(path=p)
    assert cfg.guard.mode == "cli"


def test_files_refuses_env_ads_and_dots(tmp_path):
    from bee.tools import files as fmod
    root = tmp_path / "ws"
    root.mkdir()
    assert "refused" in fmod._write_file(root, ".env", "x")["error"].lower()
    assert "refused" in fmod._write_file(root, "sub/.env", "x")["error"].lower()
    assert "refused" in fmod._write_file(root, "evil.txt:secret", "x")["error"].lower()
    assert "refused" in fmod._write_file(root, "trail. ", "x")["error"].lower()
    assert "refused" in fmod._write_file(root, "con.txt", "x")["error"].lower()
    ok = fmod._write_file(root, "notes.txt", "hello")
    assert "error" not in ok


def test_files_symlink_escape_refused(tmp_path):
    import sys
    if os.name != "nt" and not hasattr(os, "symlink"):
        return
    from bee.tools import files as fmod
    root = tmp_path / "ws"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "linkdir"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        return  # no symlink privilege on this box — nothing to prove
    out = fmod._write_file(root, "linkdir/pwned.txt", "x")
    assert "error" in out, out
    assert not (outside / "pwned.txt").exists()


def test_golden_scrubs_pii_at_capture(tmp_path, monkeypatch):
    from bee import paths as bee_paths
    from bee.agent import loop as loop_mod
    monkeypatch.setattr(bee_paths, "TRAIN_DIR", tmp_path)
    res = types_result(ok=True, escalated=True, verify=None,
                       output="contact me at bee.pa123@example.com thanks",
                       model="gemini-x")
    loop_mod._golden("my email is bee.pa123@example.com tell me", res)
    rows = (tmp_path / "golden" / "cloud_golden.jsonl").read_text(encoding="utf-8")
    assert "bee.pa123@example.com" not in rows


def types_result(**kw):
    import types
    base = dict(output="", model="test", ok=True, escalated=False, verify=None)
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_metrics_scrub_is_recursive():
    from bee.monitor import metrics as mt
    row = {"tool": "shell", "args": {"q": "email bee.pa123@example.com now please"},
           "tags": ["ok", "call bee.pa123@example.com urgently"]}
    out = mt._scrub(row)
    blob = json.dumps(out)
    assert "bee.pa123@example.com" not in blob
    assert out["tool"] == "shell"  # short enums untouched
