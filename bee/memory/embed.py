"""Embeddings: Ollama (nomic-embed-text) via LLMClient. Lazy access.

Usage:  from .embed import embed_texts;  embed_texts(ctx, ["text1", ...])
"""
from __future__ import annotations


def embed_texts(ctx, texts: list[str]) -> list[list[float]]:
    """Returns embeddings for `texts`. Raises RuntimeError if Ollama/embedder unavailable."""
    if ctx.client is None:
        raise RuntimeError("no LLM client on context")
    out = ctx.client.embed(list(texts))
    if len(out) != len(texts):
        raise RuntimeError("embedder returned wrong batch size")
    return out


def embedder_available(ctx) -> bool:
    try:
        return bool(ctx.client and ctx.client._has_ollama())
    except Exception:
        return False
