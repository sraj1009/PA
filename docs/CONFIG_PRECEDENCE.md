# M14 — Configuration Precedence Matrix

Single-source resolution: every resolvable BEE field has **exactly one**
winning source. The order below is the contract; `Config.precedence`
(see `/config` in the REPL) reports, for the running process, which layer
actually won — so the matrix is machine-verifiable, not aspirational.

## Layer order (highest wins)

| # | Layer | File / source | Notes |
|---|-------|---------------|-------|
| 1 | **process environment** | vars set in the shell / system (`$env:OLLAMA_MODEL`, Task Manager env, service env) | Always beats `.env`. `.env` only *fills* a var that is not already in the process environment. |
| 2 | **`.env`** | `<project>/.env` | Parsed by `config._load_dotenv()`; `KEY=value` lines, `#` comments; existing process env always wins. |
| 3 | **`models.yaml`** | `<project>/models.yaml` → `local_model:` | ONLY the local model name. Written by the J3 quality gate on promotion (and removed by `/gate rollback`). Env layers (1–2) still beat it. |
| 4 | **`config.yaml`** | `<project>/config.yaml` | All section/field config (`ollama.`, `cloud.`, `voice.`, `sandbox.`, `scheduler.`, `guard.`, `privacy.`, `router.`, `rag.`, `monitor.`, `welcome.`, `clap.`, `livekit.`, `user.`, `computeruse.`, `automation.`, `alerts.`, `model_gate.`). Unknown keys are ignored with a warning. |
| 5 | **dataclass defaults** | code in `bee/config.py` | The floor. |

`settings.json` is a **separate concern**: it stores the default *engine*
(hybrid / local / ollama-cloud / api-cloud) chosen at first launch. It never
overlaps a `Config` field; `/engine` and the web UI both read/write it.

## Field matrix

| Field | Layer 1 (env) | Layer 2 (.env) | Layer 3 (models.yaml) | Layer 4 (config.yaml) | Winner rule |
|---|---|---|---|---|---|
| `ollama.model` | `OLLAMA_MODEL` | `OLLAMA_MODEL` | `local_model` | `ollama.model` | first non-empty, top-down |
| `ollama.base_url` | `OLLAMA_BASE_URL` | `OLLAMA_BASE_URL` | — | `ollama.base_url` | first non-empty, top-down |
| `ollama.embed_model` | `OLLAMA_EMBED_MODEL` | `OLLAMA_EMBED_MODEL` | — | `ollama.embed_model` | first non-empty, top-down |
| `cloud.llm` | `CLOUD_LLM` | `CLOUD_LLM` | — | `cloud.llm` | first non-empty, top-down |
| `cloud.base_url` | `CLOUD_BASE_URL` | `CLOUD_BASE_URL` | — | `cloud.base_url` | first non-empty, top-down |
| `cloud.api_key` | provider-matched key (see below) | same | — | `cloud.api_key` | **EXCEPTION: an explicit `config.yaml` key wins over env**; env fills only when the config key is empty |
| `voice.edge_key` | `EDGE_TTS_KEY` | `EDGE_TTS_KEY` | — | `voice.edge_key` | first non-empty, top-down |
| `livekit.url` | `LIVEKIT_URL` | `LIVEKIT_URL` | — | `livekit.url` | first non-empty, top-down |
| `livekit.api_key` | `LIVEKIT_API_KEY` | `LIVEKIT_API_KEY` | — | `livekit.api_key` | first non-empty, top-down |
| `livekit.api_secret` | `LIVEKIT_API_SECRET` | `LIVEKIT_API_SECRET` | — | `livekit.api_secret` | first non-empty, top-down |
| `user.name` | `BEE_USER_NAME` | `BEE_USER_NAME` | — | `user.name` | first non-empty, top-down |
| `workspace` | `BEE_WORKSPACE` | `BEE_WORKSPACE` | — | *(not settable)* | env only, else project root |
| `engine` (default brain) | — | — | — | — | `settings.json` (independent layer) |
| all other fields | — | — | — | their `config.yaml` key | config.yaml or default |

### `cloud.api_key` provider matching
When `config.yaml` does not set `cloud.api_key`, BEE picks the env key that
matches the *provider prefix* of `cloud.llm` (e.g. an `openai/...` model →
`OPENAI_API_KEY`; `openrouter/...` → `OPENROUTER_API_KEY`; `anthropic/...`
→ `ANTHROPIC_API_KEY`; `gemini/...`/`google/...` → `GEMINI_API_KEY`).
Provider mapping lives in `bee/agent/providers.py` (single source of truth).
"First key that exists" is deliberately NOT the rule — it would send the
wrong key to the wrong provider.

## Why models.yaml is its own layer
The J3 quality gate promotes a new local model by writing
`models.yaml: {local_model: <candidate>}`. Keeping promotion in its own file
means:

- `config.yaml` (hand-edited, comment-rich) is never rewritten by automation;
- rollback is a single delete (`/gate rollback`);
- the promotion is visible in git history as a one-line change.

## Verification
- `/config` in the REPL prints the resolved provenance per field.
- `tests/test_config_precedence.py` pins the whole matrix: it stages each
  layer independently (tmp `config.yaml`, tmp `.env`, tmp `models.yaml`,
  controlled process env) and asserts both the winning VALUE and the reported
  SOURCE for every row above.
- `tests/test_eval_gate.py` pins the promotion/rollback behavior of the
  models.yaml layer.
