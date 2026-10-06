"""JobQueue (Phase 6) — the concurrency-control object.

Two guarantees, both enforced before any work starts:

  1. SINGLE-FLIGHT PER JOB: a job id can only be claimed once. The second
     claim (same tick, next tick, or a duplicate due to a slow writer) is
     refused — a single job can never run twice simultaneously.
  2. GLOBAL CAP: at most `max_parallel` jobs run at once across the worker.

The queue is IN-MEMORY per process. Cross-process duplicate prevention
(`bee-runfull` runs web + REPL as separate processes over the same store)
lives one layer down in JobStore.try_claim() — file-claim tokens with a
TTL, so a crashed process's claim expires instead of wedging the job.
"""
from __future__ import annotations

import threading

from .models import Job


class JobQueue:
    def __init__(self, max_parallel: int = 1):
        self.max_parallel = max(1, int(max_parallel))
        self._inflight: dict[str, Job] = {}
        self._lock = threading.RLock()

    def claim(self, job: Job) -> bool:
        """Claim a job for execution. Refused if already inflight or the
        global cap is reached (the caller then simply skips/defers)."""
        with self._lock:
            if job.id in self._inflight:
                return False
            if len(self._inflight) >= self.max_parallel:
                return False
            self._inflight[job.id] = job
            return True

    def release(self, job_id: str) -> None:
        with self._lock:
            self._inflight.pop(job_id, None)

    def inflight(self) -> list[str]:
        with self._lock:
            return list(self._inflight)

    def job(self, job_id: str) -> Job | None:
        with self._lock:
            return self._inflight.get(job_id)

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._inflight)
