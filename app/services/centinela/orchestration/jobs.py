from __future__ import annotations

import ctypes
import json
import os
import socket
import sqlite3
import threading
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Callable
from uuid import uuid4

from app.services.centinela.project_foundation import ArtifactStore

from .models import (
    TERMINAL_JOB_STATUSES,
    JobEvent,
    JobRecord,
    JobStatus,
    ResourceClass,
    clean_text,
    json_safe,
    now_iso,
)
from .persistence import OrchestrationDB


class JobManagerError(RuntimeError):
    pass


class JobNotFoundError(JobManagerError):
    pass


class JobStateError(JobManagerError):
    pass


class JobCancelled(JobManagerError):
    pass


Handler = Callable[["JobContext", dict[str, Any]], Any]


def _owner_process_alive(owner_id: str | None) -> bool:
    if not owner_id:
        return False

    try:
        hostname, pid_text, _ = owner_id.split(":", 2)
        pid = int(pid_text)
    except (AttributeError, TypeError, ValueError):
        return False

    if hostname != socket.gethostname():
        return True

    if pid == os.getpid():
        return True

    if os.name == "nt":
        process_query_limited_information = 0x1000
        still_active = 259
        error_access_denied = 5
        error_invalid_parameter = 87

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetExitCodeProcess.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_ulong),
        ]
        kernel32.GetExitCodeProcess.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int

        handle = kernel32.OpenProcess(
            process_query_limited_information,
            False,
            pid,
        )

        if not handle:
            error_code = ctypes.get_last_error()
            if error_code == error_invalid_parameter:
                return False
            if error_code == error_access_denied:
                return True
            return True

        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(
                handle,
                ctypes.byref(exit_code),
            ):
                return True
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


class JobContext:
    def __init__(
        self,
        manager: "JobManager",
        job_id: str,
    ) -> None:
        self._manager = manager
        self.job_id = job_id

    def report_progress(
        self,
        progress: int,
        message: str | None = None,
    ) -> JobRecord:
        return self._manager._report_progress(
            self.job_id,
            progress,
            message,
        )

    def check_cancelled(self) -> None:
        record = self._manager.get_job(
            self.job_id
        )
        if record.status in {
            JobStatus.CANCEL_REQUESTED,
            JobStatus.CANCELLED,
        }:
            raise JobCancelled(
                f"job cancellation requested: {self.job_id}"
            )

    @property
    def cancel_requested(self) -> bool:
        return self._manager.get_job(
            self.job_id
        ).status in {
            JobStatus.CANCEL_REQUESTED,
            JobStatus.CANCELLED,
        }


