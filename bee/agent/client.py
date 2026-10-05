"""LLM client: LiteLLM primary, native Ollama HTTP fallback.

chat(name, messages, tools) -> normalized dict:
  {content: str|None, tool_calls: [{name, arguments(dict)}], usage: {prompt, completion}}
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import httpx

from ..config import Config

log = logging.getLogger("bee.llm")

try:
    import litellm
    litellm.suppress_debug_info = True
    HAS_LITELLM = True
except Exception:  # pragma: no cover
    litellm = None
    HAS_LITELLM = False


def _is_gemini3plus(model: str) -> bool:
    """True for Gemini 3+ (gemini-3-flash-preview, gemini-3.6-flash, flash-latest/preview).

    For these, Google (a) deprecates temperature/top_p/top_k and (b) warns that
    temperature < 1.0 can cause infinite loops / degraded reasoning, strongly
    recommending the default 1.0. So BEE sends NO sampling params for them: the
    persona + system prompt carry the "crisp/structured" guidance instead, and this
    is what silences litellm's per-call DeprecationWarning at the source.
    """
    m = (model or "").split("/", 1)[-1].lower()
    if "gemini" not in m:
        return False
    return ("gemini-3" in m) or ("flash-latest" in m) or ("flash-preview" in m)



class LLMError(Exception):
    def __init__(self, msg: str, kind: str = "server", retryable: bool | None = None):
        super().__init__(msg)
        self.kind = kind
        if retryable is not None:
            self.retryable = retryable

    @staticmethod
    def classify(msg: str) -> "LLMError":
        m = msg.lower()
        if "rate" in m or "limit" in m or "429" in m:
            return LLMError(msg, "rate_limit", True)
        if "overloaded" in m or "529" in m or "server is loading" in m or "busy" in m or "503" in m or "502" in m or "500" in m:
            return LLMError(msg, "overloaded", True)
        if "not found" in m and ("model" in m or "404" in m):
            return LLMError(msg, "model_not_found", False)
        if "connect" in m or "timeout" in m or "refused" in m or "unreachable" in m:
            return LLMError(msg, "connect", True)
        if "auth" in m or "401" in m or "403" in m or "api key" in m:
            return LLMError(msg, "auth", False)
        return LLMError(msg, "server", True)


class LLMClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        if not HAS_LITELLM:
            log.warning("litellm not installed — using native Ollama HTTP (local models only). `pip install litellm` for cloud.")

    # ------------------------------------------------------------------ chat
    def chat(self, name: str, messages: list[dict], tools: list | None = None,
             max_retries: int = 2, on_tool_call=None) -> dict:
        info = self.cfg.get_llm(name)
        model = self._model_ref(info)
        kwargs = dict(
            model=model,
            messages=self._norm_messages(messages),
            max_tokens=info["max_tokens"],
            timeout=info.get("timeout", 120),
        )
        # Gemini 3+ deprecates sampling params (and temp<1.0 degrades reasoning) —
        # omit them so Google's default 1.0 + the system prompt govern the style.
        if not _is_gemini3plus(model):
            kwargs["temperature"] = info["temperature"]
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if info["cloud"] and info.get("base_url"):
            kwargs["api_base"] = info["base_url"]
        if info["cloud"] and info.get("api_key"):
            kwargs["api_key"] = info["api_key"]
        if not info["cloud"] and HAS_LITELLM and self.cfg.ollama.keep_alive:
            # release the local model from RAM/VRAM after keep_alive (memory saver)
            kwargs["extra_body"] = {"keep_alive": self.cfg.ollama.keep_alive}

        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                if HAS_LITELLM:
                    resp = litellm.completion(**kwargs)
                    return self._norm_litellm(resp, on_tool_call)
                if info["cloud"]:
                    raise LLMError("cloud requested but litellm not installed", "server", False)
                return self._native_ollama(info, messages, tools, on_tool_call)
            except LLMError as e:
                last_err = e
                if not e.retryable or attempt >= max_retries:
                    raise
                time.sleep(1.5 * (2 ** attempt))
            except Exception as e:  # classify unknowns
                err = LLMError.classify(str(e))
                last_err = err
                if not err.retryable or attempt >= max_retries:
                    raise LLMError(str(e), err.kind, err.retryable) from e
                time.sleep(1.5 * (2 ** attempt))
        raise LLMError(str(last_err), "server")  # pragma: no cover

    # ---------------------------------------------------------------- embed
    def embed(self, texts: list[str]) -> list[list[float]]:
        texts = [t if t else " " for t in texts]
        if not self._has_ollama():
            raise LLMError("Ollama not reachable for embeddings", "connect")
        if HAS_LITELLM:
            try:
                resp = litellm.embedding(model=f"ollama_chat/{self.cfg.ollama.embed_model}", input=texts)
                return [d["embedding"] for d in resp["data"]]
            except Exception:
                pass
        url = f"{self.cfg.ollama.base_url}/api/embeddings"
        out = []
        for t in texts:
            r = httpx.post(url, json={"model": self.cfg.ollama.embed_model, "prompt": t[:8000]}, timeout=60)
            r.raise_for_status()
            out.append(r.json()["embedding"])
        return out

    def models_list(self) -> list[str]:
        try:
            r = httpx.get(f"{self.cfg.ollama.base_url}/api/tags", timeout=5)
            return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            return []

    # ------------------------------------------------------------- internals
    def _model_ref(self, info: dict) -> str:
        if info["cloud"]:
            return info["name"]
        return f"ollama_chat/{info['name']}" if HAS_LITELLM else info["name"]

    @staticmethod
    def _norm_messages(messages: list[dict]) -> list[dict]:
        msgs = []
        for m in messages:
            mm = dict(m)
            role = mm.get("role")
            if role == "tool":
                mm["role"] = "tool"
                mm["tool_call_id"] = mm.get("tool_call_id", "call_0")
                mm["content"] = mm.get("content", "")
            elif role in ("assistant", "user", "system"):
                mm.pop("tool_calls", None) if role != "assistant" else None
                if role == "assistant" and not mm.get("content") and not mm.get("tool_calls"):
                    mm["content"] = "..."
            msgs.append(mm)
        return msgs

    @staticmethod
    def _norm_litellm(resp, on_tool_call) -> dict:
        ch = resp.choices[0].message
        tcs = []
        for tc in (ch.tool_calls or []):
            fn = tc.function or {}
            args = fn.get("arguments") or "{}"
            try:
                args = json.loads(args) if isinstance(args, str) else args
            except Exception:
                args = {"_raw": args}
            tcs.append({"id": tc.id, "name": fn.get("name", ""), "arguments": args})
            if on_tool_call:
                on_tool_call(fn.get("name", ""), args)
        usage = getattr(resp, "usage", None)
        return {
            "content": ch.content or None,
            "tool_calls": tcs,
            "usage": {"prompt": getattr(usage, "prompt_tokens", 0), "completion": getattr(usage, "completion_tokens", 0)},
        }

    def _native_ollama(self, info: dict, messages: list[dict], tools: list | None, on_tool_call) -> dict:
        payload = {
            "model": info["name"],
            "messages": self._norm_messages(messages),
            "stream": False,
            # num_ctx is configurable (cfg.ollama.num_ctx, default 8192). A big
            # ctx builds a large KV cache; on a 4 GB card a 4B model wants ~4096
            # to stay fully on-GPU (no CPU offload) and give a fast first token.
            "options": {"num_ctx": int(info.get("num_ctx", 8192)), "num_predict": info["max_tokens"],
                        "temperature": info["temperature"]},
        }
        if self.cfg.ollama.keep_alive:
            payload["keep_alive"] = self.cfg.ollama.keep_alive  # unload after last use
        if tools:
            payload["tools"] = tools
        r = httpx.post(f"{info['base_url']}/api/chat", json=payload, timeout=info.get("timeout", 300))
        r.raise_for_status()
        data = r.json()
        m = data.get("message", {})
        tcs = []
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {})
            tcs.append({"id": f"call_{len(tcs)}", "name": fn.get("name", ""), "arguments": fn.get("arguments", {})})
            if on_tool_call:
                on_tool_call(fn.get("name", ""), fn.get("arguments", {}))
        return {"content": m.get("content") or None, "tool_calls": tcs,
                "usage": {"prompt": data.get("prompt_eval_count", 0), "completion": data.get("eval_count", 0)}}

    def _has_ollama(self) -> bool:
        try:
            r = httpx.get(f"{self.cfg.ollama.base_url}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False
