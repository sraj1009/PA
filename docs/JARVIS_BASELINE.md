# BEE / PA — Phase 0 Baseline Audit (2026-10-08)

**Method:** full repository inspection (source tree, deps, config, env handling,
entry points, kernel, loop, routing, providers, tools/ToolBus, commands, memory,
RAG, scheduler, automation, voice, LiveKit, computer control, sandbox, web/API,
security, skills, ML router, telemetry, checkpoints, tests) followed by fresh
suite runs. **No code was changed in this phase** — documentation only.
Every claim below is backed by a file inspected on 2026-10-08 or by a suite
run performed that day. Companion docs: `JARVIS_ARCHITECTURE.md` (how it
works), `JARVIS_ROADMAP.md` (plan/status), `TECHNICAL_DEBT.md` (findings
with file:line — new re-audit IDs N1–N9 appended 2026-10-08).

---

## 1. Test-suite baseline (recorded before any modification)

| Gate | Exact result, 2026-10-08 |
|---|---|
| `python -m pytest tests -q` | **449 passed, 0 failed** in 37.77 s (two consecutive green runs). One earlier run the same day: 448 passed / 1 failed in 56.34 s — the failure was `wait_idle(10)` timing out in an automation-worker test under high system load; it passed in the immediately preceding and following runs. Recorded as a **load-dependent flake** (finding N7), not a code regression. |
| `python -m evals.verify_suite` | **71,914 checks, ALL PASS** — math 10,000 / dsa 38,456 / pii 13,200 / guard 4,204 / router 6,000 / rag 54 |
| Agent e2e (`/eval`, 21 tasks, real local model `bee4b`, via CLI) | **10/21**. PASS: math_basic, math_sieve, shell_echo, memory_write, web_search_tool, route_det_math, route_det_pct, math_repeat_stable ×3, verify_calc_pass, cloud_redaction. FAIL (all `missing substring` except noted): file_roundtrip, file_list_ws, dsa_lis, dsa_gcd_lcm, dsa_sort_check, dsa_graph, memory_read, calculator, plan_complex, rag_gpu_memory, and **guard_blocked** (`expect_guard=blocked but no guard block occurred` — see §5; suspected new behavioral anomaly, not yet root-caused) |
| `python -m bee.cli` core checks | "All core checks passed" (Ollama up, deps ok) per launcher; Ollama models present incl. `bee4b:latest` |

Test inventory: 449 pytest tests across `tests/` (markers auto-assigned by
`tests/conftest.py`: unit / integration / agent / scheduler / security /
e2e). The e2e layer is the 71,914-check verify suite plus the 21-task live
eval (environment-dependent: needs Ollama + `bee4b`).

## 2. Repository layout & entry points

| Path | Role |
|---|---|
| `bee/__main__.py`, `bee/cli.py` | Main entry (`python -m bee.cli [repl|web|livekit|full]`); REPL with slash commands; `full` spawns web + livekit children |
| `bee.py` | Thin root stub (legacy launcher shim) |
| `setup.ps1`, `bee-runfull.ps1`, `start_talk.ps1`, `Makefile` | Windows launchers / task runner |
| `config.yaml` (root) + `config/` | Main config (see `CONFIG_PRECEDENCE.md`) + capabilities example |
| `.env` / `.env.example` | Real secrets (git-ignored) / placeholders only (verified: no values in the example) |
| `models.yaml` | J3 promotion layer (`local_model:` only) |
| `settings.json` | Engine selection (hybrid/local/…) — independent of `Config` |
| `bee/agent/` | Loop (`loop.py` 724 lines), context, routing (`router.py`), fastpaths, engines, providers, client |
| `bee/brain/` | ML router, verifier, RAG, offline rules |
| `bee/kernel/` | AgentKernel, Task/TaskState, sessions, receipts, memory commands, events facade, **ToolBus** (`tools_bus.py`), checkpoints (J1) |
| `bee/security/` | capabilities (20 caps R0–R5, task-scoped grants), risk (regex **+ AST** layer at `risk.py:174`), audit, netguard (SSRF), secretscan |
| `bee/tools/` | 14 tool modules; `tools_by_name()` registry; `cancelable.py` (tree-kill) |
| `bee/automation/` | Durable jobs (store/queue/worker/events facade) — runs through the kernel |
| `bee/monitor/` | metrics (scrubbed), telemetry, dashboard, **rotate (M13)**, **alerts (toasts+thresholds)** |
| `bee/memory/`, `bee/episodes/`, `bee/pipeline/` | Store, diary/longterm, vector search, consolidation, SFT build |
| `bee/voice/` (+`realtime/`), `bee/livekit/` | STT/TTS, 7-state realtime engine, LiveKit agent (kernel-routed) |
| `bee/computeruse/` | 12-verb safe set, verified closed loop, emergency stops |
| `bee/webapp.py`, `bee/web/` | FastAPI: chat (SSE), voice, skills, engine, face, livekit token; bearer auth on stateful endpoints |
| `bee/scheduler.py` | Nightly durable-job registration (9 jobs incl. skill_gate, model_gate) |
| `evals/`, `bee/evals/` | 21-task suite, verify harness, results, **gate.py (J3)**, **skillgate.py (J2)** |
| `sandbox/Dockerfile` | Optional Docker sandbox (workspace jail) |
| `native/` | Go telemetry daemon (127.0.0.1:8790, WMI fallback) |
| `train/` vs `training/` | **Two training roots still coexist** (roadmap M6 — open) |
| `docs/` | 10 documents incl. this baseline |

**CI: none** (no `.github/`). **Docker: optional** (sandbox only; not required
to run BEE). No Dockerfile for the app itself.

## 3. What is implemented (verified)

- **Single agent kernel** (`bee/kernel/kernel.py`): task lifecycle
  CREATED→…→COMPLETED/FAILED/CANCELLED, run-lock serialization, receipts,
  checkpoints (J1), resume (`kernel.resume` / `/resume`).
- **Capability authorization** (`bee/security/capabilities.py`): 20
  capabilities, R0–R5, policies always_allow/ask/task/deny, task-scoped
  grants, pre-execution check in `loop.py:593-604`, untrusted-context
  escalation (post-web-content state-changing asks).
- **Guard** (`bee/guard.py` + `security/risk.py`): regex classifier (pinned
  by 4,204-check suite) + AST risk layer for Python payloads.
- **SSRF protection** (`security/netguard.py` via `tools/web.py`): loopback /
  RFC1918 / link-local / metadata refusal, redirect re-validation, timeouts,
  size cap, content-type allowlist — all in `web_fetch`.
- **Durable automation** (`bee/automation/`): 9 nightly function jobs +
  user jobs, restart recovery, cross-process claims, missed-job handling,
  default-deny proactive rules, all executed through the kernel.
- **All user surfaces kernel-routed** (10-item #1): REPL, web `/chat`,
  web `/voice`, LiveKit worker, eval runner, automation worker.
- **One EventBus** (`bee/events.py`) with two API-preserving facades
  (kernel, automation).
- **M13 rotation/caps** at every JSONL write chokepoint (5MB/2MB caps,
  bounded notifications, nightly `log_rotation` job).
- **J3 model gate** (`bee/evals/gate.py`) + **J2 skill gate**
  (`bee/evals/skillgate.py`), each with a durable nightly job + CLI.
- **M14 config precedence** (`docs/CONFIG_PRECEDENCE.md`, `Config.precedence`,
  12 contract tests).
- **LiveKit HTTP state bridge** (agent pushes bearer-auth POST to the web
  UI; in-memory + `age_s`; temp-JSON file removed).
- **OS alerts** (`monitor/alerts.py`): toast on job failure/miss + daily
  threshold scan with cooldown.
- **PII redaction** (13,200-check suite), episode redaction at write,
  archive-not-delete consolidation, vector rebuild clear-before-add.
- **Voice**: faster-whisper STT, clap wake, edge-tts/pyttsx3, 7-state
  realtime engine, LiveKit transport (12 scenario tests; **LiveKit room
  itself unverified in-field** — no credentials in the test path).
- **Computer use**: 12-verb safe set, per-action verification, action
  budget, 3 emergency stops (**WindowsDesktop unverified in-field** by CI).
- **Secret tooling**: `bee/security/secretscan.py` (scans tree; values
  never printed).

## 4. What is partially implemented

| Area | State | Evidence |
|---|---|---|
| **ToolBus as THE execution path** (program Phase 2) | **PARTIAL — exists but is not the authoritative dispatcher.** `bee/kernel/tools_bus.py` defines `ToolDef` (name, description, schema, handler, risk, capability, timeout, cancellation, verify) and `ToolBus.call()` with `UnknownToolError`/`MalformedArgsError`; the kernel builds one (`kernel.py:60`). **But the LLM's tool calls are executed in `agent/loop.py` via the raw `tools_by_name()` dict (`loop.py:427` registry, `:627` `registry[tname](ctx, **args)`, fastpath `:268`) — the bus is not in that path.** Phase 2 migration is open. | `kernel/tools_bus.py` (139 lines), `agent/loop.py:427,593-643,627` |
| **ToolBus timeout enforcement** | `ToolBus.call()` accepts `timeout` but **enforces nothing** — `meta["timed_out"]` is always `False`; no timer thread. Tool-level timeouts exist only where the tool implements them (e.g. `run_cancelable`). | `tools_bus.py:105-135` |
| **Capability `from_default()` mapping** | Captures only the FIRST capability per tool (`caps[0]`, `tools_bus.py:83`) while the gate uses the full `capabilities_for()` list. Latent under-mapping if the bus becomes authoritative. | `tools_bus.py:77-88` |
| **Task-scoped cancellation** (program Phase 4) | Cancellation is **context-scoped, not task-owned**: `kernel.cancel()` sets `ctx.cancel_event` (`kernel.py:96-102`) and nothing in the kernel clears/replaces it per task. Today every entry point that can cancel also clears it (REPL `cli.py:428,431,482`; eval runner `evals/runner.py:136`; automation uses job-scoped events), so no live leak — but the web process shares one kernel/ctx and there is no `/cancel` endpoint yet (`webapp.py`: no cancel route — verified by grep); a future web cancel would leak into the next web task. Structural fix (task-owned event) is open. | `kernel/kernel.py:96-102` (only two references to `cancel_event`), `cli.py:428-482`, `webapp.py` (no `/cancel`) |
| **Prompt-injection boundary** | Tool-level + untrusted-context escalation done; **no content-level injection filter** — untrusted text can still shape reply content (documented residual). | `loop.py:653-671`, `capabilities.py::_check_one` |
| **Memory consolidation / R6** | `scheduler.py:110` fixed (explicit `train_router.main(min_samples=10)` — no argv mutation); **`livekit/agent.py:307-314` still mutates/restores `sys.argv`** around LiveKit's Typer re-parse. | both files, verified |
| **eval_safe limits (R7)** | `tools/base.py:199` uses `ast.parse` allowlist but **no depth/size/time budget** — DoS surface remains (documented). | `tools/base.py`, `tools/calculator.py` |
| **Roadmap M5 (single Context factory)** | 3 bootstrap sites still duplicate context creation (`cli._repl`, `webapp.get_ctx`, `livekit._build_brain`). | as listed |
| **Roadmap M15 (root cleanup)** | Stray scratch at repo root: `eval_batch.py`, `eval_resume.py`, `open_grok.py`, `smoke_jarvis.py`, `run_eval_E.ps1`, `run_eval_resume.ps1`, `start_talk.ps1`, `grok_result.png`, `bee.py` stub. | root listing 2026-10-08 |

## 5. What is broken / degraded (verified 2026-10-08)

1. **`guard_blocked` eval task fails** (`expect_guard=blocked but no guard
   block occurred`). In the same run, the log shows many repeated
   `capability:automation.manage allow? [y/N]` prompts fired *inside*
   unrelated eval tasks, with tool budgets burned (file_roundtrip tools=12,
   memory_read tools=13, web_search tools=12). Suspected mechanism: the
   `/eval` path in the REPL reuses the REPL kernel whose approver prompts on
   stdin; the small model emits `automation_job` calls that get denied
   fail-closed, consuming the iteration budget before the task's real tool
   (and for guard_blocked, before the dangerous command the guard must
   block). **Not yet root-caused; treat as a blocking structural-regression
   candidate.** The 4,204-check guard suite still ALL PASS, so the guard
   classifier itself is intact.
2. **Load-dependent flake** in one automation-worker test (`wait_idle(10)`
   timeout under heavy system load; green otherwise). N7.

## 6. What is only documented (not implemented)

- **Message-level resume** — J1 is task-level (checkpoint + re-run with
  pre-crash observations); exact mid-message continuation is not claimed.
- **Content-level prompt-injection filtering** — see §4.
- **Proactive sources** beyond timer/calendar/file_change (email/app/battery/
  network/device_state are schema-supported but "unavailable" — honest
  placeholder, documented in architecture §18).
- **ICS-only calendar triggers** (no live calendar provider).
- **Sandbox as default** — Docker sandbox is optional; the primary
  `code_run`/`shell` paths run host-local under guard+capability.

## 7. What is unsafe (security findings, file:line)

| ID | Finding | Location |
|---|---|---|
| **N1 (CRITICAL)** | **`/guard off` bypasses the capability gate.** The REPL command sets `ctx.guard_on = False` (`cli.py:436`) and the loop's capability-gate check is gated on the same flag: `if … ctx.capability_gate … and ctx.guard_on:` (`loop.py:593`). Disabling the legacy regex guard therefore **also disables capability authorization** — exactly the rule the program forbids ("`/guard off` must NEVER bypass capability authorization"). Note the guard itself is only consulted for `EXEC_TOOLS` (`loop.py:605`); non-exec tools never needed it — the coupling should be severed, and the capability gate should be mandatory and not chat-toggleable. | `bee/cli.py:434-437`, `bee/agent/loop.py:593,605` |
| **N2 (HIGH)** | Direct tool dispatch via `tools_by_name()` in the main loop and fastpaths bypasses the ToolBus (validation/timeout/audit ownership duplicated in the loop). Phase 2 migration open. | `loop.py:268,427,627` |
| **N3 (HIGH)** | `ToolBus.call()` does not enforce timeouts (`timed_out` hardcoded False) — "timeout terminates execution" is not yet true for bus-routed calls. | `tools_bus.py:105-135` |
| **N4 (HIGH, latent)** | Cancel event is context-scoped; safe today only because each entry point clears it. No task-owned token; web has no cancel route. | `kernel.py:96-102`, `webapp.py` |
| **N5 (MEDIUM)** | `.gitignore` gaps for runtime memory artifacts: `memory/receipts.jsonl`, `memory/sessions/`, `memory/store.json`, `memory/checkpoints/` are untracked AND not ignored → accidental commit of personal data possible (visible in `git status` 2026-10-08). | `.gitignore:18-23` (only diary/lessons/vectors/profile/longterm ignored) |
| **N6 (MEDIUM)** | Eval budget anomaly (see §5.1) — an eval regression candidate that must not be normalized. | eval run 2026-10-08 |
| **Credential exposure history** | `.env` (LiveKit keys, cloud keys) has lived in a OneDrive-synced directory; git history is clean (no secrets committed — verified: `config.yaml` has **no** `cloud.api_key` value, `.env` is ignored, `.env.example` placeholders only), but the synced-file history makes previously stored credentials **treat as compromised → rotate** (documented in `.env.example` header and `docs/SECURITY.md`). Operator action required: rotate LiveKit API key/secret and any cloud key that existed in `.env`. | `.gitignore:13-16`, `.env.example`, root `git ls-files` check |
| **R4 sandbox mount** (carry-over) | `sandbox/Dockerfile` workspace mount exposure of `.env` — verify the mount path excludes `.env` before any sandbox use. | `sandbox/Dockerfile` |

Safe-by-construction (verified, unchanged): web bearer auth on all stateful
endpoints incl. the new `/livekit/state`; unattended surfaces fail closed;
PII redaction chokepoint in metrics/audit; SSRF policy in `web_fetch`;
capability denies have no side effect (blocked before dispatch).

## 8. What is environment-specific

| Aspect | Assumption |
|---|---|
| LLM | Ollama at `localhost:11434` with local model `bee4b` (SFT, 8 GB VRAM, `num_ctx=8192`); cloud optional via provider-matched env keys; **offline deterministic mode** keeps the assistant useful without either (verified path: `_offline_result`) |
| OS | Windows-first: `taskkill /F /T` (with `killpg` fallback), `msg.com` toasts (with `osascript`/`notify-send` fallbacks), PowerShell launchers, SAPI TTS fallback — all platform-guarded; POSIX paths exist but are untested in-field |
| Voice uploads | `ffmpeg` required for non-WAV (checked at runtime, 501 otherwise) |
| Sandbox | Docker optional |
| Timezone | Client `Asia/Calcutta`; nightly jobs use the configured tz |
| Tests | pytest suite is environment-independent (fakes/injected clocks); the 21-task e2e eval and `setup.ps1` checks require Ollama + model + (optionally) LiveKit credentials |

## 9. Docs that contradict or lag implementation (2026-10-08)

- `docs/llm-component.md` — pre-`bee4b` pipeline (known-stale, architecture §19).
- `evals/REPORT.md` — regenerated per eval run; agent section lags by one run.
- `JARVIS_ROADMAP.md` §0 status table — pre-10-item-batch (updated today).
- `TECHNICAL_DEBT.md` summary counts — pre-10-item-batch (updated today).
- `loop.py` header comment "Phase 2: …" — historical, harmless.
- **New (today):** architecture §19 list now includes `tools_bus.py`'s
  unenforced-timeout docstring claim ("single dispatch point") vs reality
  (loop.py direct dispatch) — N2.

## 10. Working-tree state at audit time

- Last commit: `14d0721` (production-hardening audit).
- **Uncommitted: the entire 10-item final-hardening batch** — 27 modified
  files + new `bee/evals/gate.py`, `bee/evals/skillgate.py`, `bee/events.py`,
  `bee/monitor/alerts.py`, `bee/monitor/rotate.py`, `bee/tools/cancelable.py`,
  `docs/CONFIG_PRECEDENCE.md`, 5 new test files (449-test suite includes
  them). Recommended first action of Phase 1: commit this batch (after
  N1–N6 triage decisions), so subsequent security work builds on a clean,
  tested baseline.
- Untracked runtime artifacts present (N5): `memory/receipts.jsonl`,
  `memory/sessions/`, `memory/store.json`.

---

*Baseline recorded 2026-10-08. No functionality changed in this phase.*
