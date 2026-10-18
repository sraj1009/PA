# Graph Report - PA  (2026-10-18)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 5058 nodes · 10871 edges · 249 communities (219 shown, 30 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 349 edges (avg confidence: 0.88)
- Token cost: 8,961 input · 1,785 output

## Graph Freshness
- Built from commit: `796a98c1`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- render.js
- Server
- test_commands.py
- page-chat.test.js
- test_voice_engine.py
- Job
- page-shop.test.js
- test_self_improve.py
- test_computeruse.py
- test_providers.py
- test_engine_speed.py
- test_structured_memory.py
- test_kernel_unit.py
- worker.py
- JobStore
- webapp.py
- test_kernel_integration.py
- kernel.py
- config.py
- cli.py
- test_webauth.py
- fastpaths.py
- realtime/__init__.py
- index/index.js
- Telemetry Integrity Testing
- test_scheduling_unified.py
- scheduler.py
- computeruse/__init__.py
- store
- Eval Runner Validation
- VoiceEngine
- test_reflection_loop.py
- computeruse/tools.py
- test_skill_gate.py
- mlrouter.py
- verify_suite.py
- test_netguard.py
- chat/index.js
- test_localserver.py
- dsa/__init__.py
- ML Router Features
- EventBus
- welcome.py
- build
- start_sources
- _run
- Guard Execution Stubs
- test_exec_tools.py
- pages
- schema.js
- JobTrigger
- make-tabbar-icons.js
- classify_risk
- test_proactive.py
- StructuredMemory
- shops/index.js
- test_automation.py
- LLMClient
- Permission Risk Assessment
- systemctl.py
- kernel/models.py
- agent.py
- transcribe.py
- _allowing_kernel
- Command Guard Rules
- md.py
- Model Training Strategy
- search.py
- Desktop
- ProceduralMemory
- Agent Configuration Layers
- Task Capability Policies
- Docker Sandbox Security
- treehole/index.js
- test_claim_grounding.py
- plan.py
- load_config
- EventBus
- run_dsa_graphs
- test_injection.py
- test_static_contracts.py
- Hardware Memory Retrieval
- test_capabilities.py
- automation_job
- test_rag.py
- AgentKernel
- test_jarvis_features.py
- Capability Authorization Gate
- runner.py
- Local Model Server
- livekit/state.py
- secretscan.py
- LiveKitTransport
- LLM Provider Registry
- test_eval_gate.py
- WindowsDesktop
- Provider Environment Configuration
- binary_tree.py
- Preference Pair Derivation
- test_phase8_memory_planning.py
- ratings.py
- Text Analysis Utilities
- Task Plan Storage
- Data Structures and Algorithms
- Agent Session Management
- test_pipeline.py
- radar/index.js
- Action Verification Logic
- UI Vision Backend
- ML Route Training
- Native Telemetry Lifecycle
- System Telemetry Daemon
- Agent Core Interface
- System Stats Provider
- Routing Tier Logic
- paths.py
- UI State Assets
- Code Generation Tool
- Deterministic Offline Fallback
- Binary Heap Implementation
- Action Claim Verification
- Retry Policy Classification
- Streaming Client Contract
- test_eval_score.py
- Project Metadata and Scripts
- memory_if.py
- kernel/__init__.py
- run_agent
- StreamingSTT
- LLM Prompt Templates
- test_audit_fixes.py
- Acoustic Clap Trigger
- SSRF Guarded Web Tools
- Microphone Audio Capture
- JSON Tool Call Extractor
- Vector Memory Management
- speak.py
- bee/__init__.py
- Dynamic Programming Recipes
- ML Performance Reporting
- Screenshot Retention Store
- Trie Prefix Tree
- base.py
- Config
- App Manifest Testing
- HTTP Client Testing
- Web Approval Workflow
- Command Registry
- System Audit Status
- Document Summarization Tool
- Hybrid RAG Retrieval
- Voice Transport Protocol
- JavaScript LLM Interface
- Fine-tuning Environment
- Active Window Detection
- Reasoning and Analysis Tool
- DSA Benchmarking
- Secure Filesystem Tools
- Formatting Utilities
- Test Suite Configuration
- Eval Workspace Restoration
- Union-Find Algorithm
- _no_fastpath
- Semantic Memory Facade
- Lexicon Word Lists
- Group Management Logic
- Dependency Management
- Privacy and Redaction
- App Transition Monitoring
- Web and Voice Endpoints
- Project Roadmap and Audits
- Execution Receipt Logging
- Model Fine-tuning Script
- Security Model Overview
- Text Embedding Service
- Service Health Checks
- Safety Control Mechanisms
- Web UI Screenshots
- Server Launch Grace
- Architecture Documentation
- Process State Reset
- Memory Consolidation Design
- Data Science Skills
- Jest Test Configuration
- State Management Setup
- test_phase7_repro.py
- Model Adapter Merging
- BEE Agent Core
- Episode Data Capture
- Evaluation Framework
- Linux CI Workflows
- Model Orchestration Registry
- Desktop Automation Stack
- LiveKit Integration Stack
- Vision Dependency Extras
- Voice Processing Stack
- Task Decomposition Skill
- Browser Automation Skill
- DSA Benchmark Skill
- Eval Status Reporting
- Planner Integration Client
- Constraint Planner Solver
- Windows CI Job
- Voice Workflow Automation
- Windows Desktop Workflow
- Grok Session Insight
- Telemetry Tracking
- Agent Configuration Query
- Recording Client Mock
- Response Object Wrapper
- Planner Logic Utilities
- Data Sanitization Utilities
- Module Layering Contract
- DPO Model Training
- Task Mocking Framework
- Module API Documentation
- Emergency Stop Hotkey
- Docker Sandbox Environment
- Event Bus System
- Drafting and Composition
- Voice Route Testing
- LLM Client Mocking
- Typed LLM Envelopes
- Device Pressure Monitoring
- MCP Server Config
- Scripted Reply Mock
- Stream Mocking Utilities
- Memory Recall Requests
- Preference Data Export
- Grounded Fallback Logic
- Agent Probe Testing
- Scripted Test Client
- Task Failure Testing
- Skill Directory Management
- Skill Validation Logic

## God Nodes (most connected - your core abstractions)
1. `load_config()` - 158 edges
2. `run_agent()` - 92 edges
3. `AgentKernel` - 71 edges
4. `make_kernel()` - 71 edges
5. `Context` - 64 edges
6. `Job` - 62 edges
7. `LLMClient` - 61 edges
8. `JobWorker` - 56 edges
9. `JobStore` - 54 edges
10. `MockDesktop` - 51 edges

## Surprising Connections (you probably didn't know these)
- `OfflineAgent Lexicon Matcher Backend` --semantically_similar_to--> `FastPaths Deterministic Tier`  [INFERRED] [semantically similar]
  campus-life/docs/2026-10-12-design.md → docs/JARVIS_ARCHITECTURE.md
- `test_followup_context_merges_time_hints()` --calls--> `AgentSession`  [EXTRACTED]
  tests/test_phase8_memory_planning.py → bee/kernel/session.py
- `test_pronoun_reference_resolves_against_active_task()` --calls--> `AgentSession`  [EXTRACTED]
  tests/test_phase8_memory_planning.py → bee/kernel/session.py
- `test_07_corrupt_executions_skips_bad_lines()` --calls--> `JobStore`  [EXTRACTED]
  tests/test_phase12_reliability.py → bee/automation/store.py
- `env()` --uses--> `Config`  [INFERRED]
  tests/test_eval_gate.py → bee/config.py

## Import Cycles
- 4-file cycle: `bee/agent/loop.py -> bee/tools/__init__.py -> bee/tools/spawn_tool.py -> bee/agent/spawn.py -> bee/agent/loop.py`

## Hyperedges (group relationships)
- **One agent interface with auto-selected backends** — campus_life_agent_interface, campus_life_llm_agent, campus_life_offline_agent [EXTRACTED 0.75]
- **Eval quality gate system: verify suite, 21 tasks, J3 model gate** — evals_report_verify_suite_71914, evals_tasks_21_task_gate, docs_production_readiness_model_gate_j3 [EXTRACTED 0.75]
- **Security hardening batch: kernel routing, bearer auth, netguard** — docs_production_readiness_single_kernel_routing, docs_security_bearer_token_auth, docs_security_netguard_ssrf [EXTRACTED 0.75]
- **Shared bearer-token auth across web surfaces** — bee_web_chat_ui, bee_web_face_visualizer, bee_web_live_voice_page, bee_web_auth_token [EXTRACTED 0.75]

## Communities (249 total, 30 thin omitted)

### Community 0 - "render.js"
Cohesion: 0.03
Nodes (114): { createStore }, { KEY }, request(), resetStore(), storage, instance(), empty(), { loadComponent, tap, text, count, simulate, wxState, resetWxState } (+106 more)

### Community 1 - "Server"
Cohesion: 0.20
Nodes (23): Bring Ollama up if it is not already. Returns True when the server is reachable…, start_background(), _cfg(), _launched(), Popen, Without OLLAMA_HOST the server BEE starts would sit on 11434 while BEE polls…, A flashing console or a pipe that fills up would make the assistant's boot…, Stand-in for the Ollama HTTP surface, with switchable reachability. (+15 more)

### Community 2 - "test_commands.py"
Cohesion: 0.12
Nodes (25): line = full command line (leading '/' ok, e.g. '/draft email ...'). Returns…, run(), DeadClient, BEE command system + Phase-4 hot-path regression tests. Covers: - config.yaml…, Regression: a reminder is measured against the scheduler's own notion of now.…, Delivery, not bookkeeping: a reminder whose time has come must raise an OS…, cfg.alerts.enabled=false is the user's opt-out from desktop popups — the record…, Always fails — forces the deterministic fallbacks. (+17 more)

### Community 3 - "page-chat.test.js"
Cohesion: 0.10
Nodes (18): groups, INTERESTS, chat, groups, agent, chat, { freeze, unfreeze, advance }, fs (+10 more)

