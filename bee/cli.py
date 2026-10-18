"""BEE CLI — REPL with voice mode, commands, and event display.

python -m bee.cli                  # REPL
python -m bee.cli voice            # straight into voice mode
python -m bee.cli plan [weekly|add "..." ...]   # run the /plan itinerary command
python -m bee.cli speak "text"     # TTS test
python -m bee.cli web              # web UI on http://127.0.0.1:8787
python -m bee.cli full             # ALL at once: web UI + Live Voice + text REPL (bee-runfull)
python -m bee.cli eval             # run the eval suite
python -m bee.cli setup            # environment check + installs
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys


# ------------------------------------------------------------------ repl
def _try_rich():
    try:
        from rich.console import Console
        from rich.markdown import Markdown
        return Console(), Markdown
    except ImportError:
        return None, None


class _Print:
    def __init__(self):
        self.console, self.Markdown = _try_rich()

    def _c(self, style, text):
        if self.console:
            self.console.print(text, style=style)
        else:
            print(text)

    def user(self, t): self._c("bold cyan", f"you> {t}")
    def bee(self, t):
        if self.console and self.Markdown:
            self.console.print(f"[bold lime]BEE>[/]", self.Markdown(t))
        else:
            print(f"BEE> {t}")
    def tool(self, t): self._c("dim", f"  · {t}")
    def info(self, t): self._c("dim italic", t)
    def error(self, t): self._c("bold red", f"  ! {t}")
    def header(self, t): self._c("bold magenta", t)


def _cmd_help(p: _Print):
    from . import commands as cmdreg
    p.info(
        "assistant commands (modular — bee/commands/):\n" + cmdreg.help_text() + "\n\n"
        "core:\n"
        "  /help            this help\n"
        "  /voice           voice command mode (speak your task; 'bee' wake word optional)\n"
        "  clap mode        python -m bee.cli clap — double-clap triggers welcome/voice task\n"
        "  full mode        python -m bee.cli full  (or .\bee-runfull.ps1) — web + live voice + REPL at once\n"
        "  /welcome [dry|reset]  Welcome Home workspace protocol (song->browsers->IDE focus)\n"
        "  /speak <text>    test text-to-speech\n"
        "  /tts [on|off|rate <wpm>|voice <name>|voices]  voice output settings (session)\n"
        "  /engine [name]     default brain: hybrid | local | ollama-cloud | api-cloud (persisted)\n"
        "  /model [local|cloud|name]   view or override the model for this session\n"
        "  /tools           list available tools\n"
        "  /skills          list skills\n"
        "  /mem [status|<query>]  memory: hybrid search, or index status (sources, age, queue)\n"
        "  /reflect         run self-review on the last task now\n"
        "  /like | /dislike  rate the last answer (+1/-1) for training\n"
        "  /correct <text>  supply the wording it should have used (teacher sample)\n"
        "  /consolidate     run memory consolidation now (diary -> longterm)\n"
        "  /eval            run the agent eval suite\n"
        "  /health          environment + service health check\n"
        "  /doctor          deep read-only report: config precedence, services, memory, disk, verdict\n"
        "  /dashboard       build & open the monitoring dashboard\n"
        "  /router          show ML router training status\n"
        "  /guard [on|off]  permission gates for destructive commands\n"
        "  /privacy [on|off]  PII redaction on cloud payloads\n"
        "  /rag [on|off]    auto memory-context for reference tasks\n"
        "  /jobs            list durable jobs (survive restarts; /job <id> for detail)\n"
        "  /job <id> <op>   op: detail | disable | enable | cancel | delete | history\n"
        "  /auto            unread notifications + proactive rules (user-authorized only)\n"
        "  /resume [id]     J1 crash recovery: list/resume interrupted tasks\n"
        "  /gate [show|baseline [model]|run [candidate]|rollback]  J3 model-upgrade quality gate\n"
        "  /skillgate [name]  J2 skill gate: structural check + eval probe (all candidates if no name)\n"
        "  /config          M14: where each config field actually came from (precedence report)\n"
        "  /clear           clear screen\n"
        "  /exit | /quit    leave\n"
        "  Ctrl-C mid-task  cancels the running task\n"
        "  'cloud: <task>'  force cloud model for one task"
    )


def _repl(cfg):
    from .agent.context import create_context
    from .agent.loop import run_agent
    from .agent import reflection
    from .voice import loop as voice_loop
    p = _Print()
    ctx = create_context(cfg)
    model_override = ctx.model_override
    last_task = None

    # Ctrl-C: cancels a running task; at the prompt it exits (as before)
    import signal
    import threading
    cancel = threading.Event()
    ctx.cancel_event = cancel
    running = {"flag": False}

    # Phase 2: one agent kernel owns task state, permissions, verification,
    # receipts and session continuity for this launch (repl/voice/web share
    # the same runtime).
    from .kernel import AgentKernel
    kernel = AgentKernel(ctx)
    ctx.kernel = kernel

    # Phase 6: durable automation (jobs + proactive rules) — restored from
    # <workspace>/automation, runs through THIS kernel, never a no-op.
    try:
        from . import scheduler as _sched_auto
        _sched_auto.start_automation(ctx, cfg, kernel)
    except Exception as e:
        p.info(f"automation not started: {e}")

    def _sigint(signum, frame):
        if running["flag"]:
            cancel.set()
        else:
            raise KeyboardInterrupt
    try:
        signal.signal(signal.SIGINT, _sigint)
    except (ValueError, OSError):
        pass

    models = ctx.client.models_list()
    p.header("BEE — local-first, self-improving PA")
    p.info(f"workspace: {cfg.workspace}")
    p.info(f"local model: {cfg.ollama.model}  |  ollama models: {', '.join(models) if models else 'NONE — start Ollama & pull models'}")
    if cfg.cloud.enabled and cfg.cloud.llm:
        p.info(f"cloud model: {cfg.cloud.llm} (auto-escalation on)")
    else:
        p.info("cloud model: not configured (set cloud.llm + API key in config.yaml)")
    try:
        from .voice import transcribe, speak
        if transcribe.available():
            p.info(f"voice: STT ready (faster-whisper '{cfg.voice.model}')  TTS: {', '.join(speak.available()) or 'none'}")
        else:
            p.info("voice: faster-whisper NOT installed — /voice disabled (pip install -r requirements-voice.txt)")
    except Exception:
        pass
    p.info("type a task, or /help for commands. /exit to quit.")

    # engine selection: asked once at first launch, persisted in settings.json
    from .agent import engines
    engine = engines.ask_engine(p.info)
    model_override = engines.override_for(engine) or model_override
    ctx.model_override = model_override
    p.info(f"engine: {engine} (switch any time with /engine)")

    # self-learning: retrain the ML router in the background when enough new
    # episodes have accumulated (TF-IDF + LogReg — a few seconds, no GPU)
    import threading
    def _auto_learn():
        try:
            from . import scheduler as _sched
            r = _sched.maybe_train_router(ctx)
            if r.get("trained"):
                p.info(f"  self-learning: ML router retrained on {r['n_train']} episodes (cv acc {r['cv_acc']})")
        except Exception:
            pass
    threading.Thread(target=_auto_learn, daemon=True).start()

    while True:
        try:
            # strip BOM/zero-width chars — piped or redirected input can carry
            # them, and a BOM-prefixed '/exit' would otherwise route to the model
            line = input("\n").strip().lstrip("\ufeff\u200b\u200e\u200f").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        # Phase 2: first-class cancellation — 'stop' cancels the active task
        if line.lower().strip(" .!?") in {"stop", "cancel", "abort", "stop it",
                                          "never mind", "nevermind", "forget it",
                                          "drop it", "halt"}:
            if running["flag"]:
                kernel.cancel()
                p.info("  stopping — the task will finish its current step safely")
            elif kernel.last_task is not None:
                lt = kernel.last_task
                p.info(f"  nothing running — last task {lt.id} ended {lt.state.value}"
                       + (f": {(lt.output or lt.error)[:120]}" if (lt.output or lt.error) else ""))
            else:
                p.info("  nothing running.")
            continue
        if line.startswith("/"):
            parts = line.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""
            if cmd in ("/exit", "/quit", "/q"):
                break
            if cmd == "/help":
                _cmd_help(p)
            elif cmd == "/clear":
                print("\033[2J\033[H", end="")
            elif cmd == "/tools":
                from .tools import build_default_tools
                for t in build_default_tools():
                    p.info(f"  {t.name:16s} {t.description[:100]}")
            elif cmd == "/skills":
                from . import paths
                from .evals.skillgate import read_meta
                for md in sorted(paths.SKILLS_DIR.glob("*/SKILL.md")):
                    body = md.read_text(encoding="utf-8", errors="ignore")
                    desc = next((ln.split(":", 1)[1].strip() for ln in body.splitlines()
                                 if ln.lower().startswith("description:")), "")
                    m = read_meta(md.parent.name)
                    p.info(f"  {md.parent.name:24s} v{m.get('version', 1)} [{m.get('status', 'active'):9s}] {desc[:70]}")
            elif cmd == "/model":
                if not arg:
                    p.info(f"current override: {model_override or 'auto (local default, cloud escalation)'}")
                else:
                    model_override = arg if arg != "auto" else None
                    p.info(f"model override set to: {model_override or 'auto'}")
            elif cmd == "/engine":
                from .agent import engines
                if not arg:
                    labels = engines.engine_labels(cfg)
                    for e, meta in engines.ENGINES.items():
                        mark = "←" if e == engines.load_engine() else " "
                        p.info(f"  {mark} [{meta['n']}] {labels[e]}")
                    p.info("  set with: /engine hybrid | local | ollama-cloud | api-cloud  (persisted)")
                elif arg in engines.ENGINES:
                    model_override = engines.override_for(arg)
                    ctx.model_override = model_override
                    # Do not claim "persisted" unless the write happened: a blocked
                    # file (OneDrive locks this one on this machine) used to lose the
                    # choice silently while the REPL said it was saved (A41b).
                    if engines.save_engine(arg):
                        p.info(f"engine set to {arg} (persisted; this session: "
                               f"{model_override or 'auto routing'})")
                    else:
                        p.info(f"engine set to {arg} for THIS session only — "
                               f"it could not be written to settings.json")
                else:
                    p.error("unknown engine — run /engine with no arg to list")
            elif cmd == "/tts":
                from .voice import speak
                v = cfg.voice
                a = (arg or "").lower()
                try:
                    if a in ("on", "off"):
                        v.speak = (a == "on")
                        p.info(f"TTS: {'ON' if v.speak else 'OFF'} (session; config.yaml voice.speak to persist)")
                    elif a.startswith("rate "):
                        v.tts_rate = max(80, min(300, int(a.split(None, 1)[1])))
                        p.info(f"TTS rate: {v.tts_rate} wpm")
                    elif a.startswith("voice "):
                        v.tts_voice = arg.split(None, 1)[1].strip()
                        p.info(f"TTS voice: '{v.tts_voice or 'system default'}'")
                    elif a == "voices":
                        vs = speak.py_voices()
                        p.info("SAPI voices: " + (", ".join(vs) or "none found")
                               + "  ·  edge-tts ids (need voice.edge_key): en-US-AriaNeural, "
                                 "en-US-AndrewMultilingualNeural, en-GB-RyanNeural, en-IN-NeerjaNeural")
                    elif a == "test":
                        ok = speak.speak("Text to speech is working. I am BEE.", cfg)
                        p.info("TTS test: " + ("spoken" if ok else "no backend available (pip install pyttsx3)"))
                    else:
                        p.info(f"TTS: {'ON' if v.speak else 'OFF'} · rate {v.tts_rate} wpm · "
                               f"voice '{v.tts_voice or 'default'}' · backends: {', '.join(speak.available()) or 'none'}")
                except Exception as e:
                    p.error(f"/tts: {type(e).__name__}: {e}")
            elif cmd == "/voice":
                voice_loop.run_voice_loop(ctx)
            elif cmd == "/speak":
                if arg:
                    from .voice import speak
                    speak.speak(arg, cfg)
                else:
                    p.error("usage: /speak <text>")
            elif cmd == "/mem":
                if arg.strip().lower() == "status":
                    from .memory import status as memstatus
                    p.info(memstatus.render(memstatus.collect()))
                    continue
                if not arg:
                    p.error("usage: /mem <query>   (or /mem status for the index report)")
                    continue
                from .memory.search import memory_search_hybrid
                res = memory_search_hybrid(ctx, arg, k=5)
                if not res:
                    p.info("  (nothing found)")
                for r in res:
                    p.info(f"  [{r['mode']} {r['score']}|{r['source'].split('memory/')[-1]}] {r['text'][:160]}")
            elif cmd == "/reflect":
                if last_task is None:
                    p.error("no task to reflect on yet")
                    continue
                lesson = reflection.reflect(ctx, last_task[0], last_task[1])
                p.bee(lesson or "(nothing to add)")
            elif cmd in ("/like", "/dislike", "/correct"):
                # RLAIF input: rate the last answer (+1/-1) or supply the
                # wording it should have used. Stored in memory/ratings.db;
                # the nightly SFT build blocklists -1 tasks and trains on
                # corrections, so feedback becomes weights automatically.
                if last_task is None:
                    p.error("no task to rate yet")
                    continue
                from .memory import ratings as _ratings
                task_text, res = last_task[0], last_task[1]
                out_text = getattr(res, "output", "") or ""
                model = getattr(res, "model", "") or ""
                if cmd == "/correct" and not arg:
                    p.error("usage: /correct <what the answer should have said>")
                    continue
                rating = -1 if cmd in ("/dislike", "/correct") else +1
                try:
                    _ratings.record(task_text, out_text, rating,
                                    correction=arg if cmd == "/correct" else "",
                                    model=model, source="repl")
                except ValueError as e:
                    p.error(f"not recorded: {e}")
                    continue
                if cmd == "/like":
                    p.bee("recorded +1 — similar answers stay in the training set.")
                elif cmd == "/dislike":
                    p.bee("recorded -1 — this task is blocklisted from future training.")
                else:
                    p.bee("correction recorded — it becomes a teacher sample tonight.")
            elif cmd == "/consolidate":
                from . import scheduler
                out = scheduler.run_nightly(ctx)
                p.bee(json.dumps(out, indent=1, ensure_ascii=False))
            elif cmd == "/jobs":
                w = getattr(ctx, "automation_worker", None)
                if w is None:
                    p.error("automation is not running (config automation.enabled)")
                elif not arg:
                    jobs = w.jobs()
                    if not jobs:
                        p.info("  (no jobs yet — ask me: 'Every weekday at 8AM, tell me my schedule')")
                    from .automation.models import display_local
                    for j in jobs:
                        mark = "on " if j.enabled else "off"
                        # stored UTC-canonical; DISPLAY in the job's timezone
                        nx = display_local(j.next_run, j.timezone) if j.next_run else "-"
                        p.info(f"  [{mark}] {j.id:22s} {j.state:10s} next={nx:22s} {j.description[:56]}")
                    p.info("  (next-run shown in the job's timezone; stored in UTC) · "
                           "/job <id> [detail|disable|enable|cancel|delete|history]")
                else:
                    p.error("usage: /jobs (list) · /job <id> <op>")
            elif cmd == "/job":
                w = getattr(ctx, "automation_worker", None)
                if w is None:
                    p.error("automation is not running")
                    continue
                parts2 = arg.split()
                if not parts2:
                    p.error("usage: /job <id> [detail|disable|enable|cancel|delete|history]")
                    continue
                jid = parts2[0]
                op = parts2[1].lower() if len(parts2) > 1 else "detail"
                if op == "history":
                    rows = w.history(jid)
                    if not rows:
                        p.info("  (no executions recorded)")
                    from .automation.models import display_local
                    hj = w.store.load_job(w._resolve(jid))
                    hz = hj.timezone if hj else "UTC"
                    for e in rows:
                        st = display_local(e["started_at"], hz) if e.get("started_at") else "-"
                        p.info(f"  {st}  a{e['attempt']}  {e['status']:12s} {e['error'][:74]}")
                elif op in ("disable", "enable", "cancel", "delete"):
                    fn = getattr(w, f"{op}_job")
                    p.info(f"  {op}: {'ok' if fn(jid) else 'job not found'}")
                else:
                    j = w.store.load_job(w._resolve(jid))
                    if j is None:
                        p.error(f"job not found: {jid}")
                        continue
                    s = j.summary()
                    from .automation.models import display_local
                    nx = display_local(j.next_run, j.timezone) if j.next_run else "-"
                    lx = display_local(j.last_run, j.timezone) if j.last_run else "-"
                    p.info(f"  {s['id']}  state={s['state']}  enabled={s['enabled']}")
                    p.info(f"  trigger: {s['trigger']}  next: {nx}  last: {lx}")
                    p.info(f"  owner={s['owner']}  attempts={s['attempts']}  tz={j.timezone} (stored UTC)")
                    p.info(f"  permissions: {j.permissions}")
                    p.info(f"  retry: {j.retry_policy}  max_runtime: {j.max_runtime:.0f}s")
                    for e in w.history(j.id, 3):
                        p.info(f"  · {e['started_at']}  a{e['attempt']}  {e['status']}  {e['error'][:80]}")
            elif cmd == "/auto":
                w = getattr(ctx, "automation_worker", None)
                if w is None:
                    p.error("automation is not running")
                    continue
                if not arg:
                    notifs = w.notifications(unread_only=True)[-10:]
                    if not notifs:
                        p.info("  (no unread notifications)")
                    for n in notifs:
                        p.info(f"  [{n['kind']}] {n['message'][:110]}")
                    rules = w.policy.rules if w.policy else []
                    if not rules:
                        p.info("  (no proactive rules — ask me to add one; each requires your authorization)")
                    for r in rules:
                        # who authored it and what it does: a rule the model
                        # created is not the same authorization as one the user
                        # typed, and an `agent_task` rule runs unattended later
                        p.info(f"  rule {r.id} ({r.kind}) {'on' if r.enabled else 'off'}"
                               f" [{r.action.get('type') or '?'} by {r.created_by}]:"
                               f" {r.description or r.action.get('message') or r.action.get('task')}")
                    p.info("  /auto read = mark notifications read · /jobs manages jobs")
                elif arg == "read":
                    p.info(f"  marked {w.mark_notifications_read()} notification(s) read")
                else:
                    p.error("usage: /auto | /auto read")
            elif cmd == "/resume":
                # J1 crash recovery: re-run an interrupted task
                pends = kernel.pending_checkpoints()
                if not pends:
                    p.info("  (no interrupted tasks — checkpoints clear on normal completion)")
                elif not arg:
                    for r in pends:
                        p.info(f"  {r['task_id'][:14]}  state={r['state']}  steps={len(r.get('observations') or [])}  {r['text'][:50]}")
                    p.info("  /resume <task_id> to resume one (or restart BEE and say 'continue')")
                else:
                    try:
                        res = kernel.resume(task_id=arg)
                        p.bee((res.output or res.error or "")[:400])
                    except RuntimeError as e:
                        p.error(str(e))
            elif cmd == "/gate":
                # J3 model-upgrade quality gate
                from .evals import gate as mgate
                sub = arg.split()[0] if arg else "show"
                val = arg.split(None + " ")[1].strip() if len(arg.split()) > 1 else ""
                if sub in ("", "show"):
                    data = mgate.load_baselines()
                    for name, b in (data.get("models") or {}).items():
                        active = " (ACTIVE)" if name == cfg.ollama.model else ""
                        p.info(f"  {name:20s} baseline {b.get('score'):8s}  {b.get('ts', '')}{active}")
                    for pr in (data.get("promotions") or [])[-5:]:
                        p.info(f"  promotion: {pr.get('from')} -> {pr.get('to')} "
                               f"({pr.get('before')} -> {pr.get('after')})  {pr.get('ts', '')}")
                    p.info(f"  candidate: {cfg.model_gate.candidate or '(none — set model_gate.candidate in config.yaml)'}  "
                           f"margin: {cfg.model_gate.margin}  "
                           f"adjudication: {getattr(cfg.model_gate, 'adjudication_rounds', 0)}")
                    _queued = mgate.pending_candidate()
                    if _queued:
                        p.info(f"  queued (auto-chain): {_queued} — the nightly gate consumes it")
                elif sub == "baseline":
                    try:
                        r = mgate.set_baseline(ctx, val or None)
                        p.bee(str(r))
                    except Exception as e:
                        p.error(str(e))
                elif sub == "run":
                    try:
                        r = mgate.model_quality_gate(ctx, candidate=val or None)
                        p.bee(str(r))
                    except Exception as e:
                        p.error(str(e))
                elif sub == "rollback":
                    r = mgate.rollback_model()
                    p.bee(str(r))
                else:
                    p.error("usage: /gate [show|baseline [model]|run [candidate]|rollback]")
            elif cmd == "/skillgate":
                # J2 skill gate (structural check + bounded eval probe)
                from .evals import skillgate
                if arg:
                    r = skillgate.gate_skill(ctx, arg)
                    p.bee(str(r))
                else:
                    r = skillgate.gate_candidates(ctx)
                    p.bee(str(r))
            elif cmd == "/config":
                # M14: provenance of every resolvable field
                p.info("  config precedence (winner per field):")
                for k in sorted(cfg.precedence):
                    p.info(f"  {k:24s} <- {cfg.precedence[k]}")
                p.info("  full matrix: docs/CONFIG_PRECEDENCE.md")
            elif cmd == "/eval":
                from .evals import runner
                try:
                    cancel.clear()
                    runner.run_suite(ctx)
                finally:
                    cancel.clear()
            elif cmd == "/guard":
                if arg == "on":
                    ctx.guard_on = True
                elif arg == "off":
                    ctx.guard_on = False
                p.info(f"guard: {'ON' if ctx.guard_on else 'OFF'} (mode={ctx.guard_mode}; config.yaml guard.mode = cli|unattended|always)")
            elif cmd == "/privacy":
                if arg == "on":
                    ctx.privacy_on = True
                elif arg == "off":
                    ctx.privacy_on = False
                p.info(f"privacy redaction (cloud payloads): {'ON' if ctx.privacy_on else 'OFF'}")
            elif cmd == "/rag":
                if arg == "on":
                    ctx.rag_on = True
                elif arg == "off":
                    ctx.rag_on = False
                p.info(f"RAG auto-context: {'ON' if ctx.rag_on else 'OFF'}")
            elif cmd == "/router":
                from .brain import mlrouter
                s = mlrouter.summarize()
                if s.get("trained"):
                    p.info(f"ML router: trained on {s['n_train']} episodes (cv acc {s['cv_acc']}) — {s['artifact']}")
                else:
                    p.info("ML router: not trained yet (needs episodes; run: python -m bee.pipeline.train_router)")
            elif cmd == "/health":
                from .monitor import health
                health.cli_report(cfg)
            elif cmd == "/doctor":
                from .monitor import doctor
                doctor.cli_report(cfg)
            elif cmd == "/dashboard":
                from .monitor import dashboard
                f = dashboard.build()
                p.info(f"dashboard written: {f}")
                try:
                    import os
                    os.startfile(str(f))  # Windows: open in browser
                except Exception:
                    pass
            else:
                # modular command registry: /plan /draft /summarize /code /think
                from . import commands
                res = commands.run(ctx, line)
                if res is not None:
                    p.bee(res)
                else:
                    p.error(f"unknown command: {cmd} — /help")
            continue

        # normal task
        p.user(line)
        last_task = None
        cancel.clear()
        running["flag"] = True
        try:
            # Phase 2: tasks run through the kernel (state machine,
            # permissions, verification, receipts, session continuity).
            result = kernel.run(line, session_id="repl", model=model_override,
                                on_event=lambda ev: _on_event(p, ev))
        except KeyboardInterrupt:
            cancel.set()
            result = None
        finally:
            running["flag"] = False
        if result is None:
            p.info("  (cancelled)")
        else:
            p.bee(result.output)
            # text AND voice output: speak the answer when TTS is enabled (/tts off
            # to mute). Queue it — an inline call stalled the prompt (and /exit)
            # behind the full TTS backend timeouts on a wedged audio stack;
            # failures are logged by the speaker worker.
            if result.ok and cfg.voice.enabled and cfg.voice.speak:
                try:
                    from .voice import speak as _speak
                    _speak.enqueue(result.output, cfg)
                except Exception as e:
                    log.warning("TTS raised: %s: %s", type(e).__name__, e)
            meta = f"model={result.model} iters={result.iterations} tools={result.tool_calls}"
            if result.escalated:
                meta = "(escalated to cloud) " + meta
            if result.verify and result.verify != "pass":
                meta += f" verify={result.verify}"
            if result.route_source not in ("", "heuristic"):
                meta += f" route={result.route_source}"
            p.info("  " + meta)
            if not result.ok:
                p.error(result.error)
            last_task = (line, result)
            # The lesson is written by the kernel now (`AgentKernel._reflect`), so
            # every surface learns, not just this REPL (A40b). `/reflect` still
            # re-runs it on demand for the last task.


def _on_event(p: _Print, ev: dict):
    t = ev.get("type")
    if t == "tool_start":
        a = json.dumps(ev.get("args") or {}, ensure_ascii=False)
        p.tool(f"→ {ev.get('tool')}  {a[:140]}")
    elif t == "tool_result":
        mark = "✓" if ev.get("ok") else "✗"
        p.tool(f"{mark} {ev.get('tool')} ({ev.get('seconds')}s) {str(ev.get('preview',''))[:100]}")
    elif t == "guard" and ev.get("action") != "allow":
        p.tool(f"⚠ guard [{ev.get('action')}] {ev.get('tool')}: {ev.get('reason','')}")
    elif t == "redact":
        p.info(f"  🔒 {ev.get('n')} PII item(s) redacted before cloud")
    elif t == "verify" and ev.get("verdict") != "pass":
        p.info(f"  verify: {ev.get('verdict')} — {str(ev.get('findings',''))[:120]}")
    elif t == "escalate":
        p.info(f"  ⤴ escalating to cloud model ({ev.get('reason','')[:80]})")
    elif t == "route" and ev.get("escalated"):
        p.info("  ⤴ routed to cloud (complex task)")
    elif t == "route" and ev.get("source") == "deterministic":
        p.info("  ⚡ deterministic tier (no LLM)")


# ------------------------------------------------------------------ web
def _warn_if_public_bind(host: str) -> None:
    """Loud warning when the web UI is bound beyond loopback.

    The token gates the full agent (shell/code as the operator), so a LAN
    bind is a network-exposed shell; the default is 127.0.0.1 (see
    bee/webapp.py:public_bind_warning + docs/SECURITY.md §2)."""
    from .webapp import public_bind_warning
    w = public_bind_warning(host)
    if w:
        print(w)


def _web(cfg, host: str, port: int):
    import uvicorn
    from .webapp import app
    from .agent.context import create_context
    from . import webapp
    # Unattended surface: a guard 'ask' must never call input() from a
    # worker thread. The interactive kernel below answers via the browser
    # card and falls back to deny when no stream is attached.
    ctx = create_context(cfg, guard_mode="unattended")
    from .agent import engines
    engine = engines.ask_engine()
    ctx.model_override = engines.override_for(engine)
    print(f"engine: {engine} (change live from the dropdown in the browser)")
    webapp.CTX = ctx
    # Print the web auth token ONCE at startup (operator reads it from the
    # console or temp/web_token.txt; it is never logged afterwards).
    print(f"\n  web auth token: {webapp._resolve_token()}")
    print(f"  (saved to temp/web_token.txt — git-ignored; override with BEE_WEB_TOKEN in .env)\n")
    _warn_if_public_bind(host)
    try:
        from . import scheduler
        # Interactive kernel FIRST (found live 2026-10-17): start_automation
        # would otherwise install an auto-deny kernel on ctx, and every
        # /chat permission ask would silently reuse it — the browser never
        # saw a card for gated calls.
        scheduler.start_automation(ctx, cfg, kernel=webapp.get_kernel(ctx))
    except Exception:
        pass
    # pre-warm the STT model in the background so the first voice upload
    # doesn't pay the (one-time) model download
    import threading
    def _warm_stt():
        try:
            from .voice import transcribe
            transcribe._load(cfg.voice.model, cfg.voice.device, cfg.voice.compute_type)
            print("STT model ready (web voice).")
        except Exception as e:
            print(f"STT prewarm: {str(e)[:160]}")
    threading.Thread(target=_warm_stt, daemon=True).start()
    print(f"BEE web UI -> http://{host}:{port}  (Ctrl-C to stop)")
    uvicorn.run(app, host=host, port=port, log_level="warning")


# ------------------------------------------------------------------ realtime
# Engine state -> the face vocabulary the web /face page animates on. The
# LiveKit agent already pushes these; the LOCAL realtime engine did not, so the
# face sat on "idle" during /voice sessions (a test-pinned gap, not a guess).
FACE_STATE = {
    "IDLE": "idle", "LISTENING": "listening", "PROCESSING": "listening",
    "THINKING": "thinking", "SPEAKING": "speaking",
    "INTERRUPTED": "listening", "ERROR": "error",
}


def _realtime(cfg, livekit: bool = False, always_on: bool = False) -> int:
    """Phase 4: true realtime conversational voice.

    Transport (mic or LiveKit room) -> VAD -> streaming STT (interim partials)
    -> VoiceEngine (wake / endpointing / barge-in / state machine) -> AGENT
    KERNEL (same AgentSession/Task system as text) -> streamed LLM tokens ->
    sentence-pipelined streaming TTS -> speaker.
    """
    from .agent import engines
    from .agent.context import create_context
    from .kernel import AgentKernel
    from .voice.realtime import (MicTransport, StreamingSTT, StreamingTTS,
                                 VoiceEngine, VoiceEngineCfg)

    if not StreamingSTT.available():
        print("voice STT not installed — pip install -r requirements-voice.txt")
        return 1

    ctx = create_context(cfg)
    engine = engines.ask_engine()
    ctx.model_override = engines.override_for(engine)
    kernel = AgentKernel(ctx)
    ctx.kernel = kernel

    vc = cfg.voice
    eng_cfg = VoiceEngineCfg(
        wake_word=vc.wake_word or "bee",
        always_on=always_on,
        silence_ms=vc.rt_silence_ms,
        max_utterance_ms=vc.rt_max_utterance_ms,
        partial_stt=vc.rt_partial_stt,
        partial_every_ms=vc.rt_partial_every_ms,
        partial_min_growth=vc.rt_partial_min_growth,
        barge_in=vc.rt_barge_in,
        conversation=vc.rt_conversation,
        wake_ack=vc.rt_wake_ack,
        stt_timeout=vc.rt_stt_timeout,
        tts_timeout=vc.rt_tts_timeout,
        reconnect_max=vc.rt_reconnect_max,
        sample_rate=vc.sample_rate,
    )

    if livekit:
        from .livekit.transport import LiveKitTransport
        transport = LiveKitTransport(cfg)
        sink_note = "LiveKit room"
    else:
        transport = MicTransport(sample_rate=vc.sample_rate)
        sink_note = "speakers"

    try:
        from .livekit import state as face_bridge
    except Exception:
        face_bridge = None
    shown = {"state": "idle"}

    def _face(to, **kw):
        """Push the face state (best-effort: no web UI must never break voice)."""
        if face_bridge is None:
            return
        shown["state"] = to
        try:
            face_bridge.set_state(to, engine=engine, **kw)
        except Exception:
            pass

    def on_event(ev):
        t = ev.get("type")
        if t == "state":
            print(f"  [voice] {ev.get('from')} -> {ev.get('to')}")
            _face(FACE_STATE.get(str(ev.get("to")), "idle"))
        elif t == "partial":
            print(f"  · {ev.get('text')}")
        elif t == "transcript":
            print(f"  you> {ev.get('text')}")
            _face(shown["state"], last_user=str(ev.get("text") or ""))
        elif t == "reply":
            print(f"  BEE> (spoken) {str(ev.get('text'))[:200]}")
            _face("speaking", last_reply=str(ev.get("text") or ""))
        elif t == "barge_in":
            print("  [voice] barge-in: TTS stopped, task cancelled")
        elif t == "wake":
            print("  [voice] wake word heard" + (" (repeat)" if ev.get("repeat") else ""))
        elif t == "error":
            print(f"  [voice] ERROR: {ev.get('error')}")
        elif t == "recovered":
            print("  [voice] recovered")

    stt = StreamingSTT(sample_rate=vc.sample_rate, model=vc.model,
                       device=vc.device, compute_type=vc.compute_type,
                       timeout=vc.rt_stt_timeout)
    tts = StreamingTTS(sink=transport.play,
                       voice=vc.tts_voice or "en-US-AndrewMultilingualNeural",
                       rate=vc.tts_rate, edge_key=vc.edge_key,
                       timeout=vc.rt_tts_timeout)
    eng = VoiceEngine(transport, stt, tts, kernel, cfg=eng_cfg, on_event=on_event)
    print(f"\n  REALTIME VOICE — engine {engine} · STT faster-whisper {vc.model}"
          f" · TTS streaming -> {sink_note}")
    print(f"  wake word: {eng_cfg.wake_word!r} · always-on: {always_on}"
          f" · barge-in: {'ON' if eng_cfg.barge_in else 'OFF (rt_barge_in: false)'}"
          f" · Ctrl-C to stop\n")
    try:
        eng.run()
    finally:
        eng.close()
    return 0


# ------------------------------------------------------------------ setup
def _setup():
    import importlib.util
    import shutil
    print("== BEE environment check ==")
    checks = []
    def check(name, fn):
        try:
            ok, note = fn()
            checks.append((ok, name, note))
        except Exception as e:
            checks.append((False, name, str(e)))

    check("python >= 3.10", lambda: (sys.version_info >= (3, 10), sys.version.split()[0]))
    for mod, req in [("yaml", "pyyaml"), ("httpx", "httpx"), ("pydantic", "pydantic"),
                     ("litellm", "litellm (cloud + ollama)"), ("lancedb", "lancedb (vector memory)"),
                     ("apscheduler", "apscheduler (nightly jobs)"), ("fastapi", "fastapi+uvicorn (web UI)"),
                     ("rich", "rich (prettier CLI)"), ("faster_whisper", "faster-whisper (voice in)"),
                     ("sounddevice", "sounddevice+numpy (mic)"), ("pyttsx3", "pyttsx3 (voice out)"),
                     ("playwright", "playwright (browser, optional)")]:
        check(mod, lambda m=mod: (bool(importlib.util.find_spec(m)),
                                  "ok" if importlib.util.find_spec(m) else f"missing — pip install {req}"))

    import httpx
    def ollama():
        try:
            r = httpx.get("http://localhost:11434/api/tags", timeout=3)
            names = [m["name"] for m in r.json().get("models", [])]
            return (bool(names), ", ".join(names)
                    or "no models — run: ollama pull qwen2.5:3b, then ollama create bee4b -f models/bee4b.Modelfile")
        except Exception:
            return (False, "OFFLINE — start Ollama: https://ollama.com/download/windows")
    check("ollama", ollama)
    def _docker_check():
        if not shutil.which("docker"):
            return (False, "missing — Docker Desktop (sandbox, optional)")
        try:
            r = subprocess.run(["docker", "info"], capture_output=True, timeout=15)
        except Exception:
            return (False, "CLI present but unresponsive — start Docker Desktop")
        if r.returncode == 0:
            return (True, "ok (daemon running)")
        return (True, "CLI ok, daemon NOT running — start Docker Desktop for the sandbox")
    check("docker", _docker_check)

    for ok, name, note in checks:
        print(f"  [{'✓' if ok else '✗'}] {name:38s} {note}")
    missing = [n for ok, n, _ in checks if not ok and n not in ("playwright",)]
    if missing:
        print(f"\nQuick fix:  pip install -r requirements.txt -r requirements-voice.txt")
    else:
        print("\nAll core checks passed. Try:  python -m bee.cli")


# ------------------------------------------------------------------ full
def _full(cfg, host: str, port: int, room: "str | None"):
    """Full-stack one-shot: web UI + Live Voice (browser) + text REPL.

    Spawns the web server and the LiveKit voice agent as child processes
    (logs under temp/), opens the browser on the Live Voice page, then runs
    the interactive REPL in the foreground. /exit (or Ctrl-C) tears the
    children down.
    """
    import os
    import time
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    logdir = root / "temp"
    logdir.mkdir(exist_ok=True)
    # the spawned live-voice process pushes UI state to THIS web server
    # (HTTP bridge, item 10) — it must know the port
    os.environ["BEE_WEB_PORT"] = str(port)
    spawned: list = []

    def spawn(label: str, args: list, logname: str):
        logf = (logdir / logname).open("ab")
        try:
            # -u: unbuffered — child stdout goes to a log file, and default
            # block buffering would swallow everything until the child flushes
            p = subprocess.Popen([sys.executable, "-u", "-m", "bee.cli"] + args, cwd=str(root),
                                 stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        except Exception as e:
            logf.close()
            print(f"  [full] {label} failed to start: {e}")
            return
        spawned.append((label, p, logf))
        print(f"  [full] {label} running (pid {p.pid}, log temp/{logname})")

    _warn_if_public_bind(host)
    spawn("web UI", ["web", "--host", host, "--port", str(port)], "bee-full-web.log")
    lk = cfg.livekit
    if getattr(lk, "enabled", True) and (lk.url and lk.api_key and lk.api_secret):
        spawn("live voice", ["livekit", "--room", room or getattr(lk, "room", "bee-pa") or "bee-pa"],
              "bee-full-livekit.log")
    else:
        print("  [full] live voice skipped (no LiveKit keys in .env — add LIVEKIT_URL/API_KEY/API_SECRET to enable)")
    time.sleep(3)
    try:
        if os.name == "nt":
            os.startfile(f"http://{host}:{port}/livekit")  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", f"http://{host}:{port}/livekit"])
    except Exception:
        print(f"  [full] open the browser yourself: http://{host}:{port}/livekit")
    try:
        _repl(cfg)
    finally:
        for label, p, logf in spawned:
            try:
                p.terminate()
                p.wait(timeout=6)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
            try:
                logf.close()
            except Exception:
                pass
            print(f"  [full] {label} stopped")


# Third-party loggers that would otherwise drown BEE's own diagnostics.
log = logging.getLogger("bee.cli")
_QUIET_LOGGERS = ("httpx", "httpcore", "h11", "urllib3", "openai", "litellm",
                  "LiteLLM",
                  "lancedb", "LanceDB", "numba", "faster_whisper", "livekit",
                  "watchfiles", "uvicorn.access")


def setup_logging(level: str = "") -> None:
    """Install the app-wide log handler, once, on every BEE surface.

    Before this existed no handler was attached anywhere: root fell back to
    Python's last-resort handler (WARNING+ only), so the INFO/DEBUG lines that
    explain a TTS backend fallback, a refused router artifact or why a fast
    path declined were discarded on the floor. Output goes to stderr so the
    REPL/web answer stream on stdout stays clean.

    Level precedence: explicit argument > BEE_LOG_LEVEL > INFO.
    """
    wanted = (level or os.environ.get("BEE_LOG_LEVEL", "INFO")).strip().upper()
    lvl = getattr(logging, wanted, logging.INFO)
    root = logging.getLogger()
    if getattr(root, "_bee_configured", False):
        root.setLevel(lvl)
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
    root.addHandler(handler)
    root.setLevel(lvl)
    for noisy in _QUIET_LOGGERS:
        logging.getLogger(noisy).setLevel(max(logging.WARNING, lvl))
    root._bee_configured = True


def _hard_exit(code) -> None:
    """Flush user-visible state, then os._exit — skipping CPython finalization.

    The CLI spawns daemon threads (TTS speaker, event watchers, automation,
    native boot). At interpreter shutdown CPython freezes daemons wherever
    they are; a daemon frozen mid-import leaks the import lock, and the next
    finalizer can then block forever. Observed on this machine: every
    `python -m bee repl` hung AFTER `/exit` for minutes — faulthandler dump:
    a litellm __del__ importing aiohttp_transport stuck on the module lock,
    main thread already gone (inside Py_FinalizeEx). Task receipts and ratings
    are written per task, so everything user-visible is already durable:
    release the native daemon if we launched it, flush the log handlers, and
    leave deterministically.
    """
    if code is None:
        code = 0
    elif not isinstance(code, int):
        sys.stderr.write(f"{code}\n")
        code = 1
    try:
        from . import native as _native
        _native.stop()               # no-op unless THIS process launched it
    except Exception:
        pass
    try:
        import logging as _logging
        _logging.shutdown()          # flush file/CSV handlers
    except Exception:
        pass
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.flush()
        except Exception:
            pass
    os._exit(code)


def main(argv=None):
    # Windows consoles default to cp1252 — force UTF-8 so symbols never crash the CLI
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="bee", description="BEE - local-first self-improving PA")
    ap.add_argument("mode", nargs="?", default="repl",
                    choices=["repl", "voice", "clap", "web", "plan", "speak", "eval", "setup",
                              "consolidate", "livekit", "realtime", "full", "health", "doctor",
                              "memory"])
    ap.add_argument("rest", nargs="*")
    ap.add_argument("--config", default=None, help="path to config.yaml")
    ap.add_argument("--host", default="127.0.0.1",
                    help="web bind address; the default 127.0.0.1 is the only safe "
                         "choice — 0.0.0.0 exposes shell-capable tools to the network "
                         "(see docs/SECURITY.md)")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--room", default=None, help="LiveKit room name (livekit mode)")
    ap.add_argument("--always-on", action="store_true",
                    help="realtime: skip the wake word (always listening)")
    ap.add_argument("--log-level", default="", metavar="LEVEL",
                    help="diagnostic stream level (DEBUG|INFO|WARNING); "
                         "default INFO, or BEE_LOG_LEVEL")
    args = ap.parse_args(argv)
    setup_logging(args.log_level)

    if args.mode == "setup":
        _setup()
        return 0

    if args.mode == "doctor":
        # Read-only report: dispatches BEFORE config load (it reports a broken
        # config itself, exit 2) and before any background service starts.
        from .monitor import doctor
        return doctor.run(args.config)

    if args.mode == "memory":
        # Read-only index status (source counts, age, queue); no services.
        from .memory import status as memstatus
        return memstatus.run(args.rest)

    from .config import load_config
    cfg = load_config(args.config)

    if args.mode == "health":
        from .monitor import health
        health.cli_report(cfg)
        return 0

    p = _Print()

    # Start the native Go telemetry daemon in the background (never blocks startup).
    # System stats then read from it in ~1 ms instead of a PowerShell/CIM round-trip.
    try:
        from . import native
        native.start_background()
    except Exception:
        pass

    # Same shape for the local model server: if Ollama is not already answering,
    # start it on a background thread so the first task does not silently degrade
    # to cloud/deterministic mode because of a reboot (A60).
    try:
        from .agent import localserver
        localserver.start_background(cfg)
    except Exception:
        pass

    if args.mode == "repl":
        _repl(cfg)
    elif args.mode == "voice":
        from .agent.context import create_context
        from .agent import engines
        from .voice import loop as voice_loop
        ctx = create_context(cfg)
        engine = engines.ask_engine()
        ctx.model_override = engines.override_for(engine)
        print(f"engine: {engine} (asked once, persisted — change in REPL with /engine)")
        voice_loop.run_voice_loop(ctx)
    elif args.mode == "web":
        _web(cfg, args.host, args.port)
    elif args.mode == "full":
        _full(cfg, args.host, args.port, args.room or (args.rest[0] if args.rest else None))
    elif args.mode == "plan":
        from .agent.context import create_context
        from . import commands
        sub = " ".join(args.rest) or "daily"
        ctx = create_context(cfg)
        print(commands.run(ctx, f"plan {sub}"))
    elif args.mode == "clap":
        from .agent.context import create_context
        from .voice import clap as clap_mode
        ctx = create_context(cfg)
        # Acceptance audit P1-2: clap voice tasks run through the SAME kernel
        # as every other surface — before this fix this process ran
        # run_agent with a kernel-less ctx (no capability gate, no receipts,
        # no verification).
        import threading
        ctx.cancel_event = threading.Event()
        from .kernel import AgentKernel
        ctx.kernel = AgentKernel(ctx)
        # engine choice only matters when the clap records a spoken task
        if (cfg.clap.action or "welcome").lower() == "voice":
            from .agent import engines
            engine = engines.ask_engine()
            ctx.model_override = engines.override_for(engine)
            print(f"engine: {engine} (asked once, persisted — change in REPL with /engine)")
        clap_mode.run_clap_mode(ctx)
    elif args.mode == "livekit":
        from .livekit import agent as lk
        room = args.room or (args.rest[0] if args.rest else None)
        sys.exit(lk.run(cfg, room=room))
    elif args.mode == "realtime":
        sys.exit(_realtime(cfg, livekit="livekit" in args.rest,
                           always_on=args.always_on))
    elif args.mode == "speak":
        from .voice import speak
        speak.speak(" ".join(args.rest) or "Hello, I am BEE.", cfg)
    elif args.mode == "consolidate":
        from .agent.context import create_context
        from . import scheduler
        ctx = create_context(cfg)
        print(json.dumps(scheduler.run_nightly(ctx), indent=1, ensure_ascii=False))
    elif args.mode == "eval":
        from .agent.context import create_context
        from .evals import runner
        ctx = create_context(cfg)
        runner.run_suite(ctx)
    return 0


if __name__ == "__main__":
    try:
        _hard_exit(main())
    except SystemExit as e:          # modes that call sys.exit() inside main()
        _hard_exit(e.code)
    except KeyboardInterrupt:        # Ctrl-C at shutdown must still leave
        _hard_exit(130)
