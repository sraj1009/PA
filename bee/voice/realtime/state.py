"""Voice state machine (Phase 4).

The VOICE layer owns this state machine — and nothing else. Business logic
(tasks, permissions, memory, verification) lives in the kernel; the engine
just moves audio into tasks and tasks' answers back into speech.

    IDLE ──wake/always-on──> LISTENING
    LISTENING ──endpoint──> PROCESSING ──stt final──> THINKING
    THINKING ──first token──> SPEAKING ──tts done──> LISTENING (or IDLE)
    SPEAKING/THINKING ──barge-in──> INTERRUPTED ──drain──> LISTENING
    any ──failure──> ERROR ──reconnect ok──> IDLE
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class VoiceState(str, Enum):
    IDLE = "IDLE"                 # listening for wake (or parked)
    LISTENING = "LISTENING"       # user is being heard; interim transcripts flow
    PROCESSING = "PROCESSING"     # utterance ended; final STT in flight
    THINKING = "THINKING"         # kernel task running; no audio out yet
    SPEAKING = "SPEAKING"         # TTS streaming to the speaker
    INTERRUPTED = "INTERRUPTED"   # barge-in: TTS stopped, task cancelled
    ERROR = "ERROR"               # mic/network/provider failure; recovering


TRANSITIONS: dict[VoiceState, set[VoiceState]] = {
    VoiceState.IDLE: {VoiceState.LISTENING, VoiceState.ERROR},
    VoiceState.LISTENING: {VoiceState.PROCESSING, VoiceState.THINKING,
                           VoiceState.IDLE, VoiceState.ERROR},
    VoiceState.PROCESSING: {VoiceState.THINKING, VoiceState.LISTENING,
                            VoiceState.IDLE, VoiceState.ERROR},
    VoiceState.THINKING: {VoiceState.SPEAKING, VoiceState.INTERRUPTED,
                          VoiceState.LISTENING, VoiceState.IDLE, VoiceState.ERROR},
    VoiceState.SPEAKING: {VoiceState.LISTENING, VoiceState.IDLE,
                          VoiceState.INTERRUPTED, VoiceState.ERROR},
    VoiceState.INTERRUPTED: {VoiceState.LISTENING, VoiceState.IDLE, VoiceState.ERROR},
    VoiceState.ERROR: {VoiceState.IDLE, VoiceState.LISTENING},
}


class InvalidVoiceTransition(Exception):
    pass


def voice_transition(cur: VoiceState, target: VoiceState) -> None:
    if target != cur and target not in TRANSITIONS.get(cur, set()):
        raise InvalidVoiceTransition(f"{cur.value} -> {target.value}")


@dataclass
class VoiceEngineCfg:
    """Engine tunables (defaults mirror config.yaml voice: rt_* fields)."""
    wake_word: str = "bee"
    always_on: bool = False            # False = wake-gated; True = always listening
    barge_in: bool = True              # user speech interrupts TTS + task
    silence_ms: int = 700              # endpointing silence
    max_utterance_ms: int = 15000      # force-finalize long utterances
    partial_stt: bool = True
    partial_every_ms: int = 900
    partial_min_growth: int = 32000    # bytes of new audio before a new partial
    conversation: bool = True          # stay LISTENING after an answer
    wake_ack: bool = True              # speak "Yes?" after the wake word
    stt_timeout: float = 30.0
    tts_timeout: float = 20.0
    reconnect_max: float = 30.0
    frame_ms: int = 100                # expected input frame duration
    sample_rate: int = 16000
    barge_min_speech_ms: int = 250     # sustained speech needed to barge in
    echo_gate: float = 2.0             # while TTS plays, user speech must be
                                       # echo_gate x the normal VAD threshold
                                       # (BEE's own voice stays below it)
    listen_timeout_ms: int = 6000      # wake-gated: return to IDLE if the user
                                       # was woken but never speaks
    wake_max_ms: int = 2500            # max capture window for a wake utterance
    max_reconnect_attempts: int = 0    # 0 = unlimited (run() gives up only at N)
    stop_words: tuple = ("stop", "cancel", "abort", "stop it", "never mind",
                         "halt", "enough", "silence")
    ack_words: tuple = ("done", "ok", "okay", "fine", "thanks", "thank you",
                        "good", "yes", "all set", "nice")
    session_id: str = "voice"
    history: list = field(default_factory=list)   # state trace (for tests/UX)
