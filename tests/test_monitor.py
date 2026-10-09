"""Tests for the monitoring layer: metrics stream, health checks, dashboard."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bee.config import load_config  # noqa: E402
from bee import paths  # noqa: E402
from bee.monitor import metrics, health, dashboard  # noqa: E402

cfg = load_config()
PASS = 0
ATTEMPTS = 0


def check(ok, label, note=""):
    global PASS, ATTEMPTS
    ATTEMPTS += 1
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label} {note}")
    if ok:
        PASS += 1
    assert ok, label


print("== 1) metrics record/stats ==")
# This module writes real events while it is being COLLECTED, so it is also the
# guard: the stream it appends to must not be the user's. (conftest applies the
# redirect in pytest_configure for exactly this reason — a fixture would run too
# late and every suite run leaked one event into metrics/metrics.jsonl.)
check(paths.PROJECT_ROOT not in paths.METRICS_FILE.parents,
      "test suite writes to an isolated metrics file",
      f"({paths.METRICS_FILE})")
before = metrics.load_all()
metrics.record("test_probe", value=1, ok=True)
time.sleep(0.01)
after = metrics.load_all()
check(len(after) == len(before) + 1, "event appended", f"({len(before)} -> {len(after)})")
last = after[-1]
check(last.get("event") == "test_probe", "last event is probe")
st = metrics.stats(window_hours=1)
check(isinstance(st, dict) and "total_tasks" in st, "stats returns dict with total_tasks")

print("== 2) health run_checks ==")
checks = health.run_checks(cfg)
check(len(checks) >= 8, f"{len(checks)} checks returned", f"(need >= 8)")
ok_names = [c["name"] for c in checks if c["ok"]]
check(all(set(c) == {"ok", "name", "note"} for c in checks), "check shape ok/name/note")
check("python" in ok_names[0], "python check passes", f"({ok_names[0]})")
ollama_row = next((c for c in checks if c["name"] == "ollama"), None)
check(ollama_row is not None, "ollama row present",
      f"(ok={ollama_row['ok'] if ollama_row else '-'} {str(ollama_row['note'])[:60] if ollama_row else ''})")
try:
    health.cli_report(cfg)
    check(True, "cli_report runs without exception")
except Exception as e:
    check(False, "cli_report runs without exception", str(e)[:100])

print("== 3) dashboard build ==")
f = dashboard.build()
check(Path(f).exists(), "dashboard file written", f"({f})")
html = Path(f).read_text(encoding="utf-8")
check("<!DOCTYPE html>" in html.lower() or "<html" in html.lower(), "valid html shell")
check("#d7ff00" in html.lower(), "brand accent present")
check("BEE" in html, "branding present")
check(len(html) > 5000, f"self-contained (no external assets) size={len(html)}")

print("== 4) dashboard is LIVE, not just a snapshot (L3/M8) ==")
static = dashboard.render()
check('http-equiv="refresh"' not in static, "written snapshot does not self-reload")
check("python -m bee.cli dashboard" in static, "snapshot tells you how to refresh it")
live = dashboard.render(refresh_seconds=30)
check('http-equiv="refresh" content="30"' in live, "live view reloads every 30 s")
check("live view" in live, "live view says so on the page")

# the claim that matters: the SAME function answers twice with different numbers
# because it reads the metrics at request time. A file-based dashboard cannot.
class _M:
    def __init__(self):
        self.rows = []

    def load_all(self):
        return list(self.rows)

    def stats(self, window_hours=24 * 7):
        n = sum(1 for r in self.rows if r.get("event") == "task")   # like the real one
        return {"total_tasks": n, "tasks_ok": n,
                "success_rate": 1.0, "avg_seconds": 0.1, "avg_iters": 1,
                "escalations": 0, "guard_denied": 0, "guard_asks": 0,
                "redactions": 0, "verify_fail": 0}


_stub = _M()
_real_metrics = dashboard.metrics
dashboard.metrics = _stub
try:
    _stub.rows = [{"ts": time.time(), "event": "task", "ok": True,
                   "model": "bee4b", "seconds": 0.1},
                  {"ts": time.time(), "event": "route", "source": "fastpath"}]
    a = dashboard.render(refresh_seconds=30)
    _stub.rows.append({"ts": time.time(), "event": "task", "ok": True,
                       "model": "glm-5.2", "seconds": 0.2})
    _stub.rows.append({"ts": time.time(), "event": "route", "source": "ml-router"})
    b = dashboard.render(refresh_seconds=30)
    check(a != b, "two renders differ once new events are recorded")
    check(">1<" in a.replace(" ", "") and ">2<" in b.replace(" ", ""),
          "the KPI counts the new event", "(1 -> 2)")
    check("fastpath" in a and "ml-router" not in a, "first view shows only its own sources")
    check("ml-router" in b and "bee4b" in b, "second view picks up the new source + model")
finally:
    dashboard.metrics = _real_metrics

src = Path(dashboard.__file__).read_text(encoding="utf-8")
check("placeholder" not in src, "no leftover placeholder series in the dashboard")

print(f"\nmonitor: {PASS}/{ATTEMPTS} passed")
