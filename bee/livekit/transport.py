"""LiveKit as a VoiceTransport (Phase 4).

Implements the transport protocol (bee/voice/realtime/transport.py) on top of a
LiveKit Cloud room:

    remote participant audio  ->  resampled 16 kHz s16le frames  ->  engine
    engine TTS audio (mp3)    ->  decoded + resampled            ->  AudioSource

The asyncio world runs in a background thread; the VoiceEngine only ever sees
the synchronous read_frame() / play() surface. This is what keeps LiveKit
behind the abstraction: the engine and the agent kernel never import LiveKit.

Honest status: this wrapper is NOT verified against a live room in this
environment (no LiveKit credentials in the test path). The locally exercised
transport is MicTransport (see bee/voice/realtime/transport.py); this file is
kept thin, lazy-imports livekit, and fails with TransportError when livekit is
missing or the room cannot be joined.
"""
from __future__ import annotations

import asyncio
import io
import logging
import queue
import threading
import time

from ..voice.realtime.transport import TransportError

log = logging.getLogger("bee.livekit.transport")

IN_RATE = 16000     # capture rate the engine expects (16 kHz mono s16le)


def _resample(s16: bytes, from_rate: int, to_rate: int) -> bytes:
    """Nearest-neighbor mono s16 resample (good enough for voice)."""
    if from_rate == to_rate or not s16:
        return s16
    import numpy as np
    x = np.frombuffer(s16, dtype="<i2").astype(np.float32)
    n_out = max(1, int(len(x) * to_rate / from_rate))
    idx = (np.arange(n_out) * from_rate / to_rate).astype(np.int64)
    idx = np.clip(idx, 0, len(x) - 1)
    return x[idx].astype("<i2").tobytes()


def _decode_audio(audio: bytes, to_rate: int = 24000) -> bytes | None:
    """Decode TTS bytes (mp3 or wav) to mono s16le @ to_rate via PyAV.

    PyAV ships with livekit-agents; if absent (or decode fails) returns None
    and the chunk is dropped (logged), never raising into the engine.
    """
    try:
        import av
    except ImportError:
        log.warning("PyAV not available — cannot decode TTS for the room")
        return None
    try:
        container = av.open(io.BytesIO(audio))
        resampler = av.AudioResampler(format="s16", layout="mono", rate=to_rate)
        out: list[bytes] = []
        for frame in container.decode(audio=0):
            for rf in resampler.resample(frame):
                out.append(rf.to_ndarray().tobytes())
            for rf in resampler.resample(None):
                out.append(rf.to_ndarray().tobytes())
        container.close()
        return b"".join(out) or None
    except Exception as e:
        log.warning("TTS decode failed (%s) — chunk dropped", str(e)[:120])
        return None


