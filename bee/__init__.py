"""BEE — a local-first, self-improving, general-purpose personal agent.

Stack (see README.md):
- Local LLM via Ollama (default Qwen3) with optional hybrid cloud escalation
- Tool-driven loop: files, shell, sandbox, web, code, memory, skills, planning
- Voice in (faster-whisper) / voice out (pyttsx3 / edge-tts)
- ML/DL/DSA capability track (sandbox image + skills + DSA library + benchmarks)
"""

__version__ = "1.0.0"
NAME = "BEE"
