from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import dataclass
from typing import Any

from app.services.centinela.orchestration import (
    JobContext,
    JobManager,
    JobStatus,
    ProjectState,
    ProjectStateMachine,
    ResourceClass,
)
from app.services.centinela.orchestration.models import json_safe
from app.services.centinela.project_foundation import ArtifactRef, ArtifactStore

from .models import (
    PRODUCTION_SPINE_VERSION,
    ProductionStatus,
    ScheduleDisposition,
    SpineStage,
    StageArtifact,
    StageBinding,
    StageDescriptor,
    StageDisposition,
    StageResult,
    StageSchedule,
)
from .persistence import ProductionSpineDB


class ProductionSpineError(RuntimeError):
    pass


class StageUnavailableError(ProductionSpineError):
    pass


class StageStateError(ProductionSpineError):
    pass


class StageConflictError(ProductionSpineError):
    pass


class StageOutputError(ProductionSpineError):
    pass


_RESOURCE_RANK = {
    ResourceClass.LIGHT: 0,
    ResourceClass.MEDIUM: 1,
    ResourceClass.HEAVY: 2,
    ResourceClass.EXCLUSIVE: 3,
}


STAGE_DESCRIPTORS: dict[SpineStage, StageDescriptor] = {
    SpineStage.RESEARCH: StageDescriptor(
        SpineStage.RESEARCH,
        ProjectState.DRAFT,
        ProjectState.RESEARCH_READY,
        ("fact_lock",),
        ResourceClass.LIGHT,
        "R3/existing astronomy research",
    ),
    SpineStage.SCRIPT: StageDescriptor(
        SpineStage.SCRIPT,
        ProjectState.RESEARCH_READY,
        ProjectState.SCRIPT_READY,
        ("final_script",),
        ResourceClass.MEDIUM,
        "R6 Writer Room",
    ),
    SpineStage.SCENES: StageDescriptor(
        SpineStage.SCENES,
        ProjectState.SCRIPT_READY,
        ProjectState.SCENES_READY,
        ("scene_plan",),
        ResourceClass.MEDIUM,
        "existing Astronomy/Cinematic Directors",
    ),
    SpineStage.MEDIA: StageDescriptor(
        SpineStage.MEDIA,
        ProjectState.SCENES_READY,
        ProjectState.MEDIA_READY,
        ("material_selection",),
        ResourceClass.MEDIUM,
        "R4 Media Resolver",
    ),
    SpineStage.AUDIO: StageDescriptor(
        SpineStage.AUDIO,
        ProjectState.MEDIA_READY,
        ProjectState.AUDIO_READY,
        ("audio_bundle",),
        ResourceClass.HEAVY,
        "R7 audio/subtitle executors",
    ),
    SpineStage.VIDEO_BASE: StageDescriptor(
        SpineStage.VIDEO_BASE,
        ProjectState.AUDIO_READY,
        ProjectState.VIDEO_BASE_READY,
        ("video_base_manifest",),
        ResourceClass.HEAVY,
        "existing Video Base renderer",
    ),
    SpineStage.REVIEW_PREP: StageDescriptor(
        SpineStage.REVIEW_PREP,
        ProjectState.VIDEO_BASE_READY,
        ProjectState.READY_FOR_HUMAN_REVIEW,
        ("review_packet",),
        ResourceClass.LIGHT,
        "R7/R8 quality and review preparation",
    ),
    SpineStage.PUBLICATION_PACKAGE: StageDescriptor(
        SpineStage.PUBLICATION_PACKAGE,
        ProjectState.FINAL_APPROVED,
        ProjectState.PUBLICATION_PACKAGE_READY,
        ("publication_package_manifest",),
        ResourceClass.LIGHT,
        "R8 manual publication package",
    ),
}

_STATE_TO_NEXT_STAGE = {
    descriptor.source_state: stage for stage, descriptor in STAGE_DESCRIPTORS.items()
}

_PREVIOUS_STAGE = {
    SpineStage.SCRIPT: SpineStage.RESEARCH,
    SpineStage.SCENES: SpineStage.SCRIPT,
    SpineStage.MEDIA: SpineStage.SCENES,
    SpineStage.AUDIO: SpineStage.MEDIA,
    SpineStage.VIDEO_BASE: SpineStage.AUDIO,
    SpineStage.REVIEW_PREP: SpineStage.VIDEO_BASE,
    SpineStage.PUBLICATION_PACKAGE: None,
    SpineStage.RESEARCH: None,
}


