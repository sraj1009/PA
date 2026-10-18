# BEE — Security Model (Phase 1)

This document describes BEE's security posture after Phase 1
(Security + Runtime Stabilization), what each control does, and — just as
importantly — what it does **not** protect. Read the
[Known residual risks](#known-residual-risks) section before exposing BEE
to unattended operation.

## Threat model

BEE is a **local, single-operator** assistant. The realistic threats are:

1. **Prompt injection** — the LLM (local 3B or cloud) is steered by tool
   output or web content into calling dangerous tools.
2. **Credential leakage** — secrets in `.env` / config / generated files
   being read by sandboxed code, written to logs, episodes, or training data.
3. **SSRF** — the `web_fetch` tool being pointed at internal/cloud-metadata
   addresses.
4. **Unauthorized local web access** — another process/user on the machine
   driving BEE through the web UI.
5. **DoS via generated code** — fork bombs, memory exhaustion, unbounded
   downloads.

BEE is **not** designed to withstand a determined remote attacker with
code-execution on the host; the container boundary is a mitigation, not a
perfect isolation (see below).

## 1. Credentials & rotation

### ⚠️ ROTATE THESE NOW (pre-Phase-1 exposure)

Before Phase 1, BEE kept `.env` inside an **OneDrive-synced** project
directory. Treat every credential that lived there as **compromised**:

| Credential | Where it was | Action |
|---|---|---|
| **LiveKit API Key / Secret** (`LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`) | `.env` (synced) | **Rotate in the LiveKit Cloud console.** Old tokens minted with the old key remain valid until the key is rotated. |
| **Google/Gemini API key** (`GOOGLE_API_KEY` / `GEMINI_API_KEY`) | `.env` (synced) | **Revoke + reissue** in Google AI Studio. |
| Any other provider key present in `.env` (OpenAI/Anthropic/DeepSeek/OpenRouter/XAI/Edge-TTS) | `.env` (synced) | Rotate anything that has real billing/privilege. |

After rotation: keep `.env` out of cloud sync (exclude the project folder
from OneDrive sync, or move `.env` outside the synced tree).

### Rules in force since Phase 1

- `.env` and all `.env.*` (except `.env.example`) are git-ignored;
  `temp/`, `audit.jsonl`, `train/`, `metrics/` are git-ignored too.
- `.env.example` documents every supported key with **placeholder values
  only**.
- **No code path prints secret values.** Provider key lookup
  (`bee/agent/providers.py`) never logs the value; the web token is printed
  **once** at server start by design (operator read) and never logged
  afterwards; `secretscan.mask()` renders keys as `abcd…(42)`.
- **`bee/security/secretscan.py`** scans the repo (tracked + untracked,
  skipping binary/generated dirs) for known key prefixes, JWTs, PEM blocks
  and high-entropy assignments. Run it:

      make secretscan
      # or
      python -m bee.security.secretscan        # exits 1 on findings

  The pytest suite includes a repo gate that fails if a new secret pattern
  appears in source (excluding the `tests/`+`evals/` fixture zone).
- **Training data cannot become a secret sink**: the episode logger
  redacts every field through `bee/privacy.py` (`redact()`) before
  persisting, so exported SFT data inherits the same privacy rules.

## 2. Web UI authentication (was critical C1)

The web server binds to `127.0.0.1:8787` and requires a **bearer token**
on every stateful endpoint:

| Endpoint | Auth |
|---|---|
| `POST /chat`, `POST /voice`, `POST /engine`, `POST /livekit/token`, `GET /face/state` | **required** |
| `GET /`, `/health`, `/skills`, `/engine` (read), `/livekit`, `/livekit/status`, `/face` | open (read-only / static) |

Token precedence (`bee/webapp.py:_resolve_token`):

1. `BEE_WEB_TOKEN` environment variable (operator-fixed, e.g. in `.env`),
2. `temp/web_token.txt` (git-ignored; created on first run),
3. auto-generated `secrets.token_hex(16)`, saved to that file and
   **printed once** in the server console.

The UI stores the token in browser `localStorage` (🔑 button re-enters it),
retries once after a 401, and compares with `hmac.compare_digest`
(constant-time). This is a **local session credential** for a loopback
server, not a cloud secret — but it gates the full agent, so don't share it.

## 3. SSRF protection for web fetching

`bee/security/netguard.py` is the only path that fetches URLs for the agent
(`tools/web.py` delegates to it):

- scheme allowlist: **http/https only**;
- host blocklist: `localhost`, `*.local`, `*.internal`, `*.localhost`,
  `*.home.arpa`;
- **every resolved IP** is classified: loopback (`127.0.0.0/8`, `::1`),
  RFC1918 private, link-local (incl. `169.254.169.254` cloud metadata),
  unspecified, multicast, CGNAT `100.64.0.0/10`, benchmarking `198.18.0.0/15`
  are all rejected. All A/AAAA records are checked, so a domain that
  resolves to one bad IP is blocked (DNS-rebinding safe);
- **every redirect hop is re-validated** (manual redirect loop, max 5);
- connect timeout 6 s / read timeout 20 s; response capped at 1.5 MB
  (streaming, hard abort); content-type allowlist (HTML/text/JSON/XML…);
- fetched content is **explicitly marked untrusted**: the loop wraps tool
  results for `untrusted_output` tools in
  `<<< UNTRUSTED EXTERNAL DATA (url) >>>` markers so the model is told the
  text is data, not instructions.

Tests: `tests/test_netguard.py` (19 blocked-URL cases incl. metadata IP,
rebinding, redirect revalidation, size/timeout/content-type).

## 4. Tool risk classification + audit

`bee/security/risk.py` implements a layered, fail-closed model:

1. **Static profile** per tool (risk level + required capability:
   `CAP_EXEC`, `CAP_NETWORK`, `CAP_FS_WRITE`, …) — see `_TOOL_PROFILES`.
2. **Guard regex layer** (`bee/guard.py:classify`, unchanged — the
   deterministic deny/ask rules stay a fast first filter).
3. **Python AST layer** for executed code (`code_run`, and `shell`
   `python -c …` fragments):
   - **deny**: `subprocess`, `socket`, `ctypes`, `eval`, `exec`,
     `compile`, `__import__`, `os.system/popen/exec*/spawn*`,
     `os.remove/unlink/rmdir/removedirs/truncate`, `shutil.rmtree`,
     `pickle.load(s)`, `Path.unlink/rmdir` and other file-destruction
     calls. The layer is **alias-aware**: `import shutil as sh; sh.rmtree(…)`,
     `from os import system; system(…)`, `from shutil import rmtree as rm`
     and `getattr(os, "system")` are all denied — as is a deny-listed
     function merely *referenced* (`f = os.system`) without a call;
   - **deny (path escape)**: write-mode `open()` / `Path.write_text` /
     `Path.write_bytes` on a string-literal path that escapes the runtime
     workspace, the project root and the OS temp dir (absolute system
     paths, `~`, `..`-chains). Relative and dynamic paths stay **ask**;
   - **deny (SSRF)**: literal-URL HTTP calls through
     `requests/httpx/urllib/aiohttp/urllib3/http` targeting localhost,
     RFC1918, link-local (e.g. `169.254.169.254`) or other non-public
     addresses. Checked offline — no DNS at classification time;
   - **ask**: file open in write modes (in-tree/dynamic), `Path.mkdir/
     makedirs/touch`, `os.mkdir/makedirs/symlink`, `os.chmod/chown/kill/
     rename`, `shutil.move/copy/copy2/copytree`, imports of
     `os/sys/shutil/pickle/importlib/signal`, and imports of network
     clients (`requests/httpx/urllib/aiohttp/urllib3/http` — no host
     allowlist is configured, so egress needs approval);
   - unparseable `code_run` → **ask** (fail closed).
   The strictest layer wins (`RiskDecision(level, action, reason,
   capabilities, require_approval)` with `NONE→CRITICAL`).
4. **Audit record**: every tool execution in the agent loop (main +
   fastpath) is appended to `audit.jsonl` (git-ignored) as
   `{ts, tool, args, risk, action, ok, seconds, blocked, source}` —
   **args and reasons are redacted** by the privacy layer before writing.
   `bee/security/audit.py` is best-effort: it never raises into the loop.

The abstraction is deliberately minimal: `RiskDecision` is the unit that a
future interactive-approval UI would consume (`require_approval` already
encodes the ask/deny split).

## 5. Docker sandbox boundary (was high H4)

`sandbox_run` executes **untrusted, model-generated code** in the
`bee-sandbox` image. Every run now launches with:

```
--network none                      # no network access at all
--memory 2g --memory-swap 2g        # memory cap
--cpus 2                            # CPU cap
--pids-limit 128                    # fork-bomb guard
--cap-drop ALL                      # no Linux capabilities
--security-opt no-new-privileges    # no setuid escalation
--read-only                         # root filesystem read-only
--tmpfs /tmp:rw,noexec,nosuid,size=256m   # bounded scratch
--user 1000:1000                    # non-root (uid 1000 = beeuser)
-v <workspace>:/workspace           # THE explicit writable grant
-v <temp/sandbox_env_mask>:/workspace/.env:ro   # .env masked (empty file)
```

All values are configurable via the `sandbox:` section of `config.yaml`
(`network`, `memory`, `cpus`, `pids_limit`, `read_only_root`, `tmpfs_size`,
`user`, `mask_env_file`).

**What this gives you:** untrusted code gets 2 CPUs, 2 GB RAM, ≤128
processes, zero network, a read-only OS, and no privileges; it can only
write to `/tmp` (bounded) and `/workspace`. Its `.env` view is an **empty
file** — credentials are masked inside the container.

**What it does NOT give you (be honest about this):**
- Docker is a **shared-kernel** boundary. A kernel/containerd escape or a
  malicious package with a setuid binary outside the dropped-caps scope
  can still reach the host. This is a mitigation for model-generated
  mistakes, not a security boundary against a determined attacker.
- The **workspace itself is writable by design** (that is the point —
  sandbox output must be visible on the host). Anything placed *in the
  workspace* (other than `.env`, which is masked) is readable/writable by
  sandboxed code. Do not keep additional credentials in workspace files.
- `shell` / `code_run` **outside** the sandbox run directly on the host
  with your full user privileges; the risk layer can ask/deny, but an
  allowed `shell` call is as powerful as you are.
- The pre-Phase-1 image was built as root with uv at `/root/.local/bin`.
  The running image still works with `--user 1000:1000` for `python` jobs
  (verified: non-root `python` + torch import OK), but rebuild to get
  non-root `uv`/playwright paths:

      docker build -t bee-sandbox:latest ./sandbox

  If a job fails with EACCES on the old image, temporarily set
  `sandbox.user: ""` in config.yaml (image default) and rebuild when free.

**Trusted vs untrusted execution, explicitly:**

| Execution path | Trust | Boundary |
|---|---|---|
| `shell`, `code_run` (host) | trusted operator intent, model-suggested | guard + risk layers, **no** OS isolation |
| `sandbox_run` | untrusted code | Docker boundary above |
| `web_fetch` | untrusted content | netguard SSRF policy + untrusted markers |
| web UI | local session | bearer token |

## 6. LLM / provider layer (runtime, not strictly security)

- One typed contract for every LLM call: `LLMClient.request(LLMRequest) ->
  LLMResponse` with `chat(name, messages, **overrides)` as the convenience
  wrapper. All call sites (loop, commands, router, planner, RAG summarizer)
  use it; unsupported-parameter mismatches that previously silently disabled
  `/plan /draft /summarize /code /think` are fixed and regression-tested.
- `bee/agent/providers.py` is the **single** place that knows which env var
  belongs to which provider (`ProviderRegistry`, `ProviderConfig`,
  `ProviderHealth`, `kind_for_model`, `key_for`). The rest of the app calls
  `cloud_available(cfg) -> (bool, reason)` and never inspects `os.environ`
  for keys. Cloud availability reflects the **actually configured**
  provider (its key), with an explicit legacy any-key fallback.

## 7. Known residual risks

Honest list — each is tracked in `docs/TECHNICAL_DEBT.md`:

1. **LiveKit argv "start" hack** (`bee/livekit/agent.py`): typer subcommand
   workaround; documented, not a security hole but fragile.
2. **`shell` allowed = full host user privileges.** Mitigated by guard +
   risk layers and audit, not by isolation. An approval-gated execution
   mode is Phase 2 work.
3. **AST evasion**: the Python risk layer is a whitelist of dangerous
   constructs, not a sandbox — aliased imports
   (`from subprocess import run as r`) are caught, but creative
   `__subclasses__` chains are not. That is why destructive ML/data work
   belongs in `sandbox_run`.
4. **Web streaming is fake-SSE** (buffered) and `/voice` returns JSON
   despite its docstring promising mp3 (fixed the docstring; TTS response
   is Phase 6).
5. **User cron jobs are no-ops** (scheduler runs its internal jobs only) —
   Phase 3.
6. **LanceDB rebuilds duplicates** under heavy load — Phase 4.
7. **`temp/web_token.txt` lives in a OneDrive-synced folder** on this
   machine. `temp/` is git-ignored, but OneDrive sync is outside git's
   control — exclude the project from cloud sync (see rotation note).
8. **Agent eval quality ceiling**: 10/21 on the local 3B model is a
   capability limit, not a loop bug; cloud escalation covers the gap.
9. **No per-tool timeout/cancellation** beyond the sandbox's own timeout
   and the LLM client timeouts — long host `shell` calls are bounded only
   by the guard's ask/deny decision. Phase 2.

## Quick operator checklist

- [ ] Rotated LiveKit API key + secret (and any other synced `.env` key).
- [ ] Excluded `C:\Users\mshri\OneDrive\Desktop\PA` from OneDrive sync
      (or moved `.env` out of it).
- [ ] `make secretscan` passes (it is also a pytest gate).
- [ ] Web token: read from the server console / `temp/web_token.txt`
      (or set `BEE_WEB_TOKEN` in `.env` for a stable token).
- [ ] Sandbox: rebuilt non-root image (`docker build -t
      bee-sandbox:latest ./sandbox`) when convenient.
- [ ] `audit.jsonl` reviewed periodically for ask/deny escalations.
