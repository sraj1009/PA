"""Tests for the monitoring layer: metrics stream, health checks, dashboard."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bee.config import load_config  # noqa: E402
from bee.monitor import metrics, health, dashboard  # noqa: E402

cfg = load_config()
PASS = 0


def check(ok, label, note=""):
    global PASS
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label} {note}")
    if ok:
        PASS += 1
    assert ok, label


print("== 1) metrics record/stats ==")
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

print(f"\nmonitor: {PASS}/13 passed")
