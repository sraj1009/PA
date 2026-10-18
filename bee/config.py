"""BEE configuration: single-source resolution with documented precedence.

M14 — every resolvable field has exactly ONE winning source, in this order
(highest wins). Full matrix: docs/CONFIG_PRECEDENCE.md.

  1. process environment   (vars set in the shell/system, e.g. $env:OLLAMA_MODEL)
  2. .env file             (PROJECT_ROOT/.env — only fills vars NOT already in the
                            process environment)
  3. models.yaml           (local_model ONLY — the model-promotion layer written by
                            the J3 quality gate; env always beats it)
  4. config.yaml           (explicit file config)
  5. dataclass defaults    (code)

Exceptions (documented in the matrix):
  * cloud.api_key — an explicit config.yaml key WINS over env provider keys
    (an operator who set the key in config.yaml should not be surprised by
    a stale env var); env is used only to FILL an empty config key.
  * settings.json — engine selection only (hybrid/local/...); a separate
    concern that never touches Config fields.
  * workspace — env only (BEE_WORKSPACE); config.yaml does not set it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

from . import paths

log = logging.getLogger("bee.config")


@dataclass
class OllamaCfg:
    base_url: str = "http://localhost:11434"
    model: str = "bee4b"
    embed_model: str = "nomic-embed-text"
    max_tokens: int = 4096
    temperature: float = 0.2
    timeout: float = 300.0
    # Ollama keeps a loaded model resident by default (5 min). On a RAM-tight
    # box that means ~2 GB of bee4b squatting in VRAM between tasks.
    # "60s" unloads it shortly after the last local call. "" = Ollama default.
    keep_alive: str = "60s"
    # KV-cache context window. Must hold a WHOLE agent turn: with the real system
    # prompt + 30 tool schemas a turn is 5772-7339 tokens (A59, measured), and
    # Ollama does not degrade gracefully when it does not fit — it evaluates half
    # the window and answers anyway. 8192 is also the largest setting that stays
    # entirely in this box's 4 GB VRAM (/api/ps: 12288 offloads 0.46 GB and is
    # ~35% slower per call). Kept in sync with config.yaml, which ships it.
    num_ctx: int = 8192
    # Start `ollama serve` at boot when the server is not already running. BEE's
    # local tier is the product; until A60 nothing could bring the server up, so a
    # reboot silently relegated every task to cloud/deterministic mode.
    autostart: bool = True


@dataclass
class CloudCfg:
    enabled: bool = True
    llm: str = ""  # e.g. "openrouter/deepseek/deepseek-chat" or "openai/gpt-4o-mini"
    api_key: str = ""
    base_url: str = ""
    max_tokens: int = 8192
    temperature: float = 0.3
    timeout: float = 180.0
    # Hybrid speed tier: in the hybrid engine, conversational tasks go to the
    # fast cloud model FIRST (no local RAM load) with automatic local fallback
    # when cloud is down. Explicit 'local:' prefixes / "use local" / engine=local
    # always win. Set false for classic local-first hybrid.
    cloud_first: bool = True
    # --- P0-2 (2026-10-17): the cloud quota is a MANAGED resource ---
    # Second provider for the SAME call when the primary hits a rate limit /
    # auth error / 5xx: client.py cools the primary's provider kind down for
    # quota_cooldown seconds and retries on fallback_llm (its own credentials:
    # fallback_api_key, else the provider env key — zai -> ZAI_API_KEY /
    # ZHIPUAI_API_KEY). Empty fallback_llm = no failover (old behavior).
    fallback_llm: str = ""          # e.g. "zai/glm-5.3-flash"
    fallback_api_key: str = ""
    fallback_base_url: str = ""
    quota_cooldown: int = 900       # seconds a failing provider kind is skipped


@dataclass
class VoiceCfg:
    enabled: bool = True
    model: str = "base.en"          # faster-whisper model size
    device: str = "auto"            # auto | cpu | cuda
    compute_type: str = "int8"
    sample_rate: int = 16000
    silence: float = 1.2            # seconds of silence to end a recording
    max_seconds: int = 90
    wake_word: str = "bee"
    speak: bool = True
    speak_limit: int = 600
    tts_rate: int = 190
    tts_voice: str = ""        # "" = system default; SAPI substring (e.g. "aria") or edge name
    edge_key: str = ""
    # --- Phase 4 realtime voice ---
    rt_barge_in: bool = True       # user can interrupt BEE while it speaks
    rt_silence_ms: int = 700       # endpointing: silence that closes an utterance
    rt_max_utterance_ms: int = 15000
    rt_partial_stt: bool = True    # interim transcripts while the user speaks
    rt_partial_every_ms: int = 900 # min interval between partials
    rt_partial_min_growth: int = 32000  # min new audio (bytes) before a new partial
    rt_conversation: bool = True   # stay LISTENING after a response (vs back to IDLE)
    rt_wake_ack: bool = True       # speak a short ack after the wake word
    rt_stt_timeout: float = 30.0  # STT final timeout (provider-failure handling)
    rt_tts_timeout: float = 20.0  # per-sentence TTS timeout
    rt_reconnect_max: int = 30.0  # max reconnect backoff delay (seconds)


@dataclass
class SandboxCfg:
    enabled: bool = True
    image: str = "bee-sandbox:latest"
    gpu: bool = True
    workdir: str = "/workspace"
    timeout: int = 300
    max_output: int = 12000
    # --- Phase 1 hardening (sandbox runs UNTRUSTED, model-generated code) ---
    # These are defaults; any can be overridden per-machine in config.yaml.
    network: str = "none"        # docker network mode: "none" = no network at all
    memory: str = "2g"           # memory cap (also used as the --memory-swap cap)
    cpus: str = "2"              # CPU cap
    pids_limit: int = 128        # fork-bomb guard
    read_only_root: bool = True  # root FS read-only; /tmp is a size-capped tmpfs
    tmpfs_size: str = "256m"     # size of the rw /tmp tmpfs
    user: str = "1000:1000"      # non-root uid:gid inside the container; set ""
                                 # to fall back to the image default (needed only
                                 # for the pre-Phase-1 root image)
    mask_env_file: bool = True   # mask <workspace>/.env from inside the
                                 # container (tmpfs over the file) so untrusted
                                 # code cannot read host credentials


@dataclass
class SchedulerCfg:
    enabled: bool = True
    consolidate_cron: str = "0 3 * * *"  # 03:00 nightly


@dataclass
class GuardCfg:
    enabled: bool = True
    mode: str = "cli"          # cli (prompt) | unattended (auto-deny) | always (auto-approve)


@dataclass
class PrivacyCfg:
    redact_cloud: bool = True  # PII redaction on cloud-bound payloads; local never redacted


@dataclass
class RouterCfg:
    ml_enabled: bool = True
    ml_min_episodes: int = 150  # learned router activates after this many labeled episodes
    ml_confidence: float = 0.70


@dataclass
class RagCfg:
    auto_context: bool = True
    k: int = 4


@dataclass
class MonitorCfg:
    enabled: bool = True


@dataclass
class WelcomeCfg:
    """'Welcome Home' workspace protocol (ported from Super JARVIS)."""
    enabled: bool = True
    user: str = "Boss"
    retrigger_s: float = 60.0        # anti-spam guard between runs
    song_uri: str = ""               # Spotify/YouTube track URL ("" = skip song)
    urls: list = field(default_factory=list)  # [{url, monitor, fullscreen}]
    focus_ide: bool = True
    ide_fullscreen: bool = False
    ide_name: str = "IDE"            # label used in step messages
    ide_exes: list = field(default_factory=lambda: ["cursor.exe", "code.exe"])
    ide_path: str = ""               # launch target when no window is running


@dataclass
class ClapCfg:
    """Double-clap acoustic trigger (ported from Super JARVIS)."""
    action: str = "welcome"          # welcome | voice
    sample_rate: int = 44100
    block_ms: int = 40
    spike_ratio: float = 7.0
    min_rms: float = 0.012
    min_gap: float = 0.06
    max_gap: float = 0.40
    cooldown: float = 1.5
    retrigger_ratio: float = 0.55
    warmup_s: float = 1.5


@dataclass
class LivekitCfg:
    """LiveKit Cloud realtime voice (free tier) — the 'backtalk' piece.
    Secrets come from env (.env): LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET."""
    enabled: bool = True
    url: str = ""
    api_key: str = ""
    api_secret: str = ""
    room: str = "bee-pa"
    stt_lang: str = "en"


@dataclass
class UserCfg:
    """Who BEE serves — personalization (name, timezone, interests)."""
    name: str = "Boss"
    timezone: str = "Asia/Calcutta"
    region: str = "IN"
    interests: list = field(default_factory=list)


@dataclass
class ComputerUseCfg:
    """Phase 5 — safe computer use (desktop control).

    Safe set only (observe / windows / click-type-keys-scroll / clipboard).
    Every action is post-verified and bounded by a per-task budget; typed
    text, clipboard content, pixels and window titles never enter logs.
    """
    enabled: bool = True
    max_actions: int = 15                # hard cap per task (closed-loop budget)
    action_timeout: float = 10.0         # per-action execution timeout (s)
    screenshot_retention_minutes: float = 5.0
    screenshot_save: bool = False        # False = in-memory hash ring only
    hotkey: str = "ctrl+alt+q"           # global emergency-stop combo
    hotkey_enabled: bool = True


@dataclass
class AutomationCfg:
    """Phase 6 — durable automation + proactive agent.

    Jobs persist under <workspace>/automation/ and survive restarts; the
    worker executes them through the same AgentKernel as interactive
    requests. Proactive behavior is default-deny: only explicitly
    user-authorized rules (rate-limited) may act on internal events.
    """
    enabled: bool = True
    tick_seconds: float = 5.0            # scheduler pass interval
    max_parallel: int = 2                # global job concurrency cap
    miss_grace_seconds: int = 900        # one-time jobs catch up if missed by <= 15 min
    default_timezone: str = "Asia/Kolkata"
    # Event sources (bee/automation/events.py -> start_sources). Each of these
    # is READ by that function — adding a key here without wiring it there is
    # exactly the dead-switch defect class the 2026-10-08 audit recorded.
    events_enabled: bool = True          # false = no polling sources at all
    event_tick_seconds: float = 60.0     # heartbeat that proactive rules can match
    battery_poll_seconds: float = 60.0
    battery_low_percent: int = 20        # battery.low fires at/below this while unplugged
    network_poll_seconds: float = 30.0
    app_events: bool = True            # foreground-window + launch/close events
    app_poll_seconds: float = 10.0
    device_events: bool = True         # memory/disk pressure transitions
    device_poll_seconds: float = 60.0
    memory_low_mb: int = 1500          # device.memory_low at/below this free RAM
    disk_low_gb: float = 4.0           # device.disk_low at/below this free disk
    file_watch_dir: str = ""             # empty = file-change source off


@dataclass
class AlertsCfg:
    """Audit item 6 — OS-level toasts + threshold alerting.

    A daily `alert_scan` job evaluates 24h metrics stats against these
    thresholds; each breach toasts once per cooldown (no spam). Job
    failures/misses toast immediately (JobWorker._notify)."""
    enabled: bool = True
    provider_fail_rate: float = 0.5       # alert if >= 50% of LLM calls fail
    provider_fail_min_calls: int = 5      # ... but only with a real sample
    verify_fail_rate: float = 0.5         # alert if >= 50% of tasks fail verification
    min_tasks: int = 3
    permission_denied: int = 5            # absolute denials in 24h
    cooldown_seconds: float = 3600.0      # per-alert-key spam guard


@dataclass
class ModelGateCfg:
    """J3 — model-upgrade quality gate. A candidate local model is promoted
    (models.yaml) only when it beats the active model's recorded eval baseline
    by `margin` AND causes no structural-task regression. Empty `candidate`
    = the nightly gate idles (nothing to test); the P0-5 auto-chain queues the
    night's model in train/gate_candidate.json, which this gate consumes."""
    enabled: bool = True
    candidate: str = ""      # e.g. "bee4b-v2" — set when a new model is trained/pulled
    margin: int = 1          # candidate must score at least baseline + margin
    # P0-5: statistical power. Tasks the two arms DISAGREE on are re-run this
    # many extra times per side; majority decides. At n=21, a single flaky task
    # could flip a verdict either way (the live 2026-10-17 gate run sat inside
    # the suite's ±2-3 stochastic noise). 0 = single-shot (old behavior).
    adjudication_rounds: int = 2


