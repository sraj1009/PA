"""Verify the Docker sandbox end-to-end via BEE's own sandbox_run tool."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bee.config import load_config            # noqa: E402
from bee.agent.context import Context         # noqa: E402
from bee.tools import tools_by_name           # noqa: E402

cfg = load_config()
ctx = Context(cfg, workspace=cfg.workspace, name="BEE")
tools = tools_by_name()

print("== 1) hello ==")
r = tools["sandbox_run"](ctx, command="echo SANDBOX_OK && python -V && uv --version")
print(r)
assert r.get("exit_code") == 0 and "SANDBOX_OK" in r.get("output", ""), r

print("== 2) stack import check ==")
check = (
    "import importlib.util\n"
    "mods = ['torch','sklearn','polars','pandas','transformers','peft','datasets',\n"
    "        'lightgbm','xgboost','mlflow','playwright','onnxruntime','accelerate']\n"
    "missing = [m for m in mods if importlib.util.find_spec(m) is None]\n"
    "import torch\n"
    "print('STACK_OK missing=' + str(missing) + ' torch=' + torch.__version__ +\n"
    "      ' cuda=' + str(torch.cuda.is_available()))"
)
r = tools["sandbox_run"](ctx, command="python - <<'EOF'\n" + check + "\nEOF")
print(r)
assert r.get("exit_code") == 0 and "STACK_OK" in r.get("output", ""), r

print("== 3) DSA inside sandbox (workspace mount check) ==")
tools["file_write"](ctx, path="sandbox_probe.txt", content="host-visible")
r = tools["sandbox_run"](ctx, command="cat /workspace/sandbox_probe.txt")
print(r)
assert r.get("exit_code") == 0 and "host-visible" in r.get("output", ""), r

print("== 4) sandbox writes back to host ==")
r = tools["sandbox_run"](ctx, command="python -c \"open('/workspace/sandbox_back.txt','w').write('from-sandbox')\"")
back = (cfg.workspace / "sandbox_back.txt").read_text()
print("host sees:", repr(back))
assert back == "from-sandbox"
import os
os.remove(cfg.workspace / "sandbox_back.txt")
os.remove(cfg.workspace / "sandbox_probe.txt")

print("\nSANDBOX: ALL CHECKS PASSED")
