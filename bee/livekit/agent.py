"""LiveKit agent — BEE's live realtime voice (free-tier LiveKit Cloud).

    python -m bee.cli livekit [--room bee-pa]

The agent joins the room over WebRTC (LiveKit Cloud free tier, ~1000
agent-minutes/month). Everything intelligence- and audio-model-wise stays
LOCAL and free, reusing BEE's existing stack:

  mic -> silero VAD (local, plugin) -> BeeSTT (faster-whisper, local)
      -> BEE brain (full pipeline: fast paths, engine routing incl.
         cloud-first, tools + guard, persona, memory)
      -> BeeTTS (edge-tts neural MP3 / pyttsx3 WAV fallback) -> speakers

Secrets: LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET (from .env).
Guard runs in 'unattended' mode for the live session — dangerous actions are
auto-denied instead of blocking the call on an input() prompt.
"""
from __future__ import annotations

import asyncio
import logging
import re
import tempfile
import uuid
from pathlib import Path

from . import state as st

log = logging.getLogger("bee.livekit")

_ROOM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}$")
TTS_RATE = 24000  # frames emitted to the room at 24 kHz mono s16


# ------------------------------------------------------------------ tokens
def make_token(cfg, room: str, identity: str = "bee-web") -> str:
    """JWT room token for a human participant (Web UI join).

    Modern LiveKit SDK uses a fluent builder: AccessToken(key, secret) then
    .with_identity(...).with_ttl(...).with_grants(VideoGrants(...)).
    """
    from datetime import timedelta

    from livekit.api import AccessToken, VideoGrants
    tok = (
        AccessToken(cfg.livekit.api_key, cfg.livekit.api_secret)
        .with_identity(identity)
        .with_ttl(timedelta(hours=2))
        .with_grants(VideoGrants(
            room_join=True, room=room,
            can_publish=True, can_subscribe=True,
            can_publish_data=True, can_publish_sources=["audio"]))
    )
    return tok.to_jwt()


def validate_room(room: str) -> str:
    room = (room or "").strip()
    if not _ROOM_RE.match(room):
        raise ValueError(f"invalid room name: {room!r} (use letters/digits/-, max 64)")
    return room


# ------------------------------------------------------------------ brain
def _build_brain(cfg):
    """Returns (brain_fn, engine_label). brain_fn(task) -> reply text.

    Audit item 1: the LiveKit worker now runs through the SAME AgentKernel
    as every other surface — capability gate, task state, receipts,
    verification, telemetry. Unattended by construction: the approver
    auto-denies, so an 'ask' fails closed (no human is at this process).
    """
    from ..agent import engines
    from ..agent.context import create_context
    from ..kernel import AgentKernel

    engine = engines.load_engine()

    # guard_mode passed EXPLICITLY (was: cfg.guard.mode = "unattended", which
    # mutated the shared config object for anything else holding it)
    ctx = create_context(cfg, guard_mode="unattended")
    if getattr(ctx, "kernel", None) is None:
        kernel = AgentKernel(ctx, approver=lambda tool, args, reason: False)
        ctx.kernel = kernel
    else:
        kernel = ctx.kernel

    def brain(task: str) -> str:
        task = (task or "").strip()
        if not task:
            return ""
        st.set_state("thinking", last_user=task, engine=engine)
        try:
            res = kernel.run(task, session_id="livekit")
            out = (res.output or "").strip()
            if not res.ok and not out:
                out = f"Sorry, that didn't work. {res.error or ''}".strip()
        except Exception as e:
            log.exception("live brain failed")
            out = f"Sorry, something failed: {e}"
        st.set_state("speaking", last_reply=out)
        return out[:1200]

    return brain, engine


