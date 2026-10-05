"""BEE configuration: config.yaml + environment overrides.

Env overrides:
  OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_EMBED_MODEL
  CLOUD_LLM, OPENAI_API_KEY / OPENROUTER_API_KEY / ANTHROPIC_API_KEY, CLOUD_BASE_URL
  BEE_WORKSPACE
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


@dataclass
class SandboxCfg:
    enabled: bool = True
    image: str = "bee-sandbox:latest"
    gpu: bool = True
    workdir: str = "/workspace"
    timeout: int = 300
    max_output: int = 12000


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
    workspace: Path = paths.WORKSPACE

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
    """Pick the API key env var that matches the model's provider prefix.

    A blanket 'first key that exists' picks the WRONG key when several
    providers are configured (e.g. an OpenAI key sent to a Gemini model).
    """
    import os
    prefix = (llm or "").split("/", 1)[0].lower()
    by_prefix = {
        "gemini": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
        "google": ("GOOGLE_API_KEY",),
        "xai": ("XAI_API_KEY",),
        "x_ai": ("XAI_API_KEY",),
        "grok": ("XAI_API_KEY",),
        "openai": ("OPENAI_API_KEY",),
        "openrouter": ("OPENROUTER_API_KEY",),
        "anthropic": ("ANTHROPIC_API_KEY",),
    }
    for var in by_prefix.get(prefix, ()):
        if os.environ.get(var):
            return os.environ[var]
    # no prefix match — try all known provider vars (legacy behaviour)
    for var in ("OPENROUTER_API_KEY", "GOOGLE_API_KEY", "XAI_API_KEY",
                "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        if os.environ.get(var):
            return os.environ[var]
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


def load_config(path: str | Path | None = None) -> Config:
    p = Path(path) if path else paths.CONFIG_YAML
    data: dict = {}
    if p.exists():
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
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
    ws = os_environ_get("BEE_WORKSPACE")
    if ws:
        c.workspace = Path(ws).expanduser().resolve()
    else:
        c.workspace = paths.WORKSPACE
    c.workspace.mkdir(parents=True, exist_ok=True)
    paths.ensure_core_dirs()
    _load_dotenv()
    return _apply_env(c)


def os_environ_get(name: str) -> str | None:
    import os
    return os.environ.get(name)
