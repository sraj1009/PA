"""Double-clap acoustic trigger (ported from Super JARVIS / Hector).

    python -m bee.cli clap

Listens on the microphone for a double clap and runs the configured action
(config.yaml `clap.action`):

  - `welcome` (default): the Welcome Home protocol (bee/commands/welcome.py)
  - `voice`: record one utterance, transcribe, and run it as a normal task

Detection (same tuned constants as the reference implementation):
  - hysteresis retrigger: audio must drop below threshold * retrigger_ratio
    before a new spike can register (sustained loud audio != many claps)
  - 1.5s warmup so the mic hardware + noise floor can calibrate
  - adaptive noise floor (alpha 0.992, floor min 0.001, quiet-gate 2.2x) so
    claps themselves never inflate the baseline
  - clap = RMS >= max(noise_floor * spike_ratio, min_rms)
  - double = two claps 60-400 ms apart; 1.5s cooldown after a trigger
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

log = logging.getLogger("bee.voice.clap")


class ClapDetector:
    """Listens on the microphone for double-clap acoustic signatures."""

    def __init__(self, on_double_clap: Callable[[], None], *,
                 sample_rate: int = 44100, block_ms: int = 40,
                 spike_ratio: float = 7.0, min_rms: float = 0.012,
                 min_double_gap_s: float = 0.06, max_double_gap_s: float = 0.40,
                 cooldown_s: float = 1.5, retrigger_ratio: float = 0.55,
                 warmup_s: float = 1.5) -> None:
        self.on_double_clap = on_double_clap
        self.sample_rate = sample_rate
        self.block_ms = block_ms
        self.spike_ratio = spike_ratio
        self.min_rms = min_rms
        self.min_double_gap_s = min_double_gap_s
        self.max_double_gap_s = max_double_gap_s
        self.cooldown_s = cooldown_s
        self.retrigger_ratio = retrigger_ratio
        self.warmup_s = warmup_s

        # adaptive noise floor
        self.noise_floor = 0.01
        self.noise_floor_alpha = 0.992
        self._noise_floor_min = 0.001
        self._quiet_gate_mult = 2.2

        # detection state
        self._spike_armed = True
        self.first_clap_time: Optional[float] = None
        self.last_trigger_time = 0.0
        self._start_time: Optional[float] = None

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def is_running(self) -> bool:
        return self._running

    def _block_samples(self) -> int:
        return max(int(self.sample_rate * self.block_ms / 1000), 1)

    def _audio_callback(self, indata, frames: int, time_info: object, status: object) -> None:
        if not self._running:
            return
        now = time.monotonic()
        if self._start_time is not None and (now - self._start_time) < self.warmup_s:
            return  # let hardware + noise floor settle

        import numpy as np
        data = indata[:, 0] if indata.ndim > 1 else indata.ravel()
        rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))

        threshold = max(self.noise_floor * self.spike_ratio, self.min_rms)
        retrigger_level = threshold * self.retrigger_ratio

        quiet_gate = self.noise_floor * self._quiet_gate_mult
        if rms < quiet_gate:
            self.noise_floor = (self.noise_floor_alpha * self.noise_floor
                                + (1.0 - self.noise_floor_alpha) * rms)
            self.noise_floor = max(self._noise_floor_min, self.noise_floor)

        if rms < retrigger_level:
            self._spike_armed = True

        if (self._spike_armed and rms >= threshold
                and (now - self.last_trigger_time) >= self.cooldown_s):
            self._spike_armed = False
            if self.first_clap_time is None:
                self.first_clap_time = now
            else:
                gap = now - self.first_clap_time
                if gap < self.min_double_gap_s:
                    pass  # same clap's reverb
                elif gap <= self.max_double_gap_s:
                    self.first_clap_time = None
                    self.last_trigger_time = now
                    log.info("double clap (gap=%.3fs rms=%.5f floor=%.5f thr=%.5f)",
                             gap, rms, self.noise_floor, threshold)
                    try:
                        self.on_double_clap()
                    except Exception as exc:
                        log.error("clap callback failed: %s", exc)
                else:
                    self.first_clap_time = now  # gap too large — new first clap
        elif self.first_clap_time is not None:
            if (now - self.first_clap_time) > self.max_double_gap_s * 1.5:
                self.first_clap_time = None

    def start(self) -> bool:
        try:
            import sounddevice as sd
        except ImportError:
            log.warning("sounddevice not available — clap detection disabled.")
            return False
        if self._running:
            return True
        self._running = True
        self._start_time = time.monotonic()

        def _run() -> None:
            try:
                with sd.InputStream(samplerate=self.sample_rate,
                                    blocksize=self._block_samples(),
                                    channels=1,
                                    callback=self._audio_callback):
                    while self._running:
                        time.sleep(0.1)
            except Exception as exc:
                log.error("clap detector stream error: %s", exc)
                self._running = False

        self._thread = threading.Thread(target=_run, daemon=True, name="BeeClapDetector")
        self._thread.start()
        log.info("clap detector running (warmup=%.1fs)", self.warmup_s)
        return True

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)


# ------------------------------------------------------------------ CLI mode
def _voice_once(ctx) -> None:
    from ..agent.loop import run_agent
    from . import mic, speak, transcribe
    cfg = ctx.cfg
    print("  ... listening (speak your command, ~1s of silence ends it)")
    try:
        audio = mic.record(sample_rate=cfg.voice.sample_rate,
                           silence=cfg.voice.silence, max_seconds=cfg.voice.max_seconds)
    except mic.VoiceError as e:
        print(f"  [mic] {e}")
        return
    try:
        text = transcribe.transcribe_audio(
            audio, sample_rate=cfg.voice.sample_rate,
            model=cfg.voice.model, device=cfg.voice.device,
            compute_type=cfg.voice.compute_type)
    except Exception as e:
        print(f"  [stt] failed: {e}")
        return
    text = (text or "").strip()
    if not text:
        return
    print(f"  you: {text}")
    result = run_agent(ctx, text)
    if result and result.output:
        print(f"  BEE> {result.output}")
        if cfg.voice.speak:
            try:
                speak.speak(result.output, cfg)
            except Exception:
                pass


def run_clap_mode(ctx) -> None:
    cfg = ctx.cfg
    c = cfg.clap
    action = (c.action or "welcome").lower()
    from ..commands import welcome

    def on_clap() -> None:
        print("\n  double clap detected")
        if action == "voice":
            _voice_once(ctx)
        else:
            speak_cb = None
            if cfg.voice.enabled and cfg.voice.speak:
                from . import speak
                user = cfg.welcome.user
                speak_cb = lambda: speak.speak(f"Welcome home, {user}.", cfg)
            out = welcome.run(cfg=cfg, speak_cb=speak_cb)
            print("  " + out.replace("\n", "\n  "))

    det = ClapDetector(on_clap, sample_rate=c.sample_rate, block_ms=c.block_ms,
                       spike_ratio=c.spike_ratio, min_rms=c.min_rms,
                       min_double_gap_s=c.min_gap, max_double_gap_s=c.max_gap,
                       cooldown_s=c.cooldown, retrigger_ratio=c.retrigger_ratio,
                       warmup_s=c.warmup_s)
    if not det.start():
        print("  [clap] sounddevice not installed — pip install -r requirements-voice.txt")
        return
    print(f"\n  CLAP MODE — clap twice to trigger: {action}  (Ctrl-C to stop)")
    print("  ... calibrating (warm-up %ds), then listening.\n" % max(1, int(c.warmup_s)))
    try:
        while det.is_running():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        det.stop()
        print("\n  [clap] stopped.")
