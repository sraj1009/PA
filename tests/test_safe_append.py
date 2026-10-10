"""A51: two BEE processes appending to the same JSONL stream corrupt each other.

Measured on this machine (6 processes x 60 lines, the exact
`threading.Lock()` + `open(path, "a")` pattern from bee/monitor/metrics.py):
244 of 360 lines survived at 4 KB, 302 of 360 at 60 B, and 12 of them were torn
fragments — which is the `metrics.jsonl` row A44c found and called
"unattributable". `threading.Lock()` only serialises threads of ONE process, and
Windows gives no atomic-append guarantee (raw `os.write` on an `O_APPEND` fd was
*worse*: 136 of 360 lines).
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading

from bee import paths, safeio

CHILD = """
import sys
sys.path.insert(0, "@ROOT@")
from bee import safeio
path, n, size, proc = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
for i in range(n):
    # mixed sizes: each writer sits at a different EOF, which is what exposes a
    # lock taken "at the current position" instead of at a fixed byte
    payload = "x" * (size if i % 2 else 40)
    safeio.append_json(path, {"event": "probe", "proc": proc, "payload": payload})
"""


def _child_script(tmp_path, index):
    p = tmp_path / f"child{index}.py"
    p.write_text(CHILD.replace("@ROOT@", str(paths.PROJECT_ROOT).replace("\\", "\\\\")),
                 encoding="utf-8")
    return p


def _append_via_processes(tmp_path, procs=3, lines=25, size=20_000):
    target = tmp_path / "stream.jsonl"
    kids = [subprocess.Popen([sys.executable, str(_child_script(tmp_path, i)),
                              str(target), str(lines), str(size), str(i)],
                             cwd=str(paths.PROJECT_ROOT))
            for i in range(procs)]
    for k in kids:
        assert k.wait() == 0
    return target, procs * lines


def test_concurrent_processes_do_not_tear_or_lose_lines(tmp_path):
    target, wanted = _append_via_processes(tmp_path)
    raw = target.read_bytes().split(b"\n")[:-1]
    assert len(raw) == wanted, f"{len(raw)} of {wanted} lines survived"
    lens = set()
    for ln in raw:
        row = json.loads(ln.decode("utf-8"))          # a torn fragment raises here
        lens.add(len(row["payload"]))
    assert lens == {40, 20_000}, lens                 # nothing half-written or merged


def test_append_line_creates_parents_and_writes_one_line(tmp_path):
    p = tmp_path / "deep" / "er" / "stream.jsonl"
    safeio.append_line(p, '{"a": 1}')
    safeio.append_line(p, '{"a": 2}')
    assert p.read_text(encoding="utf-8").splitlines() == ['{"a": 1}', '{"a": 2}']


def test_a_line_never_reaches_the_console_codec(tmp_path):
    """Unicode the Windows console codec cannot represent must survive
    (the cp1252 default is what broke code_run, A49a)."""
    p = tmp_path / "u.jsonl"
    safeio.append_json(p, {"arrow": "A → C", "ru": "память"})
    assert json.loads(p.read_text(encoding="utf-8"))["arrow"] == "A → C"


def test_threads_in_one_process_are_serialised(tmp_path):
    p = tmp_path / "t.jsonl"
    ts = [threading.Thread(target=safeio.append_json,
                           args=(p, {"payload": "y" * 20_000, "proc": i}))
          for i in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 8 and all(len(r["payload"]) == 20_000 for r in rows)