@dataclass
class LearningCfg:
    """Self-improvement flywheel. `reflect` writes a short self-review per
    non-trivial task into memory/lessons/, which `context.recent_lessons()` then
    injects into every future system prompt — so it is an operator-visible
    kill-switch, not an internal detail (read by `AgentKernel._reflect`).
    `self_critique` runs one bounded local draft->critique->refine pass over
    the final answer before verification (read by the agent loop).
    `plan_first` runs the local planner tool BEFORE the loop on multi-step
    work (and on requests that ask for a plan) so the steps are in context
    while the small model executes — the planner used to run only as an
    after-the-fact rescue for plan requests (read by the agent loop)."""
    reflect: bool = True
    self_critique: bool = True
    critique_min_chars: int = 200
    plan_first: bool = True


@dataclass
class TrainingCfg:
    """Nightly QLoRA refresh (training/qlora/train.py on train/sft_v1.jsonl).

    `auto_qlora` is the opt-in for automatic GPU training: a multi-hour burn
    must never start by surprise on a daily-driver machine. Capture (golden
    cloud answers) and dataset rebuild run regardless — this switch gates only
    the torch run. Promotion is separate: the J3 model_gate adopts an adapter
    only on eval win (set model_gate.candidate to the finished adapter)."""
    auto_qlora: bool = False
    min_samples: int = 150      # don't train below this (overfit risk)
    max_samples: int = 500      # bound one night's run (newest samples first)
    preset: str = "fast"        # fast (r=8/seq2048/1ep) | full (r=16/seq4096/2ep)
    min_interval_days: float = 7.0
    max_seconds: float = 21600.0  # 6 h cap per run
    # P0-5: auto-chain merge->gate after a successful nightly training: merge
    # the adapter (merge_export.py), convert to f16 GGUF + quantize Q4_K_M,
    # `ollama create` the model, and queue it for the J3 gate
    # (train/gate_candidate.json). Needs an unpacked llama.cpp here:
    # convert_hf_to_gguf.py at this dir's root and llama-quantize*.exe
    # alongside (release zip + source zip, e.g. b11711). Empty = merge +
    # Modelfile only, no automatic import/queue.
    llama_cpp_dir: str = ""


