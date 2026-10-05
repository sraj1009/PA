"""STT device-selection regression tests.

Background: the CUDA ctranslate2 wheel on Windows needs NVIDIA cublas DLLs
(cublas64_12.dll) that a plain driver install does not provide — device
'auto' must therefore resolve to CPU on Windows, and GPU runtime errors must
fall back to CPU instead of killing the voice loop.

Run:  python -m pytest tests/test_stt_device.py -q
"""
from __future__ import annotations

import sys


def test_explicit_devices_passthrough():
    from bee.voice import transcribe as t
    assert t._pick_device("cpu") == "cpu"
    assert t._pick_device("cuda") == "cuda"


def test_auto_device_cpu_on_windows():
    from bee.voice import transcribe as t
    if sys.platform == "win32":
        t._dev_choice = None
        assert t._pick_device("auto") == "cpu"


def test_gpu_error_detection():
    from bee.voice import transcribe as t
    assert t._gpu_error(RuntimeError("Library cublas64_12.dll is not found or cannot be loaded"))
    assert t._gpu_error(OSError("CUDA error: no kernel image"))
    assert not t._gpu_error(ValueError("no default input device"))
    assert not t._gpu_error(RuntimeError("model file missing"))