# ------------------------------------------------------------------ STT
def make_stt(cfg):
    """faster-whisper STT adapter (local, reuses BEE's voice model + device logic)."""
    import numpy as np

    from livekit.agents.stt import STT, STTCapabilities, SpeechData, SpeechEvent, SpeechEventType
    from livekit import rtc

    from ..voice import transcribe as bee_stt

    class BeeSTT(STT):
        @property
        def model(self) -> str:
            return f"faster-whisper {cfg.voice.model}"

        @property
        def provider(self) -> str:
            return "bee-local"

        def __init__(self):
            super().__init__(capabilities=STTCapabilities(
                streaming=False, interim_results=False, offline_recognize=True))

        async def _recognize_impl(self, buffer, *, language, conn_options):
            frames = buffer if isinstance(buffer, list) else [buffer]
            pcm = np.frombuffer(b"".join(f.data for f in frames), dtype=np.int16)
            sr = int(frames[0].sample_rate)
            if len(pcm) < max(1600, sr // 10):  # <100 ms — not speech
                return SpeechEvent(type=SpeechEventType.FINAL_TRANSCRIPT,
                                   alternatives=[SpeechData(text="")])
            audio = pcm.astype(np.float32) / 32768.0
            text = await asyncio.to_thread(
                bee_stt.transcribe_audio, audio, sr,
                cfg.voice.model, cfg.voice.device, cfg.voice.compute_type,
                cfg.livekit.stt_lang or "en")
            return SpeechEvent(type=SpeechEventType.FINAL_TRANSCRIPT,
                               alternatives=[SpeechData(text=(text or "").strip())])

    return BeeSTT()


# ------------------------------------------------------------------ TTS
def _edge_tts_mp3(text: str, voice: str, rate: int) -> bytes:
    import asyncio

    import edge_tts
    from ..voice.speak import _edge_rate_pct

    out = Path(tempfile.gettempdir()) / f"bee_livekit_{uuid.uuid4().hex}.mp3"

    async def gen():
        await edge_tts.Communicate(text, voice, rate=_edge_rate_pct(rate)).save(str(out))

    asyncio.run(gen())
    try:
        return out.read_bytes()
    finally:
        out.unlink(missing_ok=True)


def _pyttsx3_wav(text: str, voice: str, rate: int) -> bytes:
    import pyttsx3
    from ..voice.speak import _pick_py_voice

    # pyttsx3.save_to_file to a BytesIO silently yields 0 bytes — use a real
    # temp path (found by live-room verification: the greeting produced no
    # audio with the BytesIO form).
    out = Path(tempfile.gettempdir()) / f"bee_pyttsx3_{uuid.uuid4().hex}.wav"
    eng = pyttsx3.init()
    try:
        if voice:
            _pick_py_voice(eng, voice)
        eng.setProperty("rate", rate)
        eng.save_to_file(text, str(out))
        eng.runAndWait()
        return out.read_bytes() if out.exists() else b""
    finally:
        try:
            eng.stop()
        except Exception:
            pass
        try:
            out.unlink(missing_ok=True)
        except Exception:
            pass


def make_tts(cfg):
    """edge-tts (neural MP3, free) with pyttsx3 (offline WAV) fallback.
    Audio is decoded by the LiveKit framework (PyAV) — we just push bytes."""
    from livekit.agents.tts import TTS, TTSCapabilities, ChunkedStream

    voice = getattr(cfg.voice, "tts_voice", "") or "en-US-AndrewMultilingualNeural"
    rate = int(getattr(cfg.voice, "tts_rate", 190) or 190)

    class BeeTTS(TTS):
        @property
        def model(self) -> str:
            return f"bee-tts ({voice})"

        @property
        def provider(self) -> str:
            return "edge-tts|pyttsx3"

        def __init__(self):
            super().__init__(capabilities=TTSCapabilities(streaming=False),
                             sample_rate=TTS_RATE, num_channels=1)

        # NOTE: synthesize MUST be sync and return the ChunkedStream —
        # the framework drives _run() itself. An `async def synthesize`
        # hands back a coroutine, which crashes inside the SDK's
        # `async with ...synthesize(...)` (third live-room crash class).
        def synthesize(self, text, *, conn_options):
            text = (text or "").strip()
            if not text:
                raise ValueError("empty TTS text")

            class _Stream(ChunkedStream):
                async def _run(self, output_emitter) -> None:
                    try:
                        audio = await asyncio.to_thread(_edge_tts_mp3, text, voice, rate)
                        mime = "audio/mp3"
                    except Exception as e:
                        log.info("edge-tts failed (%s) — pyttsx3 fallback", str(e)[:120])
                        audio = await asyncio.to_thread(_pyttsx3_wav, text, voice, rate)
                        mime = "audio/wav"
                    if not audio:
                        raise RuntimeError("TTS produced no audio")
                    output_emitter.initialize(
                        request_id=uuid.uuid4().hex, sample_rate=TTS_RATE,
                        num_channels=1, mime_type=mime, frame_size_ms=20)
                    output_emitter.push(audio)

            return _Stream(tts=self, input_text=text, conn_options=conn_options)

    return BeeTTS()


# ------------------------------------------------------------------ run
def available() -> tuple[bool, str]:
    try:
        import livekit.agents  # noqa: F401
        import livekit.api  # noqa: F401
        return True, ""
    except ImportError as e:
        return False, (f"{e} — install with: pip install -r requirements-livekit.txt")


def run(cfg, room: str | None = None) -> int:
    ok, err = available()
    if not ok:
        print(f"[livekit] {err}")
        return 1
    lk = cfg.livekit
    if not (lk.url and lk.api_key and lk.api_secret):
        print("[livekit] missing credentials — set LIVEKIT_URL / LIVEKIT_API_KEY / "
              "LIVEKIT_API_SECRET in .env")
        return 1
    try:
        room = validate_room(room or lk.room or "bee-pa")
    except ValueError as e:
        print(f"[livekit] {e}")
        return 1

    from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli

    brain, engine = _build_brain(cfg)
    user = cfg.user.name or "Boss"
    stt = make_stt(cfg)
    tts = make_tts(cfg)
    # VAD + streaming wrapper are built HERE (worker main thread): livekit
    # plugins register on import and refuse to load inside the job task
    # thread, so importing silero inside entrypoint() crashes every job.
    from livekit.agents import stt as _stt
    from livekit.plugins import silero as _silero
    stream_stt = _stt.StreamAdapter(stt=stt, vad=_silero.VAD.load())

    class BeeAgent(Agent):
        def __init__(self):
            super().__init__(instructions=(
                "You are BEE, a sharp, efficient personal assistant. "
                f"Serve {user}. Keep spoken answers short and natural — one to three "
                "sentences unless asked for detail. Never read markdown or code aloud."
            ))

        async def on_enter(self) -> None:
            # livekit-agents 1.4.6: callbacks take no session arg — the live
            # session hangs off self.session.
            await self.session.say(f"Welcome home, {user}. I'm BEE — what are we working on?")

        async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
            content = getattr(new_message, "content", "")
            if isinstance(content, list):
                content = " ".join(
                    getattr(p, "text", "") for p in content
                    if getattr(p, "text", "")).strip()
            text = (content if isinstance(content, str) else str(content)).strip()
            reply = await asyncio.to_thread(brain, text)
            if reply:
                st.set_state("listening")
                await self.session.say(reply)

    async def entrypoint(ctx: JobContext) -> None:
        # the worker runs in its own process (spawned by livekit's CLI), so it
        # never passes through bee.cli.main() — configure logging here too
        from ..cli import setup_logging
        setup_logging()
        agent = BeeAgent()
        await ctx.connect()
        # livekit-agents 1.4.6: the initial agent goes to start(), not the
        # constructor (verified against the installed SDK signature; the old
        # start_agent= kwarg crashed every dispatched job — found by a live
        # room dispatch, which no mocked test could reach). stream_stt is the
        # silero-wrapped BeeSTT built in run() on the main thread.
        await AgentSession(stt=stream_stt, tts=tts).start(agent=agent, room=ctx.room)

    opts = WorkerOptions(entrypoint_fnc=entrypoint)
    opts.ws_url = lk.url
    opts.api_key = lk.api_key
    opts.api_secret = lk.api_secret
    opts.agent_name = "bee"
    opts.num_idle_processes = 0  # no prewarm process: save RAM on this box

    st.set_state("idle", engine=engine)
    print(f"\n  LIVEKIT AGENT — room '{room}' (engine: {engine}, STT: faster-whisper "
          f"{cfg.voice.model}, TTS: edge-tts|pyttsx3)")
    print("  join:  web UI  http://127.0.0.1:8787  ->  Live Voice  ->  Join")
    print("  Ctrl-C stops the agent.\n")
    # livekit's cli.run_app() re-parses sys.argv with its own Typer app. BEE's
    # own argv ('livekit --room ...') would be misread as an unknown subcommand.
    # Point it at the 'start' (local worker) subcommand instead — the server
    # already carries ws_url / api_key / api_secret from the WorkerOptions above.
    import sys
    _orig_argv = sys.argv
    sys.argv = [_orig_argv[0], "start"]
    try:
        cli.run_app(opts)
    except KeyboardInterrupt:
        pass
    finally:
        sys.argv = _orig_argv
    st.set_state("idle")
    return 0