@dataclass
class Config:
    ollama: OllamaCfg = field(default_factory=OllamaCfg)
    cloud: CloudCfg = field(default_factory=CloudCfg)
    voice: VoiceCfg = field(default_factory=VoiceCfg)
    sandbox: SandboxCfg = field(default_factory=SandboxCfg)
    scheduler: SchedulerCfg = field(default_factory=SchedulerCfg)
    guard: GuardCfg = field(default_factory=GuardCfg)
    privacy: PrivacyCfg = field(default_factory=PrivacyCfg)
    router: RouterCfg = field(default_factory=RouterCfg)
    rag: RagCfg = field(default_factory=RagCfg)
    monitor: MonitorCfg = field(default_factory=MonitorCfg)
    welcome: WelcomeCfg = field(default_factory=WelcomeCfg)
    clap: ClapCfg = field(default_factory=ClapCfg)
    livekit: LivekitCfg = field(default_factory=LivekitCfg)
    user: UserCfg = field(default_factory=UserCfg)
    computeruse: ComputerUseCfg = field(default_factory=ComputerUseCfg)
    automation: AutomationCfg = field(default_factory=AutomationCfg)
    alerts: AlertsCfg = field(default_factory=AlertsCfg)
    model_gate: ModelGateCfg = field(default_factory=ModelGateCfg)
    learning: LearningCfg = field(default_factory=LearningCfg)
    training: TrainingCfg = field(default_factory=TrainingCfg)
    workspace: Path = paths.WORKSPACE
    # M14: where each resolvable field actually came from (default | config.yaml
    # | models.yaml | .env | process-env | env-provider-key). Attached by
    # load_config; inspectable after the fact (single-source-of-truth proof).
    precedence: dict = field(default_factory=dict, repr=False, compare=False)

    def get_llm(self, name: str) -> dict:
        """Resolve an LLM name (local default, cloud default, or explicit) to a dict."""
        name = (name or "").strip().lower()
        if name in ("", "local", "auto"):
            return {
                "name": self.ollama.model,
                "base_url": self.ollama.base_url,
                "max_tokens": self.ollama.max_tokens,
                "temperature": self.ollama.temperature,
                "timeout": self.ollama.timeout,
                "num_ctx": self.ollama.num_ctx,
                "cloud": False,
            }
        if name == "cloud":
            llm = self.cloud.llm
            if not llm:
                raise ValueError("cloud model not configured: set cloud.llm in config.yaml")
            return {
                "name": llm,
                "base_url": self.cloud.base_url,
                "max_tokens": self.cloud.max_tokens,
                "temperature": self.cloud.temperature,
                "timeout": self.cloud.timeout,
                "cloud": True,
                "api_key": self.cloud.api_key,
            }
        # treat as a raw model name (e.g. "qwen3:4b" or "openai/gpt-4o-mini")
        cloud = ":" not in name and "/" in name
        if cloud:
            return {
                "name": name,
                "base_url": self.cloud.base_url,
                "max_tokens": self.cloud.max_tokens,
                "temperature": self.cloud.temperature,
                "timeout": self.cloud.timeout,
                "cloud": True,
                "api_key": self.cloud.api_key,
            }
        return {
            "name": name,
            "base_url": self.ollama.base_url,
            "max_tokens": self.ollama.max_tokens,
            "temperature": self.ollama.temperature,
            "timeout": self.ollama.timeout,
            # num_ctx belongs to the Ollama server options, so it applies to ANY
            # local model (an explicit "qwen3:4b" or the ollama-cloud "x:cloud"
            # override). Omitting it here let client.py fall back to its own
            # hardcoded 8192 and silently ignore the configured value.
            "num_ctx": self.ollama.num_ctx,
            "cloud": False,
        }


