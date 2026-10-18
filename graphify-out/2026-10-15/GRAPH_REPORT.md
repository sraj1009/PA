# Graph Report - PA  (2026-10-15)

## Corpus Check
- 362 files · ~330,442 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 4735 nodes · 10174 edges · 228 communities (199 shown, 29 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 335 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `796a98c1`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- render.js
- Server
- test_fastpaths.py
- LLMClient
- test_voice_engine.py
- Job
- page-shop.test.js
- speak.py
- test_computeruse.py
- test_providers.py
- load_config
- test_structured_memory.py
- test_kernel_unit.py
- test_kernel_integration.py
- JobStore
- webapp.py
- _allowing_kernel
- test_capabilities.py
- config.py
- EventBus
- test_webauth.py
- fastpaths.py
- realtime/__init__.py
- index/index.js
- display_local
- test_scheduling_unified.py
- scheduler.py
- computeruse/__init__.py
- store
- test_eval_gate.py
- VoiceEngine
- test_reflection_loop.py
- computeruse/tools.py
- test_skill_gate.py
- test_phase7_repro.py
- verify_suite.py
- test_netguard.py
- chat/index.js
- test_localserver.py
- dsa/__init__.py
- save_bundle
- run_agent
- welcome.py
- build_sft.py
- base.py
- _run
- test_commands.py
- test_exec_tools.py
- pages
- schema.js
- worker.py
- make-tabbar-icons.js
- classify_risk
- test_proactive.py
- StructuredMemory
- test_telemetry.py
- test_automation.py
- _Print
- cli.py
- systemctl.py
- kernel.py
- test_phase8_memory_planning.py
- transcribe.py
- ComputerUseSession
- test_guard.py
- md.py
- Training and Scale Plan
- search.py
- Desktop
- kernel/__init__.py
- Agent Interface chat classify match
- automation/events.py
- test_sandbox.py
- treehole/index.js
- test_api_card.py
- plan.py
- test_voice_tts.py
- EventBus
- run_dsa_graphs
- test_injection.py
- test_static_contracts.py
- Config
- test_jarvis_features.py
- automation_job
- test_rag.py
- AgentKernel
- SimpleNamespace
- page-chat.test.js
- run_suite
- localserver.py
- livekit/state.py
- secretscan.py
- CapabilityGate
- .__init__
- Context
- WindowsDesktop
- start_emergency_hotkey
- binary_tree.py
- transition
- AgentSession
- _no_fastpath
- offline.js
- EventBus
- dsa/verify.py
- LiveKitTransport
- test_pipeline.py
- moodscore.js
- test_verifier.py
- verifier.py
- train_router.py
- native/__init__.py
- main.go
- createAgent
- get_system_stats
- test_claim_grounding.py
- paths.py
- Active state design vivid blue outline
- radar/index.js
- run_offline
- Heap
- ScriptedClient
- StreamingTTS
- test_dsa.py
- test_eval_score.py
- package.json
- health.py
- permission.py
- ExecutionReceipt
- StreamingSTT
- prompts.js
- test_capability_report_is_honest_on_this_machine
- alerts.py
- web.py
- mic.py
- _extract_text_tool_calls
- _VecStore
- T
- shim-lifecycle.test.js
- ml_report.py
- commands/__init__.py
- ScreenshotStore
- Trie
- ClapDetector
- planner.js
- app-manifest.test.js
- live-ollama.test.js
- _denying_kernel
- test_plan_store.py
- Feature Status Authoritative
- summarize.py
- sandbox.py
- VoiceTransport
- createLlm
- QLoRA fine-tuning Qwen3 8GB 3050
- _FakeWin32
- commands/code.py
- bench.py
- files.py
- format.js
- conftest.py
- think.py
- UnionFind
- load_episodes
- _Semantic
- lexicon.js
- core/groups.js
- requirements.txt BEE Core
- RecordingClient
- BatterySource
- Live Voice Page
- BEE to JARVIS Roadmap
- FileChangeSource
- train.py
- BEE Security Model
- embed.py
- env
- Safe Computer Action Set
- Grok web UI screenshot showing gated conversation
- grace
- eval_probe
- _fresh_state
- Memory Layers and Nightly Consolidation
- Polars lazy scan filter group_by pipeline
- jest.night.config.js
- setup.js
- p7
- merge_export.py
- agent/__init__.py
- episodes/__init__.py
- evals/__init__.py
- Linux Core CI Job
- Bee4b Primary Orchestrator Model
- Computer Use Desktop Stack
- LiveKit Agent Stack
- requirements-vision.txt Vision Extras
- requirements-voice.txt Voice Stack
- Break down tasks SKILL
- browser SKILL
- DSA sorting graphs DP benchmark harness
- eval_status.py
- bench_model.py
- Constraint Planner Solver
- Windows Core CI Job
- Voice Optional Workflow
- Windows Desktop Optional Workflow
- Insight: unauthenticated Grok session is gated requiring signup to continue
- bee-telemetry
- Q: Why does load_config() connect Voice, Agent Loop, LLM Client, ToolBus and 40+ other communities?
- agent-probe.test.js
- _Resp
- FrozenDate
- _fn_skill_gate
- test_followup_classifier_separates_commands_from_nudges
- test_ramble_detector_covers_the_phrasings_the_live_model_actually_used
- test_grounded_fallback_does_not_quote_a_refusal_as_evidence

## God Nodes (most connected - your core abstractions)
1. `load_config()` - 136 edges
2. `run_agent()` - 76 edges
3. `AgentKernel` - 69 edges
4. `make_kernel()` - 69 edges
5. `Job` - 62 edges
6. `Context` - 58 edges
7. `JobWorker` - 56 edges
8. `JobStore` - 54 edges
9. `MockDesktop` - 51 edges
10. `VoiceEngine` - 50 edges

## Surprising Connections (you probably didn't know these)
- `OfflineAgent Lexicon Matcher Backend` --semantically_similar_to--> `FastPaths Deterministic Tier`  [INFERRED] [semantically similar]
  campus-life/docs/2026-10-12-design.md → docs/JARVIS_ARCHITECTURE.md
- `test_embedding_still_works_when_litellm_is_unavailable()` --uses--> `LLMClient`  [INFERRED]
  tests/test_streaming_contract.py → bee/agent/client.py
- `test_embedding_uses_a_provider_ref_litellm_actually_maps()` --uses--> `LLMClient`  [INFERRED]
  tests/test_streaming_contract.py → bee/agent/client.py
- `ctx()` --uses--> `Context`  [INFERRED]
  tests/test_commands.py → bee/agent/context.py
- `ctx()` --uses--> `Context`  [INFERRED]
  tests/test_engines_session.py → bee/agent/context.py

## Import Cycles
- 4-file cycle: `bee/agent/loop.py -> bee/tools/__init__.py -> bee/tools/spawn_tool.py -> bee/agent/spawn.py -> bee/agent/loop.py`

## Hyperedges (group relationships)
- **One agent interface with auto-selected backends** — campus_life_agent_interface, campus_life_llm_agent, campus_life_offline_agent [EXTRACTED 0.75]
- **Eval quality gate system: verify suite, 21 tasks, J3 model gate** — evals_report_verify_suite_71914, evals_tasks_21_task_gate, docs_production_readiness_model_gate_j3 [EXTRACTED 0.75]
- **Security hardening batch: kernel routing, bearer auth, netguard** — docs_production_readiness_single_kernel_routing, docs_security_bearer_token_auth, docs_security_netguard_ssrf [EXTRACTED 0.75]
- **Shared bearer-token auth across web surfaces** — bee_web_chat_ui, bee_web_face_visualizer, bee_web_live_voice_page, bee_web_auth_token [EXTRACTED 0.75]

## Communities (228 total, 29 thin omitted)

### Community 0 - "render.js"
Cohesion: 0.04
Nodes (102): resetStore(), storage, empty(), { loadComponent, tap, text, count, simulate, wxState, resetWxState }, badge(), { loadComponent, text, classes, count, simulate }, { loadComponent, allText, count, simulate }, moodscore (+94 more)

### Community 1 - "Server"
Cohesion: 0.20
Nodes (23): Bring Ollama up if it is not already. Returns True when the server is reachable…, start_background(), _cfg(), _launched(), Popen, Without OLLAMA_HOST the server BEE starts would sit on 11434 while BEE polls…, A flashing console or a pipe that fills up would make the assistant's boot…, Stand-in for the Ollama HTTP surface, with switchable reachability. (+15 more)

### Community 2 - "test_fastpaths.py"
Cohesion: 0.08
Nodes (31): _convert(), _attach_worker(), ctx(), DeadClient, _h(), fixture, Tests for fast paths (instant pure-Python answers), engine selection, and cloud…, One implementation: the same words through either surface produce the same… (+23 more)

### Community 3 - "LLMClient"
Cohesion: 0.06
Nodes (40): _is_gemini3plus(), LLMClient, LLMError, Exception, GENUINE streaming completion: `on_token(str)` is called for every content delta…, Native Ollama: POST /api/chat with stream:true (NDJSON deltas)., One LLM completion. Returns the normalized dict: {content: str|None,…, True for Gemini 3+ (gemini-3-flash-preview, gemini-3.6-flash, flash-… (+32 more)

### Community 4 - "test_voice_engine.py"
Cohesion: 0.07
Nodes (50): FakeTTS, Test double with the StreamingTTS lifecycle. Mirrors the real pipeline: begin()…, FakeKernel, FakeSTT, make_engine(), Voice engine tests (Phase 4) — true realtime conversation behavior. Required…, Kernel stand-in: run() 'works' for delay seconds (polling the cancel event like…, User barges in while BEE is thinking/speaking: TTS stops immediately, the task… (+42 more)

### Community 5 - "Job"
Cohesion: 0.09
Nodes (17): iso(), Job, parse_dt(), datetime, Persist a datetime CANONICALLY IN UTC (timezone rule, 2026-10-08)., JobWorker, datetime, EventBus (+9 more)

### Community 6 - "page-shop.test.js"
Cohesion: 0.05
Nodes (52): locate(), COMPARATORS, filter(), haversineKm(), isOpen(), toRad(), cats, ORIGIN (+44 more)

### Community 7 - "speak.py"
Cohesion: 0.13
Nodes (23): available(), _decode_to_wav(), _edge_tts_speak(), _play_media(), Path, py_voices(), _pyttsx3_speak(), Text-to-speech. Primary: pyttsx3 (offline; SAPI5 on Windows, espeak on Linux,… (+15 more)

### Community 8 - "test_computeruse.py"
Cohesion: 0.07
Nodes (37): ComputerAction, Risk after provenance: unproven click coordinates escalate to high (the risk…, Log/audit-safe view — NEVER includes the typed text payload, clipboard…, MockDesktop, Simulate the USER (or another app) changing the screen mid-task., Deterministic desktop for tests. Windows: add_window(); launchers:…, computeruse_emergency_stop(), STOP all active computer-control sessions immediately. Returns the number of… (+29 more)

### Community 9 - "test_providers.py"
Cohesion: 0.08
Nodes (40): LLMRequest, LLMResponse, Typed request envelope (preferred API). `request()` wraps `chat()`; all legacy…, Typed response envelope mirroring the `chat()` dict contract., _cloud_up(), Cloud tier is usable only if enabled, configured AND credentialed. Availability…, cloud_available(), env_key_for() (+32 more)

### Community 10 - "load_config"
Cohesion: 0.08
Nodes (41): load_config(), Path, reset_enabled_cache_for_tests(), build_default_tools(), _computeruse_builder(), tools_litellm(), Audit-pass regressions (2026-10-08): operator switches must have effects. Every…, voice.rt_barge_in / rt_partial_min_growth were dropped when building… (+33 more)

### Community 11 - "test_structured_memory.py"
Cohesion: 0.06
Nodes (57): _as_recall(), is_hardware_query(), MemoryRequest, parse(), Deterministic memory requests (Phase 3, Part C). 'Remember that my project is…, Remember my GPU from last time?' is a RECALL request. `_REMEMBER_RE` used to…, _kernel(), _mem() (+49 more)

### Community 12 - "test_kernel_unit.py"
Cohesion: 0.07
Nodes (32): MalformedArgsError, ToolBus (Phase 2) — the single dispatch point for agent tool calls. Every tool…, litellm/openai function schemas for the registered tools only., Execute a registered tool. Returns (result, seconds, ok, meta). meta:…, Build from the existing registered tool modules (bee.tools)., ToolBus, ToolDef, ToolTimeoutError (+24 more)

### Community 13 - "test_kernel_integration.py"
Cohesion: 0.07
Nodes (53): Acceptance audit P1-1: with a kernel attached, the agent loop must dispatch…, test_f2_loop_executes_tools_through_toolbus(), N4: the KERNEL owns task-scoped cancellation. A cancel event left SET by a…, Loop breaker gap: the exact-args breakers never match when a small model re-…, Retrying one failing call with reworded arguments used to burn the whole budget…, test_n4_stale_cancel_event_does_not_poison_new_task(), test_repeated_denials_lock_tools_instead_of_burning_the_budget(), test_repeated_tool_failures_lock_without_punishing_good_work() (+45 more)

### Community 14 - "JobStore"
Cohesion: 0.06
Nodes (22): ExecutionHistory, JobExecution, _new_id(), Notification, Persisted per-job execution history (append-only JSONL in JobStore)., _atomic_write(), JobStore, Path (+14 more)

### Community 15 - "webapp.py"
Cohesion: 0.08
Nodes (45): litellm stream=True — per-chunk deltas (works for Ollama + Gemini)., _plate(), _todo(), Command, get(), available(), cancel_task(), chat() (+37 more)

### Community 16 - "_allowing_kernel"
Cohesion: 0.10
Nodes (21): _allowing_kernel(), A kernel that grants every permission, so a test can observe the LOOP's own…, dsa_gcd_lcm spent 48 tool calls on one task: a 3B model that re-runs broken…, Same loop, different symptom: six SUCCESSFUL calls of one tool with ever-…, dsa_gcd_lcm / dsa_lis / dsa_graph, live: tools=0 and an answer that DESCRIBES a…, A45a: the model displayed code that stores the results in variables and never…, The read-out must only be appended when there is no output of its own —…, When permission is refused the answer must not pretend the computation happened… (+13 more)

### Community 17 - "test_capabilities.py"
Cohesion: 0.09
Nodes (29): CapabilityStore, _Entry, IntEnum, Path, User-configurable policies. File format (config/capabilities.yaml):…, Task-scoped grants die with the task — never carried over., Risk, _gate() (+21 more)

### Community 18 - "config.py"
Cohesion: 0.05
Nodes (45): AlertsCfg, _apply_env(), AutomationCfg, _build_from_yaml(), ClapCfg, CloudCfg, ComputerUseCfg, _dotenv_defines() (+37 more)

### Community 19 - "EventBus"
Cohesion: 0.19
Nodes (9): EventBus, callable, Typed kernel event bus (Phase 2) — a thin facade over the project's ONE shared…, _emit(), AgentEvent, AgentEventKind, Enum, One typed event. The kernel emits these; an EventBus fans them out to UI… (+1 more)

### Community 20 - "test_webauth.py"
Cohesion: 0.07
Nodes (37): reset_token_for_tests(), test_web_livekit_and_face_endpoints(), _client(), _client_with_kernel(), dash_env(), _page(), fixture, parametrize (+29 more)

### Community 21 - "fastpaths.py"
Cohesion: 0.07
Nodes (34): _brightness(), _cim(), FastExec, FastPath, _files_list(), _files_list_reply(), _http_text(), _lock() (+26 more)

### Community 22 - "realtime/__init__.py"
Cohesion: 0.08
Nodes (29): VoiceEngine (Phase 4) — the realtime conversation orchestrator. Pipeline (one…, bee.voice.realtime — Phase 4 true-realtime voice. Clean layering:…, InvalidVoiceTransition, Enum, Exception, str, Voice state machine (Phase 4). The VOICE layer owns this state machine — and…, Engine tunables (defaults mirror config.yaml voice: rt_* fields). (+21 more)

### Community 23 - "index/index.js"
Cohesion: 0.07
Nodes (36): canCheck(), coverage(), dayIndex(), doCheckin(), groupByZone(), latestFor(), list(), streak() (+28 more)

### Community 24 - "display_local"
Cohesion: 0.14
Nodes (17): display_local(), Render a stored (UTC-canonical) timestamp in the USER'S timezone — for display…, _cancel(), _clock(), _list(), parse_when(), datetime, /remind — natural-language reminders on the durable job store. Usage: /remind… (+9 more)

### Community 25 - "test_scheduling_unified.py"
Cohesion: 0.13
Nodes (34): effective_max_attempts(), Retry budget for a job (scheduling unification, 2026-10-08). Destructive/side-…, MemoryStack, Facade: memory.<kind> gives the kernel one object per store. Phase 3:…, _cron_to_trigger(), Return (JobTrigger, note) or raise ValueError with the reason., scheduler_tools(), Ctx (+26 more)

### Community 26 - "scheduler.py"
Cohesion: 0.08
Nodes (34): _note(), _fn_build_sft(), _fn_consolidate(), _fn_flush_memory_index(), _fn_rebuild_vectors(), _fn_teach_back(), _fn_train_router(), diary_add() (+26 more)

### Community 27 - "computeruse/__init__.py"
Cohesion: 0.08
Nodes (24): is_credential_target(), Computer-use action model (Phase 5) — one safe desktop action. Every action the…, Heuristic gate for the 'no credential entry' rule (checked on the SEMANTIC…, bee.computeruse — Phase 5: SAFE computer use. Desktop capture -> structured UI…, Computer-use privacy (Phase 5). Rules enforced in code (not just documented):…, active_sessions(), default_windows_key_state(), ComputerUseSession (Phase 5) — the closed-loop desktop executor. Loop… (+16 more)

### Community 28 - "store"
Cohesion: 0.09
Nodes (33): { createStore }, { KEY }, request(), save(), store(), tzOffsetMin(), instance(), groups (+25 more)

### Community 29 - "test_eval_gate.py"
Cohesion: 0.10
Nodes (35): _fn_model_gate(), J3: model-upgrade quality gate (candidate vs recorded baseline)., baseline_record(), load_baselines(), model_quality_gate(), _now(), promote_model(), J3 — model-upgrade quality gate. The local model is a moving target (SFT… (+27 more)

### Community 30 - "VoiceEngine"
Cohesion: 0.13
Nodes (6): Process one ~100 ms frame. NEVER raises — failures route to ERROR., Resolve a held answer once the verifier has judged it., Owns the voice state machine and timing; delegates all task logic to the kernel…, ERROR -> IDLE (or LISTENING when always-on) once the transport is up., Blocking transport pump with reconnect + capped backoff. stop() (or Ctrl-C)…, VoiceEngine

### Community 31 - "test_reflection_loop.py"
Cohesion: 0.05
Nodes (50): _all_bullets_empty(), `worked: None / failed: None / next: None` teaches nothing and burns the prompt…, A lesson is not a note to self — `context.recent_lessons()` injects it into…, Trivial tasks (canned replies, one-shot local answers, no tools) yield no…, LLM-based self-review. Returns the lesson text ("" if skipped)., reflect(), time_stamp(), _trivial() (+42 more)

### Community 32 - "computeruse/tools.py"
Cohesion: 0.10
Nodes (35): DesktopError, make_desktop(), RuntimeError, Default desktop factory — WindowsDesktop on Windows, DesktopError elsewhere…, computer_clipboard(), computer_input(), computer_observe(), computer_stop() (+27 more)

### Community 33 - "test_skill_gate.py"
Cohesion: 0.16
Nodes (32): bump_skill(), candidate_names(), gate_candidates(), gate_skill(), meta_path(), _now(), Path, J2 — skill versioning + eval gate. A skill (skills/<name>/SKILL.md [+… (+24 more)

### Community 34 - "test_phase7_repro.py"
Cohesion: 0.10
Nodes (36): _compat_issue(), default_meta(), load(), load_status(), predict(), ML route classifier — learns local|cloud routing from BEE's own episodes.…, Training-time environment metadata recorded INTO the artifact (Phase 7). Keys:…, when compatible; otherwise a clear, actionable message (Phase 7). MAJOR scikit-… (+28 more)

### Community 35 - "verify_suite.py"
Cohesion: 0.11
Nodes (31): Max revenue cutting a rod of length n (prices[i] for length i+1). O(n^2)., rod_cut(), luhn_ok(), _gen_expr(), _is_subseq(), _load_bench(), _luhn_check_digit(), main() (+23 more)

### Community 36 - "test_netguard.py"
Cohesion: 0.10
Nodes (30): FetchResult, _ip_class(), NetGuardError, Exception, SSRF-hardened HTTP fetching for model-driven web tools. The `web_fetch` tool…, Fetch a URL under the full SSRF policy. Raises NetGuardError on any violation.…, Raised when a URL or its fetch violates the SSRF policy., Return a blocking class name for a non-public IP, else None. (+22 more)

### Community 37 - "chat/index.js"
Cohesion: 0.10
Nodes (31): byId(), current(), expire(), open(), peer(), push(), reap(), send() (+23 more)

### Community 38 - "test_localserver.py"
Cohesion: 0.15
Nodes (20): compact_messages(), Cheap prompt-size estimator used for history budgeting. A59 showed `chars/4`…, Drop oldest tool-history pairs before the model drops them for us. Ollama…, _token_estimate(), _ctx(), _DownClient, _fat_tools(), _pairs() (+12 more)

### Community 39 - "dsa/__init__.py"
Cohesion: 0.08
Nodes (24): BEE DSA library — curated, tested building blocks + benchmark harness. Usage:…, Segment tree with range query + point update. O(log n) each. Default op = sum.…, Inclusive range [lo, hi]., SegmentTree, bubble_sort(), counting_sort(), heap_sort(), insertion_sort() (+16 more)

### Community 40 - "save_bundle"
Cohesion: 0.16
Nodes (17): make_mlp(), _NUM_FEAT_NAMES(), Path, The DL route model: a **feature-scaled** neural net. Scaling is the crux — TF-…, Persist the artifact WITH training metadata (Phase 7). Callers that know the…, save_bundle(), _features_matrix(), _make_data() (+9 more)

### Community 41 - "run_agent"
Cohesion: 0.04
Nodes (70): LLM client: LiteLLM primary, native Ollama HTTP fallback. chat(name, messages,…, AgentResult, _audit_record(), _diary(), _finish(), _fmt_result_text(), _golden(), _grounded_fallback() (+62 more)

### Community 42 - "welcome.py"
Cohesion: 0.10
Nodes (32): _chrome_executable(), _due(), focus_or_launch_ide(), _foreground_hwnd(), _ide_executable(), _main_hwnd_win32(), _monitor_rects(), open_url_chrome() (+24 more)

### Community 43 - "build_sft.py"
Cohesion: 0.12
Nodes (24): build(), load_golden(), main(), _no_tool_single_turn(), paraphrase_augment(), Path, quality_score(), Episodes + cloud goldens → SFT dataset (Qwen3 chat format, loss-masked, PII-… (+16 more)

### Community 44 - "base.py"
Cohesion: 0.08
Nodes (33): _check_bounds(), _ev(), eval_safe(), _guarded_pow(), _pow_func(), AST, Path, Shared helpers for tools: the T registry type, output envelopes, safe eval,… (+25 more)

### Community 45 - "_run"
Cohesion: 0.12
Nodes (30): automate_tools(), _convert(), _count(), _dedupe(), _fill(), _find(), _inventory(), _jsonq() (+22 more)

### Community 46 - "test_commands.py"
Cohesion: 0.09
Nodes (25): line = full command line (leading '/' ok, e.g. '/draft email ...'). Returns…, run(), ctx(), DeadClient, fixture, BEE command system + Phase-4 hot-path regression tests. Covers: - config.yaml…, Regression: UnboundLocalError (res_v) when the guard ALLOWED an exec tool., Scripted LLMClient stand-in — no network, no model. (+17 more)

### Community 47 - "test_exec_tools.py"
Cohesion: 0.11
Nodes (30): envelope(), Tool-result dict. `limit` overrides the default truncation cap so a tool's own…, _kill_tree(), Cancellable subprocess execution (J1 — audit item 3). The old exec tools used…, Run `cmd`; returns (returncode, stdout, stderr, kind) with kind in {'ok',…, run_cancelable(), _child_env(), code_tools() (+22 more)

### Community 48 - "pages"
Cohesion: 0.06
Nodes (31): lazyCodeLoading, pages, permission, scope.userLocation, requiredPrivateInfos, desc, sitemapLocation, style (+23 more)

### Community 49 - "schema.js"
Cohesion: 0.11
Nodes (24): migrate(), schema(), clone(), createStore(), load(), persist(), read(), reset() (+16 more)

### Community 50 - "worker.py"
Cohesion: 0.09
Nodes (26): Durable automation + proactive agent (Phase 6). Objects (per the Phase 6 spec):…, Durable automation models (Phase 6; UTC-canonical storage, 2026-10-08). Job /…, JobQueue, JobQueue (Phase 6) — the concurrency-control object. Two guarantees, both…, Claim a job for execution. Refused if already inflight or the global cap is…, get_tz(), next_run(), _parse_hhmm() (+18 more)

### Community 51 - "make-tabbar-icons.js"
Cohesion: 0.09
Nodes (24): app, fs, path, { render, ICONS, OFF, ON, SIZE }, ROOT, zlib, chunk(), coverage() (+16 more)

### Community 52 - "classify_risk"
Cohesion: 0.10
Nodes (35): Attribute, analyze_python(), classify_risk(), _escalate(), _module_for_attr(), _open_write_mode(), Call, IntEnum (+27 more)

### Community 53 - "test_proactive.py"
Cohesion: 0.15
Nodes (21): ProactivePolicy, ProactiveRule, Default-deny gate between the event bus and any action (Phase 11). check(event)…, quiet_hours=(start,end) local hours, wrap-aware ((22, 7) = 22:00 to 07:00).…, _ev(), Phase 11 — PROACTIVE JARVIS + EVENT INTELLIGENCE (2026-10-08). The proactive…, When this file appears, tell me' — FileChangeSource -> bus -> policy -> notify,…, The event is information; only an explicitly authorized proactive rule may turn… (+13 more)

### Community 54 - "StructuredMemory"
Cohesion: 0.10
Nodes (16): MemoryItem, _now(), Path, Delete by id, or (for 'Forget that.') the LAST matched item when a query is…, Compact, source-labeled digest for context injection., Purge expired + long-tombstoned items; returns count removed., Timezone-safe expiry check (fixed 2026-10-08): expiries are stored UTC-…, StructuredMemory (+8 more)

### Community 55 - "test_telemetry.py"
Cohesion: 0.08
Nodes (23): _bars(), build(), _kpi(), Path, Self-contained monitoring dashboard → metrics/dashboard.html. Reads…, Snapshot the dashboard to metrics/dashboard.html (the `/dashboard` command).…, The dashboard as HTML. `refresh_seconds` > 0 makes the page reload itself,…, render() (+15 more)

### Community 56 - "test_automation.py"
Cohesion: 0.08
Nodes (60): JobTrigger, Ctx, due_one_time(), FakeClock, FakeKernel, FakeResult, FakeTask, _force_running() (+52 more)

### Community 57 - "_Print"
Cohesion: 0.27
Nodes (3): _creator(), _Print, _try_rich()

### Community 58 - "cli.py"
Cohesion: 0.05
Nodes (68): create_context(), Single application-context factory (Phase 1: replaces the 7+ duplicated…, ask_engine(), engine_labels(), load_engine(), override_for(), Engine selection: which brain does BEE use by default? Asked once at first…, Human-facing engine labels. The api-cloud label reflects the ACTUAL configured… (+60 more)

### Community 59 - "systemctl.py"
Cohesion: 0.11
Nodes (32): _battery(), _specs(), _hardware_note(), Live inventory for a recall about the box itself ('' / {} if not one)., format_hardware(), get_battery(), get_hardware(), _keybd() (+24 more)

### Community 60 - "kernel.py"
Cohesion: 0.10
Nodes (30): _best_lines(), _qwords(), AgentKernel (Phase 2) — the single agent runtime. Flow (kernel-owned; the LLM…, Friendly name for where a memory hit came from. The hybrid index stores…, The bullets inside a memory chunk that actually answer this query. A chunk is…, _src_label(), Observation, What the kernel SAW happen for one tool call (never the model's claim). (+22 more)

### Community 61 - "test_phase8_memory_planning.py"
Cohesion: 0.10
Nodes (27): Action, new_id(), Plan, Kernel data model (Phase 2) — the typed objects the agent runtime is built…, One executable step in a plan. `tool` is a registered ToolBus name; None means…, Kernel-owned execution plan (Phase 8: typed + validated BEFORE ToolBus). kind:…, build_plan(), classify_intent() (+19 more)

### Community 62 - "transcribe.py"
Cohesion: 0.10
Nodes (26): BEE voice: mic capture -> faster-whisper (local) -> text; text -> TTS. Optional…, _ensure_gate(), print_status(), Voice command loop: listen -> (wake word) -> task -> speak. Usage in REPL:…, If text starts with/contains the wake word, return the remainder (or None)., Terminal approval for capability asks in voice mode. Voice has no kernel…, Attach a capability gate to kernel-less voice contexts. The REPL/web/LiveKit…, run_voice_loop() (+18 more)

### Community 63 - "ComputerUseSession"
Cohesion: 0.15
Nodes (12): Log/audit-safe entry for one executed (or blocked) action., redact_entry(), ComputerUseSession, _now(), Run fn() in a worker thread; join(timeout). If it overruns, the call is…, One task's computer-control state: budget, provenance, stop state, redacted…, True iff (x, y) lies inside a rect seen in the LAST observe., One action, closed-loop: snapshot -> act -> snapshot -> verify. Returns a dict… (+4 more)

### Community 64 - "test_guard.py"
Cohesion: 0.15
Nodes (14): classify(), preview_call(), Returns (action, reason) where action in allow|ask|deny., One line saying what the user is actually being asked to allow. The prompt used…, Guard rule table — labeled commands. Run: python tests/test_guard.py, The kernel asks about a CAPABILITY with args={} (a capability spans several…, Approval is worthless if the prompt is blank. Before this, the approver printed…, test_capability_prompt_names_the_pending_call() (+6 more)

### Community 65 - "md.py"
Cohesion: 0.13
Nodes (22): add_facts(), all_chunks(), chunk_md(), _clean_fact(), _fact_core(), _finger(), is_transcript(), memory_search() (+14 more)

### Community 66 - "Training and Scale Plan"
Cohesion: 0.22
Nodes (10): Bee-8B QLoRA Local Brain, BEE LLM Component Design, J3 Model Upgrade Quality Gate, Constitutional AI and RLAIF Pipeline, Training and Scale Plan, 3D Parallelism TP PP DP Design, Verification Report, Verify Suite 71914 Checks All Pass (+2 more)

### Community 67 - "search.py"
Cohesion: 0.12
Nodes (23): auto_context(), needs_context(), Hybrid RAG over BEE memory — vector + keyword fused with Reciprocal Rank…, RRF fusion of vector (when available) and keyword rankings., Markdown context block for the system/user message, or '' if not needed., retrieve(), BEE memory: Markdown (transparent) + optional LanceDB vectors (semantic search)., _dirty_file() (+15 more)

### Community 68 - "Desktop"
Cohesion: 0.08
Nodes (5): Desktop, Protocol, Desktop abstraction (Phase 5). ComputerUseSession talks ONLY to this protocol.…, WindowInfo, test_active_window_falls_back_when_the_api_raises()

### Community 69 - "kernel/__init__.py"
Cohesion: 0.06
Nodes (20): BEE Agent Kernel (Phase 2) — one coherent agent runtime. Objects: AgentSession,…, EntityMemory, EpisodicMemory, ProceduralMemory, Protocol, Short-horizon state for the active session (kernel-owned, in-process)., What happened, when (tasks, tool calls, outcomes)., Durable facts: profile, long-term notes, RAG corpus. (+12 more)

### Community 70 - "Agent Interface chat classify match"
Cohesion: 0.18
Nodes (12): Agent Interface chat classify match, Honesty Rules and Labels, LlmAgent Local Ollama Backend, Campus Life Mini Program, Mood Radar Six Axes, OfflineAgent Lexicon Matcher Backend, Page to Component Test Shim, Local Storage Quota Prune Path (+4 more)

### Community 71 - "automation/events.py"
Cohesion: 0.13
Nodes (16): AppEventSource, EventSource, NetworkSource, _PollSource, Internal EventBus + proactive policy (Phase 6). An EventBus carries internal…, Adapter interface: a source PUBLISHES events; it never acts., Shared poll loop: run `scan()` on an interval, never crash the loop., Edge-triggered connectivity events: network.down / network.restored. Probes by… (+8 more)

### Community 72 - "test_sandbox.py"
Cohesion: 0.27
Nodes (13): sandbox_tools(), _ctx(), R, GPU fallback tests for the Docker sandbox tool (no docker calls are made —…, Operator knobs: disable read-only + run as image default user (old root image…, Stub subprocess.run: track only `docker run` argv; probes get plain success., Phase 1: untrusted code must run with the full container boundary., test_gpus_flag_with_nvidia_runtime() (+5 more)

### Community 73 - "treehole/index.js"
Cohesion: 0.13
Nodes (21): add(), anonId(), close(), counts(), dayKey(), validate(), WORDS, agent (+13 more)

### Community 74 - "test_api_card.py"
Cohesion: 0.33
Nodes (8): module_api_card(), _module_source(), A50: a request that names one of BEE's own modules gets that module's REAL…, test_an_attribute_path_resolves_to_its_module(), test_card_lists_the_real_public_signatures(), test_names_that_are_not_project_modules_add_nothing(), test_the_card_is_bounded(), test_the_model_sees_the_card_in_the_request()

### Community 75 - "plan.py"
Cohesion: 0.15
Nodes (23): _date(), classify(), _daily_blocks(), _dispatch(), _llm(), _load(), _next_id(), _open() (+15 more)

### Community 76 - "test_voice_tts.py"
Cohesion: 0.11
Nodes (22): _speak(), Streaming-TTS and local-playback regressions (audit 2026-10-08). Two real…, No shell-out player may come back: it only decoded WAV, so MP3 output…, Backend order must degrade, never claim a silent success., (data chunk size field, actual payload bytes)., A streamed (0xFFFFFFFF) header decodes fine in Python but winsound cannot size…, Piping ffmpeg WAV output to stdout produces unknown-size headers; the fallback…, The regression end-to-end: a real MP3 (what edge-tts produces) must become a… (+14 more)

### Community 77 - "EventBus"
Cohesion: 0.13
Nodes (12): Inspect the visible UI (read-only). Returns the structured snapshot the agent…, EventBus, callable, THE shared EventBus (audit item 9 — one implementation, project-wide). Before…, Convenience: receive every event (the kernel facade uses this)., Routing key: explicit name attr (BusEvent) or kind.value (AgentEvent)., Dispatch; returns the number of handlers INVOKED (a handler that raises is…, _Ev (+4 more)

### Community 78 - "run_dsa_graphs"
Cohesion: 0.11
Nodes (23): _adj(), bellman_ford(), bfs(), build_adj(), dfs_order(), dijkstra(), floyd_warshall(), has_cycle_undirected() (+15 more)

### Community 79 - "test_injection.py"
Cohesion: 0.16
Nodes (19): _blocked(), _model_views(), Prompt-injection corpus (acceptance audit YELLOW: "no injection corpus test…, A task-scoped grant suppresses the escalation (documented); revoking the task's…, Same rule end-to-end: approve before the fetch, deny after — the post-fetch…, End-to-end: what the MODEL actually sees must be un-escapable., Re-aim the bus's registered handler — the loop dispatches through ToolBus,…, A blocked tool call records its verdict inside the result payload. (+11 more)

### Community 80 - "test_static_contracts.py"
Cohesion: 0.14
Nodes (22): _collect(), _collect_class(), find_mismatches(), _function_contexts(), _lookup_method(), _mismatch(), AST, Call (+14 more)

### Community 81 - "Config"
Cohesion: 0.07
Nodes (39): _embedded_expr(), _heuristic(), _is_det(), math_expr(), _normalize_expr(), Hybrid routing — four tiers, fused heuristics + learned ML. Tiers (in order of…, True when the residue is arithmetic whose only names are math functions. The…, Extract the arithmetic from a prose-wrapped ask: 'Use the calculator tool to… (+31 more)

### Community 82 - "test_jarvis_features.py"
Cohesion: 0.06
Nodes (35): match(), _photo(), Remind me what my passport number is' is a question, not a reminder. The fast…, What is in the oven' must not be answered with a directory listing., What hardware do I need to run llama" is a purchase question; 'what is the spec…, Non-Windows or a blocked CIM query must not produce a fake spec sheet., The eval's own sentence: 'Run python: <snippet> — list which sorts are correct…, The 120-char ceiling was global before; the per-path `max_len` must not quietly… (+27 more)

### Community 83 - "automation_job"
Cohesion: 0.18
Nodes (21): automation_job(), _days_from(), _num(), automation_job tool (Phase 6) — user-facing automation management. The user…, Cast a model-supplied number with a message that names the field and the…, Accept the integers the schema documents and the day names a small model writes…, _trigger_from(), _worker() (+13 more)

### Community 84 - "test_rag.py"
Cohesion: 0.09
Nodes (20): Deterministic recall@k: for each (question, answer_key), did a chunk containing…, recall_eval(), _score(), _FakeStore, RAG — trigger detection + deterministic recall@k. Run: python tests/test_rag.py, The write path only queues — it must never block on an embedding call., A maintenance job the `scheduler.enabled` switch does not stop is the defect…, Regression against the way this feature was first written wrong:… (+12 more)

### Community 85 - "AgentKernel"
Cohesion: 0.14
Nodes (13): _agent_stub(), AgentKernel, _hw_conflict(), Warn when a stored spec contradicts the machine standing in front of us.…, First-class cancellation: stop the active task safely., Post-task self-review, gated by `learning.reflect`. Reflection is an…, Persist enough of the in-flight task to RESUME after a crash (J1). Redacted,…, Interrupted (non-terminal) checkpoints, oldest first. (+5 more)

### Community 86 - "SimpleNamespace"
Cohesion: 0.14
Nodes (13): skill_tools(), SimpleNamespace, test_model_gate_disabled_skips_evaluation(), test_remind_reports_errors_rather_than_raising(), _FakeResp, One stand-in that satisfies both call shapes: `chat()` reads…, env(), fixture (+5 more)

### Community 87 - "page-chat.test.js"
Cohesion: 0.08
Nodes (20): { createLlm }, offlineEngine, groups, INTERESTS, chat, groups, agent, chat (+12 more)

### Community 88 - "run_suite"
Cohesion: 0.12
Nodes (20): eval_approver(), _isolated_memory(), _isolated_telemetry(), Path, The permission prompt the eval answers on the user's behalf. `file_write` is…, Leave every source file exactly as the run found it — by bytes, not by git.…, Public entry: the run happens against an isolated copy of memory, and the…, only: substring match (str) or explicit id list (list) — for batched runs.… (+12 more)

### Community 89 - "localserver.py"
Cohesion: 0.15
Nodes (19): _base(), _boot(), _child_env(), exe_path(), _is_local(), _launch(), _model_present(), Start the local model server when the user expects it and it is not running.… (+11 more)

### Community 90 - "livekit/state.py"
Cohesion: 0.14
Nodes (17): _bearer_token(), get_state(), _push(), Live-voice shared state — HTTP push bridge (replaces the temp-JSON file). The…, Last state recorded in THIS process (debug/diagnostics). The web UI reads its…, Same source the webapp resolves from: BEE_WEB_TOKEN env, else the per-server…, Record the state locally (debug) and push it to the web UI., Best-effort POST to the web UI. Returns True on 2xx. (+9 more)

### Community 91 - "secretscan.py"
Cohesion: 0.16
Nodes (19): Finding, _is_binary(), main(), mask(), Path, Lightweight secret detection for source / generated-file audits. Usage: python…, Scan the project tree (excluding .env and data dirs). Sorted, stable., Safe form of a credential for logs: prefix + length only. (+11 more)

### Community 92 - "CapabilityGate"
Cohesion: 0.16
Nodes (15): capabilities_for(), Capability, CapabilityGate, GateDecision, Capability-based authorization (Phase 3, Part A/B). Capabilities are coarse…, Capabilities required to run `tool` with these args (base + escalation)., Pre-execution authorization. `confirmer(capability, reason) -> bool` is the…, test_code_run_delete_escalation() (+7 more)

### Community 93 - ".__init__"
Cohesion: 0.11
Nodes (6): _Entity, _Episodic, _Procedural, Entity memory over the structured store (type='entity')., Kernel's in-memory working set, scoped by task (global notes use "")., _Working

### Community 94 - "Context"
Cohesion: 0.05
Nodes (51): _api_lines(), build_sub_system(), build_system_prompt(), Context, _doc1(), _module_hint(), Path, Per-turn context assembly: system prompt, skills index, memory pointers. (+43 more)

### Community 95 - "WindowsDesktop"
Cohesion: 0.13
Nodes (3): Real desktop (Windows-first). Lazy imports; missing deps -> DesktopError.…, Resolve the foreground window from its handle directly. The old version…, WindowsDesktop

### Community 96 - "start_emergency_hotkey"
Cohesion: 0.14
Nodes (14): hotkey_state(), HotkeyStopper, Arm the global stop combo once per process (idempotent). Called when the first…, Introspection for /health and /cu status: is the stop combo live?, Test/shutdown hook — retire the poller., Polls a key-combo (injectable for tests) and fires the emergency stop. On…, One poll cycle. Returns True if the stop fired on this poll., start_emergency_hotkey() (+6 more)

### Community 97 - "binary_tree.py"
Cohesion: 0.20
Nodes (19): bst_contains(), bst_insert(), count_nodes(), from_sorted(), height(), inorder(), is_valid_bst(), lca() (+11 more)

### Community 98 - "transition"
Cohesion: 0.16
Nodes (17): Single-shot LLM task for slash commands — SAME kernel infrastructure (provider…, str, Task, TaskState, _ts(), can_transition(), InvalidTransitionError, Exception (+9 more)

### Community 99 - "AgentSession"
Cohesion: 0.13
Nodes (12): AgentSession, Path, Returns one of: ('cancel', <active task text or ''>) — user wants to stop…, Compact state block the kernel can inject so the model has the conversation…, test_session_context_block(), test_session_followup_resolution(), test_session_persistence_round_trip(), test_05_corrupt_session_file_degrades_to_new() (+4 more)

### Community 100 - "_no_fastpath"
Cohesion: 0.16
Nodes (17): _no_fastpath(), no function calls were provided / the available functions are…' is the model…, These two tests aim at the loop's wrap-up logic. Listing the workspace is now…, math_sieve on the live box: 39.9 s, tools=0, and the shipped answer was `I'm…, The fix must not turn a recoverable ramble into a declared failure: one ramble,…, plan_complex, live: '…Use the planner tool.' answered with 'None of the…, test_a_wrap_pass_that_still_rambles_becomes_an_honest_fallback(), test_an_answer_that_only_rambles_once_is_still_wrapped_normally() (+9 more)

### Community 101 - "offline.js"
Cohesion: 0.17
Nodes (19): bankFor(), beforeFragment(), bigrams(), chat(), classify(), hits(), idfFactory(), L (+11 more)

### Community 102 - "EventBus"
Cohesion: 0.11
Nodes (9): BusEvent, EventBus, match supports three key shapes: {"name": "device.memory_low"} the event name…, Synchronous in-process bus — a thin facade over the project's ONE shared…, Publish; returns the number of handlers that ran. The proactive policy gate is…, kernel and automation buses must be thin facades over bee.events., test_one_implementation_two_facades(), A poller that outlives the worker is an orphan thread that keeps publishing… (+1 more)

### Community 103 - "dsa/verify.py"
Cohesion: 0.15
Nodes (26): coin_change(), coin_change_count(), edit_distance(), knapsack(), lcs(), lis(), Classic dynamic-programming recipes with complexity notes., # of (unordered) ways to make amount. O(amount * len(coins)). (+18 more)

### Community 104 - "LiveKitTransport"
Cohesion: 0.07
Nodes (16): _agent_token(), _decode_audio(), LiveKitTransport, LiveKit as a VoiceTransport (Phase 4). Implements the transport protocol…, Room JWT for the agent participant (room join + publish/subscribe)., Nearest-neighbor mono s16 resample (good enough for voice)., Decode TTS bytes (mp3 or wav) to mono s16le @ to_rate via PyAV. PyAV ships with…, A LiveKit room behind the VoiceTransport protocol. (+8 more)

### Community 105 - "test_pipeline.py"
Cohesion: 0.14
Nodes (22): Chat messages with `loss` flags from a stored episode row. Returns (messages,…, row_to_messages(), Sanitize episodes for export/training: PII scrub + size bounds. The training…, Returns (clean_row_copy, total_redactions)., scrub_episode(), _scrub_str(), detect_type(), _last_ev() (+14 more)

### Community 106 - "moodscore.js"
Cohesion: 0.17
Nodes (16): attached(), { polygon }, recompute(), AXES, clamp100(), KEYWORDS, localDay(), mentions() (+8 more)

### Community 107 - "test_verifier.py"
Cohesion: 0.11
Nodes (16): _calc(), Verifier — deterministic claim checks against episode events + disk. Run:…, Did any tool run?' is far too weak. Live evidence: the model made 23 harmless…, The rule must not demand evidence for prose it cannot resolve to a target, or…, I ran out of steps…" is ordinary speech, but 'ran' sat in the claim verb list,…, The eval produced `I executed the shell command 'git reset --hard HEAD~1'` with…, test_a_claim_must_match_a_receipt_not_just_any_receipt(), test_a_claim_without_a_quoted_target_needs_only_some_receipt() (+8 more)

### Community 108 - "verifier.py"
Cohesion: 0.15
Nodes (18): _calc_checks(), _claim_checks(), _claimed_targets(), _clause_start(), _file_checks(), _hedged(), _opened_urls(), _phantom_file_checks() (+10 more)

### Community 109 - "train_router.py"
Cohesion: 0.17
Nodes (16): features(), dataset_version(), evaluate_classifier(), imbalance_report(), label_row(), main(), Episodes → ML route classifier (TF-IDF + LogisticRegression). Labels derived…, `argv`/`min_samples` allow in-process callers (scheduler) to set the sample… (+8 more)

### Community 110 - "native/__init__.py"
Cohesion: 0.16
Nodes (18): build(), _client(), _create_flags(), ensure(), healthy(), _install_go(), _launch(), BEE native subsystem — a Go-built system-telemetry daemon. Python is excellent… (+10 more)

### Community 111 - "main.go"
Cohesion: 0.20
Nodes (18): cpuPct(), ftVal(), getBattery(), getDisk(), getRam(), healthHandler(), main(), round1() (+10 more)

### Community 112 - "createAgent"
Cohesion: 0.35
Nodes (10): createAgent(), chat(), classify(), decide(), explain(), mode(), ready(), setPreference() (+2 more)

### Community 113 - "get_system_stats"
Cohesion: 0.14
Nodes (15): _sysstats(), Fast native stats, or None if the daemon is unavailable., stats(), format_system_stats(), get_system_stats(), CPU / RAM / disk / battery. Native-first: query the resident Go telemetry…, test_get_system_stats_parse(), test_stats_no_battery() (+7 more)

### Community 114 - "test_claim_grounding.py"
Cohesion: 0.19
Nodes (17): verify(), _ok_event(), A47/A48 — an answer's file claims are checked against the disk, and a run of…, The A56 gap in the other direction: no 'I', no preposition — 'Saved x.txt' with…, Episode events store tool output under 'result'; the receipt blob only read…, A56: the answer denies the action, and the claim check read the negation's own…, test_a_bare_saved_filename_is_still_a_claim(), test_a_claimed_file_that_really_exists_passes() (+9 more)

### Community 115 - "paths.py"
Cohesion: 0.05
Nodes (42): Episode, Episode logger — persist complete task episodes for the data pipeline. Each…, Serialize + REDACT before persistence. Episodes feed SFT builds and cloud…, Qwen3/OpenAI chat format with `loss` flag for masking tool/user turns. Returns…, _short(), force_reset_throttle(), Size-bounded rotation for append-only JSONL streams (M13 — audit item 2). Every…, Rotate `path` if it has grown past max_bytes. Returns True if a rotation… (+34 more)

### Community 116 - "Active state design vivid blue outline"
Cohesion: 0.18
Nodes (18): Active state design vivid blue outline, explore.png inactive location pin icon gray, explore-on.png active location pin icon blue, Explore tab concept location pin discovery, Inactive state design muted slate gray outline, index.png inactive home house icon gray, index-on.png active home house icon blue, Index Home tab concept house (+10 more)

### Community 117 - "radar/index.js"
Cohesion: 0.16
Nodes (14): label(), LABELS, ORDER, events(), fmt, mood, moodscore, onDays() (+6 more)

### Community 118 - "run_offline"
Cohesion: 0.21
Nodes (15): Deterministic offline fallback — real answers for a narrow task class when…, Returns a deterministic answer, or an honest capability message., run_offline(), _try_list(), _try_math(), _try_sort(), Offline deterministic fallback. Run: python tests/test_offline.py, test_fallback_message() (+7 more)

### Community 119 - "Heap"
Cohesion: 0.19
Nodes (5): Heap, 1-indexed binary heap. min_heap=True gives a min-heap (smallest on top)., True if x has higher priority than y (should sit above it)., Push x then pop the top, atomically. O(log n). Returns min(x, old_top),…, The k largest (default) or k smallest items currently in the heap.

### Community 120 - "ScriptedClient"
Cohesion: 0.13
Nodes (6): chat() pops scripted items: str -> final answer; dict -> raw LLM out; Exception…, ScriptedClient, Same shape as tests/test_kernel_integration.py, plus chat_stream so the…, A 3B model says 'I executed git reset --hard' having run nothing. The verifier…, ScriptedClient, test_unverified_action_claim_gets_corrected_before_the_task_ends()

### Community 121 - "StreamingTTS"
Cohesion: 0.17
Nodes (6): Event, Immediate teardown (barge-in): drop queued sentences + flag the in-flight…, GENUINE streaming: consume edge-tts's chunk iterator live., sink(audio_bytes) plays one chunk; on_first() fires at the first chunk of an…, Start a fresh utterance (resets first-chunk tracking). `busy` is set…, StreamingTTS

### Community 122 - "test_dsa.py"
Cohesion: 0.15
Nodes (10): median(), quickselect(), Binary heap (min/max) + quickselect — independent of `heapq` internals.…, Median (lower-middle for even n) in expected O(n) via quickselect., k-th smallest (0-indexed) element in expected O(n) via 3-way quickselect.…, Manual test runner (no pytest needed): python tests/run_manual.py, DSA library correctness — runs the full verify_all() harness. ~6,000+…, Regression: merge_sort must be stable under reverse=True (equal keys keep… (+2 more)

### Community 123 - "test_eval_score.py"
Cohesion: 0.16
Nodes (21): A52: `score` is the latest row per task id over ALL of results.jsonl, so a…, summarize(), agent_eval_lines(), _latest_llm_run(), The agent-eval evidence for REPORT.md, as TWO separately-labelled numbers…, REPORT.md bullets for the agent eval, worded so a partial or skip-inflated run…, _history(), A52: the eval headline must be the score of the run that ran.… (+13 more)

### Community 124 - "package.json"
Cohesion: 0.12
Nodes (15): description, devDependencies, jest, jest-environment-jsdom, miniprogram-simulate, name, private, scripts (+7 more)

### Community 125 - "health.py"
Cohesion: 0.24
Nodes (11): offline_hint(), For `/health` and the web status panel: what the autostart actually did. There…, What to tell a user whose server is not answering. BEE can start it now, so the…, status(), cli_report(), _disk_free_gb(), docker_has_image(), Path (+3 more)

### Community 126 - "permission.py"
Cohesion: 0.22
Nodes (8): PermissionDecision, decide(), Permission decisions (Phase 2) — ONE entry point over the existing guard. Does…, (risk_level, capabilities) from the security risk layer; ('low', ()) for non-…, Full gate for one tool call. `approver` — optional (tool, args, reason) -> bool…, risk_info(), test_permission_allow_ask_deny(), test_permission_risk_metadata()

### Community 127 - "ExecutionReceipt"
Cohesion: 0.11
Nodes (11): EventBus, Path, Human (or test) consult for a capability that needs confirmation. Mirrors the…, ExecutionReceipt, Append-only proof row for one meaningful action. Secrets are redacted before…, Path, Execution receipts (Phase 2) — append-only, redacted JSONL proof rows. Every…, ReceiptLog (+3 more)

### Community 128 - "StreamingSTT"
Cohesion: 0.21
Nodes (4): Final transcript over the whole utterance; honors self.timeout., Windowed partials + one final pass, over faster-whisper., Interim transcript of the utterance so far ('' if nothing yet)., StreamingSTT

### Community 129 - "prompts.js"
Cohesion: 0.25
Nodes (6): CHAT_BASE, CLASSIFY_SCHEMA, CLASSIFY_SYSTEM, EXPLAIN_SYSTEM, MOODS, PERSONAS

### Community 130 - "test_capability_report_is_honest_on_this_machine"
Cohesion: 0.50
Nodes (4): available_sources(), Honest capability report (sources are adapters; missing deps = 'unavailable')., The report must not overclaim — and must not underclaim either: whatever…, test_capability_report_is_honest_on_this_machine()

### Community 131 - "alerts.py"
Cohesion: 0.11
Nodes (22): _fn_alert_scan(), Daily threshold alerting (audit item 6): evaluate metrics stats against…, check_thresholds(), _cooldown_ok(), _load_state(), _mark_fired(), _notify_store(), os_notify() (+14 more)

### Community 132 - "web.py"
Cohesion: 0.11
Nodes (18): BEE security layer (Phase 1). Modules: netguard — SSRF-hardened URL fetching…, mark_untrusted(), Wrap external content in an UNFORGEABLE data fence. The fence used to be a…, Wrap a web-tool result so the model sees it as DATA, never as instructions…, truncate(), untrusted_fence(), _fetch(), _html_to_text() (+10 more)

### Community 133 - "mic.py"
Cohesion: 0.27
Nodes (13): _has(), _pcm_to_float(), Path, RuntimeError, Microphone capture with silence detection. Primary: sounddevice (numpy frames).…, Best-effort mic capture across available backends., _read_wav(), record() (+5 more)

### Community 134 - "_extract_text_tool_calls"
Cohesion: 0.24
Nodes (12): _extract_text_tool_calls(), _iter_json_blocks(), Yield each top-level {...} block (string/escape aware). Handles JSONL-style…, Small local models sometimes emit tool calls as TEXT (JSON / JSONL / fenced).…, Unit tests for the text tool-call extractor (handles JSONL/fenced/array +…, test_args_as_string(), test_array(), test_empty() (+4 more)

### Community 135 - "_VecStore"
Cohesion: 0.23
Nodes (6): lancedb renamed table_names() -> list_tables() (0.39 warns on the old…, Clear-before-add (B2/M12 fix, audit 2026-10-06): the old implementation did…, Re-index ONE memory file: drop its old rows, add the current chunks.…, _VecStore, B2/M12: rebuilding twice must NOT double the row count., test_vector_rebuild_no_duplicates()

### Community 136 - "T"
Cohesion: 0.12
Nodes (18): automation_tools(), T, file_tools(), health_tools(), system_health — BEE checks its own environment from inside the loop., _automation_builder(), Tool registry: default toolset + litellm/openai schema export., tools_openai() (+10 more)

### Community 137 - "shim-lifecycle.test.js"
Cohesion: 0.18
Nodes (7): install(), PAGE_LIFECYCLE, simulate, id, path, shim, { text, simulate, wxState, resetWxState }

### Community 138 - "ml_report.py"
Cohesion: 0.22
Nodes (12): full_report(), _pctl(), ML router report (Program Phase 7, 2026-10-08). One place to answer "how is the…, Fallback rate + latency percentiles over the last `window_hours`., The last training report (per-class metrics etc.), if any., Artifact + training + runtime in one dict (for /health-style output)., Human-readable one-screen summary., render() (+4 more)

### Community 139 - "commands/__init__.py"
Cohesion: 0.26
Nodes (10): _deterministic(), draft(), _extract_fallback(), _llm(), /draft — emails, memos, outreach, proposals, reports + note extraction. Usage:…, -> (kind, body, tone). Kind = first word if it is a known kind., _split(), help_text() (+2 more)

### Community 140 - "ScreenshotStore"
Cohesion: 0.17
Nodes (6): Path, Bounded screenshot retention. Default (save_dir=None): in-memory hash ring only…, Delete ALL saved frames (called on session end / emergency stop)., ScreenshotStore, Event, test_11_screenshot_retention()

### Community 141 - "Trie"
Cohesion: 0.24
Nodes (3): _Node, Trie (prefix tree) — autocomplete, spellcheck, prefix queries. O(L) per op…, Trie

### Community 142 - "ClapDetector"
Cohesion: 0.16
Nodes (9): ClapDetector, Listens on the microphone for double-clap acoustic signatures., _feed(), _mk_det(), Feed synthetic blocks; advance a fake monotonic clock by dt each block., test_cooldown_blocks_second_double(), test_double_clap_triggers_once(), test_single_clap_does_not_trigger() (+1 more)

### Community 143 - "planner.js"
Cohesion: 0.24
Nodes (8): explain(), gapsFrom(), label(), mmhh(), overlaps(), solve(), p, W

### Community 144 - "app-manifest.test.js"
Cohesion: 0.18
Nodes (8): app, BUILTIN_TAGS, fs, pageDirs, path, ROOT, SOURCE_DIRS, SOURCE_FILES

### Community 145 - "live-ollama.test.js"
Cohesion: 0.20
Nodes (8): http, request(), { URL }, agent, { createLlm }, llm, offline, { request }

### Community 146 - "_denying_kernel"
Cohesion: 0.20
Nodes (9): ScriptedClient, _AnswersWhenToolsClosed, _denying_kernel(), The real wrap pass calls chat(tools=None): the model can only answer., A48: locking the tools after 3 refusals still let every later iteration pay a…, A47 end to end: refused writes + 'File created: …' must not be ok=True., _rotating_refused_calls(), test_a_phantom_file_claim_is_not_delivered_as_success() (+1 more)

### Community 147 - "test_plan_store.py"
Cohesion: 0.25
Nodes (10): _plan(), fixture, A54 — /plan owns a JSON task store, and three ways to lose the user's tasks.…, The write goes to a sibling temp file and is renamed over the store, so a…, store(), test_a_save_never_leaves_a_partial_file(), test_an_unreadable_store_is_kept_not_erased(), test_ids_do_not_repeat_after_a_prune() (+2 more)

### Community 148 - "Feature Status Authoritative"
Cohesion: 0.25
Nodes (11): JARVIS Acceptance Audit, Agent Kernel run_agent Loop, FastPaths Deterministic Tier, Production Readiness Audit, Single Kernel Routing All Surfaces, Spawn Task Gate Bypass P0, Feature Status Authoritative, Agent Eval 18 of 21 (+3 more)

### Community 149 - "summarize.py"
Cohesion: 0.33
Nodes (9): _extractive(), _fetch_url(), _llm(), /summarize — articles, papers, reports → executive summary + dense bullets +…, Comparative table of entity→number pairs (metrics, prices, versions)., _read_file(), _sentences(), summarize() (+1 more)

### Community 150 - "sandbox.py"
Cohesion: 0.22
Nodes (8): _ensure_env_mask_file(), _nvidia_runtime(), Path, sandbox_run — Docker sandbox (bee-sandbox image, GPU passthrough optional). The…, Does this Docker setup have the nvidia runtime (GPU passthrough)? Docker…, An empty host file to bind over <workspace>/.env inside the container. Lives…, Host path as the docker CLI should receive it. Docker Desktop (Windows) accepts…, _to_container_path()

### Community 151 - "VoiceTransport"
Cohesion: 0.20
Nodes (5): Protocol, Establish capture/playback. Raises TransportError on failure., Blocking read of one ~100 ms 16 kHz mono s16le frame. Returns None on timeout…, Render a TTS audio chunk (format is transport-specific)., VoiceTransport

### Community 152 - "createLlm"
Cohesion: 0.21
Nodes (14): createLlm(), chat(), clamp(), classify(), contentOf(), explain(), parseMood(), probe() (+6 more)

### Community 153 - "QLoRA fine-tuning Qwen3 8GB 3050"
Cohesion: 0.20
Nodes (10): finetune SKILL, QLoRA fine-tuning Qwen3 8GB 3050, pytorch SKILL, PyTorch VRAM budget training skeleton, Docker ML environment sandbox_run GPU, sandbox SKILL, transformers SKILL, HF Transformers inference dataset pipeline (+2 more)

### Community 154 - "_FakeWin32"
Cohesion: 0.20
Nodes (4): _FakeWin32, The old version searched list_windows() (which drops untitled windows), so a…, test_active_window_is_none_only_when_truly_unknown(), test_active_window_resolves_the_handle_directly()

### Community 155 - "commands/code.py"
Cohesion: 0.36
Nodes (8): code(), _debug_fallback(), _detect_lang(), _llm(), /code — production-grade code generation + systematic debugging. Usage: /code…, _save(), _skeleton(), test_code_lang_detection()

### Community 156 - "bench.py"
Cohesion: 0.31
Nodes (8): check(), compare_sorts(), Path, Benchmark + correctness harness for the DSA library. run_bench(fn, *args,…, Benchmark all sorting implementations on the same random input; verify against…, report(), run_bench(), time_once()

### Community 157 - "files.py"
Cohesion: 0.54
Nodes (7): _edit_file(), _file_list(), Path, Filesystem tools: file_read, file_write, file_list, file_edit., _read_file(), resolve(), _write_file()

### Community 158 - "format.js"
Cohesion: 0.42
Nodes (7): ago(), clock(), countdown(), day(), pad(), shifted(), stamp()

### Community 159 - "conftest.py"
Cohesion: 0.28
Nodes (6): _isolate_append_only_streams(), _isolate_post_task_model_calls(), pytest_configure(), Test pyramid markers (audit 2026-10-06; Phase-7 categories 2026-10-08). The…, Reflection (A40b) adds ONE local-model call after every non-trivial task, on…, A test run must not write into the user's real telemetry or training data.…

### Community 160 - "think.py"
Cohesion: 0.39
Nodes (7): _deterministic(), _facts(), _llm(), /think — stress-test ideas, trade-offs, pros/cons matrices, strategic…, Pull claim-ish fragments (numbers, named risks, constraints) for the…, _save(), think()

### Community 161 - "UnionFind"
Cohesion: 0.27
Nodes (4): Union-Find / Disjoint Set Union with path compression + union by rank. Near…, UnionFind, Union-find reference (independent of graphs.has_cycle_undirected)., _ref_has_cycle()

### Community 162 - "load_episodes"
Cohesion: 0.32
Nodes (6): load_episodes(), BEE data pipeline: episodes → validate → sanitize → SFT / router training data., build_report(), main(), Path, Pipeline report → train/PIPELINE_REPORT.md (data flywheel health).

### Community 163 - "_Semantic"
Cohesion: 0.25
Nodes (6): Long-term markdown memory. Phase 8: entries carry PROVENANCE inline (source…, _Semantic, test_semantic_add_writes_provenance(), `_Semantic.search` called rag.retrieve(query, k=) instead of retrieve(ctx,…, test_durable_memory_facade_dedupes_promotions(), test_semantic_search_really_reaches_rag()

### Community 164 - "lexicon.js"
Cohesion: 0.25
Nodes (7): INTENSIFIERS, MOOD_WORDS, NEGATED_TARGET, NEGATIONS, REPLIES, SEPARATORS, TOPIC_STOP

### Community 165 - "core/groups.js"
Cohesion: 0.36
Nodes (5): byId(), join(), { match }, matchText(), rank()

### Community 167 - "requirements.txt BEE Core"
Cohesion: 0.25
Nodes (8): Core deps litellm lancedb fastapi apscheduler, requirements.txt BEE Core, requirements-ml.txt Pinned ML Stack, Pinned scikit-learn numpy scipy joblib versions, Router Model Artifact Meta, Docker sandbox GPU isolation note, Training code versus train data separation, training NOTE code vs data

### Community 168 - "RecordingClient"
Cohesion: 0.25
Nodes (3): ctx(), fixture, RecordingClient

### Community 169 - "BatterySource"
Cohesion: 0.11
Nodes (12): BatterySource, DeviceSource, Edge-triggered power events: battery.low / battery.unplugged / battery.charged…, Memory / disk pressure transitions — this machine's documented failure mode (a…, CollectBus, A foreground poll must not become an event storm: baseline first, then only…, A value oscillating on the threshold must not become a ping storm, and a…, test_app_event_source_emits_transitions_only() (+4 more)

### Community 170 - "Live Voice Page"
Cohesion: 0.32
Nodes (8): Web Auth Bearer Token, Chat SSE Endpoint, Web Chat UI, Face State Endpoint, Face Visualizer Page, Live Voice Page, LiveKit Token Endpoint, LiveKit Room Config

### Community 171 - "BEE to JARVIS Roadmap"
Cohesion: 0.32
Nodes (8): JARVIS Baseline Audit, guard_blocked Eval Anomaly, Coherence Pass Fixes F0-F5, BEE to JARVIS Roadmap, Jarvis Milestones J1-J6, H1 AST Risk Layer for Code Run, Technical Debt Report, H8 Eval Safe Computation Budget

### Community 172 - "FileChangeSource"
Cohesion: 0.29
Nodes (3): FileChangeSource, Path, Polling file-change watcher (no external dependency): fires file_change events…

### Community 173 - "train.py"
Cohesion: 0.53
Nodes (5): load_samples(), main(), Path, QLoRA fine-tuning of Qwen2.5-3B-Instruct for BEE — single 4 GB GPU friendly.…, summarize()

### Community 174 - "BEE Security Model"
Cohesion: 0.40
Nodes (6): N1 Guard Off Disables Capability Gate, Web Bearer Token Authentication, BEE Security Model, Docker Sandbox Boundary, Netguard SSRF Protection, ToolBus as Execution Dispatcher

### Community 175 - "embed.py"
Cohesion: 0.40
Nodes (3): embed_texts(), Embeddings: Ollama (nomic-embed-text) via LLMClient. Lazy access. Usage: from…, Returns embeddings for `texts`. Raises RuntimeError if Ollama/embedder…

### Community 176 - "env"
Cohesion: 0.33
Nodes (4): env(), FakeClient, fixture, Isolated gate environment: baselines + models.yaml + diary in tmp.

### Community 177 - "Safe Computer Action Set"
Cohesion: 0.40
Nodes (5): Capability Policies, Guard Mode, Coordinate Provenance Check, Emergency Stop Mechanisms, Safe Computer Action Set

### Community 178 - "Grok web UI screenshot showing gated conversation"
Cohesion: 0.50
Nodes (5): User chat bubble with text Hi agent, Essential and optional cookies consent banner with Reject All and Accept All Cookies, Grok full power features: AI images and videos, Skills and Connectors, Generate files, Chat history, Grok web UI screenshot showing gated conversation, Continue your conversation signup gate with Sign up for free CTA

### Community 179 - "grace"
Cohesion: 0.40
Nodes (5): grace(), For the router: a launch is in flight, so give the server the moment it needs…, The availability branch runs on every task; an idle-timeout here would be a…, test_grace_never_blocks_when_bee_never_launched_anything(), test_grace_picks_up_a_launch_that_completes_a_moment_later()

### Community 180 - "eval_probe"
Cohesion: 0.50
Nodes (4): eval_probe(), _latest_per_task(), Latest recorded outcome per eval task id (the pre-probe baseline)., Re-run a bounded subset of STRUCTURAL eval tasks with the skill force-included…

### Community 181 - "_fresh_state"
Cohesion: 0.40
Nodes (5): Forget the one-attempt state (tests, or a user who starts Ollama by hand and…, reset(), _fresh_state(), fixture, One launch attempt per process is real behaviour — tests must not inherit it…

### Community 182 - "Memory Layers and Nightly Consolidation"
Cohesion: 0.50
Nodes (4): Memory Consolidation Design, Memory Layers and Nightly Consolidation, BEE System Prompt, Operating Principles Act Verify

### Community 183 - "Polars lazy scan filter group_by pipeline"
Cohesion: 0.50
Nodes (4): polars SKILL, Polars lazy scan filter group_by pipeline, sklearn SKILL, Tabular baseline LightGBM validation SHAP

### Community 187 - "p7"
Cohesion: 0.67
Nodes (3): p7(), fixture, Isolated artifact + metrics + fresh cache for each test.

### Community 206 - "bench_model.py"
Cohesion: 0.60
Nodes (4): _bench_embed(), _bench_gen(), main(), Local model throughput/latency benchmark → evals/bench_model.json. Run: python…

### Community 220 - "Q: Why does load_config() connect Voice, Agent Loop, LLM Client, ToolBus and 40+ other communities?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Why does load_config() connect Voice, Agent Loop, LLM Client, ToolBus and 40+ other communities?, Source Nodes

## Knowledge Gaps
- **320 isolated node(s):** `OllamaCfg`, `CloudCfg`, `VoiceCfg`, `SandboxCfg`, `SchedulerCfg` (+315 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **29 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `load_config()` connect `load_config` to `test_fastpaths.py`, `LLMClient`, `test_capability_report_is_honest_on_this_machine`, `test_voice_engine.py`, `T`, `test_computeruse.py`, `test_structured_memory.py`, `test_kernel_unit.py`, `test_kernel_integration.py`, `JobStore`, `webapp.py`, `_allowing_kernel`, `test_capabilities.py`, `config.py`, `_denying_kernel`, `test_reflection_loop.py`, `computeruse/tools.py`, `load_episodes`, `verify_suite.py`, `test_phase7_repro.py`, `RecordingClient`, `run_agent`, `welcome.py`, `build_sft.py`, `base.py`, `test_commands.py`, `test_proactive.py`, `test_telemetry.py`, `test_automation.py`, `cli.py`, `test_phase8_memory_planning.py`, `automation/events.py`, `test_sandbox.py`, `bench_model.py`, `test_injection.py`, `Config`, `test_jarvis_features.py`, `SimpleNamespace`, `Context`, `start_emergency_hotkey`, `EventBus`, `train_router.py`, `test_claim_grounding.py`, `paths.py`, `ScriptedClient`?**
  _High betweenness centrality (0.115) - this node is a cross-community bridge._
- **Why does `AgentKernel` connect `AgentKernel` to `test_voice_engine.py`, `test_computeruse.py`, `test_structured_memory.py`, `test_kernel_unit.py`, `test_kernel_integration.py`, `webapp.py`, `_allowing_kernel`, `_denying_kernel`, `EventBus`, `test_scheduling_unified.py`, `scheduler.py`, `test_reflection_loop.py`, `test_automation.py`, `cli.py`, `kernel.py`, `test_phase8_memory_planning.py`, `kernel/__init__.py`, `run_suite`, `Context`, `transition`, `AgentSession`, `test_claim_grounding.py`, `ScriptedClient`, `permission.py`, `ExecutionReceipt`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Why does `run_agent()` connect `run_agent` to `test_fastpaths.py`, `LLMClient`, `web.py`, `_extract_text_tool_calls`, `test_providers.py`, `load_config`, `webapp.py`, `test_localserver.py`, `base.py`, `test_commands.py`, `grace`, `cli.py`, `kernel.py`, `transcribe.py`, `search.py`, `test_api_card.py`, `Config`, `test_jarvis_features.py`, `AgentKernel`, `Context`, `test_claim_grounding.py`, `paths.py`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `run_agent()` (e.g. with `LLMError` and `Context`) actually correct?**
  _`run_agent()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `AgentKernel` (e.g. with `EventBus` and `MemoryStack`) actually correct?**
  _`AgentKernel` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `Job` (e.g. with `JobQueue` and `JobStore`) actually correct?**
  _`Job` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `OllamaCfg`, `CloudCfg`, `VoiceCfg` to the rest of the system?**
  _320 weakly-connected nodes found - possible documentation gaps or missing edges._