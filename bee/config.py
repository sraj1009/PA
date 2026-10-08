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
    # KV-cache context window. A big ctx (8192) suits an 8B that already fits in
    # VRAM, but for a 4B on a 4 GB card a leaner 4096 keeps the whole model + KV
    # cache on-GPU (fully accelerated, no CPU offload) — faster first token.
    num_ctx: int = 8192


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
    = the nightly gate idles (nothing to test)."""
    enabled: bool = True
    candidate: str = ""      # e.g. "bee4b-v2" — set when a new model is trained/pulled
    margin: int = 1          # candidate must score at least baseline + margin


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