def _env_key_for(llm: str) -> str:
    """Provider-matched API key for a model reference.

    DELEGATES to bee.agent.providers (the single source of truth for
    provider kinds / env keys / aliases). A blanket 'first key that exists'
    would send the WRONG key when several providers are configured (e.g. an
    OpenAI key sent to a Gemini model).
    """
    from .agent.providers import env_key_for
    key = env_key_for(llm)
    if key:
        return key
    # no provider-prefix match — legacy behaviour: any configured cloud key
    from .agent.providers import ProviderKind, key_for
    for k in ProviderKind:
        if k == ProviderKind.OLLAMA:
            continue
        if key_for(k):
            return key_for(k)
    return ""


def _apply_env(c: Config) -> Config:
    import os
    if os.environ.get("OLLAMA_BASE_URL"):
        c.ollama.base_url = os.environ["OLLAMA_BASE_URL"].rstrip("/")
    if os.environ.get("OLLAMA_MODEL"):
        c.ollama.model = os.environ["OLLAMA_MODEL"]
    if os.environ.get("OLLAMA_EMBED_MODEL"):
        c.ollama.embed_model = os.environ["OLLAMA_EMBED_MODEL"]
    if not c.cloud.api_key:  # explicit config.yaml key wins; else provider-matched env var
        c.cloud.api_key = _env_key_for(c.cloud.llm)
    if os.environ.get("CLOUD_LLM"):
        c.cloud.llm = os.environ["CLOUD_LLM"]
        c.cloud.enabled = True
    if os.environ.get("CLOUD_BASE_URL"):
        c.cloud.base_url = os.environ["CLOUD_BASE_URL"]
    if os.environ.get("EDGE_TTS_KEY"):
        c.voice.edge_key = os.environ["EDGE_TTS_KEY"]
    if os.environ.get("LIVEKIT_URL"):
        c.livekit.url = os.environ["LIVEKIT_URL"].rstrip("/")
    if os.environ.get("LIVEKIT_API_KEY"):
        c.livekit.api_key = os.environ["LIVEKIT_API_KEY"]
    if os.environ.get("LIVEKIT_API_SECRET"):
        c.livekit.api_secret = os.environ["LIVEKIT_API_SECRET"]
    if os.environ.get("BEE_USER_NAME"):
        c.user.name = os.environ["BEE_USER_NAME"]
    if str(getattr(c.guard, "mode", "cli")).lower() == "always":
        # The one-line footgun: auto-approve-everything must never come from
        # operator config. Programmatic/test use via make_approver("always")
        # still works (with a warning); config falls back to prompting.
        import logging as _logging
        _logging.getLogger("bee.config").warning(
            "config: guard.mode 'always' is refused (auto-approves every "
            "destructive call) — falling back to 'cli'")
        c.guard.mode = "cli"
    return c


