"""A49 — the exec tools run what the model was told they run.

  a) code_run: a piped Windows child writes stdout in cp1252, so print('✓')
     died with UnicodeEncodeError (exit 1).
  b) code_run: `python -c` only has the cwd on sys.path, so `import bee.dsa`
     (which the skill index tells the model to use) failed in any workspace
     other than the project root.
  c) shell: described as "PowerShell on Windows" while shell=True runs cmd.exe —
     every cmdlet the model wrote came back 'not recognized'.
Real subprocesses, no mocks: the defects were in how the child is started."""
from __future__ import annotations

import os
import sys
import threading
from types import SimpleNamespace

import pytest

from bee import paths
from bee.tools import code as code_mod
from bee.tools.code import code_tools
from bee.tools.shell import _powershell_retry, shell_tools

_WIN = sys.platform.startswith("win")


def _ctx(tmp_path):
    return SimpleNamespace(workspace=tmp_path, cancel_event=threading.Event())


def _code(tmp_path, src):
    return code_tools()[0].handler(_ctx(tmp_path), code=src)


def _shell(tmp_path, cmd):
    return shell_tools()[0].handler(_ctx(tmp_path), command=cmd)


def test_code_run_prints_non_latin_text(tmp_path):
    r = _code(tmp_path, "print('done \\u2713 \\u2192 \\u4f60\\u597d')")
    assert r["exit_code"] == 0, r
    assert "\u2713 \u2192 \u4f60\u597d" in r["output"], r


def test_code_run_can_import_bee_from_any_workspace(tmp_path):
    r = _code(tmp_path, "import bee.dsa.graphs as g\n"
                        "d, _ = g.dijkstra(g.build_adj(edges=[('A','B',1),('B','C',2),"
                        "('A','C',10)]), 'A')\nprint(d['C'])")
    assert r["exit_code"] == 0, r
    assert r["output"].strip() == "3", r


def test_bee_root_never_shadows_the_users_own_pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(["/u/one", "/u/two"]))
    parts = code_mod._child_env()["PYTHONPATH"].split(os.pathsep)
    assert parts == ["/u/one", "/u/two", str(paths.PROJECT_ROOT)], parts


def test_code_run_still_reports_a_failing_exit_code(tmp_path):
    r = _code(tmp_path, "import sys; sys.exit(3)")
    assert r["exit_code"] == 3, r


@pytest.mark.skipif(not _WIN, reason="cmd.exe vs PowerShell is a Windows behavior")
def test_a_powershell_cmdlet_runs_instead_of_not_recognized(tmp_path):
    (tmp_path / "only.txt").write_text("x", encoding="utf-8")
    r = _shell(tmp_path, "Get-ChildItem | Select-Object -First 1 -ExpandProperty Name")
    assert r["exit_code"] == 0, r
    assert r["output"].strip() == "only.txt", r
    assert r.get("shell") == "powershell", r


@pytest.mark.skipif(not _WIN, reason="cmd.exe vs PowerShell is a Windows behavior")
def test_cmd_chains_the_model_actually_writes_still_work(tmp_path):
    """30 of the 72 recorded shell calls use `&&` — a parse error in Windows
    PowerShell 5.1, which is why the shell stays cmd.exe."""
    r = _shell(tmp_path, "cd . && echo chained")
    assert r["exit_code"] == 0 and r["output"].strip() == "chained", r
    assert "shell" not in r, r


@pytest.mark.skipif(not _WIN, reason="cmd.exe vs PowerShell is a Windows behavior")
def test_a_command_whose_earlier_part_ran_is_not_run_twice(tmp_path):
    r = _shell(tmp_path, "echo once>>runs.txt & nosuchcmd_a49")
    assert "shell" not in r, r
    assert (tmp_path / "runs.txt").read_text().count("once") == 1


def test_retry_rule_requires_the_first_word_to_be_the_unknown_one():
    err = "'Get-Date' is not recognized as an internal or external command,\n"
    if _WIN:
        assert _powershell_retry("Get-Date", err)
    assert not _powershell_retry("git status && Get-Date", err)
    assert not _powershell_retry("echo hi & Get-Date", err)
    assert not _powershell_retry("Get-Date", "some other failure")
