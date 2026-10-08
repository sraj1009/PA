"""Vision backend abstraction (Phase 10 future-readiness, 2026-10-08).

Computer use must NOT hard-code a vision vendor. The session asks a
VisionBackend for exactly four capabilities:

  * screen description        describe(desktop, frame)      -> str
  * element detection         detect_elements(desktop, frame) -> [Element]
  * semantic target location  locate(desktop, frame, target) -> (x, y, conf) | None
  * visual state verification verify(desktop, frame, expected) -> (bool|None, detail)

The DEFAULT backend is StructuralVision — a deterministic, vendor-free
implementation over the Desktop protocol (window rects/titles). It makes
coordinate provenance and element-level verification work TODAY without
any model. A learned vision backend (any vendor, local or cloud) can be
injected later — `ComputerUseSession(vision=...)` — and the session uses
it transparently. A failing backend degrades to structural (never blocks
the loop).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class Element:
    """One detected UI element (vendor-neutral)."""
    label: str
    rect: tuple[int, int, int, int]     # (x0, y0, x1, y1)
    score: float = 1.0                  # detector confidence
    kind: str = "window"                # window | button | text | image | ...

    @property
    def center(self) -> tuple[int, int]:
        x0, y0, x1, y1 = self.rect
        return ((x0 + x1) // 2, (y0 + y1) // 2)


@runtime_checkable
class VisionBackend(Protocol):
    name: str

    def describe(self, desktop, frame: bytes | None) -> str: ...
    def detect_elements(self, desktop, frame: bytes | None) -> list[Element]: ...
    def locate(self, desktop, frame: bytes | None, target: str
               ) -> tuple[int, int, float] | None: ...
    def verify(self, desktop, frame: bytes | None, expected: dict
               ) -> tuple[bool | None, str]: ...


class StructuralVision:
    """Vendor-free default: 'vision' over the structural desktop snapshot.

    Elements = visible windows (title + rect). locate() matches the
    semantic target against element labels (exact 1.0 / substring 0.8).
    verify() handles the window-level strategies; pixel-level strategies
    return (None, 'unsupported') so the session falls back to its own
    hash-based verification.
    """

    name = "structural"

    def detect_elements(self, desktop, frame: bytes | None) -> list[Element]:
        out: list[Element] = []
        try:
            for w in desktop.list_windows():
                out.append(Element(label=w.title, rect=w.rect, score=1.0,
                                   kind="window"))
        except Exception:
            pass
        return out

    def describe(self, desktop, frame: bytes | None) -> str:
        els = self.detect_elements(desktop, frame)
        aw = None
        try:
            aw = desktop.active_window()
        except Exception:
            pass
        if not els:
            return "no visible windows"
        active = f"; active: {aw.title} (rect {list(aw.rect)})" if aw else ""
        return (f"{len(els)} visible windows: "
                + "; ".join(f"{e.label} (rect {list(e.rect)})" for e in els[:12])
                + active)

    def locate(self, desktop, frame: bytes | None, target: str
               ) -> tuple[int, int, float] | None:
        t = (target or "").strip().lower()
        if not t:
            return None
        best: tuple[Element, float] | None = None
        for e in self.detect_elements(desktop, frame):
            label = e.label.lower()
            if label == t:
                cand = (e, 1.0 * e.score)
            elif t in label or label in t:
                cand = (e, 0.8 * e.score)
            else:
                continue
            if best is None or cand[1] > best[1]:
                best = cand
        if best is None:
            return None
        el, conf = best
        cx, cy = el.center
        return cx, cy, round(conf, 2)

    def verify(self, desktop, frame: bytes | None, expected: dict
               ) -> tuple[bool | None, str]:
        exp = expected or {}
        if "window_exists" in exp:
            want = str(exp["window_exists"]).lower()
            found = any(want in e.label.lower() for e in
                        self.detect_elements(desktop, frame))
            return found, f"window_exists({exp['window_exists']}): {found}"
        if "active_window" in exp:
            want = str(exp["active_window"]).lower()
            try:
                aw = desktop.active_window()
                ok = aw is not None and want in aw.title.lower()
            except Exception:
                ok = False
            return ok, f"active_window({exp['active_window']}): {ok}"
        # pixel/clipboard strategies are verified by the session's own
        # hash/clipboard checks — this backend has no opinion on them
        return None, "structural vision: strategy handled by session verify"


def make_vision() -> VisionBackend:
    """Default backend factory (swap here to enable a learned vision model)."""
    return StructuralVision()