def _load_dotenv() -> None:
    """Load PROJECT_ROOT/.env into os.environ (existing values always win)."""
    import os
    f = paths.PROJECT_ROOT / ".env"
    if not f.exists():
        return
    for ln in f.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and not os.environ.get(k):
            os.environ[k] = v


def _section(cls, base, incoming):
    """Build a config section from a yaml dict, merged onto the defaults.

    Unknown keys are ignored (with a one-line warning) so a stray field in
    config.yaml can never crash the whole app at load time.
    """
    valid = {f.name for f in fields(base)}
    incoming = incoming or {}
    for k in incoming:
        if k not in valid:
            log.warning("config: ignoring unknown key '%s.%s' (not a field of %s)",
                        cls.__name__.lower(), k, cls.__name__)
    known = {k: v for k, v in incoming.items() if k in valid}
    return cls(**{**base.__dict__, **known})


def _build_from_yaml(data: dict) -> Config:
    """Defaults + config.yaml (layers 5+4 of the M14 matrix)."""
    c = Config()
    c.ollama = _section(OllamaCfg, c.ollama, data.get("ollama"))
    c.cloud = _section(CloudCfg, c.cloud, data.get("cloud"))
    c.voice = _section(VoiceCfg, c.voice, data.get("voice"))
    c.sandbox = _section(SandboxCfg, c.sandbox, data.get("sandbox"))
    c.scheduler = _section(SchedulerCfg, c.scheduler, data.get("scheduler"))
    c.guard = _section(GuardCfg, c.guard, data.get("guard"))
    c.privacy = _section(PrivacyCfg, c.privacy, data.get("privacy"))
    c.router = _section(RouterCfg, c.router, data.get("router"))
    c.rag = _section(RagCfg, c.rag, data.get("rag"))
    c.monitor = _section(MonitorCfg, c.monitor, data.get("monitor"))
    c.welcome = _section(WelcomeCfg, c.welcome, data.get("welcome"))
    c.clap = _section(ClapCfg, c.clap, data.get("clap"))
    c.livekit = _section(LivekitCfg, c.livekit, data.get("livekit"))
    c.user = _section(UserCfg, c.user, data.get("user"))
    c.computeruse = _section(ComputerUseCfg, c.computeruse, data.get("computeruse"))
    c.automation = _section(AutomationCfg, c.automation, data.get("automation"))
    c.alerts = _section(AlertsCfg, c.alerts, data.get("alerts"))
    c.model_gate = _section(ModelGateCfg, c.model_gate, data.get("model_gate"))
    c.learning = _section(LearningCfg, c.learning, data.get("learning"))
    c.training = _section(TrainingCfg, c.training, data.get("training"))
    return c