class LiveKitTransport:
    """A LiveKit room behind the VoiceTransport protocol."""

    name = "livekit"

    def __init__(self, cfg, room: str | None = None, identity: str = "bee-agent",
                 out_rate: int = 24000, join_timeout: float = 15.0):
        self.cfg = cfg
        from .agent import validate_room
        self.room_name = validate_room(room or getattr(cfg.livekit, "room", "") or "bee-pa")
        self.identity = identity
        self.out_rate = out_rate
        self.join_timeout = join_timeout
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._room = None
        self._src = None
        self._q: "queue.Queue[bytes]" = queue.Queue(maxsize=2000)
        self._connected = False
        self._err = ""

    # ------------------------------------------------------------ lifecycle
    def connect(self) -> None:
        try:
            import livekit.rtc as rtc  # noqa: F401
        except ImportError as e:
            raise TransportError(f"livekit not installed: {e}")
        lk = self.cfg.livekit
        if not (getattr(lk, "url", "") and getattr(lk, "api_key", "")
                and getattr(lk, "api_secret", "")):
            raise TransportError("LiveKit credentials missing — set LIVEKIT_URL / "
                                 "LIVEKIT_API_KEY / LIVEKIT_API_SECRET in .env")
        self._err = ""
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="BeeLiveKit")
        self._thread.start()
        t0 = time.time()
        while time.time() - t0 < self.join_timeout:
            if self._room is not None:
                break
            if self._err:
                raise TransportError(f"room join failed: {self._err}")
            time.sleep(0.05)
        if self._room is None and not self._err:
            raise TransportError(f"room join timed out after {self.join_timeout:.0f}s")

    def close(self) -> None:
        self._connected = False
        room, loop = self._room, self._loop
        self._room = None
        if room is not None and loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(self._disconnect(room), loop)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    def is_connected(self) -> bool:
        return self._connected and self._room is not None

    # --------------------------------------------------------------- pump in
    def read_frame(self, timeout: float = 0.2) -> bytes | None:
        if not self.is_connected():
            raise TransportError(f"not connected: {self._err or 'closed'}")
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    # --------------------------------------------------------------- pump out
    def play(self, audio: bytes) -> None:
        if not self.is_connected() or not audio:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._play_async(audio), self._loop)
        except Exception as e:
            log.debug("play failed: %s", e)

    async def _play_async(self, audio: bytes) -> None:
        import livekit.rtc as rtc
        pcm = _decode_audio(audio, self.out_rate)
        if not pcm or self._src is None:
            return
        n = len(pcm) // 2
        frame = rtc.AudioFrame(data=pcm, sample_rate=self.out_rate,
                               num_channels=1, samples_per_channel=n)
        try:
            self._src.capture_frame(frame)
        except Exception as e:
            log.debug("capture_frame failed: %s", e)

    # ------------------------------------------------------------- async core
    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            import livekit.rtc as rtc
            room = rtc.Room()
            self._room = room
            self._attach_listeners(room)
            token = _agent_token(self.cfg, self.room_name, self.identity)
            room.on("connected", lambda: self._on_connected())
            loop.run_until_complete(room.connect(self.cfg.livekit.url, token))
            self._connected = True
            loop.run_forever()
        except Exception as e:
            self._err = f"{type(e).__name__}: {e}"
            self._connected = False
            log.warning("livekit room thread ended: %s", self._err)
        finally:
            try:
                loop.stop()
            except Exception:
                pass

    def _on_connected(self) -> None:
        import livekit.rtc as rtc
        room = self._room
        self._src = rtc.AudioSource(sample_rate=self.out_rate, num_channels=1)

        async def _publish():
            track = rtc.LocalAudioTrack.create_audio_track("bee-tts", self._src)
            await room.local_participant.publish_track(track)
        asyncio.ensure_future(_publish())

    def _attach_listeners(self, room) -> None:
        def on_track(_ep, track, _pub):
            if track.kind != "audio":
                return

            def on_data(_p, data: bytes):
                try:
                    # data is s16le mono at the track's rate; resample to 16k
                    out = _resample(data, 48000, IN_RATE)
                    self._q.put_nowait(out)
                except queue.Full:
                    pass          # engine is slow/backed up — drop oldest by design
                except Exception:
                    pass
            track.on("data", on_data)

        room.on("track_subscribed", on_track)

    async def _disconnect(self, room) -> None:
        try:
            await room.disconnect()
        except Exception:
            pass


def _agent_token(cfg, room: str, identity: str) -> str:
    """Room JWT for the agent participant (room join + publish/subscribe)."""
    from datetime import timedelta

    from livekit.api import AccessToken, VideoGrants
    return (
        AccessToken(cfg.livekit.api_key, cfg.livekit.api_secret)
        .with_identity(identity)
        .with_ttl(timedelta(hours=2))
        .with_grants(VideoGrants(
            room_join=True, room=room,
            can_publish=True, can_subscribe=True,
            can_publish_data=True, can_publish_sources=["audio"]))
    ).to_jwt()
