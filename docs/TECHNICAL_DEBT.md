# BEE Technical Debt Report

Phase-1 audit (2026-10-05). Every entry cites verified file:line evidence.
Severity: **CRITICAL** = can compromise system/data security now;
**HIGH** = data loss, security gap, or silently-wrong behavior;
**MEDIUM** = maintainability/correctness risk; **LOW** = hygiene.

---

## CRITICAL

### C1. Unauthenticated web endpoints control the full agent
`bee/webapp.py` — no auth on any route.
- `POST /chat` (68-96): runs the complete `run_agent` including shell/code tools.
- `POST /engine` (149-158): mutates the **global** engine for all turns.
- `POST /livekit/token` (190-210): mints 2-hour LiveKit participant JWTs for any room name (validated for shape only, livekit/agent.py `validate_room`).
- `POST /voice` (99-137): full STT → agent pipeline.
Mitigation today: default bind `127.0.0.1:8787` (cli.py:545-546, webapp.py:227).
`--host` can widen this to LAN, at which point any host on the network owns the
machine (shell tool!).
**Fix:** token auth (env-derived, never logged) on all stateful endpoints —
Roadmap Phase 1.1.

### C2. Secrets hygiene: `.env` in synced dir, no `.gitignore` entry, no VCS
- `.env` holds `LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET` in a
  OneDrive-synced project directory.
- `.gitignore` (18 lines) has **no `.env` entry** (also missing `train/`,
  `metrics/`, `models/`, `temp/`).
- There is **no git repository** — any future `git init && git add -A`
  commits credentials instantly.
- `sandbox/Dockerfile` mounts the workspace into the container, so `.env` is
  readable inside the sandbox image runtime.
**Fix:** corrected `.gitignore` + `git init` + secret scan (Phase 0);
secrets-free mount strategy for sandbox (Phase 1.6).

## HIGH

### H1. Guard regex bypass for Python `code_run` payloads
`bee/guard.py:59-65` — `classify()` runs shell-style regexes over
`str(args["command"] or args["code"])`. Python payloads like
`shutil.rmtree(...)`, `os.remove(...)`, `Path(...).unlink()`, or
`open(p, "w")` truncation match no pattern → `allow`. `tools/code.py` (47)
runs them via host `python -c`.
**Fix:** AST-based classification pass for `code_run` (Phase 1.2).

### H2. Episodes persist unredacted tool output
`bee/agent/loop.py:579-580` — `episode.tool(name, args, ok, dt, res_v)` writes
raw tool results (files read, command output, web content) to
`train/episodes/*.jsonl`, which feeds SFT build and cloud teach-back.
`privacy.py` redacts only live cloud-bound LLM payloads — not storage.
**Fix:** redact at write time, reusing privacy.py (Phase 1.4).

### H3. Nightly consolidation irreversibly deletes diaries
`bee/scheduler.py:56-60` — after LLM-summarizing old diary entries, originals
are removed via `f.unlink()`. One bad summary = permanent data loss.
**Fix:** move originals to `memory/diary/archive/` (Phase 1.5).

### H4. LanceDB rebuild accumulates duplicates
`bee/memory/search.py:55` — `rebuild()` calls `t.add(rows)` against the
existing table every 12 h; ids are `f"{src}#{ch[:60]}"` with no
clear/upsert → duplicate rows accumulate; search returns stale copies and the
store grows without bound.
**Fix:** clear-then-add or upsert by id (Phase 4.1).

### H5. All user cron jobs are no-ops
`bee/tools/scheduler_tool.py:39-40, 50-57, 82` — restored jobs from
`jobs.json` and newly added jobs both schedule `_noop`, which writes one line
to `jobs.log`. The tool description (102) admits this, but a user who sets a
job believes it runs. `jobs.json` already contains
"Monthly_sales_analysis_report_delivery" — it will never execute.
**Fix:** job payload serialization + real execution via the kernel (Phase 3).

### H6. `sys.argv` mutation inside a live process
- `bee/scheduler.py:98-105` — retrain job rewrites
  `_sys.argv[:1] + ["--min", "10"]` around `train_router.main()`, then restores.
  Fragile: any concurrent argparse use sees the mutated argv.
- `bee/livekit/agent.py:298-306` — appends `"start"` to `sys.argv` so the
  worker entrypoint's argparse accepts it.
**Fix:** explicit argument passing; no global argv writes (Phase 3.4).

### H7. Cross-process state via temp JSON
`bee/livekit/state.py` ↔ `bee/webapp.py:219-222` (`/face/state`) — the LiveKit
worker process writes a temp JSON file that the web process reads. No atomicity
guarantee, stale reads on crash, Windows file-lock edge cases.
**Fix:** replace with the EventBus/local HTTP status in Phase 2/6, or atomic
rename writes at minimum.

### H8. `eval_safe` unbounded
`bee/tools/base.py` + `tools/calculator.py:35` — AST allowlist is good (zero
eval/exec confirmed), but there is no AST depth/node-count limit or time
budget; a crafted expression can hang or balloon the calculator tool.
**Fix:** limits + timeout (Phase 1.3).

## MEDIUM

### M1. 636-line implicit kernel; three Context bootstrap sites
`bee/agent/loop.py` owns routing, engines, RAG, act loop, verification,
episodes, and reflection inline. `Context` is constructed in cli `_repl`,
`webapp.get_ctx` (27-39), and `livekit/agent.py _build_brain` (65-96) —
~20 duplicated lines each, and `Context.client` is assigned
post-construction as an untyped optional (`agent/context.py`).
**Fix:** Phase 2 (TaskState, token, factory) / Phase 4.3.

