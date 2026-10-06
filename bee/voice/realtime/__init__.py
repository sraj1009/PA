"""bee.voice.realtime — Phase 4 true-realtime voice.

Clean layering:
    engine.VoiceEngine   owns the state machine + timing (VAD, endpointing,
                         partials, barge-in, reconnect). No business logic.
    state / vad / transport / stt_stream / tts_stream — pure voice plumbing.
    kernel (injected)    owns tasks, permissions, memory, verification —
                         voice talks to it through the SAME AgentSession /
                         Task system as text.
    LiveKit (bee/livekit/transport.py) — a concrete transport behind the
    VoiceTransport protocol; the engine and kernel never import LiveKit.
"""
from .state import (VoiceEngineCfg, VoiceState, InvalidVoiceTransition,
                    TRANSITIONS, voice_transition)
from .vad import EnergyVAD, frame_rms
from .transport import (TransportError, VoiceTransport, MicTransport,
                        NullTransport)
from .stt_stream import SttError, SttTimeout, StreamingSTT, pcm_to_float
from .tts_stream import (FakeTTS, SentenceSplitter, StreamingTTS, TtsError)
from .engine import VoiceEngine

__all__ = [
    "VoiceState", "VoiceEngineCfg", "InvalidVoiceTransition", "TRANSITIONS",
    "voice_transition", "EnergyVAD", "frame_rms", "VoiceTransport",
    "MicTransport", "NullTransport", "TransportError", "StreamingSTT",
    "SttError", "SttTimeout", "pcm_to_float", "SentenceSplitter",
    "StreamingTTS", "TtsError", "FakeTTS", "VoiceEngine",
]