def _models_yaml_override() -> str:
    """Layer 3: models.yaml `local_model` (written by the J3 quality gate on
    promotion; env layers always beat this)."""
    try:
        if paths.MODELS_YAML.exists():
            data = yaml.safe_load(paths.MODELS_YAML.read_text(encoding="utf-8")) or {}
            m = str(data.get("local_model") or "").strip()
            if m:
                return m
    except Exception:
        pass
    return ""


def _dotenv_defines(name: str) -> bool:
    """Does PROJECT_ROOT/.env define `name` (even if a process env var also does)?"""
    f = paths.PROJECT_ROOT / ".env"
    if not f.exists():
        return False
    try:
        for ln in f.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#") or "=" not in ln:
                continue
            if ln.split("=", 1)[0].strip() == name:
                return True
    except Exception:
        pass
    return False


def _precedence_report(data: dict, env_before: dict, c: Config) -> dict:
    """M14 — machine-verifiable provenance for every resolvable field:
    which of {default, config.yaml, models.yaml, .env, process-env,
    env-provider-key} actually WON."""
    def win(var: str, yaml_section: str | None, yaml_key: str,
            models_yaml: bool = False) -> str:
        if env_before.get(var):
            return "process-env"
        if _dotenv_defines(var):
            return ".env"
        if models_yaml and _models_yaml_override():
            return "models.yaml"
        if yaml_section is not None and (data.get(yaml_section) or {}).get(yaml_key) not in (None, ""):
            return "config.yaml"
        return "default"

    rep: dict = {}
    for var, section, key in (
            ("OLLAMA_MODEL", "ollama", "model"),
            ("OLLAMA_BASE_URL", "ollama", "base_url"),
            ("OLLAMA_EMBED_MODEL", "ollama", "embed_model"),
            ("CLOUD_LLM", "cloud", "llm"),
            ("CLOUD_BASE_URL", "cloud", "base_url"),
            ("EDGE_TTS_KEY", "voice", "edge_key"),
            ("LIVEKIT_URL", "livekit", "url"),
            ("LIVEKIT_API_KEY", "livekit", "api_key"),
            ("LIVEKIT_API_SECRET", "livekit", "api_secret"),
            ("BEE_USER_NAME", "user", "name"),
    ):
        rep[f"{section}.{key}"] = win(var, section, key, models_yaml=(section == "ollama" and key == "model"))
    # documented exception: explicit config.yaml key beats env provider keys
    if (data.get("cloud") or {}).get("api_key"):
        rep["cloud.api_key"] = "config.yaml (wins over env — documented exception)"
    elif _env_key_for(c.cloud.llm):
        rep["cloud.api_key"] = "env (provider-matched key)"
    else:
        rep["cloud.api_key"] = "default (empty)"
    rep["workspace"] = win("BEE_WORKSPACE", None, "")
    rep["engine"] = "settings.json (independent of Config — see matrix)"
    return rep


