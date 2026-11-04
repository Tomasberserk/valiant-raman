"""Durable Job Store and Concurrency-Safe Idempotency Registry (Stage 12D.2).

Guarantees:
1. Thread-safe and process-safe ACQUIRE(request_id) preventing duplicate job runs.
2. Atomic serialization to disk (tmp + os.replace) surviving process interruption.
3. Complete job re-loading and inspection for crash recovery.
"""

import contextlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from engine.director.schema import ProductionJob, ProductionRequest, ProductionState


@contextlib.contextmanager
def _interprocess_lock(lock_path: Path, timeout: float = 15.0, retry_interval: float = 0.02):
    """OS-level mutual exclusion lock for inter-process synchronization on Windows and Unix."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    start_time = time.monotonic()
    f = None

    while True:
        try:
            f = open(lock_path, "a+b")
            fileno = f.fileno()
            if sys.platform == "win32":
                import msvcrt

                f.seek(0)
                msvcrt.locking(fileno, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fileno, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except (IOError, OSError, PermissionError, BlockingIOError):
            if f:
                try:
                    f.close()
                except Exception:
                    pass
                f = None
            if time.monotonic() - start_time > timeout:
                raise TimeoutError(f"Timed out after {timeout}s waiting for inter-process lock on '{lock_path}'")
            time.sleep(retry_interval)

    try:
        yield
    finally:
        if f:
            try:
                fileno = f.fileno()
                if sys.platform == "win32":
                    import msvcrt

                    f.seek(0)
                    msvcrt.locking(fileno, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fileno, fcntl.LOCK_UN)
            except Exception:
                pass
            finally:
                try:
                    f.close()
                except Exception:
                    pass


class JobStore:
    """Manages persistent storage of ProductionJobs with atomic idempotency locks."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = Path(base_dir) if base_dir else Path("storage/jobs")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.base_dir / "idempotency_index.json"
        self._lock = threading.Lock()
        self._file_lock_path = self.base_dir / ".idempotency.lock"

        # Initialize index if missing
        if not self.index_path.exists():
            with _interprocess_lock(self._file_lock_path):
                if not self.index_path.exists():
                    self._write_atomic(self.index_path, json.dumps({}, indent=2))

    def acquire(self, request_id: str, request: ProductionRequest) -> Tuple[ProductionJob, bool]:
        """Atomically acquire or create a ProductionJob by request_id.

        Returns (job, is_new). If request_id already exists, loads existing job without creating a new one.
        Guarantees both intra-process thread-safety and inter-process OS-level mutual exclusion.
        """
        with self._lock:
            with _interprocess_lock(self._file_lock_path):
                index = self._load_index()
                if request_id in index:
                    existing_job_id = index[request_id]
                    existing_job = self.load_job(existing_job_id)
                    return existing_job, False

                # Create new job entity
                timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                job_id = f"job_{timestamp_str}_{uuid4().hex[:8]}"
                job_dir = self.base_dir / job_id
                job_dir.mkdir(parents=True, exist_ok=True)
                (job_dir / "artifacts").mkdir(parents=True, exist_ok=True)

                job = ProductionJob(
                    job_id=job_id,
                    request_id=request_id,
                    current_state=ProductionState.CREATED,
                    current_attempt_id="attempt_01",
                    workspace_dir=job_dir,
                    dossier_id=request.dossier.dossier_id,
                    dossier_sha256=request.dossier.dossier_sha256,
                )

                # Persist job and index atomically
                self._save_job_internal(job)
                index[request_id] = job_id
                self._save_index(index)

                return job, True

    def save_job(self, job: ProductionJob) -> None:
        """Persist updated job state atomically to disk."""
        with self._lock:
            self._save_job_internal(job)

    def _save_job_internal(self, job: ProductionJob) -> None:
        job.updated_at = datetime.now(timezone.utc)
        job_file = job.workspace_dir / "job.json"
        data = job.model_dump(mode="json")
        self._write_atomic(job_file, json.dumps(data, indent=2, default=str))

    def load_job(self, job_id: str) -> ProductionJob:
        """Load an existing job from disk."""
        job_file = self.base_dir / job_id / "job.json"
        if not job_file.exists():
            raise FileNotFoundError(f"ProductionJob file not found at '{job_file}'")

        with open(job_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ProductionJob.model_validate(data)

    def get_job_by_request_id(self, request_id: str) -> Optional[ProductionJob]:
        """Look up job by client idempotency key."""
        with self._lock:
            index = self._load_index()
            job_id = index.get(request_id)
            if not job_id:
                return None
            return self.load_job(job_id)

    def list_jobs(self) -> List[ProductionJob]:
        """List all tracked jobs sorted by creation date."""
        with self._lock:
            index = self._load_index()
            jobs = []
            for jid in index.values():
                try:
                    jobs.append(self.load_job(jid))
                except Exception:
                    pass
            return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def _load_index(self) -> Dict[str, str]:
        if not self.index_path.exists():
            return {}
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_index(self, index: Dict[str, str]) -> None:
        self._write_atomic(self.index_path, json.dumps(index, indent=2))

    @staticmethod
    def _write_atomic(target_path: Path, content: str) -> None:
        """Atomic write using temporary file and atomic replacement."""
        tmp_path = target_path.with_name(f"{target_path.stem}_{uuid4().hex[:8]}.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        max_attempts = 15
        for attempt in range(max_attempts):
            try:
                os.replace(tmp_path, target_path)
                return
            except PermissionError:
                if attempt == max_attempts - 1:
                    raise
                time.sleep(0.02 * (attempt + 1))