class JobManager:
    def __init__(
        self,
        store: ArtifactStore,
        *,
        max_workers: int = 2,
        thread_name_prefix: str = "centinela-job",
    ) -> None:
        if isinstance(max_workers, bool) or not isinstance(max_workers, int):
            raise TypeError("max_workers must be an integer")
        if not 1 <= max_workers <= 8:
            raise ValueError("max_workers must be between 1 and 8")

        self.store = store
        self.db = OrchestrationDB(store)
        self.max_workers = max_workers
        self.owner_id = (
            f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex}"
        )
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
        )
        self._lock = threading.RLock()
        self._handlers: dict[str, Handler] = {}
        self._futures: dict[str, Future[Any]] = {}
        self._shutdown = False

    def __enter__(self) -> "JobManager":
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.shutdown(wait=True)

    @staticmethod
    def _validate_handler(
        handler: Handler,
    ) -> Handler:
        if not callable(handler):
            raise TypeError("handler must be callable")
        return handler

    def register_handler(
        self,
        job_type: str,
        handler: Handler,
    ) -> None:
        job_type = clean_text(
            job_type,
            "job_type",
            maximum=128,
        )
        if not all(
            character.isalnum()
            or character in "._-"
            for character in job_type
        ):
            raise ValueError(
                "job_type contains unsafe characters"
            )
        handler = self._validate_handler(handler)

        with self._lock:
            if self._shutdown:
                raise JobManagerError(
                    "job manager is shut down"
                )
            self._handlers[job_type] = handler

    def unregister_handler(
        self,
        job_type: str,
    ) -> None:
        with self._lock:
            self._handlers.pop(
                job_type,
                None,
            )

    def enqueue(
        self,
        project_id: str,
        job_type: str,
        *,
        payload: dict[str, Any] | None = None,
        resource_class: ResourceClass | str = ResourceClass.LIGHT,
        message: str | None = None,
        auto_start: bool = True,
        retry_of_job_id: str | None = None,
        attempt: int = 1,
    ) -> JobRecord:
        if self._shutdown:
            raise JobManagerError(
                "job manager is shut down"
            )

        self.store.load_project(
            project_id
        )

        normalized_type = clean_text(
            job_type,
            "job_type",
            maximum=128,
        )
        if not all(
            character.isalnum()
            or character in "._-"
            for character in normalized_type
        ):
            raise ValueError(
                "job_type contains unsafe characters"
            )

        safe_payload = json_safe(
            payload or {},
            "job_payload",
        )
        resource = ResourceClass(
            resource_class
        )

        if message is not None:
            message = clean_text(
                message,
                "message",
                maximum=2000,
            )

        if isinstance(attempt, bool) or not isinstance(attempt, int):
            raise TypeError(
                "attempt must be an integer"
            )
        if attempt <= 0:
            raise ValueError(
                "attempt must be positive"
            )

        if retry_of_job_id is not None:
            original = self.get_job(
                retry_of_job_id
            )
            if original.project_id != project_id:
                raise JobStateError(
                    "retry parent belongs to another project"
                )

        job_id = uuid4().hex
        created_at = now_iso()

        with self.db.immediate() as connection:
            connection.execute(
                """
                INSERT INTO jobs(
                    job_id,
                    project_id,
                    job_type,
                    status,
                    progress,
                    message,
                    resource_class,
                    payload_json,
                    result_json,
                    error_type,
                    error_message,
                    created_at,
                    started_at,
                    finished_at,
                    updated_at,
                    owner_id,
                    retry_of_job_id,
                    attempt
                ) VALUES (
                    ?, ?, ?, 'QUEUED', 0, ?, ?, ?, NULL, NULL, NULL,
                    ?, NULL, NULL, ?, NULL, ?, ?
                )
                """,
                (
                    job_id,
                    project_id,
                    normalized_type,
                    message,
                    resource.value,
                    json.dumps(
                        safe_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        allow_nan=False,
                    ),
                    created_at,
                    created_at,
                    retry_of_job_id,
                    attempt,
                ),
            )
            self._append_event(
                connection,
                job_id,
                JobStatus.QUEUED,
                0,
                message,
                created_at,
            )

        if auto_start:
            self._schedule_if_possible(
                job_id
            )

        return self.get_job(
            job_id
        )

    def _append_event(
        self,
        connection: sqlite3.Connection,
        job_id: str,
        status: JobStatus,
        progress: int,
        message: str | None,
        created_at: str,
    ) -> None:
        row = connection.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) + 1
            FROM job_events
            WHERE job_id=?
            """,
            (job_id,),
        ).fetchone()
        sequence = int(row[0])

        connection.execute(
            """
            INSERT INTO job_events(
                job_id,
                sequence,
                status,
                progress,
                message,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                sequence,
                status.value,
                progress,
                message,
                created_at,
            ),
        )

    def _schedule_if_possible(
        self,
        job_id: str,
    ) -> bool:
        with self._lock:
            if self._shutdown:
                return False
            existing = self._futures.get(
                job_id
            )
            if existing is not None and not existing.done():
                return True

            record = self.get_job(
                job_id
            )
            handler = self._handlers.get(
                record.job_type
            )
            if (
                handler is None
                or record.status != JobStatus.QUEUED
            ):
                return False

            future = self._executor.submit(
                self._execute_job,
                job_id,
                handler,
            )
            self._futures[job_id] = future
            future.add_done_callback(
                lambda completed, jid=job_id: self._forget_future(
                    jid,
                    completed,
                )
            )
            return True

    def _forget_future(
        self,
        job_id: str,
        future: Future[Any],
    ) -> None:
        with self._lock:
            current = self._futures.get(
                job_id
            )
            if current is future:
                self._futures.pop(
                    job_id,
                    None,
                )

    def resume_queued(
        self,
        *,
        project_id: str | None = None,
    ) -> list[str]:
        records = self.list_jobs(
            project_id=project_id,
            status=JobStatus.QUEUED,
        )
        scheduled: list[str] = []
        for record in records:
            if self._schedule_if_possible(
                record.job_id
            ):
                scheduled.append(
                    record.job_id
                )
        return scheduled

    def _claim(
        self,
        job_id: str,
    ) -> JobRecord | None:
        now = now_iso()

        with self.db.immediate() as connection:
            row = connection.execute(
                """
                SELECT status
                FROM jobs
                WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()

            if row is None:
                raise JobNotFoundError(
                    job_id
                )

            if JobStatus(row["status"]) != JobStatus.QUEUED:
                return None

            updated = connection.execute(
                """
                UPDATE jobs
                SET
                    status='RUNNING',
                    started_at=?,
                    updated_at=?,
                    owner_id=?
                WHERE job_id=?
                  AND status='QUEUED'
                """,
                (
                    now,
                    now,
                    self.owner_id,
                    job_id,
                ),
            )
            if updated.rowcount != 1:
                return None

            job_row = connection.execute(
                """
                SELECT progress, message
                FROM jobs
                WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()

            self._append_event(
                connection,
                job_id,
                JobStatus.RUNNING,
                int(job_row["progress"]),
                job_row["message"],
                now,
            )

        return self.get_job(
            job_id
        )

    def _execute_job(
        self,
        job_id: str,
        handler: Handler,
    ) -> None:
        claimed = self._claim(
            job_id
        )
        if claimed is None:
            return

        context = JobContext(
            self,
            job_id,
        )

        try:
            context.check_cancelled()
            result = handler(
                context,
                dict(claimed.payload),
            )
            context.check_cancelled()
            safe_result = (
                None
                if result is None
                else json_safe(
                    result,
                    "job_result",
                )
            )
            self._finish_success(
                job_id,
                safe_result,
            )
        except JobCancelled:
            self._finish_cancelled(
                job_id,
                "cancelled cooperatively",
            )
        except Exception as exc:
            self._finish_failure(
                job_id,
                type(exc).__name__,
                str(exc) or type(exc).__name__,
            )

    def _report_progress(
        self,
        job_id: str,
        progress: int,
        message: str | None,
    ) -> JobRecord:
        if isinstance(progress, bool) or not isinstance(progress, int):
            raise TypeError(
                "progress must be an integer"
            )
        if not 0 <= progress <= 99:
            raise ValueError(
                "handler progress must be between 0 and 99; 100 is reserved for success"
            )
        if message is not None:
            message = clean_text(
                message,
                "message",
                maximum=2000,
            )

        now = now_iso()

        with self.db.immediate() as connection:
            row = connection.execute(
                """
                SELECT status, progress, message
                FROM jobs
                WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()

            if row is None:
                raise JobNotFoundError(
                    job_id
                )

            status = JobStatus(
                row["status"]
            )

            if status == JobStatus.CANCEL_REQUESTED:
                raise JobCancelled(
                    f"job cancellation requested: {job_id}"
                )
            if status != JobStatus.RUNNING:
                raise JobStateError(
                    f"cannot report progress while job is {status.value}"
                )

            previous = int(
                row["progress"]
            )
            if progress < previous:
                raise JobStateError(
                    "job progress cannot decrease"
                )

            effective_message = (
                message
                if message is not None
                else row["message"]
            )

            connection.execute(
                """
                UPDATE jobs
                SET
                    progress=?,
                    message=?,
                    updated_at=?
                WHERE job_id=?
                  AND status='RUNNING'
                """,
                (
                    progress,
                    effective_message,
                    now,
                    job_id,
                ),
            )
            self._append_event(
                connection,
                job_id,
                JobStatus.RUNNING,
                progress,
                effective_message,
                now,
            )

        return self.get_job(
            job_id
        )

    def request_cancel(
        self,
        job_id: str,
        *,
        reason: str = "cancellation requested",
    ) -> bool:
        reason = clean_text(
            reason,
            "reason",
            maximum=2000,
        )
        now = now_iso()

        with self.db.immediate() as connection:
            row = connection.execute(
                """
                SELECT status, progress
                FROM jobs
                WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()

            if row is None:
                raise JobNotFoundError(
                    job_id
                )

            status = JobStatus(
                row["status"]
            )
            progress = int(
                row["progress"]
            )

            if status in TERMINAL_JOB_STATUSES:
                return False
            if status == JobStatus.CANCEL_REQUESTED:
                return True

            if status == JobStatus.QUEUED:
                target = JobStatus.CANCELLED
                finished_at = now
                owner_id = None
            elif status == JobStatus.RUNNING:
                target = JobStatus.CANCEL_REQUESTED
                finished_at = None
                owner_id = self.owner_id
            else:
                raise JobStateError(
                    f"cannot cancel job in state {status.value}"
                )

            connection.execute(
                """
                UPDATE jobs
                SET
                    status=?,
                    message=?,
                    finished_at=?,
                    updated_at=?,
                    owner_id=?
                WHERE job_id=?
                """,
                (
                    target.value,
                    reason,
                    finished_at,
                    now,
                    owner_id,
                    job_id,
                ),
            )
            self._append_event(
                connection,
                job_id,
                target,
                progress,
                reason,
                now,
            )

        if target == JobStatus.CANCELLED:
            with self._lock:
                future = self._futures.get(
                    job_id
                )
                if future is not None:
                    future.cancel()

        return True

    def _finish_success(
        self,
        job_id: str,
        result: Any,
    ) -> None:
        now = now_iso()
        result_json = (
            None
            if result is None
            else json.dumps(
                result,
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
        )

        with self.db.immediate() as connection:
            row = connection.execute(
                """
                SELECT status
                FROM jobs
                WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                raise JobNotFoundError(
                    job_id
                )
            status = JobStatus(
                row["status"]
            )
            if status == JobStatus.CANCEL_REQUESTED:
                raise JobCancelled(
                    f"job cancellation requested: {job_id}"
                )
            if status != JobStatus.RUNNING:
                raise JobStateError(
                    f"cannot succeed job in state {status.value}"
                )

            connection.execute(
                """
                UPDATE jobs
                SET
                    status='SUCCEEDED',
                    progress=100,
                    result_json=?,
                    error_type=NULL,
                    error_message=NULL,
                    finished_at=?,
                    updated_at=?,
                    owner_id=NULL
                WHERE job_id=?
                """,
                (
                    result_json,
                    now,
                    now,
                    job_id,
                ),
            )
            self._append_event(
                connection,
                job_id,
                JobStatus.SUCCEEDED,
                100,
                "completed",
                now,
            )

    def _finish_failure(
        self,
        job_id: str,
        error_type: str,
        error_message: str,
    ) -> None:
        error_type = str(error_type or "Error").strip()[:256] or "Error"
        error_message = (
            str(error_message or error_type).strip()[:4000]
            or error_type
        )
        now = now_iso()

        with self.db.immediate() as connection:
            row = connection.execute(
                """
                SELECT status, progress
                FROM jobs
                WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                raise JobNotFoundError(
                    job_id
                )

            status = JobStatus(
                row["status"]
            )
            if status in TERMINAL_JOB_STATUSES:
                return
            if status == JobStatus.CANCEL_REQUESTED:
                connection.execute(
                    """
                    UPDATE jobs
                    SET
                        status='CANCELLED',
                        message='cancelled after handler failure',
                        finished_at=?,
                        updated_at=?,
                        owner_id=NULL
                    WHERE job_id=?
                    """,
                    (
                        now,
                        now,
                        job_id,
                    ),
                )
                self._append_event(
                    connection,
                    job_id,
                    JobStatus.CANCELLED,
                    int(row["progress"]),
                    "cancelled after handler failure",
                    now,
                )
                return

            if status != JobStatus.RUNNING:
                raise JobStateError(
                    f"cannot fail job in state {status.value}"
                )

            connection.execute(
                """
                UPDATE jobs
                SET
                    status='FAILED',
                    error_type=?,
                    error_message=?,
                    finished_at=?,
                    updated_at=?,
                    owner_id=NULL
                WHERE job_id=?
                """,
                (
                    error_type,
                    error_message,
                    now,
                    now,
                    job_id,
                ),
            )
            self._append_event(
                connection,
                job_id,
                JobStatus.FAILED,
                int(row["progress"]),
                "failed",
                now,
            )

    def _finish_cancelled(
        self,
        job_id: str,
        message: str,
    ) -> None:
        message = clean_text(
            message,
            "message",
            maximum=2000,
        )
        now = now_iso()

        with self.db.immediate() as connection:
            row = connection.execute(
                """
                SELECT status, progress
                FROM jobs
                WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                raise JobNotFoundError(
                    job_id
                )
            status = JobStatus(
                row["status"]
            )
            if status == JobStatus.CANCELLED:
                return
            if status not in {
                JobStatus.RUNNING,
                JobStatus.CANCEL_REQUESTED,
            }:
                raise JobStateError(
                    f"cannot finalize cancellation from {status.value}"
                )

            connection.execute(
                """
                UPDATE jobs
                SET
                    status='CANCELLED',
                    message=?,
                    finished_at=?,
                    updated_at=?,
                    owner_id=NULL
                WHERE job_id=?
                """,
                (
                    message,
                    now,
                    now,
                    job_id,
                ),
            )
            self._append_event(
                connection,
                job_id,
                JobStatus.CANCELLED,
                int(row["progress"]),
                message,
                now,
            )

    def get_job(
        self,
        job_id: str,
    ) -> JobRecord:
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM jobs
                WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            raise JobNotFoundError(
                job_id
            )
        return self._record_from_row(
            row
        )

    @staticmethod
    def _record_from_row(
        row: sqlite3.Row,
    ) -> JobRecord:
        return JobRecord(
            job_id=row["job_id"],
            project_id=row["project_id"],
            job_type=row["job_type"],
            status=JobStatus(row["status"]),
            progress=int(row["progress"]),
            message=row["message"],
            resource_class=ResourceClass(row["resource_class"]),
            payload=json.loads(row["payload_json"]),
            result=(
                None
                if row["result_json"] is None
                else json.loads(row["result_json"])
            ),
            error_type=row["error_type"],
            error_message=row["error_message"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            updated_at=row["updated_at"],
            owner_id=row["owner_id"],
            retry_of_job_id=row["retry_of_job_id"],
            attempt=int(row["attempt"]),
        )

    def list_jobs(
        self,
        *,
        project_id: str | None = None,
        status: JobStatus | str | None = None,
    ) -> list[JobRecord]:
        clauses: list[str] = []
        values: list[Any] = []

        if project_id is not None:
            self.store.load_project(
                project_id
            )
            clauses.append(
                "project_id=?"
            )
            values.append(
                project_id
            )

        if status is not None:
            normalized_status = JobStatus(
                status
            )
            clauses.append(
                "status=?"
            )
            values.append(
                normalized_status.value
            )

        where = (
            "WHERE " + " AND ".join(clauses)
            if clauses
            else ""
        )

        with self.db.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM jobs
                {where}
                ORDER BY created_at ASC, job_id ASC
                """,
                tuple(values),
            ).fetchall()

        return [
            self._record_from_row(
                row
            )
            for row in rows
        ]

    def events(
        self,
        job_id: str,
    ) -> list[JobEvent]:
        self.get_job(
            job_id
        )
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT sequence, job_id, status, progress, message, created_at
                FROM job_events
                WHERE job_id=?
                ORDER BY sequence ASC
                """,
                (job_id,),
            ).fetchall()

        return [
            JobEvent(
                sequence=int(row["sequence"]),
                job_id=row["job_id"],
                status=JobStatus(row["status"]),
                progress=int(row["progress"]),
                message=row["message"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def wait(
        self,
        job_id: str,
        timeout: float | None = None,
    ) -> JobRecord:
        with self._lock:
            future = self._futures.get(
                job_id
            )

        if future is not None:
            try:
                future.result(
                    timeout=timeout
                )
            except FutureTimeoutError:
                raise TimeoutError(
                    f"job did not complete within timeout: {job_id}"
                ) from None

        return self.get_job(
            job_id
        )

    def retry(
        self,
        job_id: str,
        *,
        auto_start: bool = True,
        message: str | None = None,
    ) -> JobRecord:
        original = self.get_job(
            job_id
        )
        if original.status not in {
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.INTERRUPTED,
        }:
            raise JobStateError(
                f"job {job_id} in {original.status.value} cannot be retried"
            )

        return self.enqueue(
            original.project_id,
            original.job_type,
            payload=original.payload,
            resource_class=original.resource_class,
            message=message or f"retry of {job_id}",
            auto_start=auto_start,
            retry_of_job_id=job_id,
            attempt=original.attempt + 1,
        )

    def recover_interrupted_jobs(
        self,
        *,
        owner_alive: Callable[[str | None], bool] = _owner_process_alive,
    ) -> list[str]:
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT job_id, status, progress, owner_id
                FROM jobs
                WHERE status IN ('RUNNING', 'CANCEL_REQUESTED')
                ORDER BY created_at ASC
                """
            ).fetchall()

        recovered: list[str] = []

        for row in rows:
            if owner_alive(
                row["owner_id"]
            ):
                continue

            now = now_iso()
            job_id = row["job_id"]

            with self.db.immediate() as connection:
                current = connection.execute(
                    """
                    SELECT status, progress, owner_id
                    FROM jobs
                    WHERE job_id=?
                    """,
                    (job_id,),
                ).fetchone()
                if current is None:
                    continue

                status = JobStatus(
                    current["status"]
                )
                if status not in {
                    JobStatus.RUNNING,
                    JobStatus.CANCEL_REQUESTED,
                }:
                    continue
                if owner_alive(
                    current["owner_id"]
                ):
                    continue

                connection.execute(
                    """
                    UPDATE jobs
                    SET
                        status='INTERRUPTED',
                        error_type='ProcessInterrupted',
                        error_message='job owner process is no longer running',
                        finished_at=?,
                        updated_at=?,
                        owner_id=NULL
                    WHERE job_id=?
                    """,
                    (
                        now,
                        now,
                        job_id,
                    ),
                )
                self._append_event(
                    connection,
                    job_id,
                    JobStatus.INTERRUPTED,
                    int(current["progress"]),
                    "interrupted after process restart",
                    now,
                )
                recovered.append(
                    job_id
                )

        return recovered

    def shutdown(
        self,
        *,
        wait: bool = True,
    ) -> None:
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
        self._executor.shutdown(
            wait=wait,
            cancel_futures=False,
        )
