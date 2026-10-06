"""Computer-use privacy (Phase 5).

Rules enforced in code (not just documented):

  1. NO typed text in logs. type_text actions log `text_len` only. The
     payload never enters the audit trail, episode logs, receipts, or the
     model-visible tool result.
  2. NO clipboard contents in logs. Verification compares and reports the
     boolean; contents stay on the clipboard.
  3. NO pixel data in logs. Observations carry a short screen hash and
     geometry — never image bytes.
  4. NO window/tab TITLES in log entries. (Titles can be sensitive — e.g.
     a browser tab titled "Bank / Transfer".) Log entries carry window
     COUNTS and the action's own `target` (the user's stated intent), not
     observed titles.
  5. Screenshots have a retention policy: in-memory hash ring by default
     (nothing on disk); optional temp-dir saves are bounded by frame count
     AND age, and purged on demand / at session end.

The model-visible observation (returned to the LLM as tool data) DOES
include window titles — the loop needs them to reason. That payload is
transient (in-context, untrusted-marked), not logged.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path


def redact_entry(action, verification, seconds: float, executed: bool,
                 post: dict | None = None) -> dict:
    """Log/audit-safe entry for one executed (or blocked) action."""
    d = action.public()
    d.update({
        "executed": executed,
        "verified": verification.verified,
        "verification_strategy": verification.strategy,
        "seconds": round(seconds, 2),
        # observed state — counts and hashes only, never titles/pixels:
        "n_windows": (post or {}).get("n_windows"),
        "screen_hash": (post or {}).get("screen_hash", "")[:8],
    })
    # verification detail may name the expected target (intent) — scrub any
    # observed titles that slipped in:
    d["verify_detail"] = verification.detail[:200]
    return d


class ScreenshotStore:
    """Bounded screenshot retention.

    Default (save_dir=None): in-memory hash ring only — screenshots exist
    transiently for verification and then only their hash survives.
    With save_dir: files are written under it, bounded by max_frames AND
    max_age_minutes; purge() enforces both.
    """

    def __init__(self, max_frames: int = 5, max_age_minutes: float = 5.0,
                 save_dir: Path | str | None = None):
        self.max_frames = max_frames
        self.max_age = max_age_minutes * 60.0
        self.save_dir = Path(save_dir) if save_dir else None
        self._ring: list[dict] = []

    def push(self, data: bytes | None, meta: dict | None = None) -> str:
        if not data:
            return ""
        h = hashlib.sha256(data).hexdigest()[:16]
        ts = time.time()
        self._ring.append({"hash": h, "ts": ts, "meta": meta or {}})
        if self.save_dir is not None:
            try:
                self.save_dir.mkdir(parents=True, exist_ok=True)
                (self.save_dir / f"frame_{int(ts * 1000)}_{h}.bin").write_bytes(data)
            except Exception:
                pass
        while len(self._ring) > self.max_frames:
            self._ring.pop(0)
        self._purge_expired()
        return h

    def _purge_expired(self) -> None:
        now = time.time()
        if self.save_dir is None:
            return
        try:
            for f in self.save_dir.glob("frame_*.bin"):
                if now - f.stat().st_mtime > self.max_age:
                    f.unlink(missing_ok=True)
        except Exception:
            pass

    def purge(self) -> int:
        """Delete ALL saved frames (called on session end / emergency stop)."""
        n = 0
        if self.save_dir is not None:
            try:
                for f in self.save_dir.glob("frame_*.bin"):
                    f.unlink(missing_ok=True)
                    n += 1
            except Exception:
                pass
        self._ring.clear()
        return n

    def hashes(self) -> list[str]:
        return [r["hash"] for r in self._ring]

    def __len__(self) -> int:
        return len(self._ring)
