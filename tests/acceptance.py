"""Final acceptance: default config (bee4b local) end-to-end + full smoke suite.

Run:  python tests/acceptance.py
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bee.config import load_config            # noqa: E402
from bee.agent.context import Context         # noqa: E402
from bee.agent.client import LLMClient        # noqa: E402
from bee.agent.loop import run_agent          # noqa: E402

failures = []


def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {name} {detail}")
    if not cond:
        failures.append(name)


print("== 1) embeddings (nomic-embed-text) ==")
cfg = load_config()
ctx = Context(cfg, workspace=cfg.workspace, name="BEE")
ctx.client = LLMClient(cfg)
try:
    e = ctx.client.embed(["hello world", "goodbye"])
    check("embed dim 768", len(e) == 2 and len(e[0]) == 768, f"(dim={len(e[0])})")
except Exception as ex:
    check("embed", False, str(ex)[:100])

print("== 2) planner (bee4b) ==")
pl = ctx.client.chat("local", [{"role": "user", "content":
    "List 3 concrete steps to clean a messy downloads folder. Numbered list only."}])
plan_txt = (pl.get("content") or "")
check("planner responds", len(plan_txt) > 30, f"({len(plan_txt)} chars)")

print("== 3) e2e multi-tool, DEFAULT config (local bee4b) ==")
task = ("Use the calculator tool to compute 256*128-1024, then write that exact result to a file called "
        "acceptance_answer.txt in the workspace, then read the file back and confirm its content matches.")
events = []
r = run_agent(ctx, task,
              on_event=lambda ev: events.append(ev.get("type") + ":" + str(ev.get("tool", ""))))
tools_used = [e for e in events if e.startswith("tool_result")]
check("task completed", r.ok and "31744" in r.output, f"iters={r.iterations} tools={len(tools_used)} model={r.model}")
check("used calculator+files", any("calculator" in t for t in tools_used)
      and any("file_write" in t for t in tools_used) and any("file_read" in t for t in tools_used),
      str(tools_used))
try:
    content = (cfg.workspace / "acceptance_answer.txt").read_text().strip()
    check("file on disk correct", "31744" in content, repr(content[:40]))
    os.remove(cfg.workspace / "acceptance_answer.txt")
except FileNotFoundError:
    check("file on disk correct", False, "file missing")

print("== 4) full offline smoke suite ==")
p = subprocess.run([sys.executable, str(ROOT / "tests" / "smoke_offline.py")],
                   capture_output=True, text=True, cwd=str(ROOT), timeout=300)
smoke_ok = "SMOKE TEST: ALL PASSED" in p.stdout
check("smoke suite all green", smoke_ok)
if not smoke_ok:
    for line in p.stdout.splitlines():
        if "FAIL" in line:
            print("   ", line)

print()
if failures:
    print(f"ACCEPTANCE: {len(failures)} FAILED -> {failures}")
    sys.exit(1)
print("ACCEPTANCE: ALL GREEN — BEE default config verified end-to-end")