### Community 4 - "test_voice_engine.py"
Cohesion: 0.07
Nodes (47): FakeTTS, Test double with the StreamingTTS lifecycle. Mirrors the real pipeline: begin()…, FakeKernel, FakeSTT, make_engine(), Voice engine tests (Phase 4) — true realtime conversation behavior. Required…, Kernel stand-in: run() 'works' for delay seconds (polling the cancel event like…, User barges in while BEE is thinking/speaking: TTS stops immediately, the task… (+39 more)

### Community 5 - "Job"
Cohesion: 0.09
Nodes (17): iso(), Job, Persist a datetime CANONICALLY IN UTC (timezone rule, 2026-10-08)., effective_max_attempts(), JobWorker, datetime, EventBus, PII/secret redaction for anything persisted as job telemetry. (+9 more)

### Community 6 - "page-shop.test.js"
Cohesion: 0.07
Nodes (29): COMPARATORS, filter(), haversineKm(), isOpen(), toRad(), cats, ORIGIN, shops (+21 more)

### Community 7 - "test_self_improve.py"
Cohesion: 0.16
Nodes (19): critique_answer(), Pre-finalize self-critique (Chain-of-Thought Verification) for local answers.…, Gate: operator flag, real (non-test) client, substantive draft., One local pass. Returns the corrected answer, or the draft unchanged on…, should_critique(), Mechanical pre-check for one tool call. Returns "" when callable, else a repair…, _validate_call(), _Chat (+11 more)

### Community 8 - "test_computeruse.py"
Cohesion: 0.08
Nodes (35): ComputerAction, Risk after provenance: unproven click coordinates escalate to high (the risk…, Log/audit-safe view — NEVER includes the typed text payload, clipboard…, MockDesktop, Simulate the USER (or another app) changing the screen mid-task., Deterministic desktop for tests. Windows: add_window(); launchers:…, make_ctx(), make_session() (+27 more)

### Community 9 - "test_providers.py"
Cohesion: 0.19
Nodes (21): _cloud_up(), Cloud tier is usable only if enabled, configured AND credentialed. Availability…, cloud_available(), _cfg(), _failover_client(), Phase 6 — unified LLM provider layer (hermetic contract tests). Pins: provider…, The loop's cloud-availability check must track the ACTUAL configured provider…, Config with a credentialed zai fallback + fresh cooldown state. (+13 more)

### Community 10 - "test_engine_speed.py"
Cohesion: 0.12
Nodes (26): LLMError, Exception, _capture_litellm(), _ctx(), _FakeOllamaResp, _mk_cfg(), Engine speed tier: hybrid cloud-first routing, cloud→local de-escalation, and…, Fake the ONLY external dependency of the primary path, and hand back the kwargs… (+18 more)

### Community 11 - "test_structured_memory.py"
Cohesion: 0.11
Nodes (28): is_hardware_query(), _kernel(), _mem(), Structured memory tests (Phase 3, Parts C/D): remember/recall/update/forget,…, The store starts empty — only explicit remember() creates items., The rag_gpu_memory eval task failed because the kernel STORED the question:…, Remember that my favorite editor is Neovim. Use the profile memory tool.' used…, test_conflict_supersedes_old_value() (+20 more)

### Community 12 - "test_kernel_unit.py"
Cohesion: 0.08
Nodes (33): MalformedArgsError, ToolBus (Phase 2) — the single dispatch point for agent tool calls. Every tool…, litellm/openai function schemas for the registered tools only., Execute a registered tool. Returns (result, seconds, ok, meta). meta:…, Build from the existing registered tool modules (bee.tools)., ToolBus, ToolDef, ToolTimeoutError (+25 more)

### Community 13 - "worker.py"
Cohesion: 0.10
Nodes (15): Durable automation + proactive agent (Phase 6). Objects (per the Phase 6 spec):…, ExecutionHistory, JobExecution, parse_dt(), datetime, Durable automation models (Phase 6; UTC-canonical storage, 2026-10-08). Job /…, Persisted per-job execution history (append-only JSONL in JobStore)., JobQueue (+7 more)

### Community 14 - "JobStore"
Cohesion: 0.10
Nodes (10): _new_id(), Notification, _atomic_write(), JobStore, Path, Execution files OLDEST FIRST (.2 -> .1 -> active) — M13 rotation never loses…, Last row per execution id wins (a crash-repair appends a terminal row for an…, Drop claim tokens older than ttl (crashed processes). Idempotent. (+2 more)

### Community 15 - "webapp.py"
Cohesion: 0.09
Nodes (45): available(), cancel_task(), chat(), dashboard(), engine_get(), engine_set(), face_page(), face_state() (+37 more)

### Community 16 - "test_kernel_integration.py"
Cohesion: 0.07
Nodes (54): Acceptance audit P1-1: with a kernel attached, the agent loop must dispatch…, test_f2_loop_executes_tools_through_toolbus(), N4: the KERNEL owns task-scoped cancellation. A cancel event left SET by a…, Loop breaker gap: the exact-args breakers never match when a small model re-…, Retrying one failing call with reworded arguments used to burn the whole budget…, test_n4_stale_cancel_event_does_not_poison_new_task(), test_repeated_denials_lock_tools_instead_of_burning_the_budget(), test_repeated_tool_failures_lock_without_punishing_good_work() (+46 more)

### Community 17 - "kernel.py"
Cohesion: 0.09
Nodes (19): EventBus, callable, Typed kernel event bus (Phase 2) — a thin facade over the project's ONE shared…, _hardware_note(), _hw_conflict(), _qwords(), AgentKernel (Phase 2) — the single agent runtime. Flow (kernel-owned; the LLM…, Warn when a stored spec contradicts the machine standing in front of us.… (+11 more)

### Community 18 - "config.py"
Cohesion: 0.04
Nodes (47): AlertsCfg, _apply_env(), AutomationCfg, _build_from_yaml(), ClapCfg, CloudCfg, ComputerUseCfg, _dotenv_defines() (+39 more)

### Community 19 - "cli.py"
Cohesion: 0.06
Nodes (52): create_context(), Single application-context factory (Phase 1: replaces the 7+ duplicated…, ask_engine(), engine_labels(), load_engine(), override_for(), Engine selection: which brain does BEE use by default? Asked once at first…, Human-facing engine labels. The api-cloud label reflects the ACTUAL configured… (+44 more)

### Community 20 - "test_webauth.py"
Cohesion: 0.07
Nodes (37): reset_token_for_tests(), test_web_livekit_and_face_endpoints(), _client(), _client_with_kernel(), dash_env(), _page(), fixture, parametrize (+29 more)

### Community 21 - "fastpaths.py"
Cohesion: 0.07
Nodes (36): _brightness(), _cim(), _date(), FastExec, FastPath, _files_list(), _files_list_reply(), _http_text() (+28 more)

### Community 22 - "realtime/__init__.py"
Cohesion: 0.09
Nodes (24): VoiceEngine (Phase 4) — the realtime conversation orchestrator. Pipeline (one…, bee.voice.realtime — Phase 4 true-realtime voice. Clean layering:…, InvalidVoiceTransition, Enum, Exception, str, Voice state machine (Phase 4). The VOICE layer owns this state machine — and…, Engine tunables (defaults mirror config.yaml voice: rt_* fields). (+16 more)

### Community 23 - "index/index.js"
Cohesion: 0.06
Nodes (39): locate(), canCheck(), coverage(), dayIndex(), doCheckin(), groupByZone(), latestFor(), list() (+31 more)

### Community 24 - "Telemetry Integrity Testing"
Cohesion: 0.23
Nodes (12): create a job' through the LLM requires the automation.manage grant., _real_kernel(), test_automation_tool_gates_on_explicit_authorization(), metrics_file(), fixture, Structured telemetry + data-integrity hardening tests (audit 2026-10-06).…, Point the metrics stream at a temp file for the duration of a test., _rows() (+4 more)

### Community 25 - "test_scheduling_unified.py"
Cohesion: 0.13
Nodes (31): _cron_to_trigger(), scheduler tool — ADAPTER over the durable automation system (2026-10-08).…, Return (JobTrigger, note) or raise ValueError with the reason., scheduler_tools(), Ctx, due_one_time(), FakeClock, FakeKernel (+23 more)

### Community 26 - "scheduler.py"
Cohesion: 0.09
Nodes (30): _fn_build_sft(), _fn_consolidate(), _fn_rebuild_vectors(), _fn_teach_back(), _fn_train_qlora(), diary_add(), _auto_chain(), consolidate() (+22 more)

### Community 27 - "computeruse/__init__.py"
Cohesion: 0.07
Nodes (39): is_credential_target(), Computer-use action model (Phase 5) — one safe desktop action. Every action the…, Heuristic gate for the 'no credential entry' rule (checked on the SEMANTIC…, bee.computeruse — Phase 5: SAFE computer use. Desktop capture -> structured UI…, Computer-use privacy (Phase 5). Rules enforced in code (not just documented):…, Log/audit-safe entry for one executed (or blocked) action., redact_entry(), active_sessions() (+31 more)

### Community 28 - "store"
Cohesion: 0.10
Nodes (29): save(), store(), tzOffsetMin(), groups, { INTERESTS, groups: pool }, onClear(), onJoinToggle(), onLoad() (+21 more)

### Community 30 - "VoiceEngine"
Cohesion: 0.13
Nodes (6): Process one ~100 ms frame. NEVER raises — failures route to ERROR., Resolve a held answer once the verifier has judged it., Owns the voice state machine and timing; delegates all task logic to the kernel…, ERROR -> IDLE (or LISTENING when always-on) once the transport is up., Blocking transport pump with reconnect + capped backoff. stop() (or Ctrl-C)…, VoiceEngine

### Community 31 - "test_reflection_loop.py"
Cohesion: 0.09
Nodes (33): _all_bullets_empty(), Self-improvement loop (Phase 3): post-task reflection. After each completed…, `worked: None / failed: None / next: None` teaches nothing and burns the prompt…, A lesson is not a note to self — `context.recent_lessons()` injects it into…, Trivial tasks (canned replies, one-shot local answers, no tools) yield no…, LLM-based self-review. Returns the lesson text ("" if skipped)., reflect(), time_stamp() (+25 more)

### Community 32 - "computeruse/tools.py"
Cohesion: 0.09
Nodes (37): DesktopError, make_desktop(), RuntimeError, Default desktop factory — WindowsDesktop on Windows, DesktopError elsewhere…, computeruse_emergency_stop(), STOP all active computer-control sessions immediately. Returns the number of…, computer_clipboard(), computer_input() (+29 more)

### Community 33 - "test_skill_gate.py"
Cohesion: 0.10
Nodes (47): Index of SHIPPED skills only. J2: skills in `candidate` status (created/updated…, skills_index(), _fn_skill_gate(), J2: gate candidate skills (structural check + bounded eval probe)., bump_skill(), candidate_names(), eval_probe(), gate_candidates() (+39 more)

### Community 34 - "mlrouter.py"
Cohesion: 0.12
Nodes (29): _fn_train_router(), _compat_issue(), default_meta(), load(), load_status(), _NUM_FEAT_NAMES(), Path, ML route classifier — learns local|cloud routing from BEE's own episodes.… (+21 more)

### Community 35 - "verify_suite.py"
Cohesion: 0.09
Nodes (35): luhn_ok(), agent_eval_lines(), _gen_expr(), _is_subseq(), _latest_llm_run(), _load_bench(), _luhn_check_digit(), main() (+27 more)

### Community 36 - "test_netguard.py"
Cohesion: 0.10
Nodes (33): FetchResult, _ip_class(), NetGuardError, Exception, SSRF-hardened HTTP fetching for model-driven web tools. The `web_fetch` tool…, Fetch a URL under the full SSRF policy. Raises NetGuardError on any violation.…, Raised when a URL or its fetch violates the SSRF policy., Return a blocking class name for a non-public IP, else None. (+25 more)

### Community 37 - "chat/index.js"
Cohesion: 0.10
Nodes (31): byId(), current(), expire(), open(), peer(), push(), reap(), send() (+23 more)

### Community 38 - "test_localserver.py"
Cohesion: 0.15
Nodes (20): compact_messages(), Cheap prompt-size estimator used for history budgeting. A59 showed `chars/4`…, Drop oldest tool-history pairs before the model drops them for us. Ollama…, _token_estimate(), _ctx(), _DownClient, _fat_tools(), _pairs() (+12 more)

### Community 39 - "dsa/__init__.py"
Cohesion: 0.06
Nodes (30): BEE DSA library — curated, tested building blocks + benchmark harness. Usage:…, Segment tree with range query + point update. O(log n) each. Default op = sum.…, Inclusive range [lo, hi]., SegmentTree, bubble_sort(), counting_sort(), heap_sort(), insertion_sort() (+22 more)

### Community 40 - "ML Router Features"
Cohesion: 0.20
Nodes (14): features(), predict(), Returns (label, confidence) or None if model unavailable., _features_matrix(), _make_data(), fixture, ML route classifier: feature extraction + ML/DL model round-trip through…, The DL option (feature-scaled MLP) must save + predict exactly like the ML one,… (+6 more)

### Community 41 - "EventBus"
Cohesion: 0.09
Nodes (14): available_sources(), EventBus, EventSource, FileChangeSource, _PollSource, Path, Internal EventBus + proactive policy (Phase 6). An EventBus carries internal…, Adapter interface: a source PUBLISHES events; it never acts. (+6 more)

### Community 42 - "welcome.py"
Cohesion: 0.10
Nodes (32): _chrome_executable(), _due(), focus_or_launch_ide(), _foreground_hwnd(), _ide_executable(), _main_hwnd_win32(), _monitor_rects(), open_url_chrome() (+24 more)

### Community 43 - "build"
Cohesion: 0.06
Nodes (41): build(), load_episodes(), load_golden(), main(), _no_tool_single_turn(), paraphrase_augment(), Path, quality_score() (+33 more)

### Community 44 - "start_sources"
Cohesion: 0.13
Nodes (16): BatterySource, NetworkSource, Edge-triggered power events: battery.low / battery.unplugged / battery.charged…, Edge-triggered connectivity events: network.down / network.restored. Probes by…, Start the event sources that actually work on this machine. This is the…, start_sources(), TimerSource, CollectBus (+8 more)

### Community 45 - "_run"
Cohesion: 0.13
Nodes (29): _convert(), _count(), _dedupe(), _fill(), _find(), _inventory(), _jsonq(), _lines() (+21 more)

### Community 46 - "Guard Execution Stubs"
Cohesion: 0.20
Nodes (5): Regression: UnboundLocalError (res_v) when the guard ALLOWED an exec tool., Scripted LLMClient stand-in — no network, no model., StubClient, test_guard_allow_executes_tool(), test_guard_deny_never_executes()

### Community 47 - "test_exec_tools.py"
Cohesion: 0.10
Nodes (31): envelope(), Tool-result dict. `limit` overrides the default truncation cap so a tool's own…, _kill_tree(), Cancellable subprocess execution (J1 — audit item 3). The old exec tools used…, Run `cmd`; returns (returncode, stdout, stderr, kind) with kind in {'ok',…, run_cancelable(), _child_env(), code_tools() (+23 more)

### Community 48 - "pages"
Cohesion: 0.06
Nodes (31): lazyCodeLoading, pages, permission, scope.userLocation, requiredPrivateInfos, desc, sitemapLocation, style (+23 more)

### Community 49 - "schema.js"
Cohesion: 0.11
Nodes (24): migrate(), schema(), clone(), createStore(), load(), persist(), read(), reset() (+16 more)

### Community 50 - "JobTrigger"
Cohesion: 0.14
Nodes (20): JobTrigger, next_run(), _parse_hhmm(), parse_ics(), _parse_ics_dt(), _parse_local(), datetime, Trigger math (Phase 6) — pure, tz-aware, deterministic. next_run(trigger, tz,… (+12 more)

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
Cohesion: 0.09
Nodes (21): MemoryItem, _now(), Path, Delete by id, or (for 'Forget that.') the LAST matched item when a query is…, Compact, source-labeled digest for context injection., Purge expired + long-tombstoned items; returns count removed., Timezone-safe expiry check (fixed 2026-10-08): expiries are stored UTC-…, StructuredMemory (+13 more)

### Community 55 - "shops/index.js"
Cohesion: 0.16
Nodes (20): api, catTextOf(), catView(), hourLabel(), onFav(), onLoad(), onRange(), onReset() (+12 more)

### Community 56 - "test_automation.py"
Cohesion: 0.15
Nodes (39): Ctx, due_one_time(), FakeClock, FakeKernel, _force_running(), make_worker(), notif_kinds(), Durable automation + proactive agent tests (Phase 6). Covers the required… (+31 more)

### Community 57 - "LLMClient"
Cohesion: 0.08
Nodes (19): _cooling(), _is_gemini3plus(), LLMClient, GENUINE streaming completion: `on_token(str)` is called for every content delta…, Native Ollama: POST /api/chat with stream:true (NDJSON deltas)., litellm stream=True — per-chunk deltas (works for Ollama + Gemini)., One LLM completion. Returns the normalized dict: {content: str|None,…, Per-provider availability, from the ProviderRegistry (never a hard-coded key… (+11 more)

### Community 58 - "Permission Risk Assessment"
Cohesion: 0.22
Nodes (8): PermissionDecision, decide(), Permission decisions (Phase 2) — ONE entry point over the existing guard. Does…, (risk_level, capabilities) from the security risk layer; ('low', ()) for non-…, Full gate for one tool call. `approver` — optional (tool, args, reason) -> bool…, risk_info(), test_permission_allow_ask_deny(), test_permission_risk_metadata()

### Community 59 - "systemctl.py"
Cohesion: 0.11
Nodes (30): _battery(), _specs(), format_hardware(), get_battery(), get_hardware(), _keybd(), lock_workstation(), media() (+22 more)

### Community 60 - "kernel/models.py"
Cohesion: 0.13
Nodes (24): Observation, Kernel data model (Phase 2) — the typed objects the agent runtime is built…, What the kernel SAW happen for one tool call (never the model's claim)., VerificationResult, check_effect(), Path, Effect verification (Phase 2). Rule: a task is verified by OBSERVING the world,…, Extract the intended filesystem target from the request, if any. Returns (kind,… (+16 more)

### Community 61 - "agent.py"
Cohesion: 0.08
Nodes (34): available(), _build_brain(), _edge_tts_mp3(), make_stt(), make_token(), make_tts(), _pyttsx3_wav(), LiveKit agent — BEE's live realtime voice (free-tier LiveKit Cloud). python -m… (+26 more)

### Community 62 - "transcribe.py"
Cohesion: 0.10
Nodes (27): BEE voice: mic capture -> faster-whisper (local) -> text; text -> TTS. Optional…, _ensure_gate(), print_status(), Voice command loop: listen -> (wake word) -> task -> speak. Usage in REPL:…, If text starts with/contains the wake word, return the remainder (or None)., Terminal approval for capability asks in voice mode. Voice has no kernel…, Attach a capability gate to kernel-less voice contexts. The REPL/web/LiveKit…, run_voice_loop() (+19 more)

### Community 63 - "_allowing_kernel"
Cohesion: 0.09
Nodes (22): _allowing_kernel(), A kernel that grants every permission, so a test can observe the LOOP's own…, dsa_gcd_lcm spent 48 tool calls on one task: a 3B model that re-runs broken…, Same loop, different symptom: six SUCCESSFUL calls of one tool with ever-…, dsa_gcd_lcm / dsa_lis / dsa_graph, live: tools=0 and an answer that DESCRIBES a…, A45a: the model displayed code that stores the results in variables and never…, The read-out must only be appended when there is no output of its own —…, When permission is refused the answer must not pretend the computation happened… (+14 more)

### Community 64 - "Command Guard Rules"
Cohesion: 0.13
Nodes (17): check(), classify(), make_approver(), mode: cli (prompt), unattended (auto-deny), always (auto-approve). WARNING:…, Full gate. Returns (proceed, action, reason). ask → consults the approver.…, Returns (action, reason) where action in allow|ask|deny., Guard rule table — labeled commands. Run: python tests/test_guard.py, The kernel asks about a CAPABILITY with args={} (a capability spans several… (+9 more)

### Community 65 - "md.py"
Cohesion: 0.11
Nodes (27): _best_lines(), The bullets inside a memory chunk that actually answer this query. A chunk is…, add_facts(), all_chunks(), chunk_md(), _clean_fact(), _fact_core(), _finger() (+19 more)

### Community 66 - "Model Training Strategy"
Cohesion: 0.22
Nodes (10): Bee-8B QLoRA Local Brain, BEE LLM Component Design, J3 Model Upgrade Quality Gate, Constitutional AI and RLAIF Pipeline, Training and Scale Plan, 3D Parallelism TP PP DP Design, Verification Report, Verify Suite 71914 Checks All Pass (+2 more)

### Community 67 - "search.py"
Cohesion: 0.14
Nodes (21): _fn_flush_memory_index(), One-line digest of a SUCCESSFUL tool-using task (task -> outcome). Diary…, record_win(), _dirty_file(), flush_dirty(), get_store(), mark_dirty(), memory_search_hybrid() (+13 more)

### Community 68 - "Desktop"
Cohesion: 0.07
Nodes (5): Desktop, Protocol, Desktop abstraction (Phase 5). ComputerUseSession talks ONLY to this protocol.…, WindowInfo, test_active_window_falls_back_when_the_api_raises()

### Community 69 - "ProceduralMemory"
Cohesion: 0.07
Nodes (13): EntityMemory, EpisodicMemory, ProceduralMemory, Protocol, Short-horizon state for the active session (kernel-owned, in-process)., What happened, when (tasks, tool calls, outcomes)., Durable facts: profile, long-term notes, RAG corpus., How to do things: skills distilled from novel successes. (+5 more)

### Community 70 - "Agent Configuration Layers"
Cohesion: 0.18
Nodes (12): Agent Interface chat classify match, Honesty Rules and Labels, LlmAgent Local Ollama Backend, Campus Life Mini Program, Mood Radar Six Axes, OfflineAgent Lexicon Matcher Backend, Page to Component Test Shim, Local Storage Quota Prune Path (+4 more)

### Community 71 - "Task Capability Policies"
Cohesion: 0.17
Nodes (12): CapabilityStore, _Entry, Path, User-configurable policies. File format (config/capabilities.yaml):…, Task-scoped grants die with the task — never carried over., _gate(), test_delete_always_confirms_even_when_allowed(), test_delete_confirm_can_be_explicitly_disabled() (+4 more)

### Community 72 - "Docker Sandbox Security"
Cohesion: 0.22
Nodes (17): sandbox_tools(), _ctx(), R, GPU fallback tests for the Docker sandbox tool (no docker calls are made —…, Operator knobs: disable read-only + run as image default user (old root image…, Stub subprocess.run: track only `docker run` argv; probes get plain success., A non-'none' network mode silently voids the SECURITY.md boundary — refuse…, If the .env mask cannot be created, fail closed instead of running unmasked… (+9 more)

### Community 73 - "treehole/index.js"
Cohesion: 0.10
Nodes (24): { createLlm }, offlineEngine, withTimeout(), add(), anonId(), close(), counts(), dayKey() (+16 more)

### Community 74 - "test_claim_grounding.py"
Cohesion: 0.08
Nodes (43): _calc_checks(), _claim_checks(), _claimed_targets(), _clause_start(), _file_checks(), _hedged(), _opened_urls(), _phantom_file_checks() (+35 more)

### Community 75 - "plan.py"
Cohesion: 0.16
Nodes (22): classify(), _daily_blocks(), _dispatch(), _llm(), _load(), _next_id(), _open(), _paths() (+14 more)

### Community 76 - "load_config"
Cohesion: 0.04
Nodes (67): LLM client: LiteLLM primary, native Ollama HTTP fallback. chat(name, messages,…, _api_lines(), build_sub_system(), build_system_prompt(), canonical_system_prompt(), Context, _doc1(), Path (+59 more)

### Community 77 - "EventBus"
Cohesion: 0.13
Nodes (12): Inspect the visible UI (read-only). Returns the structured snapshot the agent…, EventBus, callable, THE shared EventBus (audit item 9 — one implementation, project-wide). Before…, Convenience: receive every event (the kernel facade uses this)., Routing key: explicit name attr (BusEvent) or kind.value (AgentEvent)., Dispatch; returns the number of handlers INVOKED (a handler that raises is…, _Ev (+4 more)

### Community 78 - "run_dsa_graphs"
Cohesion: 0.11
Nodes (23): _adj(), bellman_ford(), bfs(), build_adj(), dfs_order(), dijkstra(), floyd_warshall(), has_cycle_undirected() (+15 more)

### Community 79 - "test_injection.py"
Cohesion: 0.14
Nodes (22): Wrap external content in an UNFORGEABLE data fence. The fence used to be a…, untrusted_fence(), _blocked(), _model_views(), Prompt-injection corpus (acceptance audit YELLOW: "no injection corpus test…, Same rule end-to-end: approve before the fetch, deny after — the post-fetch…, The markers used to be constant, so external content that printed the END…, End-to-end: what the MODEL actually sees must be un-escapable. (+14 more)

### Community 80 - "test_static_contracts.py"
Cohesion: 0.14
Nodes (22): _collect(), _collect_class(), find_mismatches(), _function_contexts(), _lookup_method(), _mismatch(), AST, Call (+14 more)

### Community 81 - "Hardware Memory Retrieval"
Cohesion: 0.12
Nodes (20): _no_inventory(), _probe_kernel(), Diary chunks record the assistant's own past answers, including wrong ones.…, Pin the live CIM round-trip off. These tests are about what memory says; the…, Search your memory for hardware' used to be answerable only if the user had…, profile.md on this box says 'NVIDIA RTX 3050 8 GB' while CIM reports 4 GB.…, Both chunks are 'authoritative' profile/longterm memory, so the source ranking…, The CIM round-trip costs ~3.5 s the first time; a recall about the project must… (+12 more)

### Community 82 - "test_capabilities.py"
Cohesion: 0.11
Nodes (22): capabilities_for(), IntEnum, Capabilities required to run `tool` with these args (base + escalation)., Risk, Capability-based authorization tests (Phase 3, Parts A/B). Run: python -m…, Layering: capability gate first, then the guard's per-command layer., Phase 12 N1 (CRITICAL): the REPL `/guard off` toggle (ctx.guard_on) must NOT…, test_code_run_delete_escalation() (+14 more)

### Community 83 - "automation_job"
Cohesion: 0.16
Nodes (23): automation_job(), automation_tools(), _days_from(), _num(), automation_job tool (Phase 6) — user-facing automation management. The user…, Cast a model-supplied number with a message that names the field and the…, Accept the integers the schema documents and the day names a small model writes…, _trigger_from() (+15 more)

### Community 84 - "test_rag.py"
Cohesion: 0.10
Nodes (19): Deterministic recall@k: for each (question, answer_key), did a chunk containing…, recall_eval(), _FakeStore, RAG — trigger detection + deterministic recall@k. Run: python tests/test_rag.py, The write path only queues — it must never block on an embedding call., A maintenance job the `scheduler.enabled` switch does not stop is the defect…, Regression against the way this feature was first written wrong:…, A queue is only as good as its last write: an index left stale (empty queue,… (+11 more)

### Community 85 - "AgentKernel"
Cohesion: 0.11
Nodes (17): _agent_stub(), AgentKernel, _emit(), EventBus, Path, First-class cancellation: stop the active task safely., Post-task self-review, gated by `learning.reflect`. Reflection is an…, Persist enough of the in-flight task to RESUME after a crash (J1). Redacted,… (+9 more)

### Community 86 - "test_jarvis_features.py"
Cohesion: 0.06
Nodes (41): match(), _photo(), Remind me what my passport number is' is a question, not a reminder. The fast…, What is in the oven' must not be answered with a directory listing., What hardware do I need to run llama" is a purchase question; 'what is the spec…, Non-Windows or a blocked CIM query must not produce a fake spec sheet., The eval's own sentence: 'Run python: <snippet> — list which sorts are correct…, The 120-char ceiling was global before; the per-path `max_len` must not quietly… (+33 more)

### Community 87 - "Capability Authorization Gate"
Cohesion: 0.16
Nodes (14): Capability, CapabilityGate, GateDecision, Capability-based authorization (Phase 3, Part A/B). Capabilities are coarse…, Pre-execution authorization. `confirmer(capability, reason) -> bool` is the…, Acceptance audit P0-1: spawn_task's sub-context MUST inherit the parent's…, test_end_task_revokes_grants(), test_f1_spawn_subagent_inherits_capability_gate() (+6 more)

### Community 88 - "runner.py"
Cohesion: 0.05
Nodes (48): _module_hint(), A45c: the index line used to carry only the description, so BEE knew a `dsa`…, check_task(), _events_ok(), _isolated_memory(), _isolated_telemetry(), load_tasks(), Eval suite runner — the self-improvement gate. Runs evals/tasks.yaml through… (+40 more)

### Community 89 - "Local Model Server"
Cohesion: 0.15
Nodes (19): _base(), _boot(), _child_env(), exe_path(), _is_local(), _launch(), _model_present(), Start the local model server when the user expects it and it is not running.… (+11 more)

### Community 90 - "livekit/state.py"
Cohesion: 0.13
Nodes (19): _bearer_token(), get_state(), _push(), Live-voice shared state — HTTP push bridge (replaces the temp-JSON file). The…, Last state recorded in THIS process (debug/diagnostics). The web UI reads its…, Same source the webapp resolves from: BEE_WEB_TOKEN env, else the per-server…, Record the state locally (debug) and push it to the web UI., Best-effort POST to the web UI. Returns True on 2xx. (+11 more)

### Community 91 - "secretscan.py"
Cohesion: 0.16
Nodes (19): Finding, _is_binary(), main(), mask(), Path, Lightweight secret detection for source / generated-file audits. Usage: python…, Scan the project tree (excluding .env and data dirs). Sorted, stable., Safe form of a credential for logs: prefix + length only. (+11 more)

### Community 92 - "LiveKitTransport"
Cohesion: 0.07
Nodes (17): _agent_token(), _decode_audio(), LiveKitTransport, LiveKit as a VoiceTransport (Phase 4). Implements the transport protocol…, Room JWT for the agent participant (room join + publish/subscribe)., Nearest-neighbor mono s16 resample (good enough for voice)., Decode TTS bytes (mp3 or wav) to mono s16le @ to_rate via PyAV. PyAV ships with…, A LiveKit room behind the VoiceTransport protocol. (+9 more)

### Community 93 - "LLM Provider Registry"
Cohesion: 0.16
Nodes (8): Provider, ProviderConfig, ProviderHealth, ProviderRegistry, A concrete, configured provider (config + live key check)., Cheap, no-network availability probe (key presence / ollama reachability)., All providers known to this deployment (built from Config, not guesses)., One provider as configured for this deployment.

### Community 94 - "test_eval_gate.py"
Cohesion: 0.07
Nodes (57): _fn_model_gate(), J3: model-upgrade quality gate (candidate vs recorded baseline)., _adjudicate(), baseline_record(), clear_pending_candidate(), load_baselines(), model_quality_gate(), _now() (+49 more)

### Community 95 - "WindowsDesktop"
Cohesion: 0.13
Nodes (3): Real desktop (Windows-first). Lazy imports; missing deps -> DesktopError.…, Resolve the foreground window from its handle directly. The old version…, WindowsDesktop

### Community 96 - "Provider Environment Configuration"
Cohesion: 0.23
Nodes (14): env_key_for(), env_vars_for(), key_for(), kind_for_model(), ProviderKind, Enum, str, Provider abstraction — the single source of truth for LLM providers. The rest… (+6 more)

### Community 97 - "binary_tree.py"
Cohesion: 0.20
Nodes (19): bst_contains(), bst_insert(), count_nodes(), from_sorted(), height(), inorder(), is_valid_bst(), lca() (+11 more)

### Community 98 - "Preference Pair Derivation"
Cohesion: 0.22
Nodes (13): _bad_chosen(), derive(), derive_candidates(), _is_model_failure(), _is_plumbing(), _load_episodes(), load_goldens(), main() (+5 more)

### Community 99 - "test_phase8_memory_planning.py"
Cohesion: 0.11
Nodes (24): Action, Plan, One executable step in a plan. `tool` is a registered ToolBus name; None means…, Kernel-owned execution plan (Phase 8: typed + validated BEFORE ToolBus). kind:…, build_plan(), classify_intent(), Typed planner (Program Phase 8, 2026-10-08). Division of labor, exactly as the…, Kernel-built plan for one execution attempt. The kernel (not the LLM)… (+16 more)

### Community 100 - "ratings.py"
Cohesion: 0.15
Nodes (28): blocklisted(), _conn(), corrections(), _db(), get(), pair_key(), pairs(), Path (+20 more)

### Community 101 - "Text Analysis Utilities"
Cohesion: 0.17
Nodes (19): bankFor(), beforeFragment(), bigrams(), chat(), classify(), hits(), idfFactory(), L (+11 more)

### Community 102 - "Task Plan Storage"
Cohesion: 0.25
Nodes (10): _plan(), fixture, A54 — /plan owns a JSON task store, and three ways to lose the user's tasks.…, The write goes to a sibling temp file and is renamed over the store, so a…, store(), test_a_save_never_leaves_a_partial_file(), test_an_unreadable_store_is_kept_not_erased(), test_ids_do_not_repeat_after_a_prune() (+2 more)

### Community 103 - "Data Structures and Algorithms"
Cohesion: 0.24
Nodes (18): median(), quickselect(), Binary heap (min/max) + quickselect — independent of `heapq` internals.…, Median (lower-middle for even n) in expected O(n) via quickselect., k-th smallest (0-indexed) element in expected O(n) via 3-way quickselect.…, _check(), Random, Comprehensive correctness verification for the BEE DSA library.… (+10 more)

### Community 104 - "Agent Session Management"
Cohesion: 0.15
Nodes (11): new_id(), AgentSession, Path, AgentSession (Phase 2) — persistent conversation state. Follow-ups ("Tomorrow."…, Compact state block the kernel can inject so the model has the conversation…, test_session_context_block(), test_session_followup_resolution(), test_session_persistence_round_trip() (+3 more)

### Community 105 - "test_pipeline.py"
Cohesion: 0.16
Nodes (20): Chat messages with `loss` flags from a stored episode row. Returns (messages,…, row_to_messages(), label_row(), detect_type(), _last_ev(), Path, Episode validation — the SFT eligibility filter. An episode is training-…, row: parsed episode JSON. Returns {type, verdict, why}. (+12 more)

### Community 106 - "radar/index.js"
Cohesion: 0.09
Nodes (30): attached(), { polygon }, recompute(), label(), LABELS, ORDER, AXES, clamp100() (+22 more)

### Community 107 - "Action Verification Logic"
Cohesion: 0.12
Nodes (14): _calc(), Verifier — deterministic claim checks against episode events + disk. Run:…, Did any tool run?' is far too weak. Live evidence: the model made 23 harmless…, The rule must not demand evidence for prose it cannot resolve to a target, or…, I ran out of steps…" is ordinary speech, but 'ran' sat in the claim verb list,…, The eval produced `I executed the shell command 'git reset --hard HEAD~1'` with…, test_a_claim_must_match_a_receipt_not_just_any_receipt(), test_a_claim_without_a_quoted_target_needs_only_some_receipt() (+6 more)

### Community 108 - "UI Vision Backend"
Cohesion: 0.16
Nodes (6): Element, Protocol, One detected UI element (vendor-neutral)., Vendor-free default: 'vision' over the structural desktop snapshot. Elements =…, StructuralVision, VisionBackend

### Community 109 - "ML Route Training"
Cohesion: 0.14
Nodes (17): make_mlp(), The DL route model: a **feature-scaled** neural net. Scaling is the crux — TF-…, dataset_version(), evaluate_classifier(), imbalance_report(), main(), Episodes → ML route classifier (TF-IDF + LogisticRegression). Labels derived…, `argv`/`min_samples` allow in-process callers (scheduler) to set the sample… (+9 more)

### Community 110 - "Native Telemetry Lifecycle"
Cohesion: 0.18
Nodes (16): build(), _client(), _create_flags(), ensure(), healthy(), _install_go(), _launch(), BEE native subsystem — a Go-built system-telemetry daemon. Python is excellent… (+8 more)

### Community 111 - "System Telemetry Daemon"
Cohesion: 0.20
Nodes (18): cpuPct(), ftVal(), getBattery(), getDisk(), getRam(), healthHandler(), main(), round1() (+10 more)

### Community 112 - "Agent Core Interface"
Cohesion: 0.40
Nodes (9): createAgent(), chat(), classify(), decide(), explain(), mode(), ready(), setPreference() (+1 more)

### Community 113 - "System Stats Provider"
Cohesion: 0.14
Nodes (15): _sysstats(), Fast native stats, or None if the daemon is unavailable., stats(), format_system_stats(), get_system_stats(), CPU / RAM / disk / battery. Native-first: query the resident Go telemetry…, test_get_system_stats_parse(), test_stats_no_battery() (+7 more)

### Community 114 - "Routing Tier Logic"
Cohesion: 0.23
Nodes (12): parametrize, _r(), Routing tiers: explicit > deterministic > ML > heuristic. Run: python…, test_deterministic(), test_deterministic_phrased(), test_explicit(), test_heuristic(), test_legacy_api() (+4 more)

### Community 115 - "paths.py"
Cohesion: 0.05
Nodes (43): Episode, Episode logger — persist complete task episodes for the data pipeline. Each…, Serialize + REDACT before persistence. Episodes feed SFT builds and cloud…, Qwen3/OpenAI chat format with `loss` flag for masking tool/user turns. Returns…, _short(), force_reset_throttle(), Size-bounded rotation for append-only JSONL streams (M13 — audit item 2). Every…, Rotate `path` if it has grown past max_bytes. Returns True if a rotation… (+35 more)

### Community 116 - "UI State Assets"
Cohesion: 0.18
Nodes (18): Active state design vivid blue outline, explore.png inactive location pin icon gray, explore-on.png active location pin icon blue, Explore tab concept location pin discovery, Inactive state design muted slate gray outline, index.png inactive home house icon gray, index-on.png active home house icon blue, Index Home tab concept house (+10 more)

### Community 117 - "Code Generation Tool"
Cohesion: 0.36
Nodes (8): code(), _debug_fallback(), _detect_lang(), _llm(), /code — production-grade code generation + systematic debugging. Usage: /code…, _save(), _skeleton(), test_code_lang_detection()

### Community 118 - "Deterministic Offline Fallback"
Cohesion: 0.21
Nodes (15): Deterministic offline fallback — real answers for a narrow task class when…, Returns a deterministic answer, or an honest capability message., run_offline(), _try_list(), _try_math(), _try_sort(), Offline deterministic fallback. Run: python tests/test_offline.py, test_fallback_message() (+7 more)

### Community 119 - "Binary Heap Implementation"
Cohesion: 0.19
Nodes (5): Heap, 1-indexed binary heap. min_heap=True gives a min-heap (smallest on top)., True if x has higher priority than y (should sit above it)., Push x then pop the top, atomically. O(log n). Returns min(x, old_top),…, The k largest (default) or k smallest items currently in the heap.

### Community 120 - "Action Claim Verification"
Cohesion: 0.22
Nodes (4): Same shape as tests/test_kernel_integration.py, plus chat_stream so the…, A 3B model says 'I executed git reset --hard' having run nothing. The verifier…, ScriptedClient, test_unverified_action_claim_gets_corrected_before_the_task_ends()

### Community 121 - "Retry Policy Classification"
Cohesion: 0.23
Nodes (8): FailureKind, Enum, str, Structured retry policy (Phase 2). Failure kinds are classified BEFORE any…, True when a blind re-run could double-act. Read-only exec (ls/cat/ echo/python…, RetryPolicy, test_retry_policy_classification(), test_retry_policy_never_retries_destructive_or_denied()

### Community 122 - "Streaming Client Contract"
Cohesion: 0.19
Nodes (17): _fake_http(), _local_client(), _nd(), Real-client streaming contract (docs/TECHNICAL_DEBT.md A37). Every previous…, A37b: the recovery branch read `e._partial`, which nothing in the codebase ever…, Same two rules checked on the other provider branch., A38: `ollama_chat/` is a CHAT provider, so litellm raised…, The native loop is the safety net, so it stays reachable — and taking it is… (+9 more)

### Community 123 - "test_eval_score.py"
Cohesion: 0.13
Nodes (26): 95% Wilson score interval for k passes in n trials (None when n = 0). P1-3: the…, A52: `score` is the latest row per task id over ALL of results.jsonl, so a…, summarize(), wilson_interval(), _history(), A52: the eval headline must be the score of the run that ran.…, eval_resume.py picked "last row in file order", the runner's own summary…, The printed score is a point estimate over tens of tasks; P1-3 publishes its… (+18 more)

### Community 124 - "Project Metadata and Scripts"
Cohesion: 0.12
Nodes (15): description, devDependencies, jest, jest-environment-jsdom, miniprogram-simulate, name, private, scripts (+7 more)

### Community 125 - "memory_if.py"
Cohesion: 0.06
Nodes (29): display_local(), Render a stored (UTC-canonical) timestamp in the USER'S timezone — for display…, get_tz(), Now' exactly as the SCHEDULER sees it, expressed in the job's timezone.…, worker_now(), _cancel(), _clock(), _list() (+21 more)

### Community 126 - "kernel/__init__.py"
Cohesion: 0.18
Nodes (16): BEE Agent Kernel (Phase 2) — one coherent agent runtime. Objects: AgentSession,…, Single-shot LLM task for slash commands — SAME kernel infrastructure (provider…, Task, TaskState, _ts(), can_transition(), InvalidTransitionError, Exception (+8 more)

### Community 127 - "run_agent"
Cohesion: 0.04
Nodes (85): _convert(), AgentResult, _audit_record(), _diary(), _finish(), _fmt_result_text(), _golden(), _offline_result() (+77 more)

### Community 128 - "StreamingSTT"
Cohesion: 0.14
Nodes (11): pcm_to_float(), RuntimeError, Streaming STT (Phase 4) — interim + final transcripts. faster-whisper is…, Final transcript over the whole utterance; honors self.timeout., Windowed partials + one final pass, over faster-whisper., Interim transcript of the utterance so far ('' if nothing yet)., StreamingSTT, SttError (+3 more)

### Community 129 - "LLM Prompt Templates"
Cohesion: 0.25
Nodes (6): CHAT_BASE, CLASSIFY_SCHEMA, CLASSIFY_SYSTEM, EXPLAIN_SYSTEM, MOODS, PERSONAS

### Community 130 - "test_audit_fixes.py"
Cohesion: 0.06
Nodes (40): _fn_alert_scan(), Daily threshold alerting (audit item 6): evaluate metrics stats against…, Install the app-wide log handler, once, on every BEE surface. Before this…, setup_logging(), check_thresholds(), _cooldown_ok(), _load_state(), _mark_fired() (+32 more)

### Community 131 - "Acoustic Clap Trigger"
Cohesion: 0.18
Nodes (5): ClapDetector, Double-clap acoustic trigger (ported from Super JARVIS / Hector). python -m…, Listens on the microphone for double-clap acoustic signatures., run_clap_mode(), _voice_once()

### Community 132 - "SSRF Guarded Web Tools"
Cohesion: 0.16
Nodes (13): BEE security layer (Phase 1). Modules: netguard — SSRF-hardened URL fetching…, mark_untrusted(), Wrap a web-tool result so the model sees it as DATA, never as instructions…, truncate(), _fetch(), _html_to_text(), web_fetch / web_search — SSRF-guarded httpx + HTML->text, DuckDuckGo (no API…, html.duckduckgo.com - verified working from this network (2026-10 probe). (+5 more)

### Community 133 - "Microphone Audio Capture"
Cohesion: 0.27
Nodes (13): _has(), _pcm_to_float(), Path, RuntimeError, Microphone capture with silence detection. Primary: sounddevice (numpy frames).…, Best-effort mic capture across available backends., _read_wav(), record() (+5 more)

### Community 134 - "JSON Tool Call Extractor"
Cohesion: 0.24
Nodes (12): _extract_text_tool_calls(), _iter_json_blocks(), Yield each top-level {...} block (string/escape aware). Handles JSONL-style…, Small local models sometimes emit tool calls as TEXT (JSON / JSONL / fenced).…, Unit tests for the text tool-call extractor (handles JSONL/fenced/array +…, test_args_as_string(), test_array(), test_empty() (+4 more)

### Community 135 - "Vector Memory Management"
Cohesion: 0.23
Nodes (6): lancedb renamed table_names() -> list_tables() (0.39 warns on the old…, Clear-before-add (B2/M12 fix, audit 2026-10-06): the old implementation did…, Re-index ONE memory file: drop its old rows, add the current chunks.…, _VecStore, B2/M12: rebuilding twice must NOT double the row count., test_vector_rebuild_no_duplicates()

### Community 136 - "speak.py"
Cohesion: 0.05
Nodes (53): _speak(), Event, Immediate teardown (barge-in): drop queued sentences + flag the in-flight…, GENUINE streaming: consume edge-tts's chunk iterator live., sink(audio_bytes) plays one chunk; on_first() fires at the first chunk of an…, Start a fresh utterance (resets first-chunk tracking). `busy` is set…, StreamingTTS, _decode_to_wav() (+45 more)

### Community 137 - "bee/__init__.py"
Cohesion: 0.07
Nodes (27): ML router report (Program Phase 7, 2026-10-08). One place to answer "how is the…, Recommend router.ml_confidence from measured outcomes (auto-tuning). Joins…, tune_thresholds(), BEE — a local-first, self-improving, general-purpose personal agent. Stack (see…, Structured memory store (Phase 3, Parts C/D). Five conceptual stores are…, _bars(), build(), _kpi() (+19 more)

### Community 138 - "Dynamic Programming Recipes"
Cohesion: 0.12
Nodes (15): coin_change(), coin_change_count(), edit_distance(), knapsack(), lcs(), lis(), Classic dynamic-programming recipes with complexity notes., Max revenue cutting a rod of length n (prices[i] for length i+1). O(n^2). (+7 more)

### Community 139 - "ML Performance Reporting"
Cohesion: 0.22
Nodes (10): full_report(), _pctl(), Fallback rate + latency percentiles over the last `window_hours`., The last training report (per-class metrics etc.), if any., Artifact + training + runtime in one dict (for /health-style output)., Human-readable one-screen summary., render(), runtime_report() (+2 more)

### Community 140 - "Screenshot Retention Store"
Cohesion: 0.17
Nodes (6): Path, Bounded screenshot retention. Default (save_dir=None): in-memory hash ring only…, Delete ALL saved frames (called on session end / emergency stop)., ScreenshotStore, Event, test_11_screenshot_retention()

### Community 141 - "Trie Prefix Tree"
Cohesion: 0.24
Nodes (3): _Node, Trie (prefix tree) — autocomplete, spellcheck, prefix queries. O(L) per op…, Trie

### Community 142 - "base.py"
Cohesion: 0.08
Nodes (29): automate_tools(), _check_bounds(), _ev(), eval_safe(), _guarded_pow(), _pow_func(), AST, Path (+21 more)

### Community 143 - "Config"
Cohesion: 0.11
Nodes (26): _embedded_expr(), _heuristic(), _is_det(), math_expr(), needs_vision(), _normalize_expr(), Hybrid routing — four tiers, fused heuristics + learned ML. Tiers (in order of…, True when the residue is arithmetic whose only names are math functions. The… (+18 more)

### Community 144 - "App Manifest Testing"
Cohesion: 0.18
Nodes (8): app, BUILTIN_TAGS, fs, pageDirs, path, ROOT, SOURCE_DIRS, SOURCE_FILES

### Community 145 - "HTTP Client Testing"
Cohesion: 0.20
Nodes (8): http, request(), { URL }, agent, { createLlm }, llm, offline, { request }

### Community 146 - "Web Approval Workflow"
Cohesion: 0.13
Nodes (17): client(), _FakeKernel, fixture, Web interactive approvals + /voice event-loop safety (2026-10-17). The web…, Stop (Escape) must not wait out the approval timeout., get_ctx() used to start automation FIRST: start_automation() then installed…, `python -m bee web` goes through cli._web — same live bug, second launcher: it…, While /voice is stuck in STT, other routes must still answer — the blocking… (+9 more)

### Community 147 - "Command Registry"
Cohesion: 0.25
Nodes (8): _plate(), _todo(), Command, get(), help_text(), BEE command registry — modular slash-commands for the REPL. Adding a command (5…, test_registry_has_all_core_commands(), test_welcome_command_registered()

### Community 148 - "System Audit Status"
Cohesion: 0.25
Nodes (11): JARVIS Acceptance Audit, Agent Kernel run_agent Loop, FastPaths Deterministic Tier, Production Readiness Audit, Single Kernel Routing All Surfaces, Spawn Task Gate Bypass P0, Feature Status Authoritative, Agent Eval 18 of 21 (+3 more)

### Community 149 - "Document Summarization Tool"
Cohesion: 0.33
Nodes (9): _extractive(), _fetch_url(), _llm(), /summarize — articles, papers, reports → executive summary + dense bullets +…, Comparative table of entity→number pairs (metrics, prices, versions)., _read_file(), _sentences(), summarize() (+1 more)

### Community 150 - "Hybrid RAG Retrieval"
Cohesion: 0.22
Nodes (8): auto_context(), needs_context(), Hybrid RAG over BEE memory — vector + keyword fused with Reciprocal Rank…, RRF fusion of vector (when available) and keyword rankings., Markdown context block for the system/user message, or '' if not needed., retrieve(), BEE memory: Markdown (transparent) + optional LanceDB vectors (semantic search)., test_triggers()

### Community 151 - "Voice Transport Protocol"
Cohesion: 0.20
Nodes (5): Protocol, Establish capture/playback. Raises TransportError on failure., Blocking read of one ~100 ms 16 kHz mono s16le frame. Returns None on timeout…, Render a TTS audio chunk (format is transport-specific)., VoiceTransport

### Community 152 - "JavaScript LLM Interface"
Cohesion: 0.21
Nodes (14): createLlm(), chat(), clamp(), classify(), contentOf(), explain(), parseMood(), probe() (+6 more)

### Community 153 - "Fine-tuning Environment"
Cohesion: 0.20
Nodes (10): finetune SKILL, QLoRA fine-tuning Qwen3 8GB 3050, pytorch SKILL, PyTorch VRAM budget training skeleton, Docker ML environment sandbox_run GPU, sandbox SKILL, transformers SKILL, HF Transformers inference dataset pipeline (+2 more)

### Community 154 - "Active Window Detection"
Cohesion: 0.20
Nodes (4): _FakeWin32, The old version searched list_windows() (which drops untitled windows), so a…, test_active_window_is_none_only_when_truly_unknown(), test_active_window_resolves_the_handle_directly()

### Community 155 - "Reasoning and Analysis Tool"
Cohesion: 0.36
Nodes (8): register(), _deterministic(), _facts(), _llm(), /think — stress-test ideas, trade-offs, pros/cons matrices, strategic…, Pull claim-ish fragments (numbers, named risks, constraints) for the…, _save(), think()

### Community 156 - "DSA Benchmarking"
Cohesion: 0.31
Nodes (8): check(), compare_sorts(), Path, Benchmark + correctness harness for the DSA library. run_bench(fn, *args,…, Benchmark all sorting implementations on the same random input; verify against…, report(), run_bench(), time_once()

### Community 157 - "Secure Filesystem Tools"
Cohesion: 0.16
Nodes (18): Privacy chokepoint (audit 2026-10-06): every string that reaches the metrics…, _scrub(), _edit_file(), _file_list(), Path, Filesystem tools: file_read, file_write, file_list, file_edit., Windows name-shape attacks the resolve() check cannot see: ADS streams…, _read_file() (+10 more)

### Community 158 - "Formatting Utilities"
Cohesion: 0.42
Nodes (7): ago(), clock(), countdown(), day(), pad(), shifted(), stamp()

### Community 159 - "Test Suite Configuration"
Cohesion: 0.28
Nodes (6): _isolate_append_only_streams(), _isolate_post_task_model_calls(), pytest_configure(), Test pyramid markers (audit 2026-10-06; Phase-7 categories 2026-10-08). The…, Reflection (A40b) adds ONE local-model call after every non-trivial task, on…, A test run must not write into the user's real telemetry or training data.…

### Community 160 - "Eval Workspace Restoration"
Cohesion: 0.20
Nodes (11): eval_approver(), Path, The permission prompt the eval answers on the user's behalf. `file_write` is…, Leave every source file exactly as the run found it — by bytes, not by git.…, _restore_workspace(), _tree_files(), The suite used to auto-deny every prompt, which made any task whose correct…, `file_roundtrip` asks for a NEW eval_probe.txt; granting file_write wholesale… (+3 more)

### Community 161 - "Union-Find Algorithm"
Cohesion: 0.36
Nodes (3): UnionFind, Union-find reference (independent of graphs.has_cycle_undirected)., _ref_has_cycle()

### Community 162 - "_no_fastpath"
Cohesion: 0.09
Nodes (29): _no_fastpath(), _plan_ctx(), no function calls were provided / the available functions are…' is the model…, These two tests aim at the loop's wrap-up logic. Listing the workspace is now…, math_sieve on the live box: 39.9 s, tools=0, and the shipped answer was `I'm…, The fix must not turn a recoverable ramble into a declared failure: one ramble,…, plan_complex, live: '…Use the planner tool.' answered with 'None of the…, P1: the planner used to run only when the user asked for a plan, as a post-hoc… (+21 more)

### Community 163 - "Semantic Memory Facade"
Cohesion: 0.25
Nodes (6): Long-term markdown memory. Phase 8: entries carry PROVENANCE inline (source…, _Semantic, test_semantic_add_writes_provenance(), `_Semantic.search` called rag.retrieve(query, k=) instead of retrieve(ctx,…, test_durable_memory_facade_dedupes_promotions(), test_semantic_search_really_reaches_rag()

### Community 164 - "Lexicon Word Lists"
Cohesion: 0.25
Nodes (7): INTENSIFIERS, MOOD_WORDS, NEGATED_TARGET, NEGATIONS, REPLIES, SEPARATORS, TOPIC_STOP

### Community 165 - "Group Management Logic"
Cohesion: 0.36
Nodes (5): byId(), join(), { match }, matchText(), rank()

### Community 167 - "Dependency Management"
Cohesion: 0.25
Nodes (8): Core deps litellm lancedb fastapi apscheduler, requirements.txt BEE Core, requirements-ml.txt Pinned ML Stack, Pinned scikit-learn numpy scipy joblib versions, Router Model Artifact Meta, Docker sandbox GPU isolation note, Training code versus train data separation, training NOTE code vs data

### Community 168 - "Privacy and Redaction"
Cohesion: 0.14
Nodes (17): _redact_for_cloud(), preview_call(), Permission gates — classify tool calls before execution: allow | ask | deny.…, One line saying what the user is actually being asked to allow. The prompt used…, _cc_replace(), detect(), is_clean(), Privacy controls — PII detection + redaction for cloud-bound payloads. Policy… (+9 more)

### Community 169 - "App Transition Monitoring"
Cohesion: 0.22
Nodes (4): AppEventSource, Foreground-window and running-app transitions. Reads through the SAME desktop…, A foreground poll must not become an event storm: baseline first, then only…, test_app_event_source_emits_transitions_only()

### Community 170 - "Web and Voice Endpoints"
Cohesion: 0.32
Nodes (8): Web Auth Bearer Token, Chat SSE Endpoint, Web Chat UI, Face State Endpoint, Face Visualizer Page, Live Voice Page, LiveKit Token Endpoint, LiveKit Room Config

### Community 171 - "Project Roadmap and Audits"
Cohesion: 0.32
Nodes (8): JARVIS Baseline Audit, guard_blocked Eval Anomaly, Coherence Pass Fixes F0-F5, BEE to JARVIS Roadmap, Jarvis Milestones J1-J6, H1 AST Risk Layer for Code Run, Technical Debt Report, H8 Eval Safe Computation Budget

### Community 172 - "Execution Receipt Logging"
Cohesion: 0.22
Nodes (8): ExecutionReceipt, Append-only proof row for one meaningful action. Secrets are redacted before…, Path, Execution receipts (Phase 2) — append-only, redacted JSONL proof rows. Every…, ReceiptLog, _redact_value(), test_receipt_fields_and_redaction(), test_receipt_log_never_raises()

### Community 173 - "Model Fine-tuning Script"
Cohesion: 0.53
Nodes (5): load_samples(), main(), Path, QLoRA fine-tuning of Qwen2.5-3B-Instruct for BEE — single 4 GB GPU friendly.…, summarize()

### Community 174 - "Security Model Overview"
Cohesion: 0.40
Nodes (6): N1 Guard Off Disables Capability Gate, Web Bearer Token Authentication, BEE Security Model, Docker Sandbox Boundary, Netguard SSRF Protection, ToolBus as Execution Dispatcher

### Community 175 - "Text Embedding Service"
Cohesion: 0.40
Nodes (3): embed_texts(), Embeddings: Ollama (nomic-embed-text) via LLMClient. Lazy access. Usage: from…, Returns embeddings for `texts`. Raises RuntimeError if Ollama/embedder…

### Community 176 - "Service Health Checks"
Cohesion: 0.24
Nodes (11): offline_hint(), For `/health` and the web status panel: what the autostart actually did. There…, What to tell a user whose server is not answering. BEE can start it now, so the…, status(), cli_report(), _disk_free_gb(), docker_has_image(), Path (+3 more)

### Community 177 - "Safety Control Mechanisms"
Cohesion: 0.40
Nodes (5): Capability Policies, Guard Mode, Coordinate Provenance Check, Emergency Stop Mechanisms, Safe Computer Action Set

### Community 178 - "Web UI Screenshots"
Cohesion: 0.50
Nodes (5): User chat bubble with text Hi agent, Essential and optional cookies consent banner with Reject All and Accept All Cookies, Grok full power features: AI images and videos, Skills and Connectors, Generate files, Chat history, Grok web UI screenshot showing gated conversation, Continue your conversation signup gate with Sign up for free CTA

### Community 179 - "Server Launch Grace"
Cohesion: 0.40
Nodes (5): grace(), For the router: a launch is in flight, so give the server the moment it needs…, The availability branch runs on every task; an idle-timeout here would be a…, test_grace_never_blocks_when_bee_never_launched_anything(), test_grace_picks_up_a_launch_that_completes_a_moment_later()

### Community 180 - "Architecture Documentation"
Cohesion: 0.22
Nodes (8): AGENTS.md — BEE personal assistant (Windows-first, local-first), Architecture (don't re-derive; verified), Docs authority, Editing, Live services (creds in `.env` — check presence, never print values), Shell (PowerShell — plain `cmd` idioms break), Tests (source of truth: `tests/conftest.py`, CI: `.github/workflows/ci.yml`), Use Graphify before grep

### Community 181 - "Process State Reset"
Cohesion: 0.40
Nodes (5): Forget the one-attempt state (tests, or a user who starts Ollama by hand and…, reset(), _fresh_state(), fixture, One launch attempt per process is real behaviour — tests must not inherit it…

### Community 182 - "Memory Consolidation Design"
Cohesion: 0.50
Nodes (4): Memory Consolidation Design, Memory Layers and Nightly Consolidation, BEE System Prompt, Operating Principles Act Verify

### Community 183 - "Data Science Skills"
Cohesion: 0.50
Nodes (4): polars SKILL, Polars lazy scan filter group_by pipeline, sklearn SKILL, Tabular baseline LightGBM validation SHAP

### Community 187 - "test_phase7_repro.py"
Cohesion: 0.12
Nodes (21): apply_threshold(), Write router.ml_confidence into config.yaml (explicit operator action). Regex…, _cfg_p7(), p7(), fixture, Phase 7 — ROUTING + TEST/CI REPRODUCIBILITY (2026-10-08). Covers, with evidence…, The pinned ML stack (requirements-ml.txt) must equal the installed versions —…, Phase 7 rule, enforced: a file is 'optional' ONLY if it is guarded by… (+13 more)

### Community 206 - "Planner Integration Client"
Cohesion: 0.25
Nodes (4): PlanFirstClient, A REAL LLMClient (so the loop's real-client gates fire, exactly as they do…, plan_complex: 'Use the planner tool.' The plan is produced BEFORE the model's…, test_plan_first_runs_for_a_plan_request_through_the_kernel()

### Community 220 - "Agent Configuration Query"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Why does load_config() connect Voice, Agent Loop, LLM Client, ToolBus and 40+ other communities?, Source Nodes

### Community 221 - "Recording Client Mock"
Cohesion: 0.25
Nodes (3): ctx(), fixture, RecordingClient

### Community 223 - "Planner Logic Utilities"
Cohesion: 0.24
Nodes (8): explain(), gapsFrom(), label(), mmhh(), overlaps(), solve(), p, W

### Community 224 - "Data Sanitization Utilities"
Cohesion: 0.50
Nodes (4): Sanitize episodes for export/training: PII scrub + size bounds. The training…, Returns (clean_row_copy, total_redactions)., scrub_episode(), _scrub_str()

### Community 225 - "Module Layering Contract"
Cohesion: 0.29
Nodes (7): Path, Layering contract: bee.tools must not statically depend on bee.agent. History:…, Module-level imports reaching bee.agent (deferred function-level imports are…, `import bee.tools` in a fresh interpreter must not load bee.agent., test_tools_have_no_static_agent_import(), test_tools_import_without_agent(), _top_level_agent_imports()

### Community 226 - "DPO Model Training"
Cohesion: 0.60
Nodes (4): load_pairs(), main(), Path, Preference tune of Qwen2.5-3B-Instruct on train/prefs.jsonl — single GPU. Stage…

### Community 228 - "Module API Documentation"
Cohesion: 0.33
Nodes (8): module_api_card(), _module_source(), A50: a request that names one of BEE's own modules gets that module's REAL…, test_an_attribute_path_resolves_to_its_module(), test_card_lists_the_real_public_signatures(), test_names_that_are_not_project_modules_add_nothing(), test_the_card_is_bounded(), test_the_model_sees_the_card_in_the_request()

### Community 229 - "Emergency Stop Hotkey"
Cohesion: 0.29
Nodes (3): HotkeyStopper, Polls a key-combo (injectable for tests) and fires the emergency stop. On…, One poll cycle. Returns True if the stop fired on this poll.

### Community 230 - "Docker Sandbox Environment"
Cohesion: 0.22
Nodes (8): _ensure_env_mask_file(), _nvidia_runtime(), Path, sandbox_run — Docker sandbox (bee-sandbox image, GPU passthrough optional). The…, Does this Docker setup have the nvidia runtime (GPU passthrough)? Docker…, An empty host file to bind over <workspace>/.env inside the container. Lives…, Host path as the docker CLI should receive it. Docker Desktop (Windows) accepts…, _to_container_path()

### Community 231 - "Event Bus System"
Cohesion: 0.25
Nodes (3): BusEvent, match supports three key shapes: {"name": "device.memory_low"} the event name…, Publish; returns the number of handlers that ran. The proactive policy gate is…

### Community 232 - "Drafting and Composition"
Cohesion: 0.39
Nodes (7): _deterministic(), draft(), _extract_fallback(), _llm(), /draft — emails, memos, outreach, proposals, reports + note extraction. Usage:…, -> (kind, body, tone). Kind = first word if it is a known kind., _split()

### Community 233 - "Voice Route Testing"
Cohesion: 0.14
Nodes (9): ctx(), _Kernel, fixture, Web /voice route — regression pins (2026-10-17). Two real defects, both visible…, Chokepoint coercion: a float64 caller must not reach the model as-is., Stands in for AgentKernel; records calls, returns the result shape., np.interp leaks float64; the ONNX VAD accepts only float32., test_read_wav_resample_returns_float32() (+1 more)

### Community 234 - "LLM Client Mocking"
Cohesion: 0.10
Nodes (15): SimpleNamespace, test_model_gate_disabled_skips_evaluation(), test_remind_reports_errors_rather_than_raising(), _FakeResp, One stand-in that satisfies both call shapes: `chat()` reads…, Gemini 3+: Google deprecates temperature AND warns temp<1.0 degrades reasoning…, test_gemini3plus_omits_temperature(), env() (+7 more)

### Community 235 - "Typed LLM Envelopes"
Cohesion: 0.33
Nodes (5): LLMRequest, LLMResponse, Typed request envelope (preferred API). `request()` wraps `chat()`; all legacy…, Typed response envelope mirroring the `chat()` dict contract., test_client_provider_api_is_public_and_hermetic()

### Community 236 - "Device Pressure Monitoring"
Cohesion: 0.33
Nodes (5): DeviceSource, Memory / disk pressure transitions — this machine's documented failure mode (a…, A value oscillating on the threshold must not become a ping storm, and a…, test_device_source_is_edge_triggered_with_hysteresis(), test_device_source_survives_a_missing_reader()

### Community 237 - "MCP Server Config"
Cohesion: 0.29
Nodes (6): type, url, mcp, servers, $schema, graphify

### Community 240 - "Memory Recall Requests"
Cohesion: 0.43
Nodes (6): _as_recall(), MemoryRequest, parse(), Deterministic memory requests (Phase 3, Part C). 'Remember that my project is…, Remember my GPU from last time?' is a RECALL request. `_REMEMBER_RE` used to…, test_recall_phrasings_the_eval_uses_reach_the_deterministic_path()

### Community 241 - "Preference Data Export"
Cohesion: 0.60
Nodes (4): export(), main(), Path, Preference pairs -> train/prefs.jsonl (RLAIF stage 2: SFT imitates, preferences…

### Community 242 - "Grounded Fallback Logic"
Cohesion: 0.50
Nodes (4): _grounded_fallback(), What to ship when even the no-tools pass only talked about plumbing. The live…, plan_complex, live: the 'honest' fallback quoted the guard's own budget notice…, test_grounded_fallback_does_not_quote_a_refusal_as_evidence()

### Community 244 - "Scripted Test Client"
Cohesion: 0.13
Nodes (9): ScriptedClient, _AnswersWhenToolsClosed, The real wrap pass calls chat(tools=None): the model can only answer., P0-4 (2026-10-17): a draft the verifier FAILED and the loop then fixed is a…, test_a_verify_fix_becomes_a_preference_pair(), chat() pops scripted items: str -> final answer; dict -> raw LLM out; Exception…, The call-order contract this suite depends on: a scripted stand-in that is not…, ScriptedClient (+1 more)

### Community 245 - "Task Failure Testing"
Cohesion: 0.50
Nodes (3): datetime, test_failure_terminal_and_notification(), test_trigger_math_calendar_ics()

## Knowledge Gaps
- **330 isolated node(s):** `CloudCfg`, `GuardCfg`, `MonitorCfg`, `OllamaCfg`, `PrivacyCfg` (+325 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **30 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `load_config()` connect `load_config` to `test_audit_fixes.py`, `test_commands.py`, `test_voice_engine.py`, `test_self_improve.py`, `test_computeruse.py`, `bee/__init__.py`, `test_engine_speed.py`, `test_structured_memory.py`, `test_kernel_unit.py`, `Config`, `webapp.py`, `test_kernel_integration.py`, `config.py`, `cli.py`, `Command Registry`, `Telemetry Integrity Testing`, `computeruse/__init__.py`, `Secure Filesystem Tools`, `test_reflection_loop.py`, `computeruse/tools.py`, `_no_fastpath`, `verify_suite.py`, `EventBus`, `welcome.py`, `build`, `start_sources`, `JobTrigger`, `test_proactive.py`, `test_automation.py`, `test_phase7_repro.py`, `agent.py`, `_allowing_kernel`, `Docker Sandbox Security`, `test_claim_grounding.py`, `Planner Integration Client`, `test_injection.py`, `Hardware Memory Retrieval`, `test_capabilities.py`, `test_jarvis_features.py`, `Capability Authorization Gate`, `runner.py`, `Recording Client Mock`, `test_phase8_memory_planning.py`, `test_pipeline.py`, `LLM Client Mocking`, `ML Route Training`, `Routing Tier Logic`, `paths.py`, `Scripted Test Client`, `Action Claim Verification`, `run_agent`?**
  _High betweenness centrality (0.138) - this node is a cross-community bridge._
- **Why does `AgentKernel` connect `AgentKernel` to `test_voice_engine.py`, `test_computeruse.py`, `test_structured_memory.py`, `test_kernel_unit.py`, `webapp.py`, `test_kernel_integration.py`, `kernel.py`, `cli.py`, `Telemetry Integrity Testing`, `scheduler.py`, `test_reflection_loop.py`, `Execution Receipt Logging`, `test_automation.py`, `Permission Risk Assessment`, `kernel/models.py`, `agent.py`, `_allowing_kernel`, `test_claim_grounding.py`, `load_config`, `Planner Integration Client`, `Hardware Memory Retrieval`, `runner.py`, `test_phase8_memory_planning.py`, `Agent Session Management`, `Action Claim Verification`, `Retry Policy Classification`, `kernel/__init__.py`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Why does `LLMClient` connect `LLMClient` to `test_self_improve.py`, `test_providers.py`, `test_engine_speed.py`, `Typed LLM Envelopes`, `load_config`, `build`, `LLM Client Mocking`, `Planner Integration Client`, `test_kernel_integration.py`, `cli.py`, `Streaming Client Contract`, `test_reflection_loop.py`, `run_agent`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `run_agent()` (e.g. with `LLMError` and `Context`) actually correct?**
  _`run_agent()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `AgentKernel` (e.g. with `EventBus` and `MemoryStack`) actually correct?**
  _`AgentKernel` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `Context` (e.g. with `run_agent()` and `ctx()`) actually correct?**
  _`Context` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `CloudCfg`, `GuardCfg`, `MonitorCfg` to the rest of the system?**
  _330 weakly-connected nodes found - possible documentation gaps or missing edges._