"""Offline smoke test: config, context, router, all 19 tools (no LLM calls).

Run:  python tests/smoke_offline.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bee.config import load_config                      # noqa: E402
from bee.agent.context import Context, build_system_prompt  # noqa: E402
from bee.agent.client import LLMClient                  # noqa: E402
from bee.agent.router import route_task                 # noqa: E402
from bee.tools import tools_litellm, tools_by_name      # noqa: E402

failures = []


def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {name} {detail}")
    if not cond:
        failures.append(name)


cfg = load_config()
ctx = Context(cfg, workspace=cfg.workspace, name="BEE")
ctx.client = LLMClient(cfg)

print("== system prompt ==")
sp = build_system_prompt(ctx)
check("prompt contains identity+profile+skills",
      "BEE" in sp and "M Shriraj" in sp and "User profile" in sp and "dsa" in sp,
      f"({len(sp)} chars)")

print("== registry ==")
tools = tools_by_name()
schemas = tools_litellm()
check("22 tools", len(tools) == 22, str(len(tools)))
check("22 schemas", len(schemas) == 22)
check("schemas well-formed",
      all(s["type"] == "function" and s["function"]["name"] in tools for s in schemas))
print("  tools:", ", ".join(sorted(tools)))

print("== router ==")
check("simple -> local", route_task("do this", cfg) == ("local", False))
check("cloud: prefix -> cloud", route_task("cloud: analyze this", cfg) == ("cloud", True))
check("'use local' -> local", route_task("use local for this", cfg) == ("local", False))
big = "Write a comprehensive in-depth research report that designs a system; " \
      "first gather data, then model it, then evaluate. " + "x" * 400
r, e = route_task(big, cfg)
check("complex + long -> cloud (escalation on)", r == "cloud" and e, f"-> {r}")

print("== calculator ==")
out = tools["calculator"](ctx, expression="(sqrt(144) + 2**5) * 3")
check("(sqrt(144)+2**5)*3 == 132", out.get("result") == "132.0", str(out))
out2 = tools["calculator"](ctx, expression="sum([1,2,3]) + len([[1,2],[3]]) + gcd(84,147)")
check("sum+len+gcd == 29", out2.get("result") == "29", str(out2))
out3 = tools["calculator"](ctx, expression="__import__('os')")
check("import blocked", "error" in out3)

print("== files ==")
w = tools["file_write"](ctx, path="smoke_test.txt", content="hello BEE\nline2")
check("write", w.get("chars") == len("hello BEE\nline2"))
rd = tools["file_read"](ctx, path="smoke_test.txt")
check("read", rd.get("content", "").startswith("hello BEE"))
ed = tools["file_edit"](ctx, path="smoke_test.txt", old="BEE", new="BEE-2")
check("edit", ed.get("replacements") == 1)
ed2 = tools["file_edit"](ctx, path="smoke_test.txt", old="nope-not-here", new="x")
check("edit missing old -> error", "error" in ed2)
lst = tools["file_list"](ctx, path=".")
check("list", "entries" in lst and len(lst["entries"]) > 3)
esc = tools["file_read"](ctx, path="../outside.txt")
check("path escape blocked", "error" in esc)

print("== memory ==")
d = tools["diary_add"](ctx, message="smoke test entry", model="local")
check("diary_add", d.get("ok") is True)
lt = tools["memory_longterm"](ctx, text="smoke fact: memory works")
check("longterm add", lt.get("ok") is True)
res = tools["memory_search"](ctx, query="memory works smoke", k=3)
hits = res.get("results", [])
check("search finds it", any("smoke" in r["text"] for r in hits), f"({len(hits)} hits)")

print("== skills ==")
s = tools["skill_create"](ctx, name="smoke-skill", description="test skill",
                          content="# smoke-skill\ndescription: test skill\n")
check("skill_create", s.get("ok") is True)
g = tools["skill_get"](ctx, name="smoke-skill")
check("skill_get", "test skill" in g.get("content", ""))
lg = tools["skill_list"](ctx)
names = [x["name"] for x in lg["skills"]]
check("8 starter skills indexed", all(n in names for n in
      ["dsa", "pytorch", "transformers", "sklearn", "polars", "finetune", "browser", "sandbox"]),
      str(len(names)))
gs = tools["skill_search"](ctx, query="algorithm benchmark")
check("skill_search hits dsa", any(m["name"] == "dsa" for m in gs["matches"]))

print("== shell + code ==")
sh = tools["shell"](ctx, command='python -c "print(6*7)"')
check("shell python 6*7", "42" in sh.get("output", ""), str(sh.get("output", ""))[:40])
sh2 = tools["shell"](ctx, command="python -c \"import sys; print(sys.version_info[:2])\"")
check("shell quotes", len(sh2.get("output", "")) > 0, sh2.get("output", sh2.get("error", ""))[:60])
code = tools["code_run"](ctx, code="print(sum(range(10)))")
check("code_run sum", "45" in code.get("output", ""))
code2 = tools["code_run"](ctx, code="print(1/0)", timeout=30)
check("code_run error captured", code2.get("exit_code") == 1 and "ZeroDivision" in code2.get("error", ""),
      str(code2)[:80])

print("== web (tolerates offline) ==")
wf = tools["web_fetch"](ctx, url="https://example.com", timeout=10)
check("web_fetch example.com", "content" in wf and "documentation examples" in wf.get("content", ""),
      wf.get("content", wf.get("error", ""))[:50])

print("== planner (LLM — skip if offline) ==")
if ctx.client._has_ollama():
    pl = tools["planner"](ctx, task="organize a messy downloads folder")
    check("planner returns plan", "plan" in pl and len(pl["plan"]) > 20)
else:
    print("  [SKIP] ollama offline — planner/loop need a live model")

print("== sandbox (tolerates no docker) ==")
sb = tools["sandbox_run"](ctx, command="echo hi")
check("sandbox responds", isinstance(sb, dict), str(sb)[:80])

# cleanup
try:
    os.remove(cfg.workspace / "smoke_test.txt")
except OSError:
    pass
from bee import paths  # noqa: E402
sk = paths.SKILLS_DIR / "smoke-skill"
if sk.exists():
    for f in sk.iterdir():
        f.unlink()
    sk.rmdir()
# remove smoke longterm bullet
lt_p = paths.LONGTERM_MD
txt = lt_p.read_text(encoding="utf-8")
lt_p.write_text(txt.replace("\n- smoke fact: memory works\n", "\n"), encoding="utf-8")

print()
if failures:
    print(f"SMOKE TEST: {len(failures)} FAILED -> {failures}")
    sys.exit(1)
print("SMOKE TEST: ALL PASSED")