def load_config(path: str | Path | None = None) -> Config:
    import os as _os
    env_before = dict(_os.environ)          # process env BEFORE .env is loaded
    p = Path(path) if path else paths.CONFIG_YAML
    data: dict = {}
    if p.exists():
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    c = _build_from_yaml(data)
    override = _models_yaml_override()      # layer 3 (models.yaml)
    if override:
        c.ollama.model = override
    paths.ensure_core_dirs()
    _load_dotenv()                          # fills .env vars (process env wins)
    c = _apply_env(c)                       # layer 1+2 (highest)
    if (data.get("cloud") or {}).get("api_key") and _env_key_for(c.cloud.llm):
        # A plaintext key in the tracked, OneDrive-synced config.yaml shadows
        # the env key (documented exception) — so a rotated env key silently
        # stops working AND the stale secret persists in VCS + sync. Loud by
        # design: prefer env-only credentials.
        import logging as _logging
        _logging.getLogger("bee.config").warning(
            "config: cloud.api_key is set in config.yaml AND a provider env key "
            "exists — the file wins, so env rotation is silently ignored and a "
            "plaintext secret sits in a synced file. Prefer env-only credentials.")
    # workspace resolved LAST so .env's BEE_WORKSPACE also counts (M14)
    ws = os_environ_get("BEE_WORKSPACE")
    if ws:
        c.workspace = Path(ws).expanduser().resolve()
    else:
        c.workspace = paths.WORKSPACE
    c.workspace.mkdir(parents=True, exist_ok=True)
    c.precedence = _precedence_report(data, env_before, c)
    return c


def os_environ_get(name: str) -> str | None:
    import os
    return os.environ.get(name)
