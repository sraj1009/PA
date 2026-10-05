"""BEE hybrid brain: routing, privacy, verification, RAG, ML router.

The intelligence is deliberately split:
  deterministic (calculator, DSA library)  →  zero-hallucination floor
  retrieval (RAG over memory)              →  grounded context
  local LLM                                →  free, private, fast
  cloud LLM                                →  hard reasoning, on demand
  verifier + guard + privacy               →  safety rails around all of it
"""