### M2. Stringly-typed event dicts + fake SSE
`loop.py` `on_event(dict)` with ad-hoc `type` keys; `webapp.py:74-96`
buffers all events and streams them after the turn completes (not SSE).
**Fix:** typed events + EventBus + real streaming (Phase 2.3, 6.1).

### M3. Global-state cluster
- `webapp.py:24` module-global `CTX`
- `agent/engines.py` module globals (engine state; also mutated by
  `livekit/agent.py:78` which forces `cfg.guard.mode = "unattended"` on a
  shared config object)
- `memory/search.py:68` module-global `_cache`
- `brain/mlrouter.py` one-shot global `_ivw_filtered`
**Fix:** state owned by Context/Session objects (Phase 2/4).

### M4. Dual routing systems
`fastpaths.py` (536 lines of regex) vs `router.py` (224, tiers) vs
`brain/mlrouter.py` (learned). Three selection mechanisms with the
complexity-floor rule as the only documented interaction. Behavior is
pinned by tests, but adding a capability means touching all three.
**Fix:** keep (they work — 6,000 router checks 100%) but document the
decision order and expose it as one `Router` interface (Phase 2/5).

### M5. Unclear config precedence (4 files)
`config.yaml` (135) / `models.yaml` (34) / `.env` / `settings.json` —
precedence is implicit in `bee/config.py` (357) and `engines.py` (102).
**Fix:** documented precedence + single resolution point (Phase 4.4).

### M6. Two eval roots, two training roots
- `evals/` (root: data — tasks.yaml, verify_suite.py, results.jsonl) vs
  `bee/evals/` (code — runner).
- `train/` (episodes, router_model.joblib, sft_v1.jsonl, golden/) vs
  `training/` (QLoRA scripts).
**Fix:** unify per subsystem with a note file (Phase 4.2).

### M7. Hardcoded `Asia/Kolkata` × 3
- `bee/scheduler.py:207` (scheduler timezone)
- `bee/tools/scheduler_tool.py:32` (user-job scheduler timezone)
- `bee/agent/offline.py:58` (answer label claims Asia/Kolkata while using
  system local time — incorrect contract for non-IST machines)
**Fix:** `timezone: local` or config-driven IANA zone (Phase 4.4).

### M8. Wrong/stale API contracts and docs
- `/voice` docstring promises "+tts mp3"; returns JSON text (webapp.py:101).
- `docs/llm-component.md` describes the pre-bee4b pipeline.
- `bee.py` (11-line stub) duplicates `python -m bee.cli` as an entry point.
- `Makefile` (34) has no `full` target (full mode lives only in
  cli.py `_full` + bee-runfull.ps1).
**Fix:** Phase 6.3.

### M9. Untested execution paths
Full-stack mode, livekit brain path, `/chat` integration, consolidation,
user-job execution (trivially "untested" — it's a no-op), teach-back, SFT
build, native Go daemon install path.
**Fix:** per-phase integration tests as each is touched (Phases 1-6).

### M10. Unbounded growth
Metrics JSONL history, episodes JSONL, diary files, LanceDB table (see H4),
`temp/` (27 scratch files, incl. full-mode child logs).
**Fix:** rotation/caps (Phase 4.5) + root cleanup (Phase 6.3).

### M11. Hidden VRAM assumption
`client.py` pins `num_ctx=8192` so `bee4b` (3B) fits 8 GB VRAM. Changing the
local model or GPU silently breaks the assumption; it is not surfaced in
config.
**Fix:** move to models.yaml with per-model context + VRAM note (Phase 5).

### M12. Potential cycles masked by lazy imports
`cli ↔ webapp` and `livekit.agent ↔ agent/voice` use function-level imports
to dodge import cycles — a sign the module boundaries are wrong.
**Fix:** resolve naturally via the Context factory / EventBus (Phase 2).

## LOW

### L1. Windows-first assumptions scattered, undocumented
`shell=True` (tools/shell.py:45), SAPI via pyttsx3 (voice/speak.py),
WMI queries (native/), `os.startfile` (cli.py:508). All intentional for
this machine but invisible to a maintainer.
**Fix:** one `PLATFORM` section in the architecture doc (done) + comments.

### L2. Unused import: `WebSocket` in webapp.py:12.

### L3. Static dashboard staleness — `monitor/dashboard` HTML is served
statically; live data only via the metrics JSONL it reads client-side.
**Fix:** live endpoint in Phase 6.2.

### L4. `models/` holds faster-whisper weights as plain files in a
OneDrive-synced dir — sync bloat. **Fix:** move to a non-synced cache
path (Phase 6.3 cleanup, with config override).

### L5. Test warning: StarletteDeprecationWarning from FastAPI
TestClient/httpx (1 warning in the 202-pass run) — cosmetic, track on
dependency upgrade.

---

## Summary counts

| Severity | Count | IDs |
|---|---|---|
| CRITICAL | 2 | C1, C2 |
| HIGH | 8 | H1–H8 |
| MEDIUM | 12 | M1–M12 |
| LOW | 5 | L1–L5 |

**Recommended first implementation phase: Roadmap Phase 0 + Phase 1**
(VCS/secret safety net, then the six security fixes C1, C2, H1, H2, H3, H8 +
sandbox mount H-portion). All other items follow the roadmap order; each ends
with the full test gates green (pytest 202+, verify_suite ALL PASS, eval
10/21 baseline as the quality floor).
