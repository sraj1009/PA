"""The hand-kept marker registry must be able to fail (A64 close, 2026-10-18).

Markers come from filename lists in tests/conftest.py, so before this file a
new tests/test_*.py that nobody added to a list ran ONLY in an unfiltered
local `pytest tests -q`: every CI job filters by marker (core / security /
integration / windows / ml) and silently deselected it. Measured 2026-10-18:
test_native (5), test_telemetry (5), test_automate (11) and test_commands
(29) passed locally but no CI job selected them; test_monitor has no test
functions at all (its checks run at import, which every collection executes).

The invariants below are enforced in BOTH directions, so neither a missing
registration nor a rename that leaves a stale entry can pass:

  * every tests/test_*.py is selected by at least one CI job, or is exempt
    with a reason (test_monitor: no selectable items; test_livekit: optional
    SDK — no CI job installs livekit, live coverage is optional.yml);
  * every name mentioned in ANY list (including category-only lists such as
    tools/agent/voice) exists on disk;
  * the CI workflow still runs the marker sets this registry feeds.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent

# Files that must NOT be selected by a CI job, each with the reason why.
EXEMPT = {
    "test_monitor": (
        "module-level checks execute at import during every collection "
        "(there are no test functions to select)"),
    "test_livekit": (
        "optional livekit SDK - no CI job installs it (live coverage is "
        "optional.yml); importorskip keeps it skip-safe everywhere else"),
}


def _registry():
    spec = importlib.util.spec_from_file_location(
        "bee_marker_registry_under_test", TESTS / "conftest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _files_on_disk():
    return {p.stem for p in TESTS.glob("test_*.py")}


def test_every_test_file_is_selected_by_some_ci_job():
    cf = _registry()
    # What the CI jobs actually select: core = unit+integration minus optional
    # deps, plus the dedicated windows and ml pockets. Category-only markers
    # (tools/agent/voice/...) drive no job, so they cannot make a file count.
    ci_selected = (set(cf._UNIT) | set(cf._INTEGRATION)
                   | set(cf._WINDOWS) | set(cf._ML)) - set(cf._OPTIONAL_DEPS)
    missing = sorted(_files_on_disk() - ci_selected - set(EXEMPT))
    assert not missing, (
        "these test files run in NO CI job (register them in _UNIT / "
        f"_INTEGRATION / a CI-selected list): {missing}")


def test_every_registered_name_exists_on_disk():
    cf = _registry()
    names = set()
    for lst in cf.MARKERS.values():
        names.update(lst)
    names.update(cf._OPTIONAL_DEPS)
    dangling = sorted(n for n in names if n not in _files_on_disk())
    assert not dangling, (
        "registry entries with no tests/<name>.py on disk (a rename left a "
        f"stale entry?): {dangling}")


def test_exemptions_are_real_files_with_reasons():
    files = _files_on_disk()
    for stem, reason in EXEMPT.items():
        assert stem in files, f"exempted file missing: {stem}"
        assert reason.strip(), f"exempted file needs a reason: {stem}"


def test_ci_workflow_still_runs_the_pockets_this_registry_feeds():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for pocket in ("-m core", "-m security", '-m "integration and not livekit"',
                   "-m windows", "-m ml"):
        assert pocket in ci, (
            f"ci.yml no longer runs {pocket!r} — the registry/meta-test "
            "contract changed; update this test deliberately")
