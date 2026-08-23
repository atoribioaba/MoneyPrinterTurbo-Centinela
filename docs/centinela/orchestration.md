# Centinela Orchestration — R2

## Scope

R2 adds the persistent project state machine and in-process job manager that sit
above the R1 Project Foundation. It does not replace MoneyPrinterTurbo's legacy
`app/services/state.py` or `app/services/task.py`; those remain intact until the
R3 Production Spine explicitly bridges them.

## Canonical project states

The forward production path is:

`DRAFT → RESEARCH_READY → SCRIPT_READY → SCENES_READY → MEDIA_READY →
AUDIO_READY → VIDEO_BASE_READY → READY_FOR_HUMAN_REVIEW → FINAL_APPROVED →
PUBLICATION_PACKAGE_READY`.

`BLOCKED` and `NEEDS_INPUT` are recoverable side states and may resume only to
the state from which they were entered. `FAILED`, `CANCELLED`, and
`PUBLICATION_PACKAGE_READY` are terminal in R2. Forward-state skipping and
backward progression are rejected.

The state machine accepts explicit target-state guards. R2 deliberately does
not hard-code artifact names such as `fact_lock` or `final_script`; R3 registers
the production-stage output requirements when those executors are wired.

## Crash-consistent transitions

The project manifest remains the canonical project state. SQLite adds a
rebuildable orchestration head and append-only transition history.

A transition is reserved first as a PENDING intent, then the R1 manifest is
written, then the transition is finalized. A crash before the manifest write can
be safely ABORTED; a crash after the manifest reaches the target can be
FINALIZED by `recover_pending_transitions()`. An unexpected third state is
treated as an integrity error rather than guessed.

This is intentionally a write-ahead protocol because filesystem manifest writes
and SQLite transactions cannot be one atomic transaction.

## Persistent jobs

`JobManager` persists job identity, project, type, payload, status, progress,
resource class, result/error metadata, retry lineage and an append-only event
history in the same `storage/centinela/centinela.db`.

Lifecycle:

`QUEUED → RUNNING → SUCCEEDED | FAILED`

Cancellation:

`QUEUED → CANCELLED`

`RUNNING → CANCEL_REQUESTED → CANCELLED`

After a process restart, active jobs whose recorded owner process is no longer
alive can be changed to `INTERRUPTED`. Queued jobs remain queued because their
payload and type are still valid; handlers are registered again by the
application and `resume_queued()` schedules only known job types.

Retries never rewrite a terminal job. `retry()` creates a new immutable job
linked through `retry_of_job_id` with an incremented attempt number.

Cancellation is cooperative. Handlers receive `JobContext` and should call
`check_cancelled()` or `report_progress()` at sensible boundaries.

## Safety

Persisted transition metadata, job payloads and job results reject secret-like
keys. Handler exceptions persist only a bounded type/message, not a traceback.
Progress is monotonic and 100 is reserved for successful completion.

R2 records `LIGHT`, `MEDIUM`, `HEAVY`, and `EXCLUSIVE` resource classes but does
not yet implement the final GPU/resource scheduler. R3 may use these values when
it wires the Production Spine to the hardware-aware execution policy.

No automatic retry, publication, architecture freeze, WanGP activation, model
download, or network service is introduced by R2.
