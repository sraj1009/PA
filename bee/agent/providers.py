"""Provider abstraction — the single source of truth for LLM providers.

The rest of the application must NOT inspect os.environ for API keys itself;
it asks the ProviderRegistry. This module centralizes:
  - which provider kinds exist (local Ollama, Gemini, OpenAI, Anthropic,
    DeepSeek, OpenRouter, xAI)
  - which env var(s) credential each kind
  - which LiteLLM prefix routes each kind
  - whether the configured cloud model is actually usable right now
    (cloud availability = real configured provider, not a hard-coded guess)

Execution still goes through LLMClient (LiteLLM primary, native Ollama
fallback); providers are about DETECTION + CONFIG + HEALTH, not transports.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class ProviderKind(str, Enum):
    OLLAMA = "ollama"        # local models via Ollama (no key)
    GEMINI = "gemini"
    GOOGLE = "google"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    OPENROUTER = "openrouter"
    XAI = "xai"


# kind -> (env vars that credential it, litellm prefix)
# Aliases in model names (google/gemini, grok -> xai, x_ai -> xai) resolve here.
PROVIDERS: dict[ProviderKind, tuple[tuple[str, ...], str]] = {
    ProviderKind.OLLAMA:     ((), "ollama_chat"),
    ProviderKind.GEMINI:     (("GOOGLE_API_KEY", "GEMINI_API_KEY"), "gemini"),
    ProviderKind.GOOGLE:     (("GOOGLE_API_KEY", "GEMINI_API_KEY"), "google"),
    ProviderKind.OPENAI:     (("OPENAI_API_KEY",), "openai"),
    ProviderKind.ANTHROPIC:  (("ANTHROPIC_API_KEY",), "anthropic"),
    ProviderKind.DEEPSEEK:   (("DEEPSEEK_API_KEY",), "deepseek"),
    ProviderKind.OPENROUTER: (("OPENROUTER_API_KEY",), "openrouter"),
    ProviderKind.XAI:        (("XAI_API_KEY",), "xai"),
}

# model-name prefix -> kind (extra aliases first, then canonical)
_PREFIX_ALIASES = {
    "grok": ProviderKind.XAI,
    "x_ai": ProviderKind.XAI,
}


def kind_for_model(model_ref: str) -> ProviderKind | None:
    """Map a model reference ('gemini/gemini-3.6-flash', 'bee4b', 'openai/gpt-4o-mini')
    to its provider kind, or None when it is a local (Ollama) model name."""
    name = (model_ref or "").strip().lower()
    if not name:
        return None
    prefix = name.split("/", 1)[0] if "/" in name else ""
    if not prefix:
        return None  # bare name = local Ollama model
    if prefix in _PREFIX_ALIASES:
        return _PREFIX_ALIASES[prefix]
    try:
        return ProviderKind(prefix)
    except ValueError:
        return None


def env_vars_for(kind: ProviderKind) -> tuple[str, ...]:
    return PROVIDERS[kind][0]


def key_for(kind: ProviderKind) -> str:
    """The first PRESENT env key for a provider kind ("" = none).
    Values are never logged; callers must treat them as secret."""
    for var in env_vars_for(kind):
        v = os.environ.get(var)
        if v:
            return v
    return ""


@dataclass(frozen=True)
class ProviderConfig:
    """One provider as configured for this deployment."""
    kind: ProviderKind
    model: str                      # model reference, e.g. "gemini/gemini-3.6-flash"
    base_url: str = ""
    configured_via: str = ""        # "" | "config" | "env"


@dataclass(frozen=True)
class ProviderHealth:
    kind: ProviderKind
    model: str
    available: bool
    reason: str = ""

    def __str__(self) -> str:
        state = "UP" if self.available else "down"
        return f"{self.kind.value} {self.model}: {state} ({self.reason})"


class Provider:
    """A concrete, configured provider (config + live key check)."""

    def __init__(self, cfg: ProviderConfig):
        self.cfg = cfg

    @property
    def name(self) -> str:
        return self.cfg.kind.value

    def has_credential(self) -> bool:
        if self.cfg.kind == ProviderKind.OLLAMA:
            return True  # local: no key needed
        return bool(self.cfg.configured_via) or bool(key_for(self.cfg.kind))

    def health(self, ollama_up: bool | None = None) -> ProviderHealth:
        """Cheap, no-network availability probe (key presence / ollama reachability)."""
        if self.cfg.kind == ProviderKind.OLLAMA:
            if ollama_up is None:
                try:
                    import httpx
                    ollama_up = httpx.get(
                        os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/tags",
                        timeout=3).status_code == 200
                except Exception:
                    ollama_up = False
            return ProviderHealth(self.cfg.kind, self.cfg.model, ollama_up,
                                  "ollama reachable" if ollama_up else "ollama not reachable")
        if not self.has_credential():
            vars_ = ", ".join(env_vars_for(self.cfg.kind)) or "n/a"
            return ProviderHealth(self.cfg.kind, self.cfg.model, False,
                                  f"no key ({vars_} not set)")
        return ProviderHealth(self.cfg.kind, self.cfg.model, True, "key configured")


class ProviderRegistry:
    """All providers known to this deployment (built from Config, not guesses)."""

    def __init__(self, providers: list[Provider]):
        self.providers = {p.cfg.kind: p for p in providers}
        self.cloud: Provider | None = next(
            (p for p in providers if p.cfg.kind != ProviderKind.OLLAMA and p.cfg.model), None)

    # ------------------------------------------------------------- factories
    @classmethod
    def from_config(cls, cfg) -> "ProviderRegistry":
        provs: list[Provider] = [
            Provider(ProviderConfig(ProviderKind.OLLAMA, cfg.ollama.model,
                                    cfg.ollama.base_url, "env"))
        ]
        if cfg.cloud.llm:
            kind = kind_for_model(cfg.cloud.llm) or ProviderKind.GEMINI
            via = "config" if cfg.cloud.api_key else ("env" if key_for(kind) else "")
            provs.append(Provider(ProviderConfig(kind, cfg.cloud.llm,
                                                 cfg.cloud.base_url, via)))
        return cls(provs)

    # ---------------------------------------------------------------- lookups
    def for_model(self, model_ref: str) -> Provider | None:
        kind = kind_for_model(model_ref)
        if kind is None:
            return self.providers.get(ProviderKind.OLLAMA)
        return self.providers.get(kind)

    def cloud_available(self, cfg) -> tuple[bool, str]:
        """Does the CONFIGURED cloud model have working credentials right now?

        Reflects the actual provider of cfg.cloud.llm (provider-matched key,
        or an explicit config key). The legacy fallback (some other cloud
        key present) is kept so existing deployments don't silently lose
        escalation — the reason string makes the source explicit.
        """
        if not (cfg.cloud.enabled and cfg.cloud.llm):
            return False, "cloud not configured (cloud.llm empty or disabled)"
        kind = kind_for_model(cfg.cloud.llm) or ProviderKind.GEMINI
        if cfg.cloud.api_key:
            return True, f"{kind.value}: explicit api_key in config"
        if key_for(kind):
            vars_ = env_vars_for(kind)
            present = next(v for v in vars_ if os.environ.get(v))
            return True, f"{kind.value}: {present} present"
        for k in ProviderKind:
            if k == ProviderKind.OLLAMA:
                continue
            if key_for(k):
                return True, f"legacy: {k.value} key present (not matched to {kind.value})"
        return False, f"{kind.value}: no API key found (set one of {', '.join(env_vars_for(kind))})"

    def health(self) -> list[ProviderHealth]:
        out = []
        ollama_up: bool | None = None
        for p in self.providers.values():
            h = p.health(ollama_up)
            if p.cfg.kind == ProviderKind.OLLAMA:
                ollama_up = h.available
            out.append(h)
        return out

    def summary(self) -> str:
        return "; ".join(str(h) for h in self.health())


# ------------------------------------------------------------- compat facade
def env_key_for(llm: str) -> str:
    """Provider-matched env key for a model reference ("" if none).
    Kept as the single implementation — bee.config delegates here."""
    kind = kind_for_model(llm)
    if kind is None:
        return ""
    return key_for(kind)


def cloud_available(cfg) -> tuple[bool, str]:
    return ProviderRegistry.from_config(cfg).cloud_available(cfg)
