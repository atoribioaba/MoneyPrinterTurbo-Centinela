from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.services.centinela.project_foundation.models import utc_now_iso, validate_id

ORCHESTRATION_SCHEMA_VERSION = 1

_SECRET_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "authorization",
    "cookie",
    "credential",
)


class ProjectState(StrEnum):
    DRAFT = "DRAFT"
    RESEARCH_READY = "RESEARCH_READY"
    SCRIPT_READY = "SCRIPT_READY"
    SCENES_READY = "SCENES_READY"
    MEDIA_READY = "MEDIA_READY"
    AUDIO_READY = "AUDIO_READY"
    VIDEO_BASE_READY = "VIDEO_BASE_READY"
    READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"
    FINAL_APPROVED = "FINAL_APPROVED"
    PUBLICATION_PACKAGE_READY = "PUBLICATION_PACKAGE_READY"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    NEEDS_INPUT = "NEEDS_INPUT"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


class ResourceClass(StrEnum):
    LIGHT = "LIGHT"
    MEDIUM = "MEDIUM"
    HEAVY = "HEAVY"
    EXCLUSIVE = "EXCLUSIVE"


PROGRESSION_STATES = (
    ProjectState.DRAFT,
    ProjectState.RESEARCH_READY,
    ProjectState.SCRIPT_READY,
    ProjectState.SCENES_READY,
    ProjectState.MEDIA_READY,
    ProjectState.AUDIO_READY,
    ProjectState.VIDEO_BASE_READY,
    ProjectState.READY_FOR_HUMAN_REVIEW,
    ProjectState.FINAL_APPROVED,
    ProjectState.PUBLICATION_PACKAGE_READY,
)

SIDE_STATES = frozenset(
    {
        ProjectState.BLOCKED,
        ProjectState.NEEDS_INPUT,
        ProjectState.FAILED,
        ProjectState.CANCELLED,
    }
)

TERMINAL_PROJECT_STATES = frozenset(
    {
        ProjectState.PUBLICATION_PACKAGE_READY,
        ProjectState.FAILED,
        ProjectState.CANCELLED,
    }
)

TERMINAL_JOB_STATUSES = frozenset(
    {
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
        JobStatus.INTERRUPTED,
    }
)


def _json_copy(value: Any, name: str) -> Any:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be JSON-safe") from exc
    return json.loads(encoded)


def assert_no_secret_keys(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = re.sub(
                r"[^a-z0-9]+",
                "_",
                str(key).lower(),
            ).strip("_")
            if any(fragment in key_text for fragment in _SECRET_KEY_FRAGMENTS):
                raise ValueError(f"secret-like key is forbidden in persisted orchestration data: {path}.{key}")
            assert_no_secret_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_no_secret_keys(item, f"{path}[{index}]")


def json_safe(value: Any, name: str, *, reject_secrets: bool = True) -> Any:
    copied = _json_copy(value, name)
    if reject_secrets:
        assert_no_secret_keys(copied, name)
    return copied


def clean_text(
    value: Any,
    name: str,
    *,
    minimum: int = 1,
    maximum: int = 2000,
) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    normalized = value.strip()
    if not (minimum <= len(normalized) <= maximum):
        raise ValueError(
            f"{name} must contain {minimum}..{maximum} characters"
        )
    return normalized


def optional_text(
    value: Any,
    name: str,
    *,
    maximum: int = 2000,
) -> str | None:
    if value is None:
        return None
    return clean_text(
        value,
        name,
        minimum=1,
        maximum=maximum,
    )


@dataclass(frozen=True, slots=True)
class StateTransition:
    transition_id: str
    project_id: str
    revision: int
    from_state: ProjectState
    to_state: ProjectState
    reason: str
    actor: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "transition_id",
            validate_id(self.transition_id, "transition_id"),
        )
        object.__setattr__(
            self,
            "project_id",
            validate_id(self.project_id, "project_id"),
        )
        if isinstance(self.revision, bool) or not isinstance(self.revision, int):
            raise TypeError("revision must be an integer")
        if self.revision <= 0:
            raise ValueError("revision must be positive")
        object.__setattr__(
            self,
            "from_state",
            ProjectState(self.from_state),
        )
        object.__setattr__(
            self,
            "to_state",
            ProjectState(self.to_state),
        )
        object.__setattr__(
            self,
            "reason",
            clean_text(self.reason, "reason", maximum=1000),
        )
        object.__setattr__(
            self,
            "actor",
            clean_text(self.actor, "actor", maximum=128),
        )
        object.__setattr__(
            self,
            "metadata",
            json_safe(self.metadata, "metadata"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "project_id": self.project_id,
            "revision": self.revision,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "reason": self.reason,
            "actor": self.actor,
            "created_at": self.created_at,
            "metadata": copy.deepcopy(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class JobRecord:
    job_id: str
    project_id: str
    job_type: str
    status: JobStatus
    progress: int
    message: str | None
    resource_class: ResourceClass
    payload: dict[str, Any]
    result: Any
    error_type: str | None
    error_message: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    updated_at: str
    owner_id: str | None
    retry_of_job_id: str | None
    attempt: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "job_id",
            validate_id(self.job_id, "job_id"),
        )
        object.__setattr__(
            self,
            "project_id",
            validate_id(self.project_id, "project_id"),
        )
        object.__setattr__(
            self,
            "job_type",
            validate_id(self.job_type, "job_type"),
        )
        object.__setattr__(
            self,
            "status",
            JobStatus(self.status),
        )
        object.__setattr__(
            self,
            "resource_class",
            ResourceClass(self.resource_class),
        )
        if isinstance(self.progress, bool) or not isinstance(self.progress, int):
            raise TypeError("progress must be an integer")
        if not 0 <= self.progress <= 100:
            raise ValueError("progress must be between 0 and 100")
        object.__setattr__(
            self,
            "message",
            optional_text(self.message, "message"),
        )
        object.__setattr__(
            self,
            "payload",
            json_safe(self.payload, "payload"),
        )
        if self.result is not None:
            object.__setattr__(
                self,
                "result",
                json_safe(self.result, "result"),
            )
        object.__setattr__(
            self,
            "error_type",
            optional_text(self.error_type, "error_type", maximum=256),
        )
        object.__setattr__(
            self,
            "error_message",
            optional_text(self.error_message, "error_message", maximum=4000),
        )
        object.__setattr__(
            self,
            "owner_id",
            optional_text(self.owner_id, "owner_id", maximum=512),
        )
        if self.retry_of_job_id is not None:
            object.__setattr__(
                self,
                "retry_of_job_id",
                validate_id(self.retry_of_job_id, "retry_of_job_id"),
            )
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int):
            raise TypeError("attempt must be an integer")
        if self.attempt <= 0:
            raise ValueError("attempt must be positive")

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_JOB_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "project_id": self.project_id,
            "job_type": self.job_type,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "resource_class": self.resource_class.value,
            "payload": copy.deepcopy(self.payload),
            "result": copy.deepcopy(self.result),
            "error_type": self.error_type,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "updated_at": self.updated_at,
            "owner_id": self.owner_id,
            "retry_of_job_id": self.retry_of_job_id,
            "attempt": self.attempt,
        }


@dataclass(frozen=True, slots=True)
class JobEvent:
    sequence: int
    job_id: str
    status: JobStatus
    progress: int
    message: str | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "job_id": self.job_id,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "created_at": self.created_at,
        }


def now_iso() -> str:
    return utc_now_iso()
