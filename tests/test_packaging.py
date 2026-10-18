"""pyproject.toml must mirror the pinned requirements*.txt files.

Packaging is ADDITIVE: setup.ps1 / Makefile / CI keep installing from
requirements*.txt (untouched), while pyproject.toml adds PEP 621 metadata
for editable/wheel installs (`pip install -e .`) plus the `bee` console
script. These tests fail the moment the two worlds drift.

Category: unit (file parsing + one light `import bee`).
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"

# Python 3.11+ (dev venv 3.11, CI 3.12); skip cleanly on older interpreters.
tomllib = pytest.importorskip("tomllib")

# pyproject extra -> the requirements file it must mirror exactly.
_EXTRA_FILES = {
    "voice": "requirements-voice.txt",
    "desktop": "requirements-desktop.txt",
    "ml": "requirements-ml.txt",
    "vision": "requirements-vision.txt",
    "livekit": "requirements-livekit.txt",
}


def _pyproject() -> dict:
    with open(PYPROJECT, "rb") as fh:
        return tomllib.load(fh)


def _pins(path: Path) -> set:
    """Exact `name==version` lines of a requirements file, comments stripped."""
    pins = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line and "==" in line:
            pins.add(line)
    return pins


def test_core_dependencies_mirror_requirements_txt():
    deps = _pyproject()["project"]["dependencies"]
    assert set(deps) == _pins(ROOT / "requirements.txt")


@pytest.mark.parametrize("extra,fname", sorted(_EXTRA_FILES.items()))
def test_extras_mirror_their_requirements_files(extra: str, fname: str):
    extras = _pyproject()["project"]["optional-dependencies"]
    assert extra in extras, f"pyproject.toml lost the '{extra}' extra"
    assert set(extras[extra]) == _pins(ROOT / fname)


def test_console_script_python_floor_and_name():
    project = _pyproject()["project"]
    assert project["scripts"] == {"bee": "bee.cli:main"}
    assert project["requires-python"] == ">=3.10"
    assert project["name"] == "bee-pa"


def test_version_matches_bee_package():
    # Static in pyproject on purpose: setuptools' dynamic-attr loader exec'd
    # the root bee.py launcher during the build ("`bee` is not a package")
    # and aborted `pip install -e .` - caught by a clean-venv run. Equality
    # with bee.__version__ is pinned here instead.
    project = _pyproject()["project"]
    assert project.get("dynamic", []) == []
    version = importlib.import_module("bee").__version__
    assert project["version"] == version
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), version


def test_build_backend_is_setuptools():
    build = _pyproject()["build-system"]
    assert build["build-backend"] == "setuptools.build_meta"
    assert any(req.startswith("setuptools") for req in build["requires"])


def test_pyproject_does_not_hijack_pytest_configuration():
    # The marker registry and rootdir stay owned by tests/conftest.py; a
    # [tool.pytest.ini_options] section here would silently take precedence.
    assert "pytest" not in _pyproject().get("tool", {})


def test_package_data_globs_match_real_files():
    # A typo'd glob would silently ship a wheel without the web UI.
    for pkg, patterns in _pyproject()["tool"]["setuptools"]["package-data"].items():
        base = ROOT / pkg.replace(".", "/")
        assert base.is_dir(), f"package-data key is not a package dir: {pkg}"
        for pat in patterns:
            assert list(base.glob(pat)), f"{pkg}: glob {pat!r} matches nothing"
