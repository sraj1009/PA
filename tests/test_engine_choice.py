"""Engine-choice persistence (A41): redirectable path, honest failures.

`settings.json` decides which brain BEE uses on EVERY surface (REPL, web, voice,
LiveKit, jobs). Three defects made that file untrustworthy:

  A41a — `settings_file()` built its path from `paths.PROJECT_ROOT` inline, so no
         test could redirect it; meanwhile `ask_engine()` writes it whenever stdin
         is not a tty, which is true of every piped launch (pytest, CI, the eval).
  A41b — `save_engine()` wrapped the write in `except Exception: pass` and
         returned None, so a failed write (OneDrive holds a lock on this machine)
         lost the user's explicit `/engine` choice with no trace, and the REPL
         still reported the switch.
  A41c — an unknown/corrupt engine name was silently turned into None.
"""
from __future__ import annotations

import json

from bee import paths
from bee.agent import engines


# ------------------------------------------------------------------ the path
def test_settings_path_is_redirectable(tmp_path, monkeypatch):
    """The whole isolation fix: the module reads `paths.SETTINGS_JSON`, so a
    caller (or the suite) can point it somewhere harmless."""
    target = tmp_path / "nested" / "settings.json"
    monkeypatch.setattr(paths, "SETTINGS_JSON", target)
    assert engines.settings_file() == target
    target.parent.mkdir(parents=True, exist_ok=True)
    assert engines.save_engine("local") is True
    assert json.loads(target.read_text(encoding="utf-8"))["engine"] == "local"
    assert engines.load_engine() == "local"


def test_the_suite_never_touches_the_users_real_settings(tmp_path, monkeypatch):
    """A41a guard, asserted the way A25b asserts the metrics isolation: the
    session-redirected path must not be the repo file, and a save that happens
    under the suite must not change the real one's bytes."""
    real = paths.PROJECT_ROOT / "settings.json"
    assert paths.SETTINGS_JSON != real, "conftest did not redirect settings.json"
    before = real.read_bytes() if real.exists() else None
    assert engines.save_engine("ollama-cloud") is True
    after = real.read_bytes() if real.exists() else None
    assert before == after, "the suite wrote the user's engine choice"


# ------------------------------------------------------------------ failures
def test_failed_save_is_reported_not_swallowed(tmp_path, monkeypatch, caplog):
    """A blocked write must not look like a saved choice (A7/A40c's rule)."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    monkeypatch.setattr(paths, "SETTINGS_JSON", blocker / "settings.json")
    with caplog.at_level("WARNING", logger="bee.engines"):
        assert engines.save_engine("local") is False
    assert any("could not persist engine" in r.getMessage() for r in caplog.records)


def test_unknown_engine_name_is_logged_not_dropped_silently(tmp_path, monkeypatch, caplog):
    """`{"engine": "grarp"}` used to read as 'no preference' with no explanation,
    so a typo in the file silently changed the user's brain."""
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"engine": "grarp"}), encoding="utf-8")
    monkeypatch.setattr(paths, "SETTINGS_JSON", f)
    with caplog.at_level("WARNING", logger="bee.engines"):
        assert engines.load_engine() is None
    assert any("unknown engine" in r.getMessage() for r in caplog.records)


def test_corrupt_settings_file_is_logged(tmp_path, monkeypatch, caplog):
    f = tmp_path / "settings.json"
    f.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(paths, "SETTINGS_JSON", f)
    with caplog.at_level("WARNING", logger="bee.engines"):
        assert engines.load_engine() is None
    assert any("unreadable" in r.getMessage() for r in caplog.records)


def test_a_list_in_settings_does_not_crash_the_reader(tmp_path, monkeypatch):
    """`data.get` on a JSON list raises AttributeError; the old code caught it
    blind, but the reader should not depend on an exception to be safe."""
    f = tmp_path / "settings.json"
    f.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(paths, "SETTINGS_JSON", f)
    assert engines.load_engine() is None


# ------------------------------------------------------------------- contents
def test_saving_the_engine_keeps_every_other_key(tmp_path, monkeypatch):
    """settings.json is shared with the IDE-facing `settings.json` convention;
    writing the engine must not flatten whatever else the user keeps there."""
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"theme": "dark", "telemetry": False}), encoding="utf-8")
    monkeypatch.setattr(paths, "SETTINGS_JSON", f)
    assert engines.save_engine("hybrid") is True
    data = json.loads(f.read_text(encoding="utf-8"))
    assert data == {"theme": "dark", "telemetry": False, "engine": "hybrid"}


def test_an_unknown_engine_can_never_be_written(tmp_path, monkeypatch):
    f = tmp_path / "settings.json"
    monkeypatch.setattr(paths, "SETTINGS_JSON", f)
    assert engines.save_engine("gpt-99") is False
    assert not f.exists()
