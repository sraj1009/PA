# Graph Report - PA  (2026-10-17)

## Corpus Check
- 402 files · ~4,902,563 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 5139 nodes · 10848 edges · 251 communities (221 shown, 30 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 344 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `796a98c1`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- render.js
- Local Model Server
- test_fastpaths.py
- page-chat.test.js
- test_voice_engine.py
- Job
- page-shop.test.js
- worker.py
- test_computeruse.py
- providers.py
- load_config
- test_structured_memory.py
- ToolBus
- Model Documentation Template
- JobStore
- webapp.py
- make_kernel
- Checkpoint Model Metadata
- config.py
- cli.py
- test_webauth.py
- fastpaths.py
- realtime/__init__.py
- index/index.js
- tc
- test_scheduling_unified.py
- scheduler.py
- computeruse/__init__.py
- store
- test_eval_gate.py
- VoiceEngine
- Self-Improvement Reflection
- computeruse/tools.py
- test_skill_gate.py
- mlrouter.py
- verify_suite.py
- SSRF Network Guard
- chat/index.js
- test_localserver.py
- dsa/__init__.py
- test_mlrouter.py
- match
- Workspace Startup Protocol
- build_sft.py
- test_engine_speed.py
- _run
- test_commands.py
- test_exec_tools.py
- App Manifest Configuration
- store.js
- load_engine
- UI Asset Generation
- classify_risk
- test_proactive.py
- StructuredMemory
- Training Checkpoint Info
- test_automation.py
- LLMClient
- permission.py
- systemctl.py
- test_kernel_unit.py
- agent.py
- transcribe.py
- _allowing_kernel
- test_guard.py
- md.py
- Training and Scale Plan
- search.py
- Desktop
- ProceduralMemory
- Agent Interface chat classify match
- Fine-tuning Model Metadata
- test_sandbox.py
- Post Management Logic
- test_claim_grounding.py
- plan.py
- context.py
- kernel/models.py
- Graph Algorithm Library
- test_injection.py
- Static Contract Analysis
- Config
- test_capabilities.py
- automation_job
- test_rag.py
- AgentKernel
- test_jarvis_features.py
- test_plan_inputs.py
- Eval Hermeticity Tests
- localserver.py
- Voice State Bridge
- Secret Detection Scanner
- LiveKitTransport
- safeio.py
- test_providers.py
- WindowsDesktop
- start_emergency_hotkey
- Binary Tree Algorithms
- loadComponent
- test_phase8_memory_planning.py
- test_self_improve.py
- Offline Chat Logic
- test_plan_store.py
- dsa/verify.py
- AgentSession
- test_pipeline.py
- moodscore.js
- test_verifier.py
- T
- train_router.py
- native/__init__.py
- main.go
- agent/index.js
- get_system_stats
- _probe_kernel
- Episode
- Active state design vivid blue outline
- commands/code.py
- run_offline
- Heap
- Context
- alerts.py
- test_streaming_contract.py
- test_eval_score.py
- package.json
- memory_if.py
- kernel/__init__.py
- agent/loop.py
- StreamingSTT
- llm.js
- test_audit_fixes.py
- ComputerUseSession
- web.py
- mic.py
- _extract_text_tool_calls
- _VecStore
- StreamingTTS
- dashboard.py
- dp.py
- ml_report.py
- ScreenshotStore
- Trie
- base.py
- test_router_tiers.py
- app-manifest.test.js
- live-ollama.test.js
- test_web_approvals.py
- draft.py
- Feature Status Authoritative
- summarize.py
- sandbox.py
- VoiceTransport
- createLlm
- QLoRA fine-tuning Qwen3 8GB 3050
- _FakeWin32
- register
- bench.py
- files.py
- format.js
- paths.py
- runner.py
- UnionFind
- load_episodes
- _Semantic
- lexicon.js
- core/groups.js
- requirements.txt BEE Core
- kernel.py
- speak
- Live Voice Page
- BEE to JARVIS Roadmap
- CapabilityGate
- train.py
- BEE Security Model
- embed.py
- test_voice_tts.py
- Safe Computer Action Set
- Grok web UI screenshot showing gated conversation
- grace
- AGENTS.md — BEE personal assistant (Windows-first, local-first)
- _fresh_state
- Memory Layers and Nightly Consolidation
- Polars lazy scan filter group_by pipeline
- jest.night.config.js
- setup.js
- test_phase7_repro.py
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
- bee.py
- Constraint Planner Solver
- Windows Core CI Job
- Voice Optional Workflow
- Windows Desktop Optional Workflow
- Insight: unauthenticated Grok session is gated requiring signup to continue
- bee-telemetry
- Q: Why does load_config() connect Voice, Agent Loop, LLM Client, ToolBus and 40+ other communities?
- RecordingClient
- _Resp
- planner.js
- _ScriptedClient
- test_layering.py
- train_dpo.py
- voice/loop.py
- CapabilityStore
- client.py
- RetryPolicy
- tools_litellm
- speak.py
- test_webapp_voice.py
- SimpleNamespace
- _decode_to_wav
- commands/__init__.py
- capabilities_for
- _DownClient
- ScriptedClient
- memory_commands.py
- _FakeStream
- bench_model.py
- eval_resume.py
- run_agent
- FrozenDate
- DEPLOY.md
- _grounded_fallback
- _FakeResp
- test_a_server_without_the_configured_model_is_told_apart_from_a_dead_one

## God Nodes (most connected - your core abstractions)
1. `load_config()` - 151 edges
2. `run_agent()` - 84 edges
3. `make_kernel()` - 71 edges
4. `AgentKernel` - 70 edges
5. `Job` - 62 edges
6. `LLMClient` - 59 edges
7. `Context` - 59 edges
8. `JobWorker` - 56 edges
9. `JobStore` - 54 edges
10. `MockDesktop` - 51 edges

## Surprising Connections (you probably didn't know these)
- `OfflineAgent Lexicon Matcher Backend` --semantically_similar_to--> `FastPaths Deterministic Tier`  [INFERRED] [semantically similar]
  campus-life/docs/2026-10-12-design.md → docs/JARVIS_ARCHITECTURE.md
- `StubClient` --uses--> `LLMError`  [INFERRED]
  tests/test_engine_speed.py → bee/agent/client.py
- `test_cloud_failover_requires_fallback_credentials()` --uses--> `LLMClient`  [INFERRED]
  tests/test_providers.py → bee/agent/client.py
- `test_cloud_failover_switches_and_cools()` --uses--> `LLMClient`  [INFERRED]
  tests/test_providers.py → bee/agent/client.py
- `test_expired_cooldown_probes_primary_again()` --uses--> `LLMClient`  [INFERRED]
  tests/test_providers.py → bee/agent/client.py

## Import Cycles
- 4-file cycle: `bee/agent/loop.py -> bee/tools/__init__.py -> bee/tools/spawn_tool.py -> bee/agent/spawn.py -> bee/agent/loop.py`

## Hyperedges (group relationships)
- **One agent interface with auto-selected backends** — campus_life_agent_interface, campus_life_llm_agent, campus_life_offline_agent [EXTRACTED 0.75]
- **Eval quality gate system: verify suite, 21 tasks, J3 model gate** — evals_report_verify_suite_71914, evals_tasks_21_task_gate, docs_production_readiness_model_gate_j3 [EXTRACTED 0.75]
- **Security hardening batch: kernel routing, bearer auth, netguard** — docs_production_readiness_single_kernel_routing, docs_security_bearer_token_auth, docs_security_netguard_ssrf [EXTRACTED 0.75]
- **Shared bearer-token auth across web surfaces** — bee_web_chat_ui, bee_web_face_visualizer, bee_web_live_voice_page, bee_web_auth_token [EXTRACTED 0.75]

## Communities (251 total, 30 thin omitted)

### Community 0 - "render.js"
Cohesion: 0.05
Nodes (89): resetStore(), storage, { loadComponent, tap, text, count, simulate, wxState, resetWxState }, { loadComponent, text, classes, count, simulate }, { loadComponent, tap, text, allText, count, simulate, wxState, resetWxState }, { loadFixture, tap, text, count }, freeze(), unfreeze() (+81 more)

### Community 1 - "Local Model Server"
Cohesion: 0.20
Nodes (23): Bring Ollama up if it is not already. Returns True when the server is reachable…, start_background(), _cfg(), _launched(), Popen, Without OLLAMA_HOST the server BEE starts would sit on 11434 while BEE polls…, A flashing console or a pipe that fills up would make the assistant's boot…, Stand-in for the Ollama HTTP surface, with switchable reachability. (+15 more)

### Community 2 - "test_fastpaths.py"
Cohesion: 0.12
Nodes (21): _attach_worker(), DeadClient, _h(), Tests for fast paths (instant pure-Python answers), engine selection, and cloud…, One implementation: the same words through either surface produce the same…, README and STATUS both still said '39 handlers' after the catalog grew to 45…, test_coin_dice_random(), test_convert_handlers() (+13 more)

### Community 3 - "page-chat.test.js"
Cohesion: 0.09
Nodes (19): groups, INTERESTS, chat, groups, advance(), agent, chat, { freeze, unfreeze, advance } (+11 more)

### Community 4 - "test_voice_engine.py"
Cohesion: 0.07
Nodes (50): FakeTTS, Test double with the StreamingTTS lifecycle. Mirrors the real pipeline: begin()…, FakeKernel, FakeSTT, make_engine(), Voice engine tests (Phase 4) — true realtime conversation behavior. Required…, Kernel stand-in: run() 'works' for delay seconds (polling the cancel event like…, User barges in while BEE is thinking/speaking: TTS stops immediately, the task… (+42 more)

### Community 5 - "Job"
Cohesion: 0.07
Nodes (21): iso(), Job, parse_dt(), datetime, Persist a datetime CANONICALLY IN UTC (timezone rule, 2026-10-08)., JobQueue, Claim a job for execution. Refused if already inflight or the global cap is…, effective_max_attempts() (+13 more)

### Community 6 - "page-shop.test.js"
Cohesion: 0.05
Nodes (50): COMPARATORS, filter(), haversineKm(), isOpen(), toRad(), cats, ORIGIN, shops (+42 more)

### Community 7 - "worker.py"
Cohesion: 0.06
Nodes (43): Durable automation + proactive agent (Phase 6). Objects (per the Phase 6 spec):…, ExecutionHistory, JobExecution, JobTrigger, Durable automation models (Phase 6; UTC-canonical storage, 2026-10-08). Job /…, Persisted per-job execution history (append-only JSONL in JobStore)., JobQueue (Phase 6) — the concurrency-control object. Two guarantees, both…, get_tz() (+35 more)

### Community 8 - "test_computeruse.py"
Cohesion: 0.08
Nodes (31): ComputerAction, Risk after provenance: unproven click coordinates escalate to high (the risk…, Log/audit-safe view — NEVER includes the typed text payload, clipboard…, MockDesktop, Simulate the USER (or another app) changing the screen mid-task., Deterministic desktop for tests. Windows: add_window(); launchers:…, make_ctx(), make_session() (+23 more)

### Community 9 - "providers.py"
Cohesion: 0.11
Nodes (22): env_key_for(), env_vars_for(), key_for(), kind_for_model(), Provider, ProviderConfig, ProviderHealth, ProviderKind (+14 more)

### Community 10 - "load_config"
Cohesion: 0.11
Nodes (30): load_config(), Path, compare(), main(), Head-to-head: same tasks on local bee4b vs cloud, judged by the suite rubric.…, ensure_core_dirs(), main(), Batch driver for the LLM eval suite (background runs must stay < 15 min).… (+22 more)

### Community 11 - "test_structured_memory.py"
Cohesion: 0.09
Nodes (31): _best_lines(), The bullets inside a memory chunk that actually answer this query. A chunk is…, is_hardware_query(), _kernel(), _mem(), Structured memory tests (Phase 3, Parts C/D): remember/recall/update/forget,…, The store starts empty — only explicit remember() creates items., The rag_gpu_memory eval task failed because the kernel STORED the question:… (+23 more)

### Community 12 - "ToolBus"
Cohesion: 0.10
Nodes (25): MalformedArgsError, ToolBus (Phase 2) — the single dispatch point for agent tool calls. Every tool…, litellm/openai function schemas for the registered tools only., Execute a registered tool. Returns (result, seconds, ok, meta). meta:…, Build from the existing registered tool modules (bee.tools)., ToolBus, ToolDef, ToolTimeoutError (+17 more)

### Community 13 - "Model Documentation Template"
Cohesion: 0.05
Nodes (37): Bias, Risks, and Limitations, Citation [optional], Compute Infrastructure, Direct Use, Downstream Use [optional], Environmental Impact, Evaluation, Factors (+29 more)

### Community 14 - "JobStore"
Cohesion: 0.08
Nodes (15): _new_id(), Notification, _atomic_write(), JobStore, Path, Execution files OLDEST FIRST (.2 -> .1 -> active) — M13 rotation never loses…, Last row per execution id wins (a crash-repair appends a terminal row for an…, Drop claim tokens older than ttl (crashed processes). Idempotent. (+7 more)

### Community 15 - "webapp.py"
Cohesion: 0.09
Nodes (44): cancel_task(), chat(), dashboard(), engine_get(), engine_set(), face_page(), face_state(), get_ctx() (+36 more)

### Community 16 - "make_kernel"
Cohesion: 0.07
Nodes (52): test_the_model_sees_the_card_in_the_request(), _events(), make_kernel(), _no_fastpath(), Kernel integration tests (Phase 2) — full task lifecycle through the REAL…, N4 contract (supersedes the old pre-set test): a cancel event left SET by a…, stop' with no running task reports the last task's state (unit-level)., Explicit intent must survive the same refactor: route_text carries the 'cloud:'… (+44 more)

### Community 17 - "Checkpoint Model Metadata"
Cohesion: 0.05
Nodes (37): Bias, Risks, and Limitations, Citation [optional], Compute Infrastructure, Direct Use, Downstream Use [optional], Environmental Impact, Evaluation, Factors (+29 more)

### Community 18 - "config.py"
Cohesion: 0.04
Nodes (47): AlertsCfg, _apply_env(), AutomationCfg, _build_from_yaml(), ClapCfg, CloudCfg, ComputerUseCfg, _dotenv_defines() (+39 more)

### Community 19 - "cli.py"
Cohesion: 0.09
Nodes (31): create_context(), Single application-context factory (Phase 1: replaces the 7+ duplicated…, ask_engine(), engine_labels(), override_for(), Engine selection: which brain does BEE use by default? Asked once at first…, Human-facing engine labels. The api-cloud label reflects the ACTUAL configured…, First-launch prompt. Non-interactive stdins (pipes/tests) default to hybrid. (+23 more)

### Community 20 - "test_webauth.py"
Cohesion: 0.07
Nodes (37): reset_token_for_tests(), test_web_livekit_and_face_endpoints(), _client(), _client_with_kernel(), dash_env(), _page(), fixture, parametrize (+29 more)

### Community 21 - "fastpaths.py"
Cohesion: 0.07
Nodes (35): _brightness(), _cim(), _convert(), _date(), FastExec, _files_list(), _files_list_reply(), _http_text() (+27 more)

### Community 22 - "realtime/__init__.py"
Cohesion: 0.08
Nodes (28): VoiceEngine (Phase 4) — the realtime conversation orchestrator. Pipeline (one…, bee.voice.realtime — Phase 4 true-realtime voice. Clean layering:…, InvalidVoiceTransition, Enum, Exception, str, Voice state machine (Phase 4). The VOICE layer owns this state machine — and…, Engine tunables (defaults mirror config.yaml voice: rt_* fields). (+20 more)

### Community 23 - "index/index.js"
Cohesion: 0.06
Nodes (38): locate(), canCheck(), coverage(), dayIndex(), doCheckin(), groupByZone(), latestFor(), list() (+30 more)

### Community 24 - "tc"
Cohesion: 0.08
Nodes (24): Acceptance audit P1-1: with a kernel attached, the agent loop must dispatch…, test_f2_loop_executes_tools_through_toolbus(), N4: the KERNEL owns task-scoped cancellation. A cancel event left SET by a…, Loop breaker gap: the exact-args breakers never match when a small model re-…, Retrying one failing call with reworded arguments used to burn the whole budget…, test_n4_stale_cancel_event_does_not_poison_new_task(), test_repeated_denials_lock_tools_instead_of_burning_the_budget(), test_repeated_tool_failures_lock_without_punishing_good_work() (+16 more)

### Community 25 - "test_scheduling_unified.py"
Cohesion: 0.13
Nodes (33): MemoryStack, Facade: memory.<kind> gives the kernel one object per store. Phase 3:…, _cron_to_trigger(), scheduler tool — ADAPTER over the durable automation system (2026-10-08).…, Return (JobTrigger, note) or raise ValueError with the reason., scheduler_tools(), Ctx, due_one_time() (+25 more)

### Community 26 - "scheduler.py"
Cohesion: 0.10
Nodes (27): _fn_build_sft(), _fn_consolidate(), _fn_flush_memory_index(), _fn_rebuild_vectors(), _fn_teach_back(), _fn_train_qlora(), diary_add(), consolidate() (+19 more)

### Community 27 - "computeruse/__init__.py"
Cohesion: 0.09
Nodes (24): is_credential_target(), Computer-use action model (Phase 5) — one safe desktop action. Every action the…, Heuristic gate for the 'no credential entry' rule (checked on the SEMANTIC…, bee.computeruse — Phase 5: SAFE computer use. Desktop capture -> structured UI…, Computer-use privacy (Phase 5). Rules enforced in code (not just documented):…, Log/audit-safe entry for one executed (or blocked) action., redact_entry(), active_sessions() (+16 more)

### Community 28 - "store"
Cohesion: 0.06
Nodes (49): { createStore }, { KEY }, request(), save(), store(), tzOffsetMin(), instance(), label() (+41 more)

### Community 29 - "test_eval_gate.py"
Cohesion: 0.09
Nodes (39): _fn_model_gate(), J3: model-upgrade quality gate (candidate vs recorded baseline)., baseline_record(), load_baselines(), model_quality_gate(), _now(), promote_model(), _rate_limited_ids() (+31 more)

### Community 30 - "VoiceEngine"
Cohesion: 0.13
Nodes (6): Process one ~100 ms frame. NEVER raises — failures route to ERROR., Resolve a held answer once the verifier has judged it., Owns the voice state machine and timing; delegates all task logic to the kernel…, ERROR -> IDLE (or LISTENING when always-on) once the transport is up., Blocking transport pump with reconnect + capped backoff. stop() (or Ctrl-C)…, VoiceEngine

### Community 31 - "Self-Improvement Reflection"
Cohesion: 0.09
Nodes (33): _all_bullets_empty(), Self-improvement loop (Phase 3): post-task reflection. After each completed…, `worked: None / failed: None / next: None` teaches nothing and burns the prompt…, A lesson is not a note to self — `context.recent_lessons()` injects it into…, Trivial tasks (canned replies, one-shot local answers, no tools) yield no…, LLM-based self-review. Returns the lesson text ("" if skipped)., reflect(), time_stamp() (+25 more)

### Community 32 - "computeruse/tools.py"
Cohesion: 0.09
Nodes (37): DesktopError, make_desktop(), RuntimeError, Default desktop factory — WindowsDesktop on Windows, DesktopError elsewhere…, computeruse_emergency_stop(), STOP all active computer-control sessions immediately. Returns the number of…, computer_clipboard(), computer_input() (+29 more)

### Community 33 - "test_skill_gate.py"
Cohesion: 0.10
Nodes (45): Index of SHIPPED skills only. J2: skills in `candidate` status (created/updated…, skills_index(), _fn_skill_gate(), J2: gate candidate skills (structural check + bounded eval probe)., bump_skill(), candidate_names(), eval_probe(), gate_candidates() (+37 more)

### Community 34 - "mlrouter.py"
Cohesion: 0.20
Nodes (19): _compat_issue(), load(), load_status(), ML route classifier — learns local|cloud routing from BEE's own episodes.…, when compatible; otherwise a clear, actionable message (Phase 7). MAJOR scikit-…, Returns bundle dict or None. Cached by (path, mtime): predict() runs on EVERY…, Clear, machine-readable load report (Phase 7): what happened and why, without a…, _sklearn_ver() (+11 more)

### Community 35 - "verify_suite.py"
Cohesion: 0.10
Nodes (34): luhn_ok(), agent_eval_lines(), _gen_expr(), _is_subseq(), _latest_llm_run(), _load_bench(), _luhn_check_digit(), main() (+26 more)

### Community 36 - "SSRF Network Guard"
Cohesion: 0.10
Nodes (33): FetchResult, _ip_class(), NetGuardError, Exception, SSRF-hardened HTTP fetching for model-driven web tools. The `web_fetch` tool…, Fetch a URL under the full SSRF policy. Raises NetGuardError on any violation.…, Raised when a URL or its fetch violates the SSRF policy., Return a blocking class name for a non-public IP, else None. (+25 more)

### Community 37 - "chat/index.js"
Cohesion: 0.10
Nodes (31): byId(), current(), expire(), open(), peer(), push(), reap(), send() (+23 more)

### Community 38 - "test_localserver.py"
Cohesion: 0.26
Nodes (14): compact_messages(), Cheap prompt-size estimator used for history budgeting. A59 showed `chars/4`…, Drop oldest tool-history pairs before the model drops them for us. Ollama…, _token_estimate(), _fat_tools(), _pairs(), A60 — BEE can bring up its own local model server. Nothing used to start…, test_compact_drops_oldest_tool_pairs_to_fit_budget() (+6 more)

### Community 39 - "dsa/__init__.py"
Cohesion: 0.06
Nodes (30): BEE DSA library — curated, tested building blocks + benchmark harness. Usage:…, Segment tree with range query + point update. O(log n) each. Default op = sum.…, Inclusive range [lo, hi]., SegmentTree, bubble_sort(), counting_sort(), heap_sort(), insertion_sort() (+22 more)

### Community 40 - "test_mlrouter.py"
Cohesion: 0.20
Nodes (14): features(), predict(), Returns (label, confidence) or None if model unavailable., _features_matrix(), _make_data(), fixture, ML route classifier: feature extraction + ML/DL model round-trip through…, The DL option (feature-scaled MLP) must save + predict exactly like the ML one,… (+6 more)

### Community 41 - "match"
Cohesion: 0.09
Nodes (23): FastPath, match(), Remind me what my passport number is' is a question, not a reminder. The fast…, What is in the oven' must not be answered with a directory listing., What hardware do I need to run llama" is a purchase question; 'what is the spec…, Non-Windows or a blocked CIM query must not produce a fake spec sheet., The eval's own sentence: 'Run python: <snippet> — list which sorts are correct…, The 120-char ceiling was global before; the per-path `max_len` must not quietly… (+15 more)

### Community 42 - "Workspace Startup Protocol"
Cohesion: 0.10
Nodes (32): _chrome_executable(), _due(), focus_or_launch_ide(), _foreground_hwnd(), _ide_executable(), _main_hwnd_win32(), _monitor_rects(), open_url_chrome() (+24 more)

### Community 43 - "build_sft.py"
Cohesion: 0.10
Nodes (29): build(), load_golden(), main(), _no_tool_single_turn(), paraphrase_augment(), Path, quality_score(), Episodes + cloud goldens → SFT dataset (Qwen3 chat format, loss-masked, PII-… (+21 more)

### Community 44 - "test_engine_speed.py"
Cohesion: 0.12
Nodes (26): _capture_litellm(), _ctx(), _FakeOllamaResp, _mk_cfg(), Engine speed tier: hybrid cloud-first routing, cloud→local de-escalation, and…, Fake the ONLY external dependency of the primary path, and hand back the kwargs…, `cfg.ollama.num_ctx` was sent by the native fallbacks (`_native_ollama`,…, Same omission, second method: `chat_stream` built its kwargs without num_ctx… (+18 more)

### Community 45 - "_run"
Cohesion: 0.13
Nodes (29): _convert(), _count(), _dedupe(), _fill(), _find(), _inventory(), _jsonq(), _lines() (+21 more)

### Community 46 - "test_commands.py"
Cohesion: 0.12
Nodes (20): line = full command line (leading '/' ok, e.g. '/draft email ...'). Returns…, run(), ctx(), DeadClient, fixture, BEE command system + Phase-4 hot-path regression tests. Covers: - config.yaml…, Regression: UnboundLocalError (res_v) when the guard ALLOWED an exec tool., Scripted LLMClient stand-in — no network, no model. (+12 more)

### Community 47 - "test_exec_tools.py"
Cohesion: 0.11
Nodes (29): envelope(), Tool-result dict. `limit` overrides the default truncation cap so a tool's own…, _kill_tree(), Cancellable subprocess execution (J1 — audit item 3). The old exec tools used…, Run `cmd`; returns (returncode, stdout, stderr, kind) with kind in {'ok',…, run_cancelable(), _child_env(), code_tools() (+21 more)

### Community 48 - "App Manifest Configuration"
Cohesion: 0.06
Nodes (31): lazyCodeLoading, pages, permission, scope.userLocation, requiredPrivateInfos, desc, sitemapLocation, style (+23 more)

### Community 49 - "store.js"
Cohesion: 0.11
Nodes (24): migrate(), schema(), clone(), createStore(), load(), persist(), read(), reset() (+16 more)

### Community 50 - "load_engine"
Cohesion: 0.11
Nodes (24): load_engine(), The persisted engine choice, through `paths` so the test suite can redirect it…, Persist the choice. Returns whether it actually happened: the caller may not be…, save_engine(), settings_file(), _default_engine_override(), Engine-choice persistence (A41): redirectable path, honest failures.…, The whole isolation fix: the module reads `paths.SETTINGS_JSON`, so a caller… (+16 more)

### Community 51 - "UI Asset Generation"
Cohesion: 0.09
Nodes (24): app, fs, path, { render, ICONS, OFF, ON, SIZE }, ROOT, zlib, chunk(), coverage() (+16 more)

### Community 52 - "classify_risk"
Cohesion: 0.08
Nodes (43): Attribute, audit_path(), Path, Record one tool-call audit row. `decision` is a risk.RiskDecision (or None for…, Last n audit rows (for /audit-style inspection + tests)., recent(), record(), analyze_python() (+35 more)

### Community 53 - "test_proactive.py"
Cohesion: 0.04
Nodes (63): AppEventSource, available_sources(), BatterySource, BusEvent, DeviceSource, EventBus, EventSource, FileChangeSource (+55 more)

### Community 54 - "StructuredMemory"
Cohesion: 0.10
Nodes (17): MemoryItem, _now(), Path, Structured memory store (Phase 3, Parts C/D). Five conceptual stores are…, Delete by id, or (for 'Forget that.') the LAST matched item when a query is…, Compact, source-labeled digest for context injection., Purge expired + long-tombstoned items; returns count removed., Timezone-safe expiry check (fixed 2026-10-08): expiries are stored UTC-… (+9 more)

### Community 55 - "Training Checkpoint Info"
Cohesion: 0.05
Nodes (37): Bias, Risks, and Limitations, Citation [optional], Compute Infrastructure, Direct Use, Downstream Use [optional], Environmental Impact, Evaluation, Factors (+29 more)

### Community 56 - "test_automation.py"
Cohesion: 0.08
Nodes (61): Ctx, due_one_time(), FakeClock, FakeKernel, FakeResult, FakeTask, _force_running(), make_worker() (+53 more)

### Community 57 - "LLMClient"
Cohesion: 0.08
Nodes (18): _cooling(), LLMClient, LLMError, Exception, GENUINE streaming completion: `on_token(str)` is called for every content delta…, Native Ollama: POST /api/chat with stream:true (NDJSON deltas)., litellm stream=True — per-chunk deltas (works for Ollama + Gemini)., One LLM completion. Returns the normalized dict: {content: str|None,… (+10 more)

### Community 58 - "permission.py"
Cohesion: 0.12
Nodes (11): Inspect the visible UI (read-only). Returns the structured snapshot the agent…, Routing key: explicit name attr (BusEvent) or kind.value (AgentEvent)., Dispatch; returns the number of handlers INVOKED (a handler that raises is…, PermissionDecision, decide(), Permission decisions (Phase 2) — ONE entry point over the existing guard. Does…, (risk_level, capabilities) from the security risk layer; ('low', ()) for non-…, Full gate for one tool call. `approver` — optional (tool, args, reason) -> bool… (+3 more)

### Community 59 - "systemctl.py"
Cohesion: 0.11
Nodes (30): _battery(), _specs(), format_hardware(), get_battery(), get_hardware(), _keybd(), lock_workstation(), media() (+22 more)

### Community 60 - "test_kernel_unit.py"
Cohesion: 0.12
Nodes (31): Observation, What the kernel SAW happen for one tool call (never the model's claim)., VerificationResult, check_effect(), Path, Effect verification (Phase 2). Rule: a task is verified by OBSERVING the world,…, Extract the intended filesystem target from the request, if any. Returns (kind,…, Whole-task verdict. fail — a tool errored, an effect check failed, or the… (+23 more)

### Community 61 - "agent.py"
Cohesion: 0.08
Nodes (35): available(), _build_brain(), _edge_tts_mp3(), make_stt(), make_token(), make_tts(), _pyttsx3_wav(), LiveKit agent — BEE's live realtime voice (free-tier LiveKit Cloud). python -m… (+27 more)

### Community 62 - "transcribe.py"
Cohesion: 0.15
Nodes (18): _voice_once(), available(), _gpu_error(), _load(), _model_dir(), _once(), _pick_device(), Exception (+10 more)

### Community 63 - "_allowing_kernel"
Cohesion: 0.09
Nodes (22): _allowing_kernel(), A kernel that grants every permission, so a test can observe the LOOP's own…, dsa_gcd_lcm spent 48 tool calls on one task: a 3B model that re-runs broken…, Same loop, different symptom: six SUCCESSFUL calls of one tool with ever-…, dsa_gcd_lcm / dsa_lis / dsa_graph, live: tools=0 and an answer that DESCRIBES a…, A45a: the model displayed code that stores the results in variables and never…, The read-out must only be appended when there is no output of its own —…, When permission is refused the answer must not pretend the computation happened… (+14 more)

### Community 64 - "test_guard.py"
Cohesion: 0.12
Nodes (19): check(), classify(), make_approver(), preview_call(), mode: cli (prompt), unattended (auto-deny), always (auto-approve). WARNING:…, Full gate. Returns (proceed, action, reason). ask → consults the approver.…, Returns (action, reason) where action in allow|ask|deny., One line saying what the user is actually being asked to allow. The prompt used… (+11 more)

### Community 65 - "md.py"
Cohesion: 0.10
Nodes (29): add_facts(), all_chunks(), chunk_md(), _clean_fact(), _fact_core(), _finger(), is_transcript(), memory_search() (+21 more)

### Community 66 - "Training and Scale Plan"
Cohesion: 0.22
Nodes (10): Bee-8B QLoRA Local Brain, BEE LLM Component Design, J3 Model Upgrade Quality Gate, Constitutional AI and RLAIF Pipeline, Training and Scale Plan, 3D Parallelism TP PP DP Design, Verification Report, Verify Suite 71914 Checks All Pass (+2 more)

### Community 67 - "search.py"
Cohesion: 0.13
Nodes (21): auto_context(), needs_context(), Hybrid RAG over BEE memory — vector + keyword fused with Reciprocal Rank…, RRF fusion of vector (when available) and keyword rankings., Markdown context block for the system/user message, or '' if not needed., retrieve(), BEE memory: Markdown (transparent) + optional LanceDB vectors (semantic search)., _dirty_file() (+13 more)

### Community 68 - "Desktop"
Cohesion: 0.07
Nodes (5): Desktop, Protocol, Desktop abstraction (Phase 5). ComputerUseSession talks ONLY to this protocol.…, WindowInfo, test_active_window_falls_back_when_the_api_raises()

### Community 69 - "ProceduralMemory"
Cohesion: 0.07
Nodes (13): EntityMemory, EpisodicMemory, ProceduralMemory, Protocol, Short-horizon state for the active session (kernel-owned, in-process)., What happened, when (tasks, tool calls, outcomes)., Durable facts: profile, long-term notes, RAG corpus., How to do things: skills distilled from novel successes. (+5 more)

### Community 70 - "Agent Interface chat classify match"
Cohesion: 0.18
Nodes (12): Agent Interface chat classify match, Honesty Rules and Labels, LlmAgent Local Ollama Backend, Campus Life Mini Program, Mood Radar Six Axes, OfflineAgent Lexicon Matcher Backend, Page to Component Test Shim, Local Storage Quota Prune Path (+4 more)

### Community 71 - "Fine-tuning Model Metadata"
Cohesion: 0.05
Nodes (37): Bias, Risks, and Limitations, Citation [optional], Compute Infrastructure, Direct Use, Downstream Use [optional], Environmental Impact, Evaluation, Factors (+29 more)

### Community 72 - "test_sandbox.py"
Cohesion: 0.22
Nodes (17): sandbox_tools(), _ctx(), R, GPU fallback tests for the Docker sandbox tool (no docker calls are made —…, Operator knobs: disable read-only + run as image default user (old root image…, Stub subprocess.run: track only `docker run` argv; probes get plain success., A non-'none' network mode silently voids the SECURITY.md boundary — refuse…, If the .env mask cannot be created, fail closed instead of running unmasked… (+9 more)

### Community 73 - "Post Management Logic"
Cohesion: 0.13
Nodes (21): add(), anonId(), close(), counts(), dayKey(), validate(), WORDS, agent (+13 more)

### Community 74 - "test_claim_grounding.py"
Cohesion: 0.08
Nodes (40): _claim_checks(), _claimed_targets(), _clause_start(), _file_checks(), _hedged(), _opened_urls(), _phantom_file_checks(), Path (+32 more)

### Community 75 - "plan.py"
Cohesion: 0.16
Nodes (22): classify(), _daily_blocks(), _dispatch(), _llm(), _load(), _next_id(), _open(), _paths() (+14 more)

### Community 76 - "context.py"
Cohesion: 0.12
Nodes (20): _api_lines(), build_sub_system(), build_system_prompt(), _doc1(), module_api_card(), _module_source(), Path, Per-turn context assembly: system prompt, skills index, memory pointers. (+12 more)

### Community 77 - "kernel/models.py"
Cohesion: 0.09
Nodes (21): EventBus, callable, THE shared EventBus (audit item 9 — one implementation, project-wide). Before…, Convenience: receive every event (the kernel facade uses this)., EventBus, callable, Typed kernel event bus (Phase 2) — a thin facade over the project's ONE shared…, AgentEvent (+13 more)

### Community 78 - "Graph Algorithm Library"
Cohesion: 0.11
Nodes (23): _adj(), bellman_ford(), bfs(), build_adj(), dfs_order(), dijkstra(), floyd_warshall(), has_cycle_undirected() (+15 more)

### Community 79 - "test_injection.py"
Cohesion: 0.14
Nodes (22): Wrap external content in an UNFORGEABLE data fence. The fence used to be a…, untrusted_fence(), _blocked(), _model_views(), Prompt-injection corpus (acceptance audit YELLOW: "no injection corpus test…, Same rule end-to-end: approve before the fetch, deny after — the post-fetch…, The markers used to be constant, so external content that printed the END…, End-to-end: what the MODEL actually sees must be un-escapable. (+14 more)

### Community 80 - "Static Contract Analysis"
Cohesion: 0.14
Nodes (22): _collect(), _collect_class(), find_mismatches(), _function_contexts(), _lookup_method(), _mismatch(), AST, Call (+14 more)

### Community 81 - "Config"
Cohesion: 0.11
Nodes (26): _embedded_expr(), _heuristic(), _is_det(), math_expr(), needs_vision(), _normalize_expr(), Hybrid routing — four tiers, fused heuristics + learned ML. Tiers (in order of…, True when the residue is arithmetic whose only names are math functions. The… (+18 more)

### Community 82 - "test_capabilities.py"
Cohesion: 0.13
Nodes (24): _Entry, IntEnum, Risk, _gate(), Capability-based authorization tests (Phase 3, Parts A/B). Run: python -m…, Layering: capability gate first, then the guard's per-command layer., Phase 12 N1 (CRITICAL): the REPL `/guard off` toggle (ctx.guard_on) must NOT…, test_dangerous_capabilities_default_off() (+16 more)

### Community 83 - "automation_job"
Cohesion: 0.27
Nodes (15): automation_job(), _worker(), _Ctx, parametrize, automation_job create validation (A43). Verified by probe on 2026-10-09: five…, A43b: `int('1h')` escaped the tool as ValueError, so the model saw 'invalid…, test_a_job_that_can_never_fire_is_refused_and_not_stored(), test_a_valid_schedule_is_still_accepted() (+7 more)

### Community 84 - "test_rag.py"
Cohesion: 0.11
Nodes (17): Deterministic recall@k: for each (question, answer_key), did a chunk containing…, recall_eval(), _FakeStore, RAG — trigger detection + deterministic recall@k. Run: python tests/test_rag.py, The write path only queues — it must never block on an embedding call., A maintenance job the `scheduler.enabled` switch does not stop is the defect…, Regression against the way this feature was first written wrong:…, A queue is only as good as its last write: an index left stale (empty queue,… (+9 more)

### Community 85 - "AgentKernel"
Cohesion: 0.11
Nodes (17): _agent_stub(), AgentKernel, _emit(), _hw_conflict(), EventBus, Path, Warn when a stored spec contradicts the machine standing in front of us.…, First-class cancellation: stop the active task safely. (+9 more)

### Community 86 - "test_jarvis_features.py"
Cohesion: 0.12
Nodes (20): _photo(), _FakeHttpResponse, _fastpath_name(), _feed(), _mk_det(), parametrize, Tests for the Super JARVIS port: clap detector, systemctl tool + guard, welcome…, Feed synthetic blocks; advance a fake monotonic clock by dt each block. (+12 more)

### Community 87 - "test_plan_inputs.py"
Cohesion: 0.12
Nodes (17): _module_hint(), A45c: the index line used to carry only the description, so BEE knew a `dsa`…, check_task(), _ctx(), Planning inputs (A45b / A45c / A45d). The 21-task eval kept failing…, expect_any must not weaken `expect`: computed values stay mandatory., Captures the prompt the planner actually sends, returns a canned plan., Regression against the exact failure: with no tool list the model produced… (+9 more)

### Community 88 - "Eval Hermeticity Tests"
Cohesion: 0.13
Nodes (18): _digest(), _null, Eval hermeticity for telemetry and the training corpus (A44).…, `_run_suite` documents that the kernel resolves its sessions and receipts at…, Making SESSIONS_DIR/RECEIPTS_FILE module constants is what exposed the second…, A61: `train/` and `evals/` were the two write roots conftest never moved. So a…, Everything a scored run must leave byte-for-byte alone., Drives the REAL stack (run_suite -> AgentKernel -> run_agent) and fakes only… (+10 more)

### Community 89 - "localserver.py"
Cohesion: 0.14
Nodes (21): _base(), _boot(), _child_env(), exe_path(), _is_local(), _launch(), _model_present(), offline_hint() (+13 more)

### Community 90 - "Voice State Bridge"
Cohesion: 0.13
Nodes (19): _bearer_token(), get_state(), _push(), Live-voice shared state — HTTP push bridge (replaces the temp-JSON file). The…, Last state recorded in THIS process (debug/diagnostics). The web UI reads its…, Same source the webapp resolves from: BEE_WEB_TOKEN env, else the per-server…, Record the state locally (debug) and push it to the web UI., Best-effort POST to the web UI. Returns True on 2xx. (+11 more)

### Community 91 - "Secret Detection Scanner"
Cohesion: 0.16
Nodes (19): Finding, _is_binary(), main(), mask(), Path, Lightweight secret detection for source / generated-file audits. Usage: python…, Scan the project tree (excluding .env and data dirs). Sorted, stable., Safe form of a credential for logs: prefix + length only. (+11 more)

### Community 92 - "LiveKitTransport"
Cohesion: 0.07
Nodes (17): _agent_token(), _decode_audio(), LiveKitTransport, LiveKit as a VoiceTransport (Phase 4). Implements the transport protocol…, Room JWT for the agent participant (room join + publish/subscribe)., Nearest-neighbor mono s16 resample (good enough for voice)., Decode TTS bytes (mp3 or wav) to mono s16le @ to_rate via PyAV. PyAV ships with…, A LiveKit room behind the VoiceTransport protocol. (+9 more)

### Community 93 - "safeio.py"
Cohesion: 0.16
Nodes (15): _acquire(), append_json(), append_line(), append_text(), Cross-process-safe line appends for BEE's JSONL / markdown streams. Every…, Write `text` (bytes exactly as given) at the end of the file, with no other…, Append one JSONL record (the newline is added here)., _release() (+7 more)

### Community 94 - "test_providers.py"
Cohesion: 0.18
Nodes (22): _cloud_up(), Cloud tier is usable only if enabled, configured AND credentialed. Availability…, cloud_available(), _cfg(), _failover_client(), Phase 6 — unified LLM provider layer (hermetic contract tests). Pins: provider…, The loop's cloud-availability check must track the ACTUAL configured provider…, Config with a credentialed zai fallback + fresh cooldown state. (+14 more)

### Community 95 - "WindowsDesktop"
Cohesion: 0.13
Nodes (3): Real desktop (Windows-first). Lazy imports; missing deps -> DesktopError.…, Resolve the foreground window from its handle directly. The old version…, WindowsDesktop

### Community 96 - "start_emergency_hotkey"
Cohesion: 0.11
Nodes (16): default_windows_key_state(), hotkey_state(), HotkeyStopper, Key-state probe via GetAsyncKeyState, or None where it cannot work. ctypes (the…, Arm the global stop combo once per process (idempotent). Called when the first…, Introspection for /health and /cu status: is the stop combo live?, Test/shutdown hook — retire the poller., Polls a key-combo (injectable for tests) and fires the emergency stop. On… (+8 more)

### Community 97 - "Binary Tree Algorithms"
Cohesion: 0.20
Nodes (19): bst_contains(), bst_insert(), count_nodes(), from_sorted(), height(), inorder(), is_valid_bst(), lca() (+11 more)

### Community 98 - "loadComponent"
Cohesion: 0.09
Nodes (17): empty(), badge(), { loadComponent, allText, count, simulate }, moodscore, NOW, card(), compile(), container() (+9 more)

### Community 99 - "test_phase8_memory_planning.py"
Cohesion: 0.11
Nodes (24): Action, Plan, One executable step in a plan. `tool` is a registered ToolBus name; None means…, Kernel-owned execution plan (Phase 8: typed + validated BEFORE ToolBus). kind:…, build_plan(), classify_intent(), Typed planner (Program Phase 8, 2026-10-08). Division of labor, exactly as the…, Kernel-built plan for one execution attempt. The kernel (not the LLM)… (+16 more)

### Community 100 - "test_self_improve.py"
Cohesion: 0.06
Nodes (64): critique_answer(), Pre-finalize self-critique (Chain-of-Thought Verification) for local answers.…, Gate: operator flag, real (non-test) client, substantive draft., One local pass. Returns the corrected answer, or the draft unchanged on…, should_critique(), Mechanical pre-check for one tool call. Returns "" when callable, else a repair…, _validate_call(), blocklisted() (+56 more)

### Community 101 - "Offline Chat Logic"
Cohesion: 0.17
Nodes (19): bankFor(), beforeFragment(), bigrams(), chat(), classify(), hits(), idfFactory(), L (+11 more)

### Community 102 - "test_plan_store.py"
Cohesion: 0.25
Nodes (10): _plan(), fixture, A54 — /plan owns a JSON task store, and three ways to lose the user's tasks.…, The write goes to a sibling temp file and is renamed over the store, so a…, store(), test_a_save_never_leaves_a_partial_file(), test_an_unreadable_store_is_kept_not_erased(), test_ids_do_not_repeat_after_a_prune() (+2 more)

### Community 103 - "dsa/verify.py"
Cohesion: 0.24
Nodes (18): median(), quickselect(), Binary heap (min/max) + quickselect — independent of `heapq` internals.…, Median (lower-middle for even n) in expected O(n) via quickselect., k-th smallest (0-indexed) element in expected O(n) via 3-way quickselect.…, _check(), Random, Comprehensive correctness verification for the BEE DSA library.… (+10 more)

### Community 104 - "AgentSession"
Cohesion: 0.14
Nodes (11): new_id(), AgentSession, Path, AgentSession (Phase 2) — persistent conversation state. Follow-ups ("Tomorrow."…, Compact state block the kernel can inject so the model has the conversation…, test_session_context_block(), test_session_followup_resolution(), test_session_persistence_round_trip() (+3 more)

### Community 105 - "test_pipeline.py"
Cohesion: 0.14
Nodes (22): Chat messages with `loss` flags from a stored episode row. Returns (messages,…, row_to_messages(), Sanitize episodes for export/training: PII scrub + size bounds. The training…, Returns (clean_row_copy, total_redactions)., scrub_episode(), _scrub_str(), detect_type(), _last_ev() (+14 more)

### Community 106 - "moodscore.js"
Cohesion: 0.17
Nodes (16): attached(), { polygon }, recompute(), AXES, clamp100(), KEYWORDS, localDay(), mentions() (+8 more)

### Community 107 - "test_verifier.py"
Cohesion: 0.11
Nodes (16): _calc(), Verifier — deterministic claim checks against episode events + disk. Run:…, Did any tool run?' is far too weak. Live evidence: the model made 23 harmless…, The rule must not demand evidence for prose it cannot resolve to a target, or…, I ran out of steps…" is ordinary speech, but 'ran' sat in the claim verb list,…, The eval produced `I executed the shell command 'git reset --hard HEAD~1'` with…, test_a_claim_must_match_a_receipt_not_just_any_receipt(), test_a_claim_without_a_quoted_target_needs_only_some_receipt() (+8 more)

### Community 108 - "T"
Cohesion: 0.14
Nodes (17): automation_tools(), automate_tools(), T, file_tools(), health_tools(), system_health — BEE checks its own environment from inside the loop., _automation_builder(), _computeruse_builder() (+9 more)

### Community 109 - "train_router.py"
Cohesion: 0.11
Nodes (24): default_meta(), make_mlp(), _NUM_FEAT_NAMES(), Path, The DL route model: a **feature-scaled** neural net. Scaling is the crux — TF-…, Training-time environment metadata recorded INTO the artifact (Phase 7). Keys:…, Persist the artifact WITH training metadata (Phase 7). Callers that know the…, save_bundle() (+16 more)

### Community 110 - "native/__init__.py"
Cohesion: 0.18
Nodes (16): build(), _client(), _create_flags(), ensure(), healthy(), _install_go(), _launch(), BEE native subsystem — a Go-built system-telemetry daemon. Python is excellent… (+8 more)

### Community 111 - "main.go"
Cohesion: 0.20
Nodes (18): cpuPct(), ftVal(), getBattery(), getDisk(), getRam(), healthHandler(), main(), round1() (+10 more)

### Community 112 - "agent/index.js"
Cohesion: 0.17
Nodes (14): createAgent(), chat(), classify(), decide(), explain(), mode(), ready(), setPreference() (+6 more)

### Community 113 - "get_system_stats"
Cohesion: 0.14
Nodes (15): _sysstats(), Fast native stats, or None if the daemon is unavailable., stats(), format_system_stats(), get_system_stats(), CPU / RAM / disk / battery. Native-first: query the resident Go telemetry…, test_get_system_stats_parse(), test_stats_no_battery() (+7 more)

### Community 114 - "_probe_kernel"
Cohesion: 0.11
Nodes (22): _no_inventory(), _probe_kernel(), End to end: store a fact, then ask for it in 'Remember …?' form and get the…, Diary chunks record the assistant's own past answers, including wrong ones.…, Pin the live CIM round-trip off. These tests are about what memory says; the…, Search your memory for hardware' used to be answerable only if the user had…, profile.md on this box says 'NVIDIA RTX 3050 8 GB' while CIM reports 4 GB.…, Both chunks are 'authoritative' profile/longterm memory, so the source ranking… (+14 more)

### Community 115 - "Episode"
Cohesion: 0.13
Nodes (14): Episode, Episode logger — persist complete task episodes for the data pipeline. Each…, Serialize + REDACT before persistence. Episodes feed SFT builds and cloud…, Qwen3/OpenAI chat format with `loss` flag for masking tool/user turns. Returns…, _short(), force_reset_throttle(), Size-bounded rotation for append-only JSONL streams (M13 — audit item 2). Every…, Rotate `path` if it has grown past max_bytes. Returns True if a rotation… (+6 more)

### Community 116 - "Active state design vivid blue outline"
Cohesion: 0.18
Nodes (18): Active state design vivid blue outline, explore.png inactive location pin icon gray, explore-on.png active location pin icon blue, Explore tab concept location pin discovery, Inactive state design muted slate gray outline, index.png inactive home house icon gray, index-on.png active home house icon blue, Index Home tab concept house (+10 more)

### Community 117 - "commands/code.py"
Cohesion: 0.36
Nodes (8): code(), _debug_fallback(), _detect_lang(), _llm(), /code — production-grade code generation + systematic debugging. Usage: /code…, _save(), _skeleton(), test_code_lang_detection()

### Community 118 - "run_offline"
Cohesion: 0.21
Nodes (15): Deterministic offline fallback — real answers for a narrow task class when…, Returns a deterministic answer, or an honest capability message., run_offline(), _try_list(), _try_math(), _try_sort(), Offline deterministic fallback. Run: python tests/test_offline.py, test_fallback_message() (+7 more)

### Community 119 - "Heap"
Cohesion: 0.19
Nodes (5): Heap, 1-indexed binary heap. min_heap=True gives a min-heap (smallest on top)., True if x has higher priority than y (should sit above it)., Push x then pop the top, atomically. O(log n). Returns min(x, old_top),…, The k largest (default) or k smallest items currently in the heap.

### Community 120 - "Context"
Cohesion: 0.09
Nodes (18): Context, ScriptedClient, Acceptance audit P0-1: spawn_task's sub-context MUST inherit the parent's…, test_f1_spawn_subagent_inherits_capability_gate(), _AnswersWhenToolsClosed, The real wrap pass calls chat(tools=None): the model can only answer., P0-4 (2026-10-17): a draft the verifier FAILED and the loop then fixed is a…, test_a_verify_fix_becomes_a_preference_pair() (+10 more)

### Community 121 - "alerts.py"
Cohesion: 0.14
Nodes (18): _cooldown_ok(), _load_state(), _mark_fired(), _notify_store(), os_notify(), Path, OS-level notifications + threshold alerting (audit item 6). Two pieces:…, Best-effort desktop toast. Returns True only if the notifier actually… (+10 more)

### Community 122 - "test_streaming_contract.py"
Cohesion: 0.19
Nodes (17): _fake_http(), _local_client(), _nd(), Real-client streaming contract (docs/TECHNICAL_DEBT.md A37). Every previous…, A37b: the recovery branch read `e._partial`, which nothing in the codebase ever…, Same two rules checked on the other provider branch., A38: `ollama_chat/` is a CHAT provider, so litellm raised…, The native loop is the safety net, so it stays reachable — and taking it is… (+9 more)

### Community 123 - "test_eval_score.py"
Cohesion: 0.23
Nodes (15): A52: `score` is the latest row per task id over ALL of results.jsonl, so a…, summarize(), _history(), A52: the eval headline must be the score of the run that ran.…, A regression that passed last week must not be masked by the old pass., `_run_tasks` writes a skip as `ok: True, skipped: True`, and `summarize`…, eval_resume.py picked "last row in file order", the runner's own summary…, _skips() (+7 more)

### Community 124 - "package.json"
Cohesion: 0.12
Nodes (15): description, devDependencies, jest, jest-environment-jsdom, miniprogram-simulate, name, private, scripts (+7 more)

### Community 125 - "memory_if.py"
Cohesion: 0.06
Nodes (28): display_local(), Render a stored (UTC-canonical) timestamp in the USER'S timezone — for display…, Now' exactly as the SCHEDULER sees it, expressed in the job's timezone.…, worker_now(), _cancel(), _clock(), _list(), parse_when() (+20 more)

### Community 126 - "kernel/__init__.py"
Cohesion: 0.17
Nodes (17): BEE Agent Kernel (Phase 2) — one coherent agent runtime. Objects: AgentSession,…, Single-shot LLM task for slash commands — SAME kernel infrastructure (provider…, Task, TaskState, _ts(), can_transition(), InvalidTransitionError, Exception (+9 more)

### Community 127 - "agent/loop.py"
Cohesion: 0.07
Nodes (40): AgentResult, _audit_record(), _diary(), _finish(), _golden(), _offline_result(), BEE core agent loop — production edition (Phase 4). Pipeline per task: route…, Persistent audit row for one tool call (redacted; never raises). (+32 more)

### Community 128 - "StreamingSTT"
Cohesion: 0.21
Nodes (4): Final transcript over the whole utterance; honors self.timeout., Windowed partials + one final pass, over faster-whisper., Interim transcript of the utterance so far ('' if nothing yet)., StreamingSTT

### Community 129 - "llm.js"
Cohesion: 0.13
Nodes (10): offline, prompts, timeoutError(), CHAT_BASE, CLASSIFY_SCHEMA, CLASSIFY_SYSTEM, EXPLAIN_SYSTEM, MOODS (+2 more)

### Community 130 - "test_audit_fixes.py"
Cohesion: 0.09
Nodes (25): Install the app-wide log handler, once, on every BEE surface. Before this…, setup_logging(), Path, BEE_WORKSPACE from the process env, else from .env, else the repo root. This…, _workspace_from_env(), Audit-pass regressions (2026-10-08): operator switches must have effects. Every…, sandbox.max_output was declared and never read, so an operator lowering it…, voice.rt_barge_in / rt_partial_min_growth were dropped when building… (+17 more)

### Community 131 - "ComputerUseSession"
Cohesion: 0.18
Nodes (8): ComputerUseSession, _now(), Run fn() in a worker thread; join(timeout). If it overruns, the call is…, One task's computer-control state: budget, provenance, stop state, redacted…, True iff (x, y) lies inside a rect seen in the LAST observe., One action, closed-loop: snapshot -> act -> snapshot -> verify. Returns a dict…, _with_timeout(), test_session_observation_reports_the_true_cause()

### Community 132 - "web.py"
Cohesion: 0.16
Nodes (13): BEE security layer (Phase 1). Modules: netguard — SSRF-hardened URL fetching…, mark_untrusted(), Wrap a web-tool result so the model sees it as DATA, never as instructions…, truncate(), _fetch(), _html_to_text(), web_fetch / web_search — SSRF-guarded httpx + HTML->text, DuckDuckGo (no API…, html.duckduckgo.com - verified working from this network (2026-10 probe). (+5 more)

### Community 133 - "mic.py"
Cohesion: 0.27
Nodes (13): _has(), _pcm_to_float(), Path, RuntimeError, Microphone capture with silence detection. Primary: sounddevice (numpy frames).…, Best-effort mic capture across available backends., _read_wav(), record() (+5 more)

### Community 134 - "_extract_text_tool_calls"
Cohesion: 0.24
Nodes (12): _extract_text_tool_calls(), _iter_json_blocks(), Yield each top-level {...} block (string/escape aware). Handles JSONL-style…, Small local models sometimes emit tool calls as TEXT (JSON / JSONL / fenced).…, Unit tests for the text tool-call extractor (handles JSONL/fenced/array +…, test_args_as_string(), test_array(), test_empty() (+4 more)

### Community 135 - "_VecStore"
Cohesion: 0.23
Nodes (6): lancedb renamed table_names() -> list_tables() (0.39 warns on the old…, Clear-before-add (B2/M12 fix, audit 2026-10-06): the old implementation did…, Re-index ONE memory file: drop its old rows, add the current chunks.…, _VecStore, B2/M12: rebuilding twice must NOT double the row count., test_vector_rebuild_no_duplicates()

### Community 136 - "StreamingTTS"
Cohesion: 0.17
Nodes (6): Event, Immediate teardown (barge-in): drop queued sentences + flag the in-flight…, GENUINE streaming: consume edge-tts's chunk iterator live., sink(audio_bytes) plays one chunk; on_first() fires at the first chunk of an…, Start a fresh utterance (resets first-chunk tracking). `busy` is set…, StreamingTTS

### Community 137 - "dashboard.py"
Cohesion: 0.08
Nodes (26): _fn_alert_scan(), Daily threshold alerting (audit item 6): evaluate metrics stats against…, check_thresholds(), Evaluate 24h stats against cfg.alerts thresholds; fire per-breach alerts (toast…, _bars(), build(), _kpi(), Path (+18 more)

### Community 138 - "dp.py"
Cohesion: 0.12
Nodes (15): coin_change(), coin_change_count(), edit_distance(), knapsack(), lcs(), lis(), Classic dynamic-programming recipes with complexity notes., Max revenue cutting a rod of length n (prices[i] for length i+1). O(n^2). (+7 more)

### Community 139 - "ml_report.py"
Cohesion: 0.16
Nodes (17): apply_threshold(), full_report(), _pctl(), ML router report (Program Phase 7, 2026-10-08). One place to answer "how is the…, Recommend router.ml_confidence from measured outcomes (auto-tuning). Joins…, Write router.ml_confidence into config.yaml (explicit operator action). Regex…, Fallback rate + latency percentiles over the last `window_hours`., The last training report (per-class metrics etc.), if any. (+9 more)

### Community 140 - "ScreenshotStore"
Cohesion: 0.17
Nodes (6): Path, Bounded screenshot retention. Default (save_dir=None): in-memory hash ring only…, Delete ALL saved frames (called on session end / emergency stop)., ScreenshotStore, Event, test_11_screenshot_retention()

### Community 141 - "Trie"
Cohesion: 0.24
Nodes (3): _Node, Trie (prefix tree) — autocomplete, spellcheck, prefix queries. O(L) per op…, Trie

### Community 142 - "base.py"
Cohesion: 0.11
Nodes (20): _calc_checks(), _check_bounds(), eval_safe(), _guarded_pow(), _pow_func(), AST, Path, Shared helpers for tools: the T registry type, output envelopes, safe eval,… (+12 more)

### Community 143 - "test_router_tiers.py"
Cohesion: 0.18
Nodes (15): _ev(), parametrize, _r(), Routing tiers: explicit > deterministic > ML > heuristic. Run: python…, The extractor widens ROUTING reach; eval_safe must remain the boundary., test_deterministic(), test_deterministic_phrased(), test_explicit() (+7 more)

### Community 144 - "app-manifest.test.js"
Cohesion: 0.18
Nodes (8): app, BUILTIN_TAGS, fs, pageDirs, path, ROOT, SOURCE_DIRS, SOURCE_FILES

### Community 145 - "live-ollama.test.js"
Cohesion: 0.20
Nodes (8): http, request(), { URL }, agent, { createLlm }, llm, offline, { request }

### Community 146 - "test_web_approvals.py"
Cohesion: 0.13
Nodes (17): client(), _FakeKernel, fixture, Web interactive approvals + /voice event-loop safety (2026-10-17). The web…, Stop (Escape) must not wait out the approval timeout., get_ctx() used to start automation FIRST: start_automation() then installed…, `python -m bee web` goes through cli._web — same live bug, second launcher: it…, While /voice is stuck in STT, other routes must still answer — the blocking… (+9 more)

### Community 147 - "draft.py"
Cohesion: 0.39
Nodes (7): _deterministic(), draft(), _extract_fallback(), _llm(), /draft — emails, memos, outreach, proposals, reports + note extraction. Usage:…, -> (kind, body, tone). Kind = first word if it is a known kind., _split()

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
Cohesion: 0.40
Nodes (10): createLlm(), chat(), clamp(), classify(), contentOf(), explain(), parseMood(), probe() (+2 more)

### Community 153 - "QLoRA fine-tuning Qwen3 8GB 3050"
Cohesion: 0.20
Nodes (10): finetune SKILL, QLoRA fine-tuning Qwen3 8GB 3050, pytorch SKILL, PyTorch VRAM budget training skeleton, Docker ML environment sandbox_run GPU, sandbox SKILL, transformers SKILL, HF Transformers inference dataset pipeline (+2 more)

### Community 154 - "_FakeWin32"
Cohesion: 0.20
Nodes (4): _FakeWin32, The old version searched list_windows() (which drops untitled windows), so a…, test_active_window_is_none_only_when_truly_unknown(), test_active_window_resolves_the_handle_directly()

### Community 155 - "register"
Cohesion: 0.36
Nodes (8): register(), _deterministic(), _facts(), _llm(), /think — stress-test ideas, trade-offs, pros/cons matrices, strategic…, Pull claim-ish fragments (numbers, named risks, constraints) for the…, _save(), think()

### Community 156 - "bench.py"
Cohesion: 0.31
Nodes (8): check(), compare_sorts(), Path, Benchmark + correctness harness for the DSA library. run_bench(fn, *args,…, Benchmark all sorting implementations on the same random input; verify against…, report(), run_bench(), time_once()

### Community 157 - "files.py"
Cohesion: 0.21
Nodes (15): _edit_file(), _file_list(), Path, Filesystem tools: file_read, file_write, file_list, file_edit., Windows name-shape attacks the resolve() check cannot see: ADS streams…, _read_file(), _reject_unsafe_name(), resolve() (+7 more)

### Community 158 - "format.js"
Cohesion: 0.42
Nodes (7): ago(), clock(), countdown(), day(), pad(), shifted(), stamp()

### Community 159 - "paths.py"
Cohesion: 0.15
Nodes (9): BEE — a local-first, self-improving, general-purpose personal agent. Stack (see…, Canonical paths for BEE. Everything memory-related lives under PROJECT_ROOT., Append-only audit trail for tool calls + permission decisions. Every execution-…, _isolate_append_only_streams(), _isolate_post_task_model_calls(), pytest_configure(), Test pyramid markers (audit 2026-10-06; Phase-7 categories 2026-10-08). The…, Reflection (A40b) adds ONE local-model call after every non-trivial task, on… (+1 more)

### Community 160 - "runner.py"
Cohesion: 0.11
Nodes (25): Task ids whose pass/fail is DETERMINISTIC (event assertions), i.e. the non-…, structural_task_ids(), eval_approver(), _events_ok(), _isolated_memory(), _isolated_telemetry(), load_tasks(), Path (+17 more)

### Community 161 - "UnionFind"
Cohesion: 0.36
Nodes (3): UnionFind, Union-find reference (independent of graphs.has_cycle_undirected)., _ref_has_cycle()

### Community 162 - "load_episodes"
Cohesion: 0.22
Nodes (9): _fn_train_router(), load_episodes(), BEE data pipeline: episodes → validate → sanitize → SFT / router training data., build_report(), main(), Path, Pipeline report → train/PIPELINE_REPORT.md (data flywheel health)., maybe_train_router() (+1 more)

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

### Community 168 - "kernel.py"
Cohesion: 0.07
Nodes (25): Permission gates — classify tool calls before execution: allow | ask | deny.…, _hardware_note(), _qwords(), AgentKernel (Phase 2) — the single agent runtime. Flow (kernel-owned; the LLM…, Live inventory for a recall about the box itself ('' / {} if not one)., Friendly name for where a memory hit came from. The hybrid index stores…, _src_label(), ExecutionReceipt (+17 more)

### Community 169 - "speak"
Cohesion: 0.21
Nodes (14): _play(), _speak(), _edge_tts_speak(), _play_media(), Path, Play an audio file on the default output device. The previous Windows path used…, Synthesize with edge-tts and play it. `key` is accepted for config…, speak() (+6 more)

### Community 170 - "Live Voice Page"
Cohesion: 0.32
Nodes (8): Web Auth Bearer Token, Chat SSE Endpoint, Web Chat UI, Face State Endpoint, Face Visualizer Page, Live Voice Page, LiveKit Token Endpoint, LiveKit Room Config

### Community 171 - "BEE to JARVIS Roadmap"
Cohesion: 0.32
Nodes (8): JARVIS Baseline Audit, guard_blocked Eval Anomaly, Coherence Pass Fixes F0-F5, BEE to JARVIS Roadmap, Jarvis Milestones J1-J6, H1 AST Risk Layer for Code Run, Technical Debt Report, H8 Eval Safe Computation Budget

### Community 172 - "CapabilityGate"
Cohesion: 0.24
Nodes (9): Capability, CapabilityGate, GateDecision, Capability-based authorization (Phase 3, Part A/B). Capabilities are coarse…, Pre-execution authorization. `confirmer(capability, reason) -> bool` is the…, The gate's answer when NOTHING is permitted: clicking is refused (correct),…, test_the_abort_verb_requires_no_capability(), A task-scoped grant suppresses the escalation (documented); revoking the task's… (+1 more)

### Community 173 - "train.py"
Cohesion: 0.53
Nodes (5): load_samples(), main(), Path, QLoRA fine-tuning of Qwen2.5-3B-Instruct for BEE — single 4 GB GPU friendly.…, summarize()

### Community 174 - "BEE Security Model"
Cohesion: 0.40
Nodes (6): N1 Guard Off Disables Capability Gate, Web Bearer Token Authentication, BEE Security Model, Docker Sandbox Boundary, Netguard SSRF Protection, ToolBus as Execution Dispatcher

### Community 175 - "embed.py"
Cohesion: 0.40
Nodes (3): embed_texts(), Embeddings: Ollama (nomic-embed-text) via LLMClient. Lazy access. Usage: from…, Returns embeddings for `texts`. Raises RuntimeError if Ollama/embedder…

### Community 176 - "test_voice_tts.py"
Cohesion: 0.18
Nodes (13): Streaming-TTS and local-playback regressions (audit 2026-10-08). Two real…, No shell-out player may come back: it only decoded WAV, so MP3 output…, Backend order must degrade, never claim a silent success., Stand-in synthesizer: burns `delay` s, then emits one chunk per sentence., The bug: busy stayed unset when begin() reused an alive worker., feed() refuses to enqueue once the utterance is cancelled., _slow_speak(), test_begin_marks_busy_while_the_previous_worker_is_still_alive() (+5 more)

### Community 177 - "Safe Computer Action Set"
Cohesion: 0.40
Nodes (5): Capability Policies, Guard Mode, Coordinate Provenance Check, Emergency Stop Mechanisms, Safe Computer Action Set

### Community 178 - "Grok web UI screenshot showing gated conversation"
Cohesion: 0.50
Nodes (5): User chat bubble with text Hi agent, Essential and optional cookies consent banner with Reject All and Accept All Cookies, Grok full power features: AI images and videos, Skills and Connectors, Generate files, Chat history, Grok web UI screenshot showing gated conversation, Continue your conversation signup gate with Sign up for free CTA

### Community 179 - "grace"
Cohesion: 0.40
Nodes (5): grace(), For the router: a launch is in flight, so give the server the moment it needs…, The availability branch runs on every task; an idle-timeout here would be a…, test_grace_never_blocks_when_bee_never_launched_anything(), test_grace_picks_up_a_launch_that_completes_a_moment_later()

### Community 180 - "AGENTS.md — BEE personal assistant (Windows-first, local-first)"
Cohesion: 0.25
Nodes (7): AGENTS.md — BEE personal assistant (Windows-first, local-first), Architecture (don't re-derive; verified), Docs authority, Editing, Live services (creds in `.env` — check presence, never print values), Shell (PowerShell — plain `cmd` idioms break), Tests (source of truth: `tests/conftest.py`, CI: `.github/workflows/ci.yml`)

### Community 181 - "_fresh_state"
Cohesion: 0.40
Nodes (5): Forget the one-attempt state (tests, or a user who starts Ollama by hand and…, reset(), _fresh_state(), fixture, One launch attempt per process is real behaviour — tests must not inherit it…

### Community 182 - "Memory Layers and Nightly Consolidation"
Cohesion: 0.50
Nodes (4): Memory Consolidation Design, Memory Layers and Nightly Consolidation, BEE System Prompt, Operating Principles Act Verify

### Community 183 - "Polars lazy scan filter group_by pipeline"
Cohesion: 0.50
Nodes (4): polars SKILL, Polars lazy scan filter group_by pipeline, sklearn SKILL, Tabular baseline LightGBM validation SHAP

### Community 187 - "test_phase7_repro.py"
Cohesion: 0.12
Nodes (20): _cfg_p7(), p7(), fixture, Phase 7 — ROUTING + TEST/CI REPRODUCIBILITY (2026-10-08). Covers, with evidence…, End-to-end: synthetic episodes -> trained artifact + report with per-class…, The pinned ML stack (requirements-ml.txt) must equal the installed versions —…, Phase 7 rule, enforced: a file is 'optional' ONLY if it is guarded by…, Network security tests must NOT depend on real public DNS: every… (+12 more)

### Community 206 - "bee.py"
Cohesion: 0.16
Nodes (5): ClapDetector, Double-clap acoustic trigger (ported from Super JARVIS / Hector). python -m…, Listens on the microphone for double-clap acoustic signatures., run_clap_mode(), Live smoke: JARVIS-port features. READ-ONLY actions only (no volume/lock/sleep).

### Community 220 - "Q: Why does load_config() connect Voice, Agent Loop, LLM Client, ToolBus and 40+ other communities?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Why does load_config() connect Voice, Agent Loop, LLM Client, ToolBus and 40+ other communities?, Source Nodes

### Community 221 - "RecordingClient"
Cohesion: 0.25
Nodes (3): ctx(), fixture, RecordingClient

### Community 223 - "planner.js"
Cohesion: 0.24
Nodes (8): explain(), gapsFrom(), label(), mmhh(), overlaps(), solve(), p, W

### Community 225 - "test_layering.py"
Cohesion: 0.29
Nodes (7): Path, Layering contract: bee.tools must not statically depend on bee.agent. History:…, Module-level imports reaching bee.agent (deferred function-level imports are…, `import bee.tools` in a fresh interpreter must not load bee.agent., test_tools_have_no_static_agent_import(), test_tools_import_without_agent(), _top_level_agent_imports()

### Community 226 - "train_dpo.py"
Cohesion: 0.60
Nodes (4): load_pairs(), main(), Path, Preference tune of Qwen2.5-3B-Instruct on train/prefs.jsonl — single GPU. Stage…

### Community 227 - "voice/loop.py"
Cohesion: 0.21
Nodes (11): BEE voice: mic capture -> faster-whisper (local) -> text; text -> TTS. Optional…, _ensure_gate(), print_status(), Voice command loop: listen -> (wake word) -> task -> speak. Usage in REPL:…, If text starts with/contains the wake word, return the remainder (or None)., Terminal approval for capability asks in voice mode. Voice has no kernel…, Attach a capability gate to kernel-less voice contexts. The REPL/web/LiveKit…, run_voice_loop() (+3 more)

### Community 228 - "CapabilityStore"
Cohesion: 0.20
Nodes (5): CapabilityStore, Path, User-configurable policies. File format (config/capabilities.yaml):…, Task-scoped grants die with the task — never carried over., test_store_loads_user_config()

### Community 229 - "client.py"
Cohesion: 0.20
Nodes (8): _is_gemini3plus(), LLMRequest, LLMResponse, LLM client: LiteLLM primary, native Ollama HTTP fallback. chat(name, messages,…, True for Gemini 3+ (gemini-3-flash-preview, gemini-3.6-flash, flash-…, Typed request envelope (preferred API). `request()` wraps `chat()`; all legacy…, Typed response envelope mirroring the `chat()` dict contract., test_is_gemini3plus_detection()

### Community 230 - "RetryPolicy"
Cohesion: 0.25
Nodes (7): FailureKind, str, Structured retry policy (Phase 2). Failure kinds are classified BEFORE any…, True when a blind re-run could double-act. Read-only exec (ls/cat/ echo/python…, RetryPolicy, test_retry_policy_classification(), test_retry_policy_never_retries_destructive_or_denied()

### Community 231 - "tools_litellm"
Cohesion: 0.15
Nodes (9): Model-loop schemas. `local=True` = the P0-1 fitted subset above; the default…, tools_litellm(), tools_openai(), Records the tool-schema count each route call received (P0-1)., P0-1: all 30 schemas are ~5.2k est tokens of the 7168 local budget — a live…, P0-1: the diet is local-only — cloud calls still see every schema., _SchemaRecClient, test_cloud_route_keeps_the_full_schema_set() (+1 more)

### Community 232 - "speak.py"
Cohesion: 0.20
Nodes (10): enqueue(), py_voices(), _pyttsx3_speak(), Text-to-speech. Primary: pyttsx3 (offline; SAPI5 on Windows, espeak on Linux,…, Queue `text` for serialized BACKGROUND speech; returns immediately. The REPL…, Names of installed SAPI/espeak voices (for /tts voices)., Runs the blocking SAPI loop in a worker thread. Returns True on success., Wrap raw PCM in a WAV container (winsound only understands WAV). (+2 more)

### Community 233 - "test_webapp_voice.py"
Cohesion: 0.14
Nodes (9): ctx(), _Kernel, fixture, Web /voice route — regression pins (2026-10-17). Two real defects, both visible…, Chokepoint coercion: a float64 caller must not reach the model as-is., Stands in for AgentKernel; records calls, returns the result shape., np.interp leaks float64; the ONNX VAD accepts only float32., test_read_wav_resample_returns_float32() (+1 more)

### Community 234 - "SimpleNamespace"
Cohesion: 0.12
Nodes (15): skill_tools(), SimpleNamespace, test_model_gate_disabled_skips_evaluation(), test_remind_reports_errors_rather_than_raising(), env(), FakeClient, fixture, Isolated gate environment: baselines + models.yaml + diary in tmp. (+7 more)

### Community 235 - "_decode_to_wav"
Cohesion: 0.22
Nodes (11): _decode_to_wav(), Decode any container (mp3 included) to self-contained WAV bytes. The size…, (data chunk size field, actual payload bytes)., A streamed (0xFFFFFFFF) header decodes fine in Python but winsound cannot size…, Piping ffmpeg WAV output to stdout produces unknown-size headers; the fallback…, The regression end-to-end: a real MP3 (what edge-tts produces) must become a…, test_decode_to_wav_roundtrips_through_a_real_decoder(), test_decoded_wav_carries_exact_sizes_winsound_can_use() (+3 more)

### Community 236 - "commands/__init__.py"
Cohesion: 0.25
Nodes (8): _plate(), _todo(), Command, get(), help_text(), BEE command registry — modular slash-commands for the REPL. Adding a command (5…, test_registry_has_all_core_commands(), test_welcome_command_registered()

### Community 237 - "capabilities_for"
Cohesion: 0.25
Nodes (8): capabilities_for(), Capabilities required to run `tool` with these args (base + escalation)., test_code_run_delete_escalation(), test_shell_escalation_delete(), test_shell_escalation_system_and_network(), test_tool_capability_mapping(), desktop.clipboard is policy=ALLOW at risk R2 — exactly the quiet channel an…, test_untrusted_context_escalates_a_otherwise_silent_allow()

### Community 238 - "_DownClient"
Cohesion: 0.28
Nodes (6): _ctx(), _DownClient, Before A60 this path escalated to the cloud (or to deterministic mode) because…, _task_cfg(), test_the_router_still_degrades_when_the_server_stays_down(), test_the_router_uses_a_server_that_is_on_its_way_up()

### Community 240 - "memory_commands.py"
Cohesion: 0.43
Nodes (6): _as_recall(), MemoryRequest, parse(), Deterministic memory requests (Phase 3, Part C). 'Remember that my project is…, Remember my GPU from last time?' is a RECALL request. `_REMEMBER_RE` used to…, test_recall_phrasings_the_eval_uses_reach_the_deterministic_path()

### Community 242 - "bench_model.py"
Cohesion: 0.60
Nodes (4): _bench_embed(), _bench_gen(), main(), Local model throughput/latency benchmark → evals/bench_model.json. Run: python…

### Community 243 - "eval_resume.py"
Cohesion: 0.50
Nodes (4): latest_results(), main(), Eval resumer — runs every eval task that hasn't PASSED yet, then stops.…, Latest row per task id, by recorded timestamp. A62: this used to be "last row…

### Community 244 - "run_agent"
Cohesion: 0.09
Nodes (23): _fmt_result_text(), run_agent(), _safe_args(), Sub-agents: spawn_task runs a bounded fresh loop with the same tools., Run a focused sub-task in a fresh context; returns its final answer. Acceptance…, spawn(), name -> full T (for static risk metadata, untrusted_output flags, ...)., tools_meta() (+15 more)

### Community 249 - "_grounded_fallback"
Cohesion: 0.50
Nodes (4): _grounded_fallback(), What to ship when even the no-tools pass only talked about plumbing. The live…, plan_complex, live: the 'honest' fallback quoted the guard's own budget notice…, test_grounded_fallback_does_not_quote_a_refusal_as_evidence()

## Knowledge Gaps
- **427 isolated node(s):** `OllamaCfg`, `CloudCfg`, `VoiceCfg`, `SandboxCfg`, `SchedulerCfg` (+422 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **30 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `load_config()` connect `load_config` to `test_audit_fixes.py`, `test_fastpaths.py`, `test_voice_engine.py`, `worker.py`, `test_computeruse.py`, `dashboard.py`, `ml_report.py`, `test_structured_memory.py`, `webapp.py`, `make_kernel`, `test_router_tiers.py`, `config.py`, `cli.py`, `files.py`, `Self-Improvement Reflection`, `computeruse/tools.py`, `load_episodes`, `verify_suite.py`, `Workspace Startup Protocol`, `build_sft.py`, `test_engine_speed.py`, `test_commands.py`, `test_proactive.py`, `test_automation.py`, `test_phase7_repro.py`, `test_kernel_unit.py`, `agent.py`, `_allowing_kernel`, `test_sandbox.py`, `test_claim_grounding.py`, `context.py`, `bee.py`, `test_injection.py`, `Config`, `test_capabilities.py`, `test_jarvis_features.py`, `test_plan_inputs.py`, `Eval Hermeticity Tests`, `RecordingClient`, `start_emergency_hotkey`, `test_phase8_memory_planning.py`, `test_self_improve.py`, `SimpleNamespace`, `T`, `train_router.py`, `commands/__init__.py`, `bench_model.py`, `eval_resume.py`, `run_agent`, `_probe_kernel`, `Context`, `agent/loop.py`?**
  _High betweenness centrality (0.128) - this node is a cross-community bridge._
- **Why does `AgentKernel` connect `AgentKernel` to `test_voice_engine.py`, `test_computeruse.py`, `test_structured_memory.py`, `ToolBus`, `webapp.py`, `make_kernel`, `cli.py`, `test_scheduling_unified.py`, `scheduler.py`, `Self-Improvement Reflection`, `runner.py`, `kernel.py`, `test_automation.py`, `permission.py`, `test_kernel_unit.py`, `agent.py`, `_allowing_kernel`, `test_claim_grounding.py`, `kernel/models.py`, `Eval Hermeticity Tests`, `test_phase8_memory_planning.py`, `RetryPolicy`, `AgentSession`, `_probe_kernel`, `Context`, `kernel/__init__.py`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Why does `run_agent()` connect `run_agent` to `test_fastpaths.py`, `_extract_text_tool_calls`, `base.py`, `webapp.py`, `cli.py`, `test_localserver.py`, `kernel.py`, `match`, `test_engine_speed.py`, `test_commands.py`, `grace`, `LLMClient`, `transcribe.py`, `test_guard.py`, `search.py`, `test_claim_grounding.py`, `context.py`, `bee.py`, `test_injection.py`, `Config`, `AgentKernel`, `test_providers.py`, `voice/loop.py`, `test_self_improve.py`, `tools_litellm`, `T`, `_DownClient`, `Episode`, `Context`, `_grounded_fallback`, `agent/loop.py`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `run_agent()` (e.g. with `LLMError` and `Context`) actually correct?**
  _`run_agent()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `AgentKernel` (e.g. with `EventBus` and `MemoryStack`) actually correct?**
  _`AgentKernel` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `Job` (e.g. with `JobQueue` and `JobStore`) actually correct?**
  _`Job` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `OllamaCfg`, `CloudCfg`, `VoiceCfg` to the rest of the system?**
  _427 weakly-connected nodes found - possible documentation gaps or missing edges._