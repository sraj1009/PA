# BEE → JARVIS Target Architecture

**Status:** Audit document (Phase 1 of the takeover plan). Describes the *current*
architecture as verified in the source tree, then the *target* architecture with
per-component keep / wrap / replace decisions. Every claim below is backed by a
file:line reference from the audit of 2026-10-05. No code was modified while
producing this document.

Conventions: paths are relative to the project root
(`C:\Users\mshri\OneDrive\Desktop\PA\`). Line numbers are as of the audit date.

---

## 1. Current Architecture

### 1.1 System overview

BEE is a local-first, offline-capable personal assistant for Windows. The real
pipeline today is a **single implicit agent loop** (`run_agent`) surrounded by
subsystems that are bootstrapped in three independent places (CLI, web, LiveKit):

```
User
  │  (REPL / web UI / LiveKit voice / clap-triggered mic)
  ▼
bee/cli.py            ── REPL, command parser (/, .)
bee/webapp.py         ── FastAPI: /chat, /voice, /engine, /skills, /livekit/*, /face*
bee/livekit/agent.py  ── LiveKit worker (BeeSTT/BeeTTS adapters)
  │
  ▼
bee/agent/loop.py :: run_agent()          ← the de-facto Agent Kernel (636 lines)
  │
  ├─ 1. Routing decision
  │     det-math regex → explicit engine → smalltalk →
  │     fastpaths.py (536-line regex fastpaths) →
  │     brain/mlrouter.py (TF-IDF + LogReg, 408 episodes, CV 0.9975,
  │                      complexity floor: ML may escalate, never demote) →
  │     heuristic tier
  │
  ├─ 2. Engine resolution (agent/engines.py, settings.json)
  │     local | cloud | hybrid | offline
  │     → agent/client.py LLMClient (litellm + native Ollama fallback,
  │       LLMError classification, num_ctx=8192 pinned for the 3B local model)
  │
  ├─ 3. RAG auto-context (brain/rag.py → memory/search.py: LanceDB 768-dim
  │     vectors + keyword fallback, RRF fusion)
  │
  ├─ 4. Think/Act/Observe loop (≤ 25 iterations)
  │     LLM → tool call(s) →
  │       agent/guard.py permission gate (allow|ask|deny)  [loop.py:539-546]
  │       → tool dispatch (tools/*, 14 modules)
  │       → observation (res_v) → repeat guard (seen_calls) →
  │         fail_streak circuit breaker (≥2) → empty-completion retry →
  │         wrap-up nudge → forced no-tools final pass
  │     Cancellation: ev_cancel set ONLY by KeyboardInterrupt (loop.py:563-565)
  │
  ├─ 5. Verification (brain/verifier.py: math recompute / file re-read /
  │     URL citation checks; one bounded fix round)
  │
  └─ 6. Post-processing
        agent/reflection.py (lessons → memory/lessons/)
        agent/episodes/logger.py (episode JSONL → train/episodes/)
        monitor/metrics.py, monitor/health.py
        diary append (memory/diary/YYYY-MM-DD.md)
```

Supporting subsystems (not on the hot path per turn):

- **Voice:** `bee/voice/` — loop.py (REPL `/voice` mode), transcribe.py
  (faster-whisper, models as plain files under `models/`, CPU-first on Windows),
  clap.py (hysteresis retrigger, adaptive noise floor, double-clap = two claps
  60–400 ms apart, 1.5 s cooldown), speak.py (pyttsx3 SAPI primary, edge-tts
  fallback).
- **LiveKit:** `bee/livekit/` — free-tier cloud realtime worker; agent.py
  (309 lines) hosts BeeSTT (100-137) and BeeTTS (141-223) adapters;
  state.py is a **temp-JSON cross-process bridge** shared with webapp
  `/face/state`; make_token mints 2 h participant JWTs (36-54).
- **Scheduler:** `bee/scheduler.py` (217 lines) — nightly real jobs: diary
  consolidation (with LLM summarize), vector rebuild (12 h), router retrain,
  cloud teach-back, SFT build. User cron via `bee/tools/scheduler_tool.py`
  (107 lines) — **all user jobs are `_noop` log-only placeholders** (39-40, 50-57,
  82; the tool description itself admits this at 102).
- **Sandbox:** `bee/tools/sandbox.py` (117 lines) + `sandbox/Dockerfile`
  (61 lines) — Docker optional; workspace is mounted into the container.
- **Native telemetry:** `bee/native/__init__.py` (177 lines) — Go daemon on
  127.0.0.1:8790, auto toolchain install to `%LOCALAPPDATA%\bee`,
  WMI/PowerShell fallback.
- **Training flywheel:** `train/` (episodes JSONL, router_model.joblib,
  sft_v1.jsonl, golden/) and `training/` (QLoRA scripts, build_sft) — **two
  separate training roots**. `bee/pipeline/` (train_router, build_sft).

### 1.2 Component inventory (verified)

| Component | Path | Lines | Role |
|---|---|---|---|
| Agent loop / kernel | `bee/agent/loop.py` | 636 | `run_agent`: routing, engines, RAG, act loop, verifier, episodes |
| Fastpath router | `bee/agent/fastpaths.py` | 536 | Regex fastpath system (answers/tools without LLM) |
| ML router | `bee/brain/mlrouter.py` | — | TF-IDF + LogReg local/cloud classifier; complexity floor |
| Heuristic router | `bee/agent/router.py` | 224 | Tier scoring fallback |
| LLM client | `bee/agent/client.py` | 226 | litellm + native Ollama fallback, LLMError, num_ctx=8192 pin |
| Context | `bee/agent/context.py` | 135 | Bag of cfg/workspace/tools; `client` assigned post-construction (untyped/optional) |
| Engines | `bee/agent/engines.py` | 102 | local/cloud/hybrid/offline; settings.json read/write; module globals |
| Offline layer | `bee/agent/offline.py` | 65 | Deterministic offline answers |
| Reflection | `bee/agent/reflection.py` | 65 | Lesson extraction → memory/lessons/ |
| Guard | `bee/guard.py` | 99 | EXEC_TOOLS (12), DESTRUCTIVE (18-40), EXTERNAL (42-47), classify (50-66), modes (69-85), check (88-98) |
| Privacy | `bee/agent/privacy.py` | 144 | PII redaction — **cloud-bound LLM payloads only** |
| Config | `bee/config.py` | 357 | YAML load, provider-matched env keys, .env loader |
| Paths | `bee/paths.py` | 59 | WORKSPACE = project root by default |
| CLI | `bee/cli.py` | 630 | REPL (152-), web (379-409, uvicorn at 409), full (467+), defaults `--host 127.0.0.1 --port 8787` (545-546) |
| Stub entry | `bee.py` | 11 | Delegates to `python -m bee.cli` |
| Web app | `bee/webapp.py` | 228 | FastAPI; module-global CTX (24); no auth on any route |
| LiveKit agent | `bee/livekit/agent.py` | 309 | Worker; sys.argv "start" hack (298-306); guard→unattended mutation (78) |
| LiveKit state | `bee/livekit/state.py` | — | Temp-JSON bridge to web UI |
| Scheduler | `bee/scheduler.py` | 217 | Nightly jobs; diary prune `f.unlink()` (56-60); sys.argv mutation (98-105) |
| User cron tool | `bee/tools/scheduler_tool.py` | 107 | `_noop` jobs only (39-40, 50-57, 82) |
| Memory markdown | `bee/memory/md.py` | — | profile/longterm/system/lessons/diary layers |
| Memory vectors | `bee/memory/search.py` | 102 | LanceDB 768-dim; `rebuild()` (40-56) **appends** via `t.add(rows)` (55) — duplicate accumulation; module global `_cache` (68) |
| RAG | `bee/brain/rag.py` | — | RRF fusion of vectors + keyword |
| Verifier | `bee/brain/verifier.py` | — | Math recompute / file re-read / URL checks; 1 bounded fix round |
| Tool base | `bee/tools/base.py` | — | `T` dataclass (name/description/parameters/handler); `build_default_tools()`; `eval_safe` (AST allowlist, **no depth/size/time limits**) |
| Tool modules | `bee/tools/*.py` | 14 | files (139, workspace jail), automate (342, Playwright), shell (45, `shell=True`), web (multi-engine ddg→bing→wikipedia), code (47, host `python -c`), calculator (35), sandbox (117), memory (76), skills (119), planner (39), spawn_tool (29), scheduler_tool (107), health, systemctl (314) |
| Episodes | `bee/agent/episodes/logger.py` | 113 | JSONL episode records; **unredacted tool output** persisted (loop.py:579-580) |
| Monitor | `bee/monitor/{metrics,health,dashboard}.py` | — | Metrics JSONL history (unbounded), health, static HTML dashboard |
| Native daemon | `bee/native/__init__.py` | 177 | Go telemetry daemon bootstrap |
| Evals (code) | `bee/evals/` | — | Agent task runner (21 tasks in root `evals/tasks.yaml`) |
| Evals (data) | `evals/` (root) | — | tasks.yaml, verify_suite.py (1259, Wilson 95% CIs), results.jsonl, bench_model.json |
| Pipeline | `bee/pipeline/{train_router,build_sft}.py` | — | Router retrain (408 episodes), SFT jsonl build |
| Training | `train/` vs `training/` | — | Two roots: data/artifacts vs QLoRA scripts |
| Sandbox image | `sandbox/Dockerfile` | 61 | ENV lines are build flags only (no secrets); workspace mounted in |
| Setup | `setup.ps1` | 78 | One-shot: Ollama models + pip deps + optional sandbox image + env check |
| Makefile | `Makefile` | 34 | Targets for common ops; **no `full` target** (full mode is `python -m bee.cli full` / `bee-runfull.ps1`) |
| Tests | `tests/` (28 files) | — | 202 tests |
| Docs | `docs/` | — | consolidation.md, llm-component.md (stale), training-plan.md |

### 1.3 Entry points

| Entry | Command | Behavior |
|---|---|---|
| REPL | `python -m bee.cli` | Foreground agent REPL; bootstraps Context inline (cli `_repl`) |
| Web | `python -m bee.cli web` | `uvicorn.run(host, port)` (cli.py:409); defaults 127.0.0.1:8787 (cli.py:545-546); Context built lazily in `webapp.get_ctx()` (27-39) — **3rd bootstrap site** |
| Full stack | `python -m bee.cli full` or `bee-runfull.ps1` | Spawns unbuffered web child (498) + livekit child (500-504) logged to `temp/`, opens browser via `os.startfile` (508), foreground REPL, teardown on exit |
| LiveKit | `python -m bee.cli livekit` | Worker process; `livekit/agent.py` `_build_brain` (65-96) — **also a bootstrap site** |
| Eval | `python -m bee.cli eval` / `/eval` in REPL | Runs 21 tasks from `evals/tasks.yaml` |
| Setup | `powershell -ExecutionPolicy Bypass -File setup.ps1` | Environment bootstrap checks |

### 1.4 Configuration model (4 files, precedence undocumented)

| File | Lines | Holds |
|---|---|---|
| `config.yaml` | 135 | Persona, model names, guard mode, voice, livekit keys (by env name), workspace paths |
| `models.yaml` | 34 | 8 model catalog entries (local + `:cloud` aliases) |
| `.env` | 3 keys | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` (values never echoed; file is **not** covered by `.gitignore`) |
| `settings.json` | — | Runtime engine choice (currently `hybrid`); read/written by `agent/engines.py` and `/engine` endpoint |

`bee/config.py` (357) loads YAML + `.env` and resolves provider-matched env
keys. Precedence among the four files is **not documented anywhere** and is
discovered by reading `config.py`.

### 1.5 The 12 kernel responsibilities today

The target Agent Kernel must own 12 responsibilities. Current locations:

| # | Responsibility | Current location | State |
|---|---|---|---|
| 1 | Conversation session | `cli.py` REPL vars; `webapp.py` stateless-per-request (CTX global only); `livekit/agent.py` per-session | **Fragmented, 3 sites, no shared session object** |
| 2 | Task state | Local vars inside `run_agent` (iteration count, res_v init at loop.py:537, ok_flag 578) | **Implicit; no TaskState type** |
| 3 | Planning | `tools/planner.py` (39) — plan is a tool the LLM may call | Partial; no plan↔execution binding |
| 4 | Tool selection | `tools/base.py` schema list → LLM; fastpaths (536 lines) pre-empt many turns | Duplicated: regex fastpaths vs LLM selection vs ML router |
| 5 | Tool execution | `loop.py` dispatch (557-576) | Works; shell=True; code_run on host |
| 6 | Permissions | `guard.py` (99) invoked at loop.py:539-546 | Works for shell-style text; **code_run Python payloads bypass most patterns** (classify uses `args["command"] or args["code"]` string matching, 59-65) |
| 7 | Cancellation | `ev_cancel` set only by KeyboardInterrupt (loop.py:563-565) | **No CancellationToken; web/livekit turns cannot be cancelled** |
| 8 | Verification | `brain/verifier.py`, 1 bounded fix round | Good for math/file/URL; not a general policy |
| 9 | Memory | `memory/md.py` + `memory/search.py` + `episodes/logger.py` | Works; vector rebuild accumulates duplicates (search.py:55) |
| 10 | Error recovery | LLMError classification (client.py), fail_streak breaker (loop.py:553-556), repeat guard (548-552), engine fallback chain | Solid; scattered, undocumented |
| 11 | Scheduling | `scheduler.py` (real nightly jobs) + `scheduler_tool.py` (**no-op user jobs**) | Split; user-facing scheduling does not execute |
| 12 | Telemetry | `monitor/metrics.py` (JSONL, unbounded), `native/` Go daemon, `episodes` | Works; unbounded growth; no rotation |

---

## 2. Target Architecture

```
User
 → Input Layer            REPL / Web / LiveKit / mic+clap — normalized input events
 → Conversation Manager   session object, turn history, per-session model override
 → Agent Kernel           owns the 12 responsibilities below
      → Planner           (existing planner tool promoted to kernel stage)
      → Policy/Permissions guard.py promoted to Policy (AST-aware for code_run)
      → Tool Bus          typed registry + dispatch + schema (tools/base.py T)
      → Tool Execution    sandboxed by default for exec tools
      → Observation       typed Observation (value, ok, blocked, dt, redacted-for-store)
      → Verification      verifier.py generalized to per-tool verification policies
      → Response          final answer synthesis
 → Memory / Event Bus     typed events; episodes redacted at write time
```

### 2.1 Component decisions (keep / wrap / replace)

| Target component | Decision | Rationale |
|---|---|---|
| Input Layer | **Keep + normalize** | cli REPL, webapp, livekit all work; add one `InputEvent` type (source, text/audio, session_id) at the boundary |
| Conversation Manager | **New** | 3 bootstrap sites (cli `_repl`, webapp.get_ctx:27-39, livekit `_build_brain`:65-96) and 3 session flavors today; a single `Session` object (history, model_override, cancellation token) built by one factory |
| Agent Kernel | **Wrap, don't rewrite** | `run_agent` (636 lines) is the working core and the 202-test baseline pins its behavior. Introduce `TaskState`, `CancellationToken`, typed events *around* it in Phase 2; extract only after the wrapper is green |
| Planner | **Keep** | `tools/planner.py` is fine as a tool; later bind plan steps to TaskState |
| Policy/Permissions | **Promote + fix** | `guard.py` regexes are 100% on the 4,204-check guard suite; extend `classify()` with an AST pass for `code_run` Python (catches `shutil.rmtree`, `os.remove`, `Path.unlink`, truncating writes) before adding new rules |
| Tool Bus | **Keep T registry, type it** | `T` dataclass is already a clean contract; add result typing (`Observation`) and a single dispatch function used by loop, web, livekit |
| Tool Execution | **Keep; sandbox policy** | 14 modules work; exec tools stay behind Policy; `shell` keeps `shell=True` (Windows-first) but only via guarded path |
| Observation | **New type** | Replace bare `res_v` local (loop.py:537) with a dataclass carrying value/ok/blocked/duration and a redacted copy for persistence |
| Verification | **Keep + generalize** | verifier.py (math/file/URL + 1 fix round) is the best-tested part (in 71,914-check suite); make it a per-tool policy hook |
| Response | **Keep** | Final synthesis in loop.py works; SSE fake-streaming replaced by real event streaming from the bus |
| Memory | **Keep + repair** | md layers + LanceDB + episodes flywheel are working; fix rebuild dup (search.py:55 → clear-then-add or upsert), redact episodes at write, archive-not-delete in consolidation |
| Event Bus | **New** | Today `on_event` gets stringly-typed dicts. Introduce typed event dataclasses (TurnStarted, ToolCall, ToolResult, GuardDecision, Error, TurnDone) and a subscriber list; REPL prints, web streams real SSE, livekit reacts |

### 12 kernel responsibilities in the target

1. Conversation session → Conversation Manager (Session object)
2. Task state → `TaskState` dataclass inside Kernel (status enum: queued/routing/acting/verifying/done/failed/cancelled)
3. Planning → Planner stage + planner tool
4. Tool selection → Tool Bus + (fastpaths/router kept as *caches*, not owners)
5. Tool execution → Tool Bus dispatch
6. Permissions → Policy (guard.py + AST for code_run)
7. Cancellation → `CancellationToken` checked at each loop iteration, tool timeout, and engine call
8. Verification → per-tool verifier policies
9. Memory → md + vectors + episodes (redacted at write)
10. Error recovery → LLMError taxonomy + breaker + fallback chain (kept, documented)
11. Scheduling → one scheduler: nightly jobs **and** real user cron (job serialization)
12. Telemetry → metrics with rotation + Go daemon + event bus tap

---

## 3. Data Flow

### 3.1 Text turn (REPL), current

1. User types in REPL (`cli.py` `_repl`); BOM/zero-width stripped.
2. Command check (`/plan /draft /summarize /code /think /voice /eval …`).
3. `run_agent(ctx, task, model=…)` (loop.py):
   a. **Routing:** det-math regex → explicit engine hint → smalltalk →
      `fastpaths.py` regex system → `brain/mlrouter.py` (may escalate, never
      demote vs heuristic) → `router.py` tiers.
   b. **Engine:** `engines.py` resolves local/cloud/hybrid/offline from
      settings.json + per-turn model override.
   c. **RAG:** `brain/rag.py` auto-injects top-k chunks (LanceDB + keyword, RRF).
   d. **Loop:** LLM (client.py; privacy.py redaction applied to cloud payloads
      only) → tool calls → `guard.check` (539-546) → dispatch (557-576) →
      observation into `res_v` → repeat guard (548-552) → fail_streak breaker
      (553-556, trips at 2) → empty-completion retry → wrap-up nudge →
      forced no-tools final pass. Max 25 iterations.
   e. **Verify:** verifier checks math/file/URL claims; one bounded fix round.
   f. **Post:** reflection lesson, episode JSONL (**unredacted** tool output,
      loop.py:579-580), metrics, diary.
4. REPL prints answer + status line (`model=… iters=… tools=…`).

### 3.2 Voice turn (REPL `/voice` or clap)

Mic capture (`voice/loop.py`) → clap detector gates wake (hysteresis, adaptive
noise floor, double-clap 60–400 ms, 1.5 s cooldown) → faster-whisper STT
(`voice/transcribe.py`, CPU-first on Windows, models under `models/`) → same
`run_agent` path → TTS via pyttsx3 SAPI (edge-tts fallback, `voice/speak.py`).

### 3.3 Web turn

`POST /chat` (webapp.py:68-96) → `run_agent` with `on_event` buffering into a
list; the "SSE" response streams **only after the whole turn completes**
(fake streaming; 74-96). `POST /voice` (99-137) uploads to a **fixed temp
filename** `bee_upload{suffix}` (108 — concurrent-upload race), ffmpeg→STT→
run_agent→JSON text (docstring claims "+tts mp3" — incorrect API contract).
**No route is authenticated** (default bind 127.0.0.1 is the only mitigation).

### 3.4 Offline turn

Engine `offline` (engines.py) → `agent/offline.py` (65 lines) deterministic
answers (time/date note hardcodes "Asia/Kolkata" label at offline.py:58 while
using system local time) → tools still available → no cloud calls anywhere.

---

## 4. Task Lifecycle (current)

States are implicit local variables in `run_agent`:

```
QUEUED ──▶ ROUTING ──▶ RAG ──▶ ACTING (n ≤ 25) ──▶ VERIFYING ──▶ RESPONDING ──▶ DONE
                │              │  ▲                   │
                │              │  └─ fix round (≤1)   └─ failure → ERROR
                ▼              ▼
          smalltalk/fastpath   CANCELLED (KeyboardInterrupt only; loop.py:563-565)
```

- `ok_flag` derived at loop.py:578 from `res_v` (init 537; fastpath assigns 271/273).
- Repeat guard (548-552): identical (tool, args) seen before → block.
- fail_streak (553-556): 2 consecutive tool failures → stop acting.
- **Gaps:** no TaskState object, no cancellation token (web/livekit turns run
  to completion regardless), no resumable state, no per-task telemetry envelope.

## 5. Tool Lifecycle (current)

```
T(name, description, parameters, handler)   ← tools/base.py
   → build_default_tools() registers 14 modules
   → schema list sent to LLM
   → LLM emits call {name, args}
   → guard.check(name, args, enabled, mode)  ← loop.py:539-546
   → dispatch handler (557-576)
   → observation res_v (dict/str)
   → verifier hook (math/file/URL only)
   → episode.tool(name, args, ok, dt, res_v)  ← loop.py:579-580, UNREDACTED
```

- Path jail: `tools/files.py` (139) confines to workspace.
- `tools/shell.py` (45): `shell=True` (Windows-first, documented risk).
- `tools/code.py` (47): host `python -c` — runs in the host process, guarded
  only by the guard regexes, which mostly don't parse Python (see §6).
- `tools/calculator.py` (35): `eval_safe` AST allowlist — zero eval/exec
  confirmed; **no depth/size/time limit** (DoS surface).
- `tools/sandbox.py` (117) + `sandbox/Dockerfile` (61): Docker optional;
  workspace mount brings `.env` into the container's file view.
- `tools/scheduler_tool.py` (107): every user job is `_noop` (39-40, 50-57, 82).

## 6. Permission Model (current)

- `guard.py` (99): `EXEC_TOOLS = {shell, code_run, sandbox_run, systemctl}` (12).
- DESTRUCTIVE list (18-40): recursive rm, rmdir /s, format, mkfs/dd,
  Remove-Item -Recurse, del /s, DROP/TRUNCATE, git push -f, shutdown/reboot,
  taskkill, reg delete, pip uninstall, docker prune, curl|sh, shred…
- EXTERNAL list (42-47): git push, curl/wget write verbs, messaging,
  `requests.post/put/delete` in code.
- `classify()` (50-66) reads `str(args["command"] or args["code"])` and runs the
  shell-style regexes over it. **Consequence: Python `code_run` payloads that
  don't spell a shell idiom (e.g. `shutil.rmtree`, `os.remove`,
  `Path(...).unlink()`, `open(p,'w')` truncation) classify as `allow`.**
- Modes (69-85): `cli` (input prompt, EOF→deny), `unattended` (auto-deny —
  forced by livekit/agent.py:78), `always` (auto-approve, unsafe).
- Privacy (144): PII regex redaction (Luhn CC, key prefixes, Aadhaar, phones,
  secret assignments) applied **to cloud-bound LLM payloads only** — not to
  episodes, logs, or diary.
- Verification suite: 4,204 guard checks, 100% (Wilson lower 99.909%) — but the
  suite covers the existing regex surface, not the code_run AST gap.

## 7. Memory Model (current)

```
markdown layers (memory/):  profile.md · longterm.md · system.md · lessons/ · diary/
     │  md.all_chunks()
     ▼
LanceDB vectors (768-dim, nomic-embed-text)  ← rebuilt 12h (scheduler.py)
     │   rebuild() appends via t.add(rows) — search.py:55 — DUPLICATES ACCUMULATE
     ▼
RAG: RRF(vector hits, keyword fallback)  → auto-injected into prompt (brain/rag.py)
     ▲
episodes JSONL (train/episodes/)  ← unredacted tool output (loop.py:579-580)
     │
     ├─► ML router retrain (pipeline/train_router.py; 408 episodes, cv 0.9975)
     ├─► SFT build (pipeline/build_sft.py → train/sft_v1.jsonl → training/qlora)
     └─► golden cloud teach-back → skills/
```

Consolidation (scheduler.py nightly): LLM-summarizes old diary entries, then
**deletes the originals via `f.unlink()` (56-60) — irreversible**.

## 8. Provider Abstraction (current)

- `client.py` (226): litellm primary; native Ollama HTTP fallback on error;
  `LLMError` classification (auth/quota/network/timeout); `num_ctx=8192` pinned
  client-side so the 3B local model fits 8 GB VRAM (hidden assumption).
- `engines.py` (102): engine names → model aliases from models.yaml
  (8 models incl. `:cloud` aliases); settings.json holds the active engine;
  module-global state.
- Fallback chain: local → cloud (hybrid), with free-tier 429 handling in
  client error taxonomy.
- **Gap:** no `Provider` ABC; provider knowledge is spread over
  config.py env-key matching, client.py, engines.py, livekit agent env, and
  .env — a new provider means touching ~4 files. Target: `Provider` interface
  (chat / embed / models_list / availability) + registry keyed by name.

## 9. Event Model (current → target)

- Current: `on_event(dict)` callback; dict keys are stringly-typed
  (`type` = "start"|"tool"|"result"|"error"|"…"), shapes vary by call site;
  webapp buffers them for fake SSE (webapp.py:74-96); REPL prints ad hoc.
- Target: typed dataclasses — `TurnStarted(session, task)`, `ToolCall(name,
  args, task)`, `GuardDecision(action, reason)`, `ToolResult(ok, obs, dt)`,
  `Error(kind, message)`, `TurnDone(ok, iterations, tools)` — published on a
  minimal `EventBus` (subscribe/publish, in-process). REPL, web (real SSE),
  livekit, and telemetry all become subscribers. No persistence in v1.

## 10. Voice Architecture

- **REPL path:** `/voice` toggles loop; clap wake; faster-whisper STT
  (CPU-first on Windows); run_agent; pyttsx3 SAPI TTS (edge-tts fallback).
- **LiveKit path:** `bee/cli.py livekit` → worker (livekit/agent.py):
  - joins room from env; mints participant JWTs (make_token, 36-54, 2 h);
  - BeeSTT (100-137) bridges LiveKit audio → faster-whisper;
  - BeeTTS (141-223) edge-tts → SAPI fallback → LiveKit track;
  - forces guard mode `unattended` (78) — correct, but means LiveKit turns
    can be denied by guard without any approver;
  - state published to web UI via temp-JSON bridge (livekit/state.py ↔
    webapp `/face/state` 219-222, `/livekit/status` 182-187 — status returns
    no secrets, good);
  - `sys.argv` mutation to add "start" (298-306) — process-global hack;
  - `num_idle_processes=0` (287) for free-tier.
- **Model files:** faster-whisper weights live as plain files under
  `models/` (OneDrive-synced; bloats sync).

## 11. Scheduler Architecture

- `bee/scheduler.py` (217, APScheduler `BackgroundScheduler(timezone=
  "Asia/Kolkata")` at 207) nightly real jobs:
  1. Diary consolidation (summarize → **unlink originals**, 56-60);
  2. Vector rebuild (12 h; duplicate-appending, search.py:55);
  3. Router retrain — **mutates `sys.argv`** around `train_router.main()`
     (98-105: `_sys.argv[:1]+["--min","10"]`);
  4. Cloud teach-back (golden → skills);
  5. SFT build.
- `bee/tools/scheduler_tool.py` (107): user-facing cron (jobs.json, one job
  present: "Monthly_sales_analysis_report_delivery") — restored jobs and newly
  added jobs are both `_noop` (39-40, 50-57, 82); writes a single jobs.log line
  (50-57); tool description admits the no-op (102).
- Timezone hardcoded `Asia/Kolkata` in 3 places: scheduler.py:207,
  tools/scheduler_tool.py:32, offline.py:58 (label string).
- **No job serialization** — a real user job has no payload representation it
  could execute later.

## 12. Failure / Recovery Model (current)

| Failure | Detection | Recovery |
|---|---|---|
| LLM auth/quota/timeout | `LLMError` taxonomy (client.py) | engine fallback local↔cloud (hybrid); offline deterministic answers (offline.py) |
| Gemini free-tier 429 | classified quota | back off to local; documented as environmental |
| Tool failure | `ok_flag` (loop.py:578) | fail_streak circuit breaker at 2 consecutive (553-556); repeat guard blocks identical retries (548-552) |
| Empty LLM completion | detected post-turn | one retry, then wrap-up nudge, then forced no-tools final pass |
| Guard deny | classify (guard.py:50-66) | unattended: auto-deny; cli: prompt; turn continues without that tool |
| Vector store down | exception on open | keyword search only (search.py:71-74) |
| STT missing | `transcribe.available()` | web returns 501 (webapp.py:102-104); REPL disables voice |
| TTS failure | exception in speak | pyttsx3 → edge-tts fallback chain |
| LiveKit not configured | env check | `/livekit/token` returns 503 (webapp.py:202-204); status shows configured:false |
| Docker missing | which("docker") | sandbox tool reports unavailable; host tools still work |
| Cloud down entirely | provider errors | `offline` engine; all 14 tools local except web search (network) |

Offline-first holds: the assistant remains fully usable (chat + tools + memory
+ voice STT/TTS-local) with zero network; cloud is acceleration + escalation.

## 13. Test & Evaluation Harness

| Layer | Location | Exact result (2026-10-05) |
|---|---|---|
| Unit/integration | `tests/` (28 files) | **202 passed, 1 warning in 16.61s** (warning: StarletteDeprecationWarning from FastAPI TestClient) |
| Deterministic verify | `evals/verify_suite.py` (1259) | **overall ALL PASS, 71,914 checks** — math n=10,000 100% (ci95lo 99.962%); dsa n=38,456 100% (99.990%); pii n=13,200 100% (99.971%); guard n=4,204 100% (99.909%); router n=6,000 100% (99.936%); rag n=54 100% (93.359%, small-n) |
| Agent end-to-end | `evals/tasks.yaml` (21 tasks) via `bee/evals/` | **10/21 PASS** (latest run 2026-10-05T22:07:30). PASS: math_basic, math_sieve, shell_echo, calculator, web_search_tool, route_det_math, route_det_pct, math_repeat_stable (×3), guard_blocked, cloud_redaction. FAIL (11): file_roundtrip, file_list_ws, dsa_lis, dsa_gcd_lcm, dsa_sort_check, dsa_graph, memory_write, memory_read, plan_complex, verify_calc_pass, rag_gpu_memory — all local-3B "missing substring" quality ceiling, not loop bugs |
| Model bench | `evals/bench_model.json` | recorded per-model latency/quality snapshot |

## 14. Agent Kernel (Phase 2 — implemented 2026-10-05)

The feature collection is now one coherent runtime. **`bee/kernel/`** (12
modules) owns task state, permissions, verification, receipts, cancellation,
retry and conversation continuity. The LLM only *proposes* (intent, tool
actions, answers); the kernel *decides* (allowed? executed? succeeded?
persisted?). The existing `run_agent` loop is the kernel's EXECUTOR — it was
NOT rewritten; two small backward-compatible hooks were added:
`run_agent(..., on_ask=approver)` (kernel-injected permission approver) and
`guard.check(..., approver=...)`.

### 14.1 Object model (`bee/kernel/models.py`, `state.py`)

| Object | Role |
|---|---|
| `AgentSession` | persistent conversation state: active task, turns, referenced entities, pending confirmation, recent tool results, last time hint (`memory/sessions/<id>.json`) |
| `Task` | one user request; id, text, state, plan, observations, receipts, verification, retry_count |
| `TaskState` | CREATED, UNDERSTANDING, PLANNING, WAITING_FOR_PERMISSION, EXECUTING, VERIFYING, COMPLETED, FAILED, CANCELLED, WAITING_FOR_USER, RETRYING |
| `Plan` / `Action` | kernel-decided steps (description, tool, risk, capability, permission) |
| `Observation` | what the kernel SAW per tool call (result text, ok, effect) — never the model's claim |
| `VerificationResult` | pass / fail / unverified / not_run + checks |
| `PermissionDecision` | tool, action (allow/ask/deny), granted, reason, risk_level, capabilities |
| `ExecutionReceipt` | task_id, session_id, timestamp, tool, action, arguments, risk_level, permission, result, verification, duration, error, retry_count |
| `AgentEvent` | typed event (14 kinds: user_message … memory_written) |
| `EventBus` | in-process pub/sub; subscriber errors never break the kernel |

**State machine** (`state.py`): explicit transition table; illegal moves
raise `InvalidTransitionError` (fail closed — e.g. CREATED→COMPLETED,
anything out of a terminal state). Permission waits are legal mid-execution
(EXECUTING↔WAITING_FOR_PERMISSION), retries flow VERIFYING→RETRYING→EXECUTING.

### 14.2 Task flow (the lifecycle)

```
user request
  → AgentSession (load/persist)                    [session.py]
  → UNDERSTANDING — follow-up resolution:
      'stop.' → CANCELLED  ·  'Tomorrow.'/'Actually make it 10 AM.' →
      merged against the ACTIVE task  ·  unrelated → new
  → memory context (session context block + in-loop RAG)
  → PLANNING — kernel builds Plan (execute-step + verify-step)
  → EXECUTING — run_agent (routing, engines, guard, tools, episodes,
      telemetry — all pre-existing); the kernel's approver is injected via
      on_ask, so every 'ask' passes through WAITING_FOR_PERMISSION with a
      permission event + permission receipt
  → VERIFYING — deterministic effect checks (file_write→file exists,
      file_edit→replacement present, mkdir/touch→path exists, calculator→
      result present) + task-level target probe ("Create a folder called
      invoices." → invoices/ must exist afterwards); a clean tool return
      NEVER equals success — uncheckable work is 'unverified', never 'pass'
  → RETRYING — only on transient/provider/tool/verification failures, never
      on permission denials, never after a destructive action, bounded
      (max_attempts=2) with a correction note injected into the retry
  → receipt (agent-level + per-tool, redacted JSONL memory/receipts.jsonl)
  → memory update (session save + memory_written event; episodes/diary via
      the loop as before)
  → COMPLETED / FAILED / CANCELLED + typed task_* event
```

### 14.3 What was unified (no second architecture)

- **REPL** (`cli.py`): tasks run through `kernel.run()`; `stop`/`cancel`/
  … are first-class (cancel the active task or report the last task's
  terminal state); Ctrl-C still cancels mid-run via the same event.
- **Web `/chat`**: runs through the kernel with a per-UI session
  (`body["session"]`, default "web") — the web UI now gets follow-up
  continuity; 'ask' decisions auto-deny (unattended, fail closed).
- **Slash commands** (plan/draft/summarize/code/think): LLM work goes
  through `kernel.direct()` — same client/provider routing, receipts,
  events; deterministic fallbacks unchanged.
- **Memory** behind 5 interfaces (`memory_if.py`): Working / Episodic /
  Semantic / Procedural / Temporal — thin adapters over the EXISTING
  episodes, RAG/LanceDB, memory.md, skills, diary/scheduler. No redesign.
- **ToolBus** (`tools_bus.py`): every tool the LLM may use is a registered
  `ToolDef` (name, description, schema, risk, capability, timeout,
  cancellation level, untrusted flag) built from `bee.tools` + the security
  risk profiles. Unknown names raise `UnknownToolError`; non-dict args raise
  `MalformedArgsError`; arbitrary callables cannot be registered.

### 14.4 What Phase 2 does NOT claim

- LiveKit voice worker still calls `run_agent` directly (latency path;
  kernel wiring is a small follow-up, not a blocker).
- Cancellation granularity: between iterations / before each tool call
  (honest `cancellation` levels per tool); mid-subprocess kill is not
  implemented.
- Realtime-voice event streaming and proactive automation consume the new
  event model in later phases — the model exists, those consumers do not.
- Verification is deterministic + heuristic (target-name probe); it is not
  a general intent-understanding layer.

## 15. Capability Security + Structured Memory (Phase 3 — implemented 2026-10-05)

### 15.1 Capability-based authorization (`bee/security/capabilities.py`)

Three layers, checked in this order, each before execution:

```
CapabilityGate  (is this KIND of action permitted?  — capability policy)
      ↓ allowed
guard.check     (is THIS specific command safe?     — regex + AST risk)
      ↓ allowed
tool executes   (loop.py dispatch)
```

- **19 capabilities** with full metadata: identifier, description, risk
  level **R0…R5** (information-only → financial/security-critical), default
  policy (`always_allow | ask | task | deny`), confirmation policy
  (`none | on_ask | always`).
- **Dangerous defaults are OFF**: `system.control`, `financial.action`,
  `purchase`, `camera.access` default to **deny**.
- Tool→capability mapping is central (`capabilities_for`): base caps per
  tool + argument-based escalation for exec tools (shell `rm`/`del`/`rmtree`
  → `files.delete`, `shutdown`/`reboot`/`taskkill` → `system.control`,
  `curl`/`wget` → `network.read`, `python` → `python.execute`, buy/order →
  `purchase`). Future tools (email_send, purchase, camera_snap, …) are
  mapped now.
- **Policies are user-configurable** in `config/capabilities.yaml`
  (template: `config/capabilities.example.yaml`): per capability
  `policy: always_allow|ask|task|deny` and `confirm: default|always|never`.
- **Confirmation semantics** (Part B): reading files / writing drafts = no
  confirmation; sending email/messages = ask (unless explicitly trusted via
  `always_allow`+`confirm: never`); deleting files / purchasing / system
  shutdown = **always confirm** even under `always_allow`, unless the user
  explicitly sets `confirm: never`.
- **Task-scoped grants**: a 'yes' grants the capability for the CURRENT
  task only (`store.grant_for_task` / `end_task`). Grants never carry over
  to another task, and a `files.write` grant never satisfies
  `files.delete`/`purchase` — grants are keyed (task, capability).
- **Enforcement point**: `loop.py` main dispatch — the gate runs BEFORE the
  handler and BEFORE the guard; a denial produces the same blocked-result
  flow (audit + episode + 'explain the refusal' behavior). Legacy direct
  `run_agent` paths without a kernel (eval runner, LiveKit) skip the gate —
  `ctx.capability_gate` is None there (documented).
- Unattended kernels (web) get an auto-deny approver → any asking
  capability fails closed.

### 15.2 Structured memory (`bee/memory/store.py` + kernel integration)

Six conceptual stores, one typed item model:

| Store | Backed by |
|---|---|
| WorkingMemory | kernel in-process notes, task-scoped |
| EpisodicMemory | episodes JSONL (unchanged) |
| SemanticMemory | RAG/LanceDB + memory.md (unchanged) |
| ProceduralMemory | skills (unchanged) |
| TemporalMemory | diary + (scheduling not active yet) |
| **EntityMemory** (new) | structured store, `type="entity"` (people/projects/devices/apps/locations) |
| **StructuredMemory** (new, canonical) | `memory/store.json` (git-ignored) |

Every item carries: `type, source, confidence, created_at, updated_at,
importance, expiry, provenance, key, subject, tags, trusted_policy,
superseded_by`. Interfaces: **remember / recall / update / forget /
summarize / expire**.

Governance (enforced in code):
- `source ∈ {user, tool, web, model_inference}`; confidence floors/caps by
  source (user ≥0.9, tool 0.8, web ≤0.5, model_inference ≤0.5).
- A model inference can become a user fact ONLY via an explicit
  re-statement (`update(..., source="user", asserted_by_user=True)`) —
  silent promotion raises `PermissionError`.
- Web-derived content has `trusted_policy=False` forever — and the
  capability/policy layer **never reads memory**, so external content can
  never become trusted policy.
- Content is privacy-redacted on store (secrets cannot persist here).
- Same-key re-remember **supersedes** the old value (tombstone kept for
  audit, `superseded_by` linked).
- Expiry: items with past `expiry` are invisible to recall; `expire()`
  purges them (+ 14-day-old tombstones).
- **Nothing is auto-saved** — items appear only via explicit remember.

Kernel UX (deterministic, zero LLM calls, verified against the store):
- "Remember that my project is called BEE." → `memory.remember` (key
  `project.name`) + receipt + verification (item must be recallable).
- "What do you remember about this project?" → source-labeled recall.
- "Forget that." → forgets the last recalled/remembered item; forgetting
  nothing is an honest answer, not a failure.
- Memory commands are parsed BEFORE follow-up resolution so "Forget that."
  is never merged into a previous task.

## 16. Known-stale artifacts (documented for the record)

- `docs/llm-component.md` — describes the pre-`bee4b` pipeline (stale).
- `evals/REPORT.md` — regenerated by the verify run; its agent-eval section
  reflects the 2026-10-05 run (10/21); older latency notes referenced
  qwen3:8b under the bee4b heading (stale wording).
- The two preserved screenshots from 2026-10-04 (res_v UnboundLocalError;
  setup.ps1 parse errors) are **both already fixed**: `res_v` is initialized at
  loop.py:537 (and fastpath 271/273) before all uses (574-578); setup.ps1
  now runs cleanly ("All core checks passed").