class _DefaultResourceLease:
    def acquire(self, component: str, resource_class: ResourceClass, timeout_seconds: float):
        from app.models.video_base import ResourceClass as LegacyResourceClass
        from app.services.resource_governor import governor

        return governor.acquire(
            component,
            LegacyResourceClass(resource_class.value),
            timeout_seconds=timeout_seconds,
        )


@dataclass(slots=True)
class StageExecutionContext:
    store: ArtifactStore
    job_context: JobContext
    project_id: str
    stage: SpineStage
    fingerprint: str
    input_artifacts: tuple[ArtifactRef, ...]
    previous_receipt: ArtifactRef | None

    def report_progress(self, progress: int, message: str | None = None):
        return self.job_context.report_progress(progress, message)

    def check_cancelled(self) -> None:
        self.job_context.check_cancelled()


class ProductionSpine:
    """Executable application layer joining R1 artifacts, R2 state/jobs and existing services."""

    def __init__(
        self,
        store: ArtifactStore,
        *,
        state_machine: ProjectStateMachine | None = None,
        jobs: JobManager | None = None,
        resource_lease: Any | None = None,
        max_workers: int = 2,
        allow_network_adapters: bool = False,
        allow_exclusive_adapters: bool = False,
        resource_timeout_seconds: float = 300.0,
    ) -> None:
        self.store = store
        self.state_machine = state_machine or ProjectStateMachine(store)
        self.jobs = jobs or JobManager(store, max_workers=max_workers, thread_name_prefix="centinela-spine")
        self._owns_jobs = jobs is None
        self.db = ProductionSpineDB(store)
        self.resource_lease = resource_lease or _DefaultResourceLease()
        self.allow_network_adapters = bool(allow_network_adapters)
        self.allow_exclusive_adapters = bool(allow_exclusive_adapters)
        self.resource_timeout_seconds = max(0.1, float(resource_timeout_seconds))
        self._bindings: dict[SpineStage, StageBinding] = {}
        self._lock = threading.RLock()

        for stage in STAGE_DESCRIPTORS:
            self.jobs.register_handler(self._job_type(stage), self._make_job_handler(stage))

    def __enter__(self) -> "ProductionSpine":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.shutdown(wait=True)

    @staticmethod
    def _job_type(stage: SpineStage) -> str:
        return f"centinela.spine.{stage.value.lower()}"

    def _make_job_handler(self, stage: SpineStage):
        def handler(context: JobContext, payload: dict[str, Any]) -> dict[str, Any]:
            return self._run_stage_job(stage, context, payload)

        return handler

    def register_adapter(self, stage: SpineStage | str, binding: StageBinding) -> None:
        normalized = SpineStage(stage)
        if not isinstance(binding, StageBinding):
            raise TypeError("binding must be StageBinding")
        descriptor = STAGE_DESCRIPTORS[normalized]
        if _RESOURCE_RANK[binding.resource_class] < _RESOURCE_RANK[descriptor.minimum_resource_class]:
            raise ValueError(
                f"{normalized.value} requires at least {descriptor.minimum_resource_class.value}"
            )
        if binding.resource_class == ResourceClass.EXCLUSIVE and not self.allow_exclusive_adapters:
            raise ValueError("EXCLUSIVE adapters require explicit allow_exclusive_adapters=True")
        if binding.invokes_network and not self.allow_network_adapters:
            raise ValueError("network adapters require explicit allow_network_adapters=True")
        if binding.auto_publication:
            raise ValueError("automatic publication is forbidden")
        with self._lock:
            self._bindings[normalized] = binding

    def unregister_adapter(self, stage: SpineStage | str) -> None:
        with self._lock:
            self._bindings.pop(SpineStage(stage), None)

    def _binding(self, stage: SpineStage) -> StageBinding | None:
        with self._lock:
            return self._bindings.get(stage)

    def _previous_receipt(self, project_id: str, stage: SpineStage) -> ArtifactRef | None:
        if stage == SpineStage.PUBLICATION_PACKAGE:
            reviews = self.store.list_artifacts(
                project_id, artifact_type="human_review_decision"
            )
            approved = [ref for ref in reviews if ref.metadata.get("approved") is True]
            return approved[-1] if approved else None
        previous = _PREVIOUS_STAGE[stage]
        if previous is None:
            return None
        matches = [
            ref
            for ref in self.store.list_artifacts(project_id, artifact_type="spine_stage_receipt")
            if ref.metadata.get("spine_stage") == previous.value
        ]
        return matches[-1] if matches else None

    def _fingerprint(
        self,
        project_id: str,
        stage: SpineStage,
        request_payload: dict[str, Any],
        input_ids: tuple[str, ...],
    ) -> str:
        refs = [self.store.get_artifact(project_id, item) for item in input_ids]
        previous = self._previous_receipt(project_id, stage)
        stable = {
            "version": PRODUCTION_SPINE_VERSION,
            "project_id": project_id,
            "stage": stage.value,
            "request": json_safe(request_payload, "stage_request"),
            "inputs": [(ref.artifact_id, ref.sha256) for ref in refs],
            "previous_receipt": None
            if previous is None
            else (previous.artifact_id, previous.sha256),
        }
        raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()

    def _matching_receipt(
        self,
        project_id: str,
        stage: SpineStage,
        fingerprint: str,
    ) -> ArtifactRef | None:
        for ref in reversed(
            self.store.list_artifacts(project_id, artifact_type="spine_stage_receipt")
        ):
            if (
                ref.metadata.get("spine_stage") == stage.value
                and ref.metadata.get("spine_fingerprint") == fingerprint
            ):
                payload = self.store.read_json(project_id, ref.artifact_id)
                outputs = payload.get("output_artifact_ids") if isinstance(payload, dict) else None
                if not isinstance(outputs, list) or not outputs:
                    continue
                try:
                    for artifact_id in outputs:
                        self.store.read_bytes(project_id, str(artifact_id), verify_integrity=True)
                except Exception:
                    continue
                return ref
        return None

    def _latest_side_stage(self, project_id: str) -> SpineStage | None:
        history = self.state_machine.history(project_id)
        if not history:
            return None
        metadata = history[-1].metadata
        stage = metadata.get("spine_stage") if isinstance(metadata, dict) else None
        try:
            return SpineStage(stage) if stage else None
        except ValueError:
            return None

    def _resume_if_side_state(self, project_id: str, stage: SpineStage) -> ProjectState:
        current = self.state_machine.current_state(project_id)
        if current not in {ProjectState.NEEDS_INPUT, ProjectState.BLOCKED}:
            return current
        if self._latest_side_stage(project_id) != stage:
            raise StageStateError(
                f"project is {current.value} for another stage; explicit resolution required"
            )
        descriptor = STAGE_DESCRIPTORS[stage]
        self.state_machine.transition(
            project_id,
            descriptor.source_state,
            reason=f"resume {stage.value} after capability/input resolution",
            actor="centinela.production_spine",
            metadata={"spine_stage": stage.value, "resume": True},
            expected_state=current,
        )
        return descriptor.source_state

    def _active_stage_jobs(self, project_id: str, stage: SpineStage):
        active = {
            JobStatus.QUEUED,
            JobStatus.RUNNING,
            JobStatus.CANCEL_REQUESTED,
        }
        return [
            item
            for item in self.jobs.list_jobs(project_id=project_id)
            if item.job_type == self._job_type(stage) and item.status in active
        ]

    def schedule_stage(
        self,
        project_id: str,
        stage: SpineStage | str,
        *,
        request: dict[str, Any] | None = None,
        input_artifact_ids: tuple[str, ...] = (),
        auto_start: bool = True,
    ) -> StageSchedule:
        normalized = SpineStage(stage)
        descriptor = STAGE_DESCRIPTORS[normalized]
        request_payload = json_safe(request or {}, "stage_request")
        inputs = tuple(str(item) for item in input_artifact_ids)
        if len(set(inputs)) != len(inputs):
            raise ValueError("input_artifact_ids must be unique")
        for item in inputs:
            self.store.get_artifact(project_id, item)

        current = self.state_machine.current_state(project_id)
        fingerprint = self._fingerprint(project_id, normalized, request_payload, inputs)
        reusable = self._matching_receipt(project_id, normalized, fingerprint)
        binding = self._binding(normalized)

        if current in {ProjectState.NEEDS_INPUT, ProjectState.BLOCKED}:
            if self._latest_side_stage(project_id) != normalized:
                raise StageStateError(
                    f"project is {current.value} for another stage; explicit resolution required"
                )
            if reusable is None and binding is None:
                return StageSchedule(
                    normalized,
                    ScheduleDisposition.NEEDS_INPUT,
                    current,
                    fingerprint=fingerprint,
                    reason=f"adapter required; roadmap owner: {descriptor.future_owner}",
                )
            current = self._resume_if_side_state(project_id, normalized)

        if current != descriptor.source_state:
            raise StageStateError(
                f"{normalized.value} requires {descriptor.source_state.value}; project is {current.value}"
            )

        if reusable is None and binding is None:
            self.state_machine.transition(
                project_id,
                ProjectState.NEEDS_INPUT,
                reason=f"no adapter registered for {normalized.value}",
                actor="centinela.production_spine",
                metadata={
                    "spine_stage": normalized.value,
                    "missing_adapter": True,
                    "future_owner": descriptor.future_owner,
                },
                expected_state=descriptor.source_state,
            )
            return StageSchedule(
                normalized,
                ScheduleDisposition.NEEDS_INPUT,
                ProjectState.NEEDS_INPUT,
                fingerprint=fingerprint,
                reason=f"adapter required; roadmap owner: {descriptor.future_owner}",
            )

        active = self._active_stage_jobs(project_id, normalized)
        if active:
            existing = active[0]
            if existing.payload.get("fingerprint") == fingerprint:
                return StageSchedule(
                    normalized,
                    ScheduleDisposition.EXISTING_JOB,
                    current,
                    job_id=existing.job_id,
                    fingerprint=fingerprint,
                    reason="matching active stage job already exists",
                )
            raise StageConflictError(
                f"another active {normalized.value} job exists with different inputs"
            )

        resource = binding.resource_class if binding is not None else descriptor.minimum_resource_class
        payload = {
            "stage": normalized.value,
            "request": request_payload,
            "input_artifact_ids": list(inputs),
            "fingerprint": fingerprint,
        }
        try:
            job = self.jobs.enqueue(
                project_id,
                self._job_type(normalized),
                payload=payload,
                resource_class=resource,
                message=f"{normalized.value} queued",
                auto_start=auto_start,
            )
        except sqlite3.IntegrityError as exc:
            active = self._active_stage_jobs(project_id, normalized)
            if active and active[0].payload.get("fingerprint") == fingerprint:
                job = active[0]
                disposition = ScheduleDisposition.EXISTING_JOB
            else:
                raise StageConflictError("concurrent stage scheduling conflict") from exc
        else:
            disposition = ScheduleDisposition.QUEUED

        return StageSchedule(
            normalized,
            disposition,
            current,
            job_id=job.job_id,
            fingerprint=fingerprint,
        )

    def _base_dependencies(
        self,
        project_id: str,
        stage: SpineStage,
        explicit_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        ordered: list[str] = []
        previous = self._previous_receipt(project_id, stage)
        if previous is not None:
            ordered.append(previous.artifact_id)
        ordered.extend(explicit_ids)
        return tuple(dict.fromkeys(ordered))

    def _persist_artifacts(
        self,
        context: StageExecutionContext,
        binding: StageBinding,
        artifacts: tuple[StageArtifact, ...],
        *,
        disposition: StageDisposition,
    ) -> list[ArtifactRef]:
        base_inputs = self._base_dependencies(
            context.project_id,
            context.stage,
            tuple(ref.artifact_id for ref in context.input_artifacts),
        )
        refs: list[ArtifactRef] = []
        for item in artifacts:
            context.check_cancelled()
            dependencies = tuple(dict.fromkeys((*base_inputs, *item.input_artifact_ids)))
            provenance = {
                **item.provenance,
                "production_spine_version": PRODUCTION_SPINE_VERSION,
                "spine_stage": context.stage.value,
                "spine_fingerprint": context.fingerprint,
                "spine_job_id": context.job_context.job_id,
                "adapter_id": binding.adapter_id,
                "stage_disposition": disposition.value,
            }
            metadata = {
                **item.metadata,
                "spine_stage": context.stage.value,
                "spine_fingerprint": context.fingerprint,
            }
            producer = f"centinela.production_spine.{binding.adapter_id}"
            if item.payload is not None:
                ref = self.store.put_json(
                    context.project_id,
                    item.artifact_type,
                    item.payload,
                    producer=producer,
                    artifact_id=item.artifact_id,
                    producer_version=binding.producer_version,
                    input_artifact_ids=dependencies,
                    provenance=provenance,
                    metadata=metadata,
                )
            else:
                ref = self.store.ingest_file(
                    context.project_id,
                    item.artifact_type,
                    item.source_path,
                    producer=producer,
                    artifact_id=item.artifact_id,
                    producer_version=binding.producer_version,
                    input_artifact_ids=dependencies,
                    provenance=provenance,
                    metadata=metadata,
                )
            refs.append(ref)
        return refs

    def _write_receipt(
        self,
        context: StageExecutionContext,
        binding: StageBinding,
        outputs: list[ArtifactRef],
        result: StageResult,
    ) -> ArtifactRef:
        descriptor = STAGE_DESCRIPTORS[context.stage]
        payload = {
            "version": PRODUCTION_SPINE_VERSION,
            "stage": context.stage.value,
            "fingerprint": context.fingerprint,
            "adapter_id": binding.adapter_id,
            "source_state": descriptor.source_state.value,
            "target_state": descriptor.target_state.value,
            "required_artifact_types": list(descriptor.required_artifact_types),
            "output_artifact_ids": [ref.artifact_id for ref in outputs],
            "output_sha256": {ref.artifact_id: ref.sha256 for ref in outputs},
            "details": result.details,
        }
        return self.store.put_json(
            context.project_id,
            "spine_stage_receipt",
            payload,
            producer="centinela.production_spine",
            producer_version=PRODUCTION_SPINE_VERSION,
            input_artifact_ids=tuple(ref.artifact_id for ref in outputs),
            provenance={
                "spine_stage": context.stage.value,
                "spine_fingerprint": context.fingerprint,
                "spine_job_id": context.job_context.job_id,
                "adapter_id": binding.adapter_id,
            },
            metadata={
                "spine_stage": context.stage.value,
                "spine_fingerprint": context.fingerprint,
            },
        )

    def _transition_side_state(
        self,
        project_id: str,
        stage: SpineStage,
        disposition: StageDisposition,
        message: str,
        details: dict[str, Any],
    ) -> ProjectState:
        target = (
            ProjectState.NEEDS_INPUT
            if disposition == StageDisposition.NEEDS_INPUT
            else ProjectState.BLOCKED
        )
        descriptor = STAGE_DESCRIPTORS[stage]
        self.state_machine.transition(
            project_id,
            target,
            reason=message,
            actor="centinela.production_spine",
            metadata={"spine_stage": stage.value, "details": details},
            expected_state=descriptor.source_state,
        )
        return target

    def _run_stage_job(
        self,
        stage: SpineStage,
        job_context: JobContext,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        descriptor = STAGE_DESCRIPTORS[stage]
        if payload.get("stage") != stage.value:
            raise StageOutputError("persisted job stage does not match handler")
        request_payload = json_safe(payload.get("request") or {}, "stage_request")
        input_ids = tuple(payload.get("input_artifact_ids") or ())
        fingerprint = str(payload.get("fingerprint") or "")
        if not fingerprint:
            raise StageOutputError("stage fingerprint is missing")

        project_id = self.jobs.get_job(job_context.job_id).project_id
        current = self.state_machine.current_state(project_id)
        if current != descriptor.source_state:
            if current == descriptor.target_state:
                return {"disposition": "ALREADY_ADVANCED", "state": current.value}
            raise StageStateError(
                f"job expected {descriptor.source_state.value}; project is {current.value}"
            )

        expected_fingerprint = self._fingerprint(project_id, stage, request_payload, input_ids)
        if expected_fingerprint != fingerprint:
            raise StageConflictError("stage input fingerprint changed before execution")

        reusable = self._matching_receipt(project_id, stage, fingerprint)
        if reusable is not None:
            self.state_machine.transition(
                project_id,
                descriptor.target_state,
                reason=f"reuse durable receipt for {stage.value}",
                actor="centinela.production_spine",
                metadata={
                    "spine_stage": stage.value,
                    "receipt_artifact_id": reusable.artifact_id,
                    "reused": True,
                },
                expected_state=descriptor.source_state,
            )
            return {
                "disposition": "REUSED",
                "state": descriptor.target_state.value,
                "receipt_artifact_id": reusable.artifact_id,
            }

        binding = self._binding(stage)
        if binding is None:
            state = self._transition_side_state(
                project_id,
                stage,
                StageDisposition.NEEDS_INPUT,
                f"adapter unavailable for {stage.value}",
                {"future_owner": descriptor.future_owner},
            )
            return {"disposition": StageDisposition.NEEDS_INPUT.value, "state": state.value}

        input_refs = tuple(self.store.get_artifact(project_id, item) for item in input_ids)
        previous = self._previous_receipt(project_id, stage)
        execution = StageExecutionContext(
            self.store,
            job_context,
            project_id,
            stage,
            fingerprint,
            input_refs,
            previous,
        )

        job_context.report_progress(1, f"{stage.value}: waiting for resource lease")
        with self.resource_lease.acquire(
            self._job_type(stage),
            binding.resource_class,
            self.resource_timeout_seconds,
        ):
            job_context.check_cancelled()
            job_context.report_progress(10, f"{stage.value}: adapter running")
            result = binding.handler(execution, request_payload)
            if not isinstance(result, StageResult):
                raise StageOutputError("stage adapter must return StageResult")
            job_context.check_cancelled()

            if result.disposition != StageDisposition.COMPLETE:
                refs = self._persist_artifacts(
                    execution,
                    binding,
                    result.artifacts,
                    disposition=result.disposition,
                )
                state = self._transition_side_state(
                    project_id,
                    stage,
                    result.disposition,
                    result.message,
                    result.details,
                )
                return {
                    "disposition": result.disposition.value,
                    "state": state.value,
                    "evidence_artifact_ids": [ref.artifact_id for ref in refs],
                }

            types = {item.artifact_type for item in result.artifacts}
            missing = [item for item in descriptor.required_artifact_types if item not in types]
            if missing:
                raise StageOutputError(
                    f"{stage.value} missing required output artifact types: {missing}"
                )
            if not result.artifacts:
                raise StageOutputError("complete stage must produce artifacts")

            job_context.report_progress(65, f"{stage.value}: persisting artifacts")
            outputs = self._persist_artifacts(
                execution,
                binding,
                result.artifacts,
                disposition=result.disposition,
            )
            job_context.check_cancelled()
            receipt = self._write_receipt(execution, binding, outputs, result)
            job_context.check_cancelled()
            job_context.report_progress(90, f"{stage.value}: advancing project state")
            self.state_machine.transition(
                project_id,
                descriptor.target_state,
                reason=result.message,
                actor="centinela.production_spine",
                metadata={
                    "spine_stage": stage.value,
                    "receipt_artifact_id": receipt.artifact_id,
                    "adapter_id": binding.adapter_id,
                },
                expected_state=descriptor.source_state,
            )

        return {
            "disposition": StageDisposition.COMPLETE.value,
            "state": descriptor.target_state.value,
            "receipt_artifact_id": receipt.artifact_id,
            "output_artifact_ids": [ref.artifact_id for ref in outputs],
        }

    def record_human_review(
        self,
        project_id: str,
        *,
        approved: bool,
        reviewer: str,
        notes: str,
    ) -> ArtifactRef:
        if not isinstance(approved, bool):
            raise TypeError("approved must be bool")
        current = self.state_machine.current_state(project_id)
        if current == ProjectState.NEEDS_INPUT and self._latest_side_stage(project_id) is None:
            history = self.state_machine.history(project_id)
            if history and history[-1].metadata.get("human_review"):
                self.state_machine.transition(
                    project_id,
                    ProjectState.READY_FOR_HUMAN_REVIEW,
                    reason="resume human review",
                    actor="centinela.production_spine",
                    metadata={"human_review": True, "resume": True},
                    expected_state=ProjectState.NEEDS_INPUT,
                )
                current = ProjectState.READY_FOR_HUMAN_REVIEW
        if current != ProjectState.READY_FOR_HUMAN_REVIEW:
            raise StageStateError("human review requires READY_FOR_HUMAN_REVIEW")

        reviewer = str(reviewer).strip()
        notes = str(notes).strip()
        if not reviewer or not notes:
            raise ValueError("reviewer and notes are required")
        review_receipts = [
            item
            for item in self.store.list_artifacts(
                project_id, artifact_type="spine_stage_receipt"
            )
            if item.metadata.get("spine_stage") == SpineStage.REVIEW_PREP.value
        ]
        previous = review_receipts[-1] if review_receipts else None
        inputs = () if previous is None else (previous.artifact_id,)
        ref = self.store.put_json(
            project_id,
            "human_review_decision",
            {"approved": approved, "reviewer": reviewer, "notes": notes},
            producer="centinela.human_review",
            producer_version=PRODUCTION_SPINE_VERSION,
            input_artifact_ids=inputs,
            provenance={"explicit_human_decision": True},
            metadata={"approved": approved},
        )
        target = ProjectState.FINAL_APPROVED if approved else ProjectState.NEEDS_INPUT
        self.state_machine.transition(
            project_id,
            target,
            reason="human review approved" if approved else "human review rejected",
            actor=reviewer,
            metadata={
                "human_review": True,
                "decision_artifact_id": ref.artifact_id,
                "approved": approved,
            },
            expected_state=ProjectState.READY_FOR_HUMAN_REVIEW,
        )
        return ref

    def project_status(self, project_id: str) -> ProductionStatus:
        state = self.state_machine.current_state(project_id)
        if state in {ProjectState.NEEDS_INPUT, ProjectState.BLOCKED}:
            stage = self._latest_side_stage(project_id)
            if stage is not None:
                binding = self._binding(stage)
                action = (
                    f"Resolve {stage.value} input/capability and reschedule"
                    if binding is not None
                    else f"Register {stage.value} adapter ({STAGE_DESCRIPTORS[stage].future_owner})"
                )
                return ProductionStatus(
                    project_id,
                    state,
                    stage,
                    action,
                    binding is not None,
                    self._active_stage_job_id(project_id, stage),
                )
            return ProductionStatus(project_id, state, None, "Human review input required", False, None)

        if state == ProjectState.READY_FOR_HUMAN_REVIEW:
            return ProductionStatus(project_id, state, None, "Explicit human review required", False, None)
        if state == ProjectState.PUBLICATION_PACKAGE_READY:
            return ProductionStatus(project_id, state, None, "Manual publication may be prepared outside the spine", False, None)
        if state in {ProjectState.FAILED, ProjectState.CANCELLED}:
            return ProductionStatus(project_id, state, None, "Terminal project state", False, None)

        stage = _STATE_TO_NEXT_STAGE.get(state)
        if stage is None:
            return ProductionStatus(project_id, state, None, "No automatic next action", False, None)
        binding = self._binding(stage)
        return ProductionStatus(
            project_id,
            state,
            stage,
            f"Schedule {stage.value}" if binding is not None else f"Adapter required: {STAGE_DESCRIPTORS[stage].future_owner}",
            binding is not None,
            self._active_stage_job_id(project_id, stage),
        )

    def _active_stage_job_id(self, project_id: str, stage: SpineStage) -> str | None:
        active = self._active_stage_jobs(project_id, stage)
        return active[0].job_id if active else None

    def recover(self, *, project_id: str | None = None) -> dict[str, Any]:
        transitions = self.state_machine.recover_pending_transitions(project_id)
        interrupted = self.jobs.recover_interrupted_jobs()
        queued = self.jobs.resume_queued(project_id=project_id)
        return {
            "transitions": transitions,
            "interrupted_job_ids": interrupted,
            "resumed_queued_job_ids": queued,
        }

    def wait(self, job_id: str, timeout: float | None = None):
        return self.jobs.wait(job_id, timeout=timeout)

    def shutdown(self, *, wait: bool = True) -> None:
        if self._owns_jobs:
            self.jobs.shutdown(wait=wait)
