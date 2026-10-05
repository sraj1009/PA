"""Live smoke: JARVIS-port features. READ-ONLY actions only (no volume/lock/sleep)."""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bee.config import load_config
from bee.agent.client import LLMClient
from bee.agent.context import Context
from bee.agent.loop import run_agent
from bee import commands
from bee.tools import systemctl

cfg = load_config()
ctx = Context(cfg, workspace=cfg.workspace, name="BEE")
ctx.client = LLMClient(cfg)

print("== 1. systemctl: system stats (WMI, real) ==")
s = systemctl.get_system_stats()
print(systemctl.format_system_stats(s) if s else "stats unavailable")

print("\n== 2. systemctl: battery (WMI, real) ==")
b = systemctl.get_battery()
print(f"{b}" if b else "no battery (desktop/AC)")

print("\n== 3. fast path: 'how is the pc' (through run_agent, no LLM needed) ==")
r = run_agent(ctx, "how is the pc")
print(f"[{r.route_source}] {r.output}")

print("\n== 4. fast path: 'battery' (through run_agent) ==")
r = run_agent(ctx, "how much is the battery")
print(f"[{r.route_source}] {r.output}")

print("\n== 5. fast path: 'wikipedia transformer' (live REST API) ==")
r = run_agent(ctx, "what is a transformer")
print(f"[{r.route_source}] {r.output[:220]}")

print("\n== 6. fast path: 'welcome home' guard + dry plan ==")
from bee.commands import welcome
print(welcome.run(cfg=cfg, dry_run=True))

print("\n== 7. /welcome command registered ==")
cmd = commands.get("welcome")
print(f"usage: {cmd.usage} — {cmd.description}")

print("\n== 8. guard classification ==")
from bee import guard
for a, v in [("lock", ""), ("sleep", ""), ("volume", "up"), ("stats", "")]:
    print(f"  {a:8s} {v:3s} -> {guard.classify('systemctl', {'action': a, 'value': v})}")

print("\n== 9. clap detector construction ==")
from bee.voice.clap import ClapDetector
d = ClapDetector(lambda: None, **{"sample_rate": cfg.clap.sample_rate, "block_ms": cfg.clap.block_ms,
                                  "spike_ratio": cfg.clap.spike_ratio, "min_rms": cfg.clap.min_rms,
                                  "min_double_gap_s": cfg.clap.min_gap, "max_double_gap_s": cfg.clap.max_gap,
                                  "cooldown_s": cfg.clap.cooldown, "retrigger_ratio": cfg.clap.retrigger_ratio,
                                  "warmup_s": cfg.clap.warmup_s})
print(f"ClapDetector ok — action={cfg.clap.action}, blocks={d._block_samples()} samples @ {d.sample_rate}Hz")

print("\nALL SMOKE CHECKS DONE")
