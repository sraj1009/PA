"""Risk classification: Python AST analyzer + full classify_risk layering."""
from __future__ import annotations

from bee.security import risk
from bee.security.risk import RiskLevel, analyze_python, classify_risk


# ------------------------------------------------------------------ AST
def _actions(code, **kw):
    return [a for a, _ in analyze_python(code, **kw)]


def _details(code, **kw):
    return [d for _, d in analyze_python(code, **kw)]


def test_clean_code_passes():
    assert analyze_python("print(1 + 1)") == []
    assert analyze_python("import math\nprint(math.sqrt(16))") == []
    assert analyze_python("x = [1,2,3]\nprint(sorted(x))") == []


def test_destructive_python_denied():
    assert "deny" in _actions("import shutil; shutil.rmtree('/tmp/x')")
    assert "deny" in _actions("import os\nos.remove('a.txt')")
    assert "deny" in _actions("import os; os.unlink('b.txt')")
    assert "deny" in _actions("import os; os.rmdir('d/')")
    assert "deny" in _actions("from pathlib import Path\nPath('x').unlink()")
    assert "deny" in _actions("import subprocess\nsubprocess.run(['rm', '-rf', '/tmp/x'])")
    assert "deny" in _actions("import socket\nsocket.create_connection(('h', 80))")
    assert "deny" in _actions("import ctypes; ctypes.CDLL('kernel32')")
    assert "deny" in _actions("import pickle\npickle.load(open('p','rb'))")
    assert "deny" in _actions("eval('__import__(\"os\").system(\"rm -rf /\")')")
    assert "deny" in _actions("exec('import os; os.remove(\"x\")')")


def test_state_changing_python_asks():
    assert "ask" in _actions("open('out.txt','w').write('data')")
    assert "ask" in _actions("open('a.csv', mode='a')")
    assert "ask" in _actions("import os; os.rename('a','b')")
    assert "ask" in _actions("import os; os.chmod('x', 0o777)")
    assert "ask" in _actions("import os")
    assert "ask" in _actions("import sys")
    assert "ask" in _actions("import shutil; shutil.move('a','b')")
    # read-only open stays clean
    assert analyze_python("open('in.txt').read()") == []


def test_unparseable_fail_closed():
    assert _actions("def f(:", fail_closed=True) == ["ask"]
    assert analyze_python("def f(:", fail_closed=False) == []


def test_no_double_report():
    d = _details("import shutil; shutil.rmtree('/a'); shutil.rmtree('/b')")
    assert len([x for x in d if "rmtree" in x]) == 1


# ---------------------------------------------------------- classify_risk
def test_shell_layer_untouched():
    d = classify_risk("shell", {"command": "ls -la"})
    assert d.action == "allow" and d.level == RiskLevel.MEDIUM
    d = classify_risk("shell", {"command": "rm -rf /"})
    assert d.action == "deny" and d.level == RiskLevel.CRITICAL
    d = classify_risk("shell", {"command": "git push origin main"})
    assert d.action == "ask" and d.level == RiskLevel.HIGH


def test_code_run_ast_layer():
    d = classify_risk("code_run", {"code": "import shutil; shutil.rmtree('/tmp/x')"})
    assert d.action == "deny" and d.level == RiskLevel.CRITICAL
    assert d.require_approval and "python" in d.reason

    d = classify_risk("code_run", {"code": "open('out.txt','w').write('x')"})
    assert d.action == "ask" and d.level == RiskLevel.HIGH

    d = classify_risk("code_run", {"code": "print(42)"})
    assert d.action == "allow" and not d.require_approval


def test_code_run_unparseable_escalates():
    d = classify_risk("code_run", {"code": "def f(: broken"})
    assert d.action == "ask"


def test_non_exec_tools_low_risk():
    d = classify_risk("file_read", {"path": "x.md"})
    assert d.action == "allow" and d.level == RiskLevel.LOW and "fs.read" in d.capabilities
    d = classify_risk("file_write", {"path": "x.md", "content": "rm -rf /"})
    assert d.action == "allow"  # content is data for non-exec tools
    d = classify_risk("web_fetch", {"url": "https://example.com"})
    assert "network" in d.capabilities


def test_unknown_tool_fail_low_allow():
    d = classify_risk("mystery_tool", {})
    assert d.action == "allow" and d.level == RiskLevel.LOW


def test_systemctl_profile():
    d = classify_risk("systemctl", {"action": "lock"})
    assert d.action == "ask"
    d = classify_risk("systemctl", {"action": "stats"})
    assert d.action == "allow"


