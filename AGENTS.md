# AGENTS.md — BEE personal assistant (Windows-first, local-first)

## Shell (PowerShell — plain `cmd` idioms break)
- No `tail`, `wc`, `&&`-chained multiline `python -c` with nested quotes. For
  multi-line Python, write a script to `C:\Users\mshri\AppData\Local\Temp\opencode\`
  and run `python <abs-path>` with `workdir` set to the repo root.
- Two interpreters: `python` (project venv, 3.11, has all deps — use for repo
  code/tests) vs `python3` (3.13 store install, has `graphify` — use only for
  graphify commands). Never mix them.
- Scripts run by absolute path lose the repo root on `sys.path` (`import bee`
  fails). Fix: `$env:PYTHONPATH='<repo>'; python <script>`.
- `multiprocessing` spawn on Windows needs `if __name__ == "__main__"`; unguarded
  fan-out fails and falls back to sequential — expect the warning, not a crash.

## Tests (source of truth: `tests/conftest.py`, CI: `.github/workflows/ci.yml`)
- Full: `python -m pytest tests -q` (~2 min). Gate: `-m core`. Markers are a
  **hand-kept registry** — every new `tests/test_*.py` MUST be added to `_UNIT`,
  `_INTEGRATION`, or a category list or it is silently deselected from `-m core`;
  `tests/test_marker_registry.py` now fails the suite on an unregistered file
  (and on category-only entries no CI job selects).
- Hermeticity is enforced (`test_eval_hermeticity`): never write to real
  `train/`, `metrics/`, `skills/`, `memory/` from tests — use `tmp_path` +
  `monkeypatch` on `bee.paths` constants.
- Scripted-LLM tests depend on exact `client.chat` call order. Any new implicit
  model call in the agent loop (critique, reflection) must be gated so test
  doubles never see it — see `bee/agent/critique.py:should_critique`
  (`isinstance(ctx.client, LLMClient)`).
- Single eval task: `runner.run_suite(ctx, only="<id>")` (no CLI flag). Runs append
  to `evals/results.jsonl` — never quote a partial run as the suite score.

## Architecture (don't re-derive; verified)
- Execution: everything should go through `AgentKernel.run()` → `ToolBus.call()`.
  Direct `run_agent()` callers (voice loop, tests, spawn) intentionally skip the
  capability gate when `ctx.capability_gate is None` — that `is not None` guard in
  `bee/agent/loop.py` is load-bearing for 30+ callers, not a bug to "fix".
- Routing: one facade — `bee/agent/router.py:decide()` is the loop's single
  entry. Tier order (first hit wins, documented in that module's docstring and
  pinned by `tests/test_routing_order.py`): deterministic → explicit
  (prefix/hints/engine, incl. vision) → smalltalk → fast-path → ML →
  heuristic → escalate (hybrid cloud-first + availability fallback, applied by
  `run_agent` with live probes). Fast paths stay table-driven
  (`bee/agent/fastpaths.py`, ~5 lines per handler).
- Config: `load_config()` merges 6 layers; `cloud.api_key` is the one deliberate
  exception (yaml wins over env). New `config.yaml` sections need a dataclass +
  `_section()` loader line + yaml block, all three.
- Memory/RAG is LanceDB + keyword RRF (`bee/brain/rag.py`, `bee/memory/`). Do not
  add a second vector store. Diary log entries are dropped as whole `##` sections
  before chunking (never indexed — `md.chunk_md`); successes go to
  `memory/wins.md`, skills via `skills/*/SKILL.md`. Durable facts
  (profile/longterm) always write through `md.add_facts` (dedupe + update by
  subject); the nightly consolidate goes through it too. `/mem status`
  (`python -m bee.cli memory status`) shows source counts + index age.
- Requirements are pinned (`==`) in every file; ML pins must match between
  `requirements.txt` and `requirements-ml.txt` (router artifact refuses major drift).

## Live services (creds in `.env` — check presence, never print values)
- Ollama `bee4b` + `nomic-embed-text` expected; `config.yaml` already points there.
- LiveKit Cloud is reachable with repo creds; the pinned `livekit-agents==1.4.6`
  API shapes are pinned by `tests/test_livekit.py` (constructor kwargs, callback
  arities, sync `synthesize`). Verify against the installed SDK signature, not docs.

## Docs authority
- `docs/STATUS.md` is authoritative. `docs/PRODUCTION_READINESS.md` is SUPERSEDED
  (stale FAIL rows). `docs/TECHNICAL_DEBT.md` rows are evidence-linked; check the
  cited `file:line` before acting — some rows are already closed in code.
- After code changes: `python3 -m graphify update`, then `python3 -m graphify label`.
  Graph outputs live in `graphify-out/` (git-ignored; regenerate locally with `graphify update`).

## Editing
- Prefer editing over new files. After any edit, re-read the hunk and recompile
  (`ast.parse`) or run the focused tests — exact-match replacements silently join
  lines when the boundary is off.

---
<!-- graphify-rules-start (managed by `graphify init`) -->
## Use Graphify before grep

This repository is indexed by Graphify: a code graph over its call, dependency, and test structure, exposed through a connected Graphify MCP server. Before reaching for grep or reading files, use the Graphify tools your MCP client lists (their exact names and descriptions are in the server's tool list) for what the graph knows and a text search does not:

- find where a symbol, function, or class is defined (instead of grepping for it)
- understand how something works, or where a behavior is handled
- find who calls a function, or what it calls
- see what a change affects (its blast radius) and which tests cover it
- map a file's dependencies and dependents

Fall back to grep or file reads only for what the graph does not model: literal string or comment matches, non-indexed files, or reading a file you have already located. If no Graphify tools are listed, check the MCP server connection.
<!-- graphify-rules-end -->
