# BEE / Jarvis — Production Readiness Audit

**Date:** 2026-10-06 (end of hardening audit + final 10-item batch)
**Method:** full-code audit across architecture / security / reliability / agent
quality / voice / computer use / observability / testing, with every status
backed by a file:line reference, a passing test, or an explicit non-claim.
No marketing language: RED is RED even when the rest is GREEN.

**Verdict (one line):** BEE is a coherent, well-tested, single-user personal
agent runtime that is **NOT production-ready** — it is at a strong
"personal deployment" level: every user surface now runs through one
capability-gated kernel, logs are capped, failures alert, crashes are
resumable, and model/skill upgrades are gate-controlled — but end-to-end task
success is still capped at 8–13/21 by the local 3B model (the J3 quality gate
is the mechanism that closes this, once a better candidate model exists), and
two integrations remain unverified in-field (LiveKit room, real display).

**Gate results at this commit:**

| Gate | Result |
|---|---|
| `python -m pytest tests -q` | **449 passed, 0 failed** (38s) |
| `python -m evals.verify_suite` | **71,914 checks, ALL PASS** (math 10,000 / dsa 38,456 / pii 13,200 / guard 4,204 / router 6,000 / rag 54) |
| Agent e2e (21 tasks, real local model) | **EVAL_PENDING** — band 8–13 across runs; failures = model "missing substring" ceiling, not loop bugs |

**Final 10-item hardening batch (all delivered, all test-pinned):**

1. **Gate gap closed** — the three legacy `run_agent`-direct surfaces
   (`webapp /voice`, `livekit/agent.py` worker, `bee/evals` runner) now run
   through the SAME `AgentKernel` (capability gate, receipts, verification,
   telemetry). No surface bypasses the gate anymore.
2. **M13 closed** — every JSONL stream is size-capped with rotation at its
   write chokepoint (`monitor/rotate.py`): metrics 5MB/2, audit 2MB/2,
   receipts 2MB/2, episodes 5MB/1, executions 2MB/2 (history reads span
   backups); notifications capped at 500. Nightly `log_rotation` job.
3. **J1 closed** — cancel/timeout now KILLS the subprocess tree
   (`tools/cancelable.py`: `taskkill /F /T` on Windows, `killpg` elsewhere) —
   a hung subprocess can no longer outlive its task; and tasks checkpoint
   observations after every tool result, cleared only on a terminal state —
   a crash mid-task leaves a resumable checkpoint (`kernel.resume`,
   `/resume [id]`). Documented limit: resume re-runs the task with pre-crash
   observations attached (task-level, not message-level).
4. **J3 delivered** — `bee/evals/gate.py`: a candidate local model is
   promoted (via `models.yaml`, its own documented config layer) only when
   eval score ≥ baseline + margin AND no structurally-stable task regressed;
   first run seeds the baseline; `/gate show|baseline|run|rollback`; nightly
   durable job `model_gate`.
5. **Untrusted-context isolation** — after an `untrusted_output` tool
   (web fetch/search) returns content, the model view is sentinel-wrapped,
   task-scoped grants issued before ingestion are revoked, and any
   state-changing capability (R2+) the model proposes is escalated to an
   explicit ask (`capabilities.py::_check_one`, `untrusted_context`).
   Residual (documented): untrusted text can still influence the *content*
   of a reply — it can no longer silently trigger actions.
6. **Alerting delivered** — OS-level toasts (`monitor/alerts.py`,
   `msg.com`/`osascript`/`notify-send`) on job failure/miss + daily
   `alert_scan` threshold job (provider fail rate, verify fail rate,
   permission denials, metrics size) with per-key cooldown; all toasts
   redacted + truncated.
7. **J2 delivered** — skills are versioned (`skills/<name>/meta.json`);
   every create/update/teach-back bumps the version and marks the skill
   **candidate** (hidden from the prompt); the nightly `skill_gate` job
   (and `/skillgate`) runs a structural check + a bounded eval probe
   (structural tasks re-run with the skill force-included; no regression
   allowed) before a skill ships as **active**.
8. **M14 delivered** — `docs/CONFIG_PRECEDENCE.md` + `Config.precedence`
   (inspectable via `/config`) + 12 contract tests pinning the full
   process-env > .env > models.yaml > config.yaml > defaults matrix, the
   `cloud.api_key` exception, and workspace-from-.env (a real ordering bug
   found and fixed: `BEE_WORKSPACE` in `.env` was previously never applied).
   Also fixed: the `computeruse` section was never loaded from config.yaml.
9. **One EventBus** — `bee/events.py` is the single implementation; the
   kernel and automation buses are thin API-preserving facades (4 tests pin
   both APIs over one implementation, contained handler exceptions, bounded
   log, subscription order/dedupe).
10. **LiveKit temp-JSON bridge replaced** — the agent process now PUSHES
    state over loopback HTTP to the web UI (`POST /livekit/state`, bearer
    auth; port via `BEE_WEB_PORT`); the web UI holds it in memory with
    `age_s` liveness. No file, no stale-snapshot race, nothing survives a
    webapp restart (a dead agent can no longer masquerade as live).

Changes made during this audit (all covered by tests):

1. Metrics stream now **redacts every string value at the write chokepoint**
   (`monitor/metrics.py::_scrub`) — secrets/content cannot reach
   `metrics.jsonl` (previously raw task text and error strings were written).
2. **Structured telemetry** added: per-LLM-call latency + provider failure
   kind (`llm` events), terminal task rows with success/retries/verification/
   task latency (`agent_task`), and every permission requested/granted/denied
   with capability + risk (`permission`); `stats()` now reports agent success
   rate, avg task/LLM latency, provider failures, permission denials.
3. **B2/M12 closed**: vector `rebuild()` is clear-before-add (was append —
   duplicate rows grew every 12h); regression test proves stable row count.
4. Web process now runs `guard_mode="unattended"` — a guard "ask" can no
   longer call `input()` from a web worker thread (hung worker / stolen
   keypress hazard).
5. Automation execution previews + notifications are redacted before
   persistence (`automation/worker.py::_redact`).
6. **Test pyramid**: 8 auto-assigned markers in `tests/conftest.py`
   (unit/integration/security/agent/tools/voice/scheduler/e2e).

---

## 1. Architecture

| Item | Status | Evidence / limitation |
|---|---|---|
| Single executor (kernel) | **GREEN** | REPL, web `/chat`, web `/voice`, realtime voice, the LiveKit worker, the eval runner, and scheduled jobs ALL run through one `AgentKernel` instance per process (kernel run-lock serializes executions). No `run_agent`-direct surface remains (10-item #1). `cli.py::_repl`, `webapp.py::chat`+`voice`, `livekit/agent.py`, `evals/runner.py`, `voice/realtime/engine.py`, `automation/worker.py` |
| Tool registry | **GREEN** | `tools_bus.py` + `tools/__init__.py`: every tool a typed `T` definition (name, schema, risk, capabilities); unknown names raise; arbitrary callables cannot be registered |
| Duplicated agent logic | **GREEN** | Closed by 10-item #1: the three legacy `run_agent`-direct call sites (web `/voice`, LiveKit worker, eval runner) now use `kernel.run` with the same gates/state/receipts as interactive chat. Eval sessions are isolated per task/rep |
| Global state | **YELLOW** | Known, documented globals: `paths.py` module paths, `engines.py` active-engine state, `webapp.CTX`, `memory/search._cache`, `computeruse` global stop flag, `automation` per-process worker. Single-user, single-process-per-store by design; `bee-runfull` child processes share the store safely via file claims. Not a service architecture — multi-user is out of scope |
| Circular dependencies | **GREEN** | Verified import edges: `automation.worker → scheduler` and `scheduler → automation` are function-level lazy imports; `tools → computeruse/automation` are lazy builders; kernel never imports voice/livekit/scheduler |
| Provider coupling | **GREEN** | `agent/providers.py` registry (ProviderRegistry/Config/Health); `client.py` is the only file talking to wire protocols; adding a provider = one adapter + one config entry |
| Inconsistent interfaces | **GREEN** | 10-item #9: ONE `EventBus` implementation (`bee/events.py`); kernel and automation buses are thin API-preserving facades (existing call sites/tests unchanged). Guard/capability/risk remain three deliberate layers (documented), not inconsistency |
| Configuration | **GREEN** | 10-item #8 (M14): single-source precedence documented (`docs/CONFIG_PRECEDENCE.md`) and contract-pinned (12 tests) — process-env > .env > models.yaml > config.yaml > defaults, with the `cloud.api_key` exception documented; `Config.precedence` reports the winner per field (`/config`) |

## 2. Security

| Item | Status | Evidence / limitation |
|---|---|---|
| Secrets | **GREEN** | `.env` git-ignored (Phase 0); `test_secretscan.py` pins the tree free of committed keys; web token never logged, constant-time compare; receipts/audit/execution-history/metrics all redacted (this audit closed the last two gaps); cloud payloads redacted (13,200 pii checks 100%) |
| SSRF | **GREEN** | `brain/netguard.py` allow/deny for URL fetches; 19 cases pinned in verify suite; web tool routes through it |
| Command execution | **GREEN** | Two independent layers: `guard.classify` (pinned regex table) + `security/risk.py` AST classifier for Python payloads (closes R2: `shutil.rmtree`/`os.remove`/`Path.unlink` now ask/deny); `eval_safe` has depth/node/time limits (R7 closed); 4,204 guard checks 100% |
| Sandbox | **YELLOW** | Docker sandbox exists with workspace jail and (since Phase 1) no `.env` mount; **optional** — when Docker is absent, `shell`/`code_run` execute on the host guarded only by the two layers above. Default host-exec is a deliberate local-PA tradeoff, documented in the tool descriptions |
| File access | **GREEN** | `tools/files.py` workspace jail (139 lines, path normalization + escape checks); sandbox mounts a secrets-free subpath |
| Prompt injection | **YELLOW (hardened)** | Tool-level + untrusted-context isolation (10-item #5): web fetch/search output is sentinel-wrapped, pre-ingestion task grants are revoked, and any state-changing capability (R2+) proposed immediately after ingesting untrusted content is escalated to an explicit ask. Unattended surfaces auto-deny. **Residual (documented, accepted):** untrusted text can still influence the *writings* of a reply; there is no content-level injection filter (that would need an LLM-in-the-loop or a strict allowlist) |
| Tool injection | **GREEN** | Tools cannot be registered at runtime from the model; registry is code-defined; the `automation_job` tool (closest thing to dynamic behavior) is capability-gated (R3 ASK) and its actions are a closed structured set (agent_task/notify/registered-function) |
| Permissions | **GREEN** | 20 capabilities R0–R5, pre-execution gate, task-scoped grants that die with the task, unattended fail-closed everywhere (web, jobs, livekit guard mode); `test_capabilities.py` + in-job fail-closed test |
| Authentication | **YELLOW** | Web: single bearer token (env-fixed or generated), loopback bind only — adequate for a personal machine, **not** for exposure beyond 127.0.0.1. No account system by design (single user) |
| Authorization | **GREEN** | capability gate (kind of action) over guard (this specific command) over sandbox (containment) — three independent layers, strictest wins |
| Logs | **GREEN** | This audit: every string written to the metrics stream is redacted at the chokepoint; receipts/audit/job-history redacted; voice path logs no audio; computer-use logs no pixels/titles/typed text (lengths only) |
| Sensitive data retention | **GREEN** | 10-item #2 (M13 closed): every JSONL stream is size-capped with rotation at its write chokepoint — metrics 5MB/2, audit 2MB/2, receipts 2MB/2, episodes 5MB/1, executions 2MB/2 (history reads span the backups), notifications capped at 500. Episodes redacted at write (R5), diaries archived-not-deleted (R1). Golden teach-back retains successful cloud answers verbatim (intentional local-only training data) |
| LiveKit state | **GREEN** | 10-item #10 (R8 closed): worker↔web state is now a loopback HTTP **push** to the web UI (`POST /livekit/state`, bearer auth) held in memory with `age_s` liveness — no temp file, no stale-snapshot race, nothing survives a webapp restart |

## 3. Reliability

| Item | Status | Evidence / limitation |
|---|---|---|
| Retries | **GREEN** | Kernel `RetryPolicy` (max 2, bounded, never on permission denial, never after a destructive action, correction note injected); job retry with backoff + budget (crash-repair honors it); provider-failure de/escalation in loop |
| Timeouts | **GREEN** | LLM chat 120s local / 300s cloud, embed 60s, availability probes 3–6s (`client.py`); job `max_runtime` watchdog; computer-use per-action timeout (10s); web SSE 120s stall timeout; ffmpeg 60s |
| Cancellation | **GREEN** | `kernel.cancel()` first-class; Ctrl-C in REPL; voice barge-in cancels task + stops TTS same frame; job watchdog cancels the **job only** (job-scoped event, user work never cancelled — verified by test); granularity is between iterations / before each tool call |
| Crash recovery | **GREEN** | Jobs: execution-row-before-start + file claims + crash repair + missed-job handling (27 tests incl. restart). Sessions: persisted after every task. Vector store: keyword fallback. Nothing depends on in-memory-only state for correctness |
| Scheduler recovery | **GREEN** | Phase 6: restart restores jobs, recomputes next_run, never no-ops, prevents duplicates (two levels). Verified by restart-recovery tests |
| Provider failure | **GREEN** | `LLMError` taxonomy (auth/quota/network/timeout/overloaded/model_not_found); local↔cloud↔offline deterministic chain; now observable per-call (llm telemetry with error_kind) |
| Tool failure | **GREEN** | fail_streak breaker (2 consecutive), repeat-call guard, circuit breaker on dead endpoints (3rd identical call blocked), observations record `blocked` vs failed |
| Verification failure | **GREEN** | bounded one fix round in-loop; kernel verify with retry + correction note; a clean tool return is NEVER reported as verified success (unverified ≠ pass) |
| Partial completion | **GREEN** | 10-item #3 (J1 closed): task state distinguishes COMPLETED/FAILED/CANCELLED with verification reported separately, AND tasks now checkpoint observations after every tool result (cleared only on a terminal state). A crash mid-task leaves a resumable checkpoint — `kernel.resume` / `/resume [id]` re-runs the task with the pre-crash observations attached. Documented limit: resume is task-level (re-runs from the checkpoint), not message-level |
| Mid-subprocess kill | **GREEN** | 10-item #3: `shell`/`code_run` run via `tools/cancelable.py`, which KILLS the whole process tree on cancel/timeout (`taskkill /F /T` on Windows, `killpg` elsewhere) — a hung subprocess can no longer outlive its task. Return kinds distinguish ok / timeout(124) / cancelled(130) |

## 4. Agent quality

| Item | Status | Evidence / limitation |
|---|---|---|
| Task state | **GREEN** | 11-state machine with an explicit transition table; illegal transitions raise (fail closed) |
| Planning | **GREEN** | Kernel builds the execute+verify plan; the LLM proposes tool actions inside one execution step (single-executor plan, documented). 10-item #3 adds per-tool-result checkpoints with task-level resume (J1) |
| Memory | **YELLOW** | Structured store (remember/recall/update/forget/summarize/expire + provenance) is flat JSON with keyword scoring — not vector, not graph; RAG is LanceDB + keyword RRF (rebuild now duplicate-free, B2 closed) |
| Context | **GREEN** | Session persistence + follow-up resolution ("Tomorrow.", "Actually make it 10 AM", "stop.") verified; RAG auto-context for reference tasks |
| Tool selection | **GREEN** | 536-line deterministic fastpaths + ML router (CV 0.9975 on 408 episodes) with complexity floor; 6,000 router checks 100%; fastpaths bypass the LLM entirely for known intents |
| Verification | **GREEN** | Deterministic effect checks (file exists / replacement present / target probe) + answer verifier with bounded fix round; "unverified" is an honest verdict |
| Hallucinated success | **GREEN (structurally)** | The kernel reports verification separately from model output; uncheckable work is "unverified", never "pass". Residual: the *target probe* is heuristic (name-based) — it can pass a wrong-but-plausible effect, documented as a limitation, not a defect |
| Follow-up understanding | **YELLOW** | Deterministic follow-up resolution for time/cancel/continuation patterns; free-form coreference ("the other one") depends on the 3B model — quality-ceiling, not loop |
| End-to-end success | **YELLOW** | **8–13/21** across runs (11/21 this audit). Failing tasks are local-3B "missing substring" (file roundtrips, DSA edge cases, memory recall, complex plans). This is a model-quality ceiling, stable structurally across 7+ runs; it is the single biggest gap between "reliable runtime" and "reliable assistant" |

## 5. Voice

| Item | Status | Evidence / limitation |
|---|---|---|
| Interruption (barge-in) | **GREEN** | Sustained speech during SPEAKING/THINKING with 2× echo gate → TTS stop + kernel cancel in the same frame; tested |
| Streaming | **GREEN** | Genuine 3-layer streaming: windowed re-transcription partials (faster-whisper is batch — honest interim, not token-level ASR), LLM `chat_stream` tokens through the kernel bridge, sentence-pipelined edge-tts chunks. Web `/chat` real SSE (tokens precede result in the byte stream, verified) |
| Cancellation | **GREEN** | "stop." resolved at the kernel (CANCELLED task); barge-in cancels the active task |
| Reconnect | **GREEN** | Capped exponential backoff; backoff resets only on a real audio frame; mic dying every reconnect terminates at `max_reconnect_attempts` (tested, connects==2 case) |
| Session continuity | **GREEN** | Voice turns run through the kernel with a voice session id — follow-ups continue the same AgentSession |
| State machine | **GREEN** | 7 states (IDLE/LISTENING/PROCESSING/THINKING/SPEAKING/INTERRUPTED/ERROR) with illegal-transition checks; 12 tests incl. all 9 required scenarios |
| Naturalness | **YELLOW (not claimed)** | Energy VAD (not neural), STT-confirmed wake word (not always-on DSP). Explicitly NOT claimed human-level |
| LiveKit path | **YELLOW** | `LiveKitTransport` implements the `VoiceTransport` contract but is **unverified against a live room** (no credentials in the test path); the verified transport is the local mic. The legacy LiveKit *worker* (`livekit/agent.py`) still bypasses the kernel entirely |

## 6. Computer use

| Item | Status | Evidence / limitation |
|---|---|---|
| Action limits | **GREEN** | 12-verb safe set only (screenshot/inspect/open/focus/click/double-click/type/key/scroll/switch/copy/paste) — the unsafe verbs (deletion, financial, credential entry, downloads, destructive) **do not exist**; per-task budget 15 actions; per-action timeout 10s |
| Verification | **GREEN** | Every action carries target + coords + description + expected result + verification strategy; closed loop (one tool call = act→observe→verify); structural checks (window_exists/active_window/screen_changed/clipboard compare); coordinates with unproven provenance are refused, model-raw coords escalate to ASK |
| Emergency stop | **GREEN** | Three independent stops: `kernel.cancel()`, global `computeruse_emergency_stop()`, and a system-wide Ctrl+Alt+Q hotkey — any one halts all computer-use actions |
| Permission enforcement | **GREEN** | 4 new capabilities (desktop.observe/launch/control/clipboard; launch & control ASK) checked pre-execution by the same gate as everything else; unattended surfaces auto-deny |
| Privacy | **GREEN** | Typed text: length only. Clipboard: compare-only. No pixels/window titles in logs. Screenshots: in-memory hash ring, 5-min retention, disk save off by default |
| Real-desktop coverage | **YELLOW** | All 12 tests run on `MockDesktop`; `WindowsDesktop` is a thin Win32 layer **untested-in-field by CI (no display in the test path)**. UI understanding is structural (titles/classes/rects), NOT vision-model pixel reading. `screen_changed` proves change, not correct change |
| Platform | **YELLOW** | Windows 10/11 only; Linux/macOS return a clean `DesktopError` |

## 7. Observability

| Item | Status | Evidence / limitation |
|---|---|---|
| Task latency | **GREEN** | `task` events (loop) + `agent_task` terminal rows (kernel): per-task seconds, terminal state, verification verdict, retry count |
| LLM latency | **GREEN** | `llm` events per call: model, seconds, stream flag, tokens, ok, `error_kind` (added this audit) |
| Tool latency | **GREEN** | `tool` events: name, ok, seconds (both fastpath and agent paths) |
| Retries | **GREEN** | `agent_task.retried` (kernel level) + job attempt rows in `automation/executions.jsonl` |
| Task success | **GREEN** | `stats()`: success_rate, agent_success_rate, escalations |
| Verification failures | **GREEN** | `verify` events (in-loop) + `agent_task.verification` + `agent_verify_fail` aggregate; kernel receipts carry per-tool verification |
| Permission denials | **GREEN** | `guard` events (command layer) + `permission` events (capability layer, requested/granted/denied with capability + risk) + `permission_denied` aggregate |
| Provider failures | **GREEN** | `llm` ok=False rows with `error_kind`; `provider_failures` aggregate in `stats()` |
| Dashboards | **GREEN** | `monitor/health.py` (endpoint), `monitor/dashboard.py` (HTML), Go native telemetry daemon (127.0.0.1:8790) |
| No sensitive content in telemetry | **GREEN** | Single chokepoint redaction (`_scrub`) — structurally, no new call site can leak; kernel telemetry receives only ids/enums/durations |
| Retention | **YELLOW** | `metrics.jsonl` and episode/diary files have **no rotation or size caps (M13)** — long-running installs grow unbounded; the Go daemon's metrics history is capped, the JSONL streams are not |
| Alerting | **RED** | There is no alerting. Failures are observable in files/endpoints but nothing pings the user proactively beyond in-app notifications (jobs notify in the store; there is no OS-level notification path) |

## 8. Testing

**Pyramid (405 tests, markers auto-assigned by `tests/conftest.py`):**

| Layer | Tests | Select | Contents |
|---|---|---|---|
| unit | 161 | `pytest -m unit` | guard.classify, risk AST, privacy, netguard, fastpaths, verifier, mlrouter, router tiers, kernel state machine, DSA references, capability metadata, offline rules, secret scan, audit |
| integration | 115 | `pytest -m integration` | kernel+loop with scripted LLM, episodes, RAG, pipeline, sandbox, webapp TestClient, livekit config, structured memory, SFT build, automation store/worker |
| security | 92 | `pytest -m security` | guard, risk, capabilities, privacy, netguard, secret scan, web auth, sandbox jail, audit log |
| agent | 177 | `pytest -m agent` | full task lifecycle, follow-ups, routing, commands, automation agent_task e2e through the real kernel |
| tools | 50 | `pytest -m tools` | automation_job, automate, extractor, sandbox contracts |
| voice | 22 | `pytest -m voice` | realtime engine (state machine, VAD, barge-in, reconnect, all 9 required scenarios), STT device probe, livekit config |
| scheduler | 37 | `pytest -m scheduler` | triggers (incl. ICS), restart recovery ×4, missed jobs ×3, crash repair ×2, retry/backoff, concurrency, max_runtime, proactive policy |
| e2e | 115 | `pytest -m e2e` | real kernel / run_agent / web TestClient end-to-end with scripted stand-ins (no Ollama, no network, no display) |

Files may sit in multiple layers (e.g. `test_automation` is integration +
agent + tools + scheduler + e2e). Run everything: `python -m pytest tests -q`.

**Deterministic verification:** `evals/verify_suite.py` — 71,914 checks,
Wilson 95% CIs, ALL PASS at this commit. The guard suite (4,204) and
`test_guard.py` pin `guard.classify` (pure regex) byte-for-byte behavior.

**End-to-end:** `evals/tasks.yaml` (21 tasks) through the real local model —
history in `evals/results.jsonl`. This audit: 11/21 (concurrent run 8/21).
**Every failure in the band is documented as model-quality ("missing
substring" on file/DSA/memory/plan tasks), not a loop defect** — the
structural tasks (deterministic routing, guard block, cloud redaction, math
stability ×3) pass in every run. No test was weakened in this audit; the two
test corrections made were expectation errors in *new* tests (wrong IST
conversion, wrong retry semantics), both fixed toward the stricter,
correct expectation.

**Environment-specific, documented (not failures):**
- `WindowsDesktop` computer-use: no display in CI → verified on
  `MockDesktop` only.
- `LiveKitTransport`: no LiveKit credentials in the test path → verified
  against `NullTransport`/`FakeTTS` only.
- Eval band 8–13/21: depends on the local `bee4b` model on this RTX 3050
  machine; the harness is deterministic, the model is not.

---

## 9. Deployment requirements

**Target:** single-user Windows 10/11 personal machine (by design — no
multi-user, no network exposure).

- **OS/runtime:** Windows 10/11 x64; Python 3.11+; PowerShell 5.1+
- **Core:** `pip install -r requirements.txt` (FastAPI/uvicorn, litellm,
  pydantic, etc.)
- **Local model (recommended, offline-capable):** Ollama + `bee4b`
  (Qwen3-8B fine-tune, `num_ctx=8192` pinned for 8GB VRAM); nomic-embed-text
  for RAG embeddings. Without Ollama: cloud or offline-deterministic mode
- **Voice (optional):** `pip install -r requirements-voice.txt`
  (faster-whisper, edge-tts, pyttsx3) + ffmpeg on PATH
- **Computer use (optional):** `pip install -r requirements-desktop.txt`
  (pyautogui, pynput, mss)
- **Sandbox (optional):** Docker Desktop; when absent, exec tools run on the
  host under the guard+AST layers (documented risk)
- **Cloud (optional):** `.env` with provider keys (Gemini etc.) — never
  committed; `.gitignore` covers it. **Caution: this project lives in a
  OneDrive-synced folder — the .env syncs to the Microsoft tenant; keep
  cloud keys minimal or move the project out of OneDrive**
- **Network:** loopback only (web binds 127.0.0.1; Go daemon 127.0.0.1:8790)
- **Disk:** `models/` (STT weights ~1GB+), LanceDB store, episodes/train
  data; all under the workspace
- **Startup:** `python -m bee.cli` (REPL) · `python -m bee.cli web` ·
  `python -m bee.cli full` (web + livekit children + REPL)

## 10. Operational runbook

**Start/stop**
- `python -m bee.cli` — interactive REPL; `python -m bee.cli full` —
  everything. Stop: `Ctrl-C` cancels the running task; again exits.
  `bee-runfull` tears down children.
- Web token: printed once at startup, stored in `temp/web_token.txt`
  (git-ignored). Fixed token: `BEE_WEB_TOKEN` in `.env`.

**Day to day**
- Engine: web UI switcher or `settings.json` (`local` / `cloud` / `hybrid` /
  `offline`). `/engine` in REPL.
- Jobs: `/jobs` · `/job <id> disable|enable|cancel|delete|history` ·
  `/auto` (unread notifications + proactive rules) · `/auto read`.
  Or just ask: "create a job that …" (BEE asks your authorization first).
- Nightly maintenance (03:00 default, durable jobs): consolidate → 03:30
  router retrain → 04:00 teach-back → 04:15 SFT build; vector rebuild every
  12h. Disable: `/job nightly_consolidate disable`.

**Incidents**
- *Guard keeps denying a legitimate command* → inspect
  `memory/audit.jsonl` (redacted, decision + reason); the reason string
  names the rule. For exec tools the AST layer is the stricter one.
- *Cloud 429/quota* → loop de-escalates to local automatically; `llm`
  metrics rows show `error_kind=rate_limit`. No action needed.
- *Local model down* → tasks escalate to cloud, or go offline-deterministic
  (`/engine offline` works with zero network).
- *Stuck task* → `stop` / `cancel` in REPL (kernel cancel), web: start a
  new session. A hung *subprocess* cannot be killed mid-run (documented
  limit) — worst case: restart the app; jobs recover on restart.
- *Computer use misbehaving* → **Ctrl+Alt+Q** (global hotkey), `/stop`
  (kernel cancel), or `computeruse_emergency_stop()` — any one halts all
  desktop actions.
- *Suspicious automation* → `/jobs`, disable the job, `/job <id> history`
  shows every attempt with redacted error/preview.

**Observability**
- `GET /health` (open) — liveness + models + voice availability
- `monitor/dashboard.py` — HTML dashboard over `metrics/metrics.jsonl`
- `metrics.stats()` — the structured aggregates (success rates, latencies,
  provider failures, permission denials)
- Receipts: `memory/receipts.jsonl` (redacted) · Audit: `memory/audit.jsonl`
  (redacted) · Job history: `automation/executions.jsonl` (redacted)

## 11. Backup / recovery requirements

**Back up (source of truth, not reconstructible):**
- Git repository itself (code + committed evidence)
- `memory/` — profile, longterm, sessions, receipts, audit, diary (+
  `memory/diary/archive/` — archived originals are kept, never deleted)
- `train/` — episodes (SFT source), `train/golden/` (cloud teach-back)
- `skills/` — distilled + user skills
- `config.yaml`, `models.yaml`, `settings.json`, `automation/` (durable
  jobs + rules + execution history), `.env` (if you want the same cloud
  config on a restore — treat as a secret)
- `models/` — STT weights (large; re-downloadable, back up to save time)

**Do NOT back up (rebuildable / transient):**
- `memory/vector/` (LanceDB) — rebuilt by the `vector_rebuild` job /
  `rebuild_vectors()`; B2 fix guarantees idempotent rebuilds
- `metrics/`, `temp/`, `__pycache__/`, `evals/results*.json`

**Restore procedure:**
1. `git clone` (or copy) the repo to the same path layout; `pip install -r
   requirements.txt` (+ optional extras)
2. Restore `memory/`, `train/`, `skills/`, `automation/`, config files
3. Start Ollama + `bee4b`; first run restores jobs automatically
   (`worker.restore()` recomputes next_run; missed one-time jobs inside the
   15-min grace catch up exactly once, beyond it they are marked MISSED)
4. Trigger a vector rebuild once (or wait for the 12h job)

**Crash recovery (automatic):** job crash-repair per retry budget; sessions
persist per task; vector store degrades to keyword search if LanceDB is
corrupt (delete `memory/vector/` and rebuild). No manual DB repair exists
and none should be needed.

**OneDrive caveat:** the workspace is OneDrive-synced — files locked by a
running BEE can desync; back up from a stopped system or use
`git` (which is immune to sync) as the primary backup channel.

## 12. Security checklist

| # | Check | Status |
|---|---|---|
| 1 | No secrets in git (`.env` ignored; `test_secretscan` pins the tree) | **PASS** |
| 2 | Destructive commands: deny/ask at two independent layers (regex + AST) | **PASS** (4,204 + AST tests) |
| 3 | No `eval`/`exec` anywhere (AST `eval_safe` with limits) | **PASS** (grep + pinned) |
| 4 | PII redaction on cloud payloads + all persistent telemetry | **PASS** (13,200 + this audit's chokepoint) |
| 5 | SSRF allow/deny on URL fetches | **PASS** (19 pinned cases) |
| 6 | File tools confined to workspace | **PASS** |
| 7 | Web endpoints token-authenticated (constant-time), loopback-only | **PASS** (personal scope only) |
| 8 | Capability gate: 20 capabilities, task-scoped grants, unattended fail-closed | **PASS** |
| 9 | Automation requires explicit user authorization (R3 ASK) + persisted audit trail | **PASS** |
| 10 | Computer use: safe-set-only, provenance-checked coordinates, 3 emergency stops, no sensitive content in logs | **PASS** (MockDesktop-verified) |
| 11 | Sandbox (Docker) does not mount `.env` | **PASS** (Phase 1) |
| 12 | Prompt-injection content-level filtering | **FAIL (accepted risk)** — tool-level gates only; see §2 |
| 13 | LiveKit worker through the capability gate | **FAIL (open gap)** — legacy `run_agent` path; see §1 |
| 14 | `.env` not in a cloud-synced folder | **FAIL (deployment risk)** — OneDrive caveat §11 |
| 15 | Log/telemetry retention caps (M13) | **FAIL (open)** — unbounded JSONL growth |
| 16 | OS-level alerting on failures | **FAIL (absent)** — observability §7 |

## 13. Next recommended Jarvis features

Ordered by (risk removed + value) per unit of effort; none is required for
personal use today:

1. **Route the legacy surfaces through the kernel** (close checklist #13):
   `webapp /voice`, `livekit/agent.py` worker, `bee/evals` runner →
   `kernel.run` (the web `/chat` pattern already exists — small, mechanical,
   high security value).
2. **M13: rotation + caps** for `metrics.jsonl`, episodes, diaries,
   notifications (size/time bounds + archive; mirrors the diary archive
   pattern already in place).
3. **J1: resumable multi-step autonomy** — Planner steps bound to TaskState
   with per-step verification and kill-safe checkpoints (fixes the
   "partial completion" YELLOW and the hung-subprocess limit together).
4. **Model upgrade path (J3)** — nightly quality gate that promotes a local
   model only when eval ≥ baseline + margin; this is the actual fix for the
   8–13/21 ceiling (the runtime is ready; the model is the bottleneck).
5. **Content-level untrusted-context isolation** for web/file content
   (checklist #12): tag untrusted spans, strip imperative patterns before
   prompt assembly, and require ASK capabilities for any action whose
   triggering context contained untrusted content.
6. **OS-level notifications + alerting** (checklist #16): Windows toast on
   job failure/proactive events; threshold alerts on `stats()` (provider
   failure rate, verify-fail rate).
7. **J2 skill marketplace discipline** — versioning + eval gate before a
   teach-back skill ships (golden distillation already exists).
8. **M14 config precedence doc + single-resolution test matrix** (finishes
   the configuration story started in Phase 5).
9. **Consolidate the two EventBus classes** (kernel vs automation) into one
   typed bus (architecture YELLOW, currently bridged ad hoc).
10. **R8: replace the LiveKit temp-JSON state bridge** with a file-watched
    single-writer store or an in-process registry when both run together.

---

*Audit performed without adding features beyond the requested telemetry and
the documented hardening fixes (items 1–6 in the header). Every status above
is either test-pinned, code-cited, or an explicit non-claim.*