def test_shell_inline_python_c_extraction():
    d = classify_risk("shell", {"command": "python -c \"import shutil; shutil.rmtree('/tmp/x')\""})
    assert d.action == "deny" and "python -c" in d.reason
    # benign python -c stays allow
    d = classify_risk("shell", {"command": "python -c \"print(1)\""})
    assert d.action == "allow"


# ------------------- aliases, path escapes, network egress (H1+, 2026-10-18)
def test_aliased_destructive_calls_denied():
    assert "deny" in _actions("import shutil as sh\nsh.rmtree('/tmp/x')")
    assert "deny" in _actions("from shutil import rmtree\nrmtree('/tmp/x')")
    assert "deny" in _actions("from shutil import rmtree as rm\nrm('/tmp/x')")
    assert "deny" in _actions("from os import system\nsystem('echo hi')")
    assert "deny" in _actions("from os import remove\nremove('x.txt')")
    assert "deny" in _actions("import os as _o\n_o.unlink('x.txt')")
    # deny-listed function referenced without calling / reached via getattr
    assert "deny" in _actions("import os\nf = os.system")
    assert "deny" in _actions("import os\ngetattr(os, 'system')('x')")
    # benign aliasing stays clean
    assert analyze_python("import math as m\nprint(m.sqrt(2))") == []
    assert analyze_python("from math import sqrt\nprint(sqrt(4))") == []


def test_outside_workspace_writes_denied():
    from bee import paths
    outside = str(paths.PROJECT_ROOT.parent / "guard_escape.txt")
    inside = str(paths.PROJECT_ROOT / "guard_inside.txt")
    assert "deny" in _actions(f"open({outside!r}, 'w')")
    assert "deny" in _actions(f"open({outside!r}, 'a')")
    assert "deny" in _actions("open('/etc/passwd', 'w')")
    assert "deny" in _actions("open('C:\\\\Windows\\\\System32\\\\drivers\\\\etc\\\\hosts', 'a')")
    assert "deny" in _actions("open(%r, 'w')" % ("../" * 10 + "escape.txt"))
    # in-tree and dynamic paths keep the old single ask
    assert _actions(f"open({inside!r}, 'w')") == ["ask"]
    assert _actions("open('out.txt', 'w')") == ["ask"]
    assert analyze_python(f"open({outside!r})") == []      # read is not a write


def test_outside_workspace_windows_style_on_posix():
    """CI (Linux) regression: a C:\\... literal must classify as OUTSIDE even
    though posixpath.abspath would hoist it under the repo cwd."""
    from bee.security import risk
    import os as _os
    real = _os.name
    try:
        _os.name = "posix"          # simulate the CI runner's host
        assert risk._outside_workspace("C:\\Windows\\System32\\drivers\\etc\\hosts") is True
        assert risk._outside_workspace("\\\\server\\share\\evil.txt") is True
        assert risk._outside_workspace("out.txt") is None
    finally:
        _os.name = real


def test_pathlib_writes_and_state_methods():
    from bee import paths
    outside = str(paths.PROJECT_ROOT.parent / "guard_escape.txt")
    assert "deny" in _actions(
        f"from pathlib import Path\nPath({outside!r}).write_text('x')")
    assert "ask" in _actions("from pathlib import Path\nPath('out.txt').write_text('x')")
    assert "ask" in _actions("from pathlib import Path\nPath('d').mkdir()")
    assert "ask" in _actions("from pathlib import Path\nPath('out.txt').touch()")


def test_requests_egress_and_ssrf_literals():
    assert "ask" in _actions("import requests\nrequests.get('https://example.com')")
    assert "ask" in _actions("import httpx\nhttpx.post('https://example.com', json={})")
    assert "ask" in _actions("from urllib.request import urlopen\nurlopen('https://example.com')")
    # non-public literal targets deny outright (SSRF from code_run)
    assert "deny" in _actions("requests.get('http://127.0.0.1:8080/x')")
    assert "deny" in _actions("requests.get('http://169.254.169.254/latest/meta-data/')")
    assert "deny" in _actions("requests.get('http://localhost:11434/api/tags')")
    # raw sockets stay deny
    assert "deny" in _actions("import socket")


def test_alias_deny_reaches_classify_risk_and_guard():
    d = classify_risk("code_run", {"code": "import shutil as sh; sh.rmtree('/tmp/x')"})
    assert d.action == "deny"
    from bee import guard
    ok, action, _ = guard.check(
        "code_run", {"code": "import shutil as sh; sh.rmtree('/tmp/x')"},
        True, "unattended")
    assert not ok and action == "deny"
