"""Durable job store (Phase 6).

Files under <workspace>/automation/:
  jobs/job_<id>.json     one file per job (atomic write: tmp + replace)
  executions.jsonl       append-only execution history (all jobs)
  notifications.json     all notifications (read/unread flags)
  rules.json             proactive rules (explicitly user-authorized)

Every mutation is persisted BEFORE the in-memory worker observes it, so a
crash/restart can never replay work that already ran and never lose work
that was claimed. Execution rows are written before a run starts — that is
the duplicate-execution guard across restarts.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path

from .events import ProactiveRule
from .models import ExecutionHistory, Job, JobExecution, Notification


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            raise


class JobStore:
    def __init__(self, directory: Path | str):
        self.dir = Path(directory)
        (self.dir / "jobs").mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ---------------------------------------------------------------- jobs
    def _job_path(self, job_id: str) -> Path:
        safe = "".join(c for c in job_id if c.isalnum() or c in "-_")
        return self.dir / "jobs" / f"job_{safe}.json"

    def save_job(self, job: Job) -> None:
        with self._lock:
            _atomic_write(self._job_path(job.id),
                          json.dumps(job.to_dict(), indent=1, ensure_ascii=False))

    def load_job(self, job_id: str) -> Job | None:
        p = self._job_path(job_id)
        if not p.exists():
            return None
        try:
            return Job.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            return None

    def load_all_jobs(self) -> list[Job]:
        out = []
        for p in sorted((self.dir / "jobs").glob("job_*.json")):
            try:
                out.append(Job.from_dict(json.loads(p.read_text(encoding="utf-8"))))
            except Exception:
                continue
        return out

    def delete_job(self, job_id: str) -> None:
        with self._lock:
            try:
                self._job_path(job_id).unlink(missing_ok=True)
            except OSError:
                pass

    # ---------------------------------------------------------- executions
    @property
    def _exec_path(self) -> Path:
        return self.dir / "executions.jsonl"

    def append_execution(self, ex: JobExecution) -> None:
        """Persist an execution row (called BEFORE the run starts and again
        on completion — the first write is the duplicate guard)."""
        with self._lock:
            self._exec_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._exec_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(ex.to_dict(), ensure_ascii=False) + "\n")

    def executions(self) -> ExecutionHistory:
        """Last row per execution id wins (a crash-repair appends a terminal
        row for an open 'running' row); original order otherwise preserved."""
        by_id: dict[str, JobExecution] = {}
        order: list[str] = []
        if self._exec_path.exists():
            for line in self._exec_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        ex = JobExecution.from_dict(json.loads(line))
                    except Exception:
                        continue
                    if ex.id not in by_id:
                        order.append(ex.id)
                    by_id[ex.id] = ex
        return ExecutionHistory([by_id[i] for i in order])

    # -------------------------------------------------------- notifications
    @property
    def _notif_path(self) -> Path:
        return self.dir / "notifications.json"

    def load_notifications(self) -> list[Notification]:
        if not self._notif_path.exists():
            return []
        try:
            rows = json.loads(self._notif_path.read_text(encoding="utf-8"))
            return [Notification.from_dict(r) for r in rows]
        except Exception:
            return []

    def save_notifications(self, notifs: list[Notification]) -> None:
        with self._lock:
            _atomic_write(self._notif_path,
                          json.dumps([n.to_dict() for n in notifs],
                                     indent=1, ensure_ascii=False))

    def add_notification(self, n: Notification) -> None:
        with self._lock:
            notifs = self.load_notifications()
            notifs.append(n)
            self.save_notifications(notifs)

    # ---------------------------------------------------------------- rules
    @property
    def _rules_path(self) -> Path:
        return self.dir / "rules.json"

    def load_rules(self) -> list[ProactiveRule]:
        if not self._rules_path.exists():
            return []
        try:
            rows = json.loads(self._rules_path.read_text(encoding="utf-8"))
            return [ProactiveRule.from_dict(r) for r in rows]
        except Exception:
            return []

    def save_rules(self, rules: list[ProactiveRule]) -> None:
        with self._lock:
            _atomic_write(self._rules_path,
                          json.dumps([r.to_dict() for r in rules],
                                     indent=1, ensure_ascii=False))

    # ------------------------------------------------- cross-process claims
    # `bee-runfull` runs web and REPL as SEPARATE processes over the same
    # store. The in-memory JobQueue cannot see the other process, so the
    # store adds file-claim tokens: atomic tmp+replace, TTL = max_runtime +
    # grace. A live claim blocks; a stale one (crash) is taken over.
    @property
    def _claims_dir(self) -> Path:
        return self.dir / "claims"

    def _claim_path(self, job_id: str) -> Path:
        safe = "".join(c for c in job_id if c.isalnum() or c in "-_")
        return self._claims_dir / f"{safe}.claim"

    def try_claim(self, job_id: str, ttl_seconds: float) -> bool:
        with self._lock:
            p = self._claim_path(job_id)
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.exists():
                try:
                    if time.time() - p.stat().st_mtime < ttl_seconds:
                        return False                    # another process is running it
                except OSError:
                    pass
            _atomic_write(p, json.dumps({"pid": os.getpid(),
                                         "ts": time.time()}))
            return True

    def release_claim(self, job_id: str) -> None:
        with self._lock:
            try:
                self._claim_path(job_id).unlink(missing_ok=True)
            except OSError:
                pass

    def clear_stale_claims(self, ttl_seconds: float) -> int:
        """Drop claim tokens older than ttl (crashed processes). Idempotent."""
        removed = 0
        with self._lock:
            if not self._claims_dir.exists():
                return 0
            for p in self._claims_dir.glob("*.claim"):
                try:
                    if time.time() - p.stat().st_mtime >= ttl_seconds:
                        p.unlink(missing_ok=True)
                        removed += 1
                except OSError:
                    pass
        return removed
