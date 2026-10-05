"""Local speech-to-text via faster-whisper (runs fully on-device; GPU optional).

The model is stored as plain files under workspace/models/ (no HF symlinks,
which fail on Windows without Developer Mode — WinError 1314).

Device 'auto' is CPU-first on Windows: the CUDA ctranslate2 build needs NVIDIA
cublas DLLs (cublas64_12.dll) that are usually not installed with a plain
driver, so cuda is only used when explicitly requested (voice.device: "cuda")
or on non-Windows hosts where the wheel bundles its own CUDA libs. If a GPU
error still surfaces mid-inference, we rebuild on CPU and retry once.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

log = logging.getLogger("bee.stt")

_model = None
_model_key = None
_model_dev = "cpu"
_dev_choice = None  # resolved once for device='auto'


def _model_dir(model_size: str) -> Path:
    """Local model home — real files, never the HF cache's symlink layout."""
    from .. import paths
    d = paths.WORKSPACE / "models" / f"faster-whisper-{model_size}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pick_device(requested: str) -> str:
    global _dev_choice
    if requested in ("cpu", "cuda"):
        return requested
    if _dev_choice is not None:
        return _dev_choice
    if sys.platform == "win32":
        _dev_choice = "cpu"  # see module docstring
    else:
        try:
            import ctranslate2
            _dev_choice = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            _dev_choice = "cpu"
    return _dev_choice


def _load(model_size: str, device: str, compute_type: str):
    global _model, _model_key, _model_dev
    key = (model_size, device, compute_type)
    if _model is None or _model_key != key:
        from faster_whisper import WhisperModel
        d = _model_dir(model_size)
        if not (d / "model.bin").exists():
            from huggingface_hub import snapshot_download
            log.info("downloading faster-whisper %s -> %s (first run, ~150 MB)...", model_size, d)
            snapshot_download(f"Systran/faster-whisper-{model_size}", local_dir=str(d))
        dev = _pick_device(device)
        ct = compute_type
        if dev == "cpu" and ct == "float16":
            ct = "int8"  # float16 is cuda-only
        log.info("loading faster-whisper %s on %s (%s)...", model_size, dev, ct)
        _model = WhisperModel(str(d), device=dev, compute_type=ct)
        _model_key = key
        _model_dev = dev
    return _model


def _gpu_error(e: Exception) -> bool:
    return bool(re.search(r"cuda|cublas|cudnn|cudart|nvidia", str(e), re.I))


def _trans(m, audio, language: str, vad: bool) -> str:
    segments, _info = m.transcribe(audio, language=language, beam_size=1, vad_filter=vad)
    return " ".join(s.text.strip() for s in segments).strip()


def _once(m, audio, language: str) -> str:
    text = _trans(m, audio, language, vad=True)
    if not text:
        # VAD is great on long recordings but eats very short utterances
        # ("hi", "yes") — retry without it before giving up.
        text = _trans(m, audio, language, vad=False)
    return re.sub(r"\s+", " ", text)


def transcribe_audio(audio, sample_rate: int = 16000, model: str = "base.en",
                     device: str = "auto", compute_type: str = "int8",
                     language: str = "en") -> str:
    """audio: float32 1-D numpy array at sample_rate."""
    m = _load(model, device, compute_type)
    try:
        text = _once(m, audio, language)
    except Exception as e:
        if _gpu_error(e) and _model_dev != "cpu":
            log.warning("GPU STT failed at runtime (%s) - rebuilding on CPU and retrying",
                        str(e)[:120])
            m = _load(model, "cpu", "int8")
            text = _once(m, audio, language)
        else:
            raise
    return text


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False
