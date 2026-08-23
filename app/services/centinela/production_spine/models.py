from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.services.centinela.orchestration import ProjectState, ResourceClass
from app.services.centinela.orchestration.models import clean_text, json_safe
from app.services.centinela.project_foundation.models import validate_id

PRODUCTION_SPINE_VERSION = "production-spine-v0.1"


class SpineStage(StrEnum):
    RESEARCH = "RESEARCH"
    SCRIPT = "SCRIPT"
    SCENES = "SCENES"
    MEDIA = "MEDIA"
    AUDIO = "AUDIO"
    VIDEO_BASE = "VIDEO_BASE"
    REVIEW_PREP = "REVIEW_PREP"
    PUBLICATION_PACKAGE = "PUBLICATION_PACKAGE"


class StageDisposition(StrEnum):
    COMPLETE = "COMPLETE"
    NEEDS_INPUT = "NEEDS_INPUT"
    BLOCKED = "BLOCKED"


class ScheduleDisposition(StrEnum):
    QUEUED = "QUEUED"
    EXISTING_JOB = "EXISTING_JOB"
    NEEDS_INPUT = "NEEDS_INPUT"


@dataclass(frozen=True, slots=True)
class StageDescriptor:
    stage: SpineStage
    source_state: ProjectState
    target_state: ProjectState
    required_artifact_types: tuple[str, ...]
    minimum_resource_class: ResourceClass
    future_owner: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage", SpineStage(self.stage))
        object.__setattr__(self, "source_state", ProjectState(self.source_state))
        object.__setattr__(self, "target_state", ProjectState(self.target_state))
        object.__setattr__(
            self,
            "minimum_resource_class",
            ResourceClass(self.minimum_resource_class),
        )
        required = tuple(
            validate_id(item, "required_artifact_type")
            for item in self.required_artifact_types
        )
        if not required:
            raise ValueError("stage requires at least one artifact type")
        if len(set(required)) != len(required):
            raise ValueError("required artifact types must be unique")
        object.__setattr__(self, "required_artifact_types", required)
        object.__setattr__(
            self,
            "future_owner",
            clean_text(self.future_owner, "future_owner", maximum=128),
        )


@dataclass(frozen=True, slots=True)
class StageArtifact:
    artifact_type: str
    payload: Any | None = None
    source_path: str | None = None
    suffix: str = ".bin"
    artifact_id: str | None = None
    input_artifact_ids: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_type",
            validate_id(self.artifact_type, "artifact_type"),
        )
        has_payload = self.payload is not None
        has_source = self.source_path is not None
        if has_payload == has_source:
            raise ValueError("exactly one of payload or source_path is required")
        if has_payload:
            object.__setattr__(self, "payload", json_safe(self.payload, "artifact_payload"))
        else:
            source = clean_text(self.source_path, "source_path", maximum=4096)
            object.__setattr__(self, "source_path", str(Path(source)))
        if self.artifact_id is not None:
            object.__setattr__(
                self,
                "artifact_id",
                validate_id(self.artifact_id, "artifact_id"),
            )
        inputs = tuple(
            validate_id(item, "input_artifact_id")
            for item in self.input_artifact_ids
        )
        if len(set(inputs)) != len(inputs):
            raise ValueError("artifact input IDs must be unique")
        object.__setattr__(self, "input_artifact_ids", inputs)
        object.__setattr__(self, "provenance", json_safe(self.provenance, "artifact_provenance"))
        object.__setattr__(self, "metadata", json_safe(self.metadata, "artifact_metadata"))
        if not isinstance(self.suffix, str) or not self.suffix.startswith("."):
            raise ValueError("suffix must start with a dot")


@dataclass(frozen=True, slots=True)
class StageResult:
    disposition: StageDisposition
    artifacts: tuple[StageArtifact, ...] = ()
    message: str = "stage completed"
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "disposition", StageDisposition(self.disposition))
        artifacts = tuple(self.artifacts)
        if any(not isinstance(item, StageArtifact) for item in artifacts):
            raise TypeError("artifacts must contain StageArtifact values")
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "message", clean_text(self.message, "message", maximum=2000))
        object.__setattr__(self, "details", json_safe(self.details, "stage_details"))

    @classmethod
    def complete(
        cls,
        *artifacts: StageArtifact,
        message: str = "stage completed",
        details: dict[str, Any] | None = None,
    ) -> "StageResult":
        return cls(
            disposition=StageDisposition.COMPLETE,
            artifacts=tuple(artifacts),
            message=message,
            details=details or {},
        )

    @classmethod
    def needs_input(
        cls,
        message: str,
        *,
        artifacts: tuple[StageArtifact, ...] = (),
        details: dict[str, Any] | None = None,
    ) -> "StageResult":
        return cls(
            disposition=StageDisposition.NEEDS_INPUT,
            artifacts=artifacts,
            message=message,
            details=details or {},
        )

    @classmethod
    def blocked(
        cls,
        message: str,
        *,
        artifacts: tuple[StageArtifact, ...] = (),
        details: dict[str, Any] | None = None,
    ) -> "StageResult":
        return cls(
            disposition=StageDisposition.BLOCKED,
            artifacts=artifacts,
            message=message,
            details=details or {},
        )


StageHandler = Callable[[Any, dict[str, Any]], StageResult]


@dataclass(frozen=True, slots=True)
class StageBinding:
    adapter_id: str
    handler: StageHandler
    resource_class: ResourceClass
    producer_version: str | None = None
    invokes_network: bool = False
    invokes_llm: bool = False
    invokes_render: bool = False
    auto_publication: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "adapter_id", validate_id(self.adapter_id, "adapter_id"))
        if not callable(self.handler):
            raise TypeError("handler must be callable")
        object.__setattr__(self, "resource_class", ResourceClass(self.resource_class))
        if self.producer_version is not None:
            object.__setattr__(
                self,
                "producer_version",
                clean_text(self.producer_version, "producer_version", maximum=128),
            )
        for field_name in (
            "invokes_network",
            "invokes_llm",
            "invokes_render",
            "auto_publication",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be bool")


@dataclass(frozen=True, slots=True)
class StageSchedule:
    stage: SpineStage
    disposition: ScheduleDisposition
    project_state: ProjectState
    job_id: str | None = None
    fingerprint: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ProductionStatus:
    project_id: str
    state: ProjectState
    next_stage: SpineStage | None
    next_action: str
    adapter_registered: bool
    active_job_id: str | None
    architecture_freeze: bool = False
    auto_publication: bool = False
