from __future__ import annotations

from typing import Any

from .models import ProjectState
from .state_machine import InvalidTransitionError
from .state_machine import ProjectStateMachine as _RawProjectStateMachine

_STRUCTURED_REVIEW_TYPE = "human_final_review_record"
_STRUCTURED_REVIEW_PRODUCER = "centinela.human_review.structured"
_SPINE_RECEIPT_TYPE = "spine_stage_receipt"
_SPINE_RECEIPT_PRODUCER = "centinela.production_spine"
_REVIEW_GATES = (
    "science_passed",
    "visual_passed",
    "audio_passed",
    "subtitles_passed",
    "rights_passed",
    "thumbnail_passed",
    "copy_passed",
)

_FORWARD_STAGE_REQUIREMENTS: dict[ProjectState, tuple[str, ProjectState, str]] = {
    ProjectState.RESEARCH_READY: ("RESEARCH", ProjectState.DRAFT, "fact_lock"),
    ProjectState.SCRIPT_READY: ("SCRIPT", ProjectState.RESEARCH_READY, "final_script"),
    ProjectState.SCENES_READY: ("SCENES", ProjectState.SCRIPT_READY, "scene_plan"),
    ProjectState.MEDIA_READY: ("MEDIA", ProjectState.SCENES_READY, "material_selection"),
    ProjectState.AUDIO_READY: ("AUDIO", ProjectState.MEDIA_READY, "audio_bundle"),
    ProjectState.VIDEO_BASE_READY: (
        "VIDEO_BASE",
        ProjectState.AUDIO_READY,
        "video_base_manifest",
    ),
    ProjectState.READY_FOR_HUMAN_REVIEW: (
        "REVIEW_PREP",
        ProjectState.VIDEO_BASE_READY,
        "review_packet",
    ),
    ProjectState.PUBLICATION_PACKAGE_READY: (
        "PUBLICATION_PACKAGE",
        ProjectState.FINAL_APPROVED,
        "publication_package_manifest",
    ),
}


class ProjectStateMachine(_RawProjectStateMachine):
    """State machine whose public forward progression is evidence-gated.

    The raw engine still owns ordering, durability and recovery semantics. This
    public wrapper additionally requires canonical ProductionSpine receipts for
    every automated forward stage and structured human-review evidence for
    FINAL_APPROVED. Caller metadata alone is never sufficient authority.
    """

    def _require_spine_stage_evidence(
        self,
        project_id: str,
        *,
        stage: str,
        source: ProjectState,
        target: ProjectState,
        required_output_type: str,
        metadata: dict[str, Any],
    ) -> None:
        if metadata.get("spine_stage") != stage:
            raise InvalidTransitionError(
                f"{target.value} requires ProductionSpine {stage} evidence"
            )

        receipt_id = metadata.get("receipt_artifact_id")
        if not isinstance(receipt_id, str) or not receipt_id.strip():
            raise InvalidTransitionError(
                f"{target.value} requires receipt_artifact_id"
            )

        try:
            receipt_ref = self.store.get_artifact(project_id, receipt_id)
            if receipt_ref.artifact_type != _SPINE_RECEIPT_TYPE:
                raise InvalidTransitionError(
                    f"{target.value} requires a spine_stage_receipt"
                )
            if receipt_ref.producer != _SPINE_RECEIPT_PRODUCER:
                raise InvalidTransitionError(
                    f"{stage} receipt has non-canonical producer"
                )

            fingerprint = receipt_ref.metadata.get("spine_fingerprint")
            if not isinstance(fingerprint, str) or not fingerprint.strip():
                raise InvalidTransitionError(
                    f"{stage} receipt is missing canonical fingerprint metadata"
                )

            provenance = receipt_ref.provenance
            adapter_id = provenance.get("adapter_id")
            spine_job_id = provenance.get("spine_job_id")
            if (
                receipt_ref.metadata.get("spine_stage") != stage
                or provenance.get("spine_stage") != stage
                or provenance.get("spine_fingerprint") != fingerprint
                or not isinstance(spine_job_id, str)
                or not spine_job_id.strip()
                or not isinstance(adapter_id, str)
                or not adapter_id.strip()
            ):
                raise InvalidTransitionError(
                    f"{stage} receipt has non-canonical ProductionSpine provenance"
                )

            receipt = self.store.read_json(
                project_id,
                receipt_id,
                verify_integrity=True,
            )
        except InvalidTransitionError:
            raise
        except Exception as exc:
            raise InvalidTransitionError(
                f"{target.value} requires an integrity-verified {stage} receipt"
            ) from exc

        if not isinstance(receipt, dict):
            raise InvalidTransitionError(f"{stage} receipt must be a JSON object")
        if receipt.get("stage") != stage:
            raise InvalidTransitionError(f"{stage} receipt has the wrong stage")
        if receipt.get("source_state") != source.value:
            raise InvalidTransitionError(f"{stage} receipt has the wrong source state")
        if receipt.get("target_state") != target.value:
            raise InvalidTransitionError(f"{stage} receipt has the wrong target state")
        if receipt.get("fingerprint") != fingerprint:
            raise InvalidTransitionError(
                f"{stage} receipt fingerprint does not match lineage"
            )
        if receipt.get("adapter_id") != adapter_id:
            raise InvalidTransitionError(
                f"{stage} receipt adapter does not match lineage"
            )

        required_types = receipt.get("required_artifact_types")
        if (
            not isinstance(required_types, list)
            or required_output_type not in required_types
        ):
            raise InvalidTransitionError(
                f"{stage} receipt does not require {required_output_type}"
            )

        output_ids = receipt.get("output_artifact_ids")
        if not isinstance(output_ids, list) or not output_ids:
            raise InvalidTransitionError(f"{stage} receipt has no outputs")
        normalized_output_ids = [str(output_id) for output_id in output_ids]
        if len(set(normalized_output_ids)) != len(normalized_output_ids):
            raise InvalidTransitionError(f"{stage} receipt contains duplicate outputs")
        if tuple(normalized_output_ids) != receipt_ref.input_artifact_ids:
            raise InvalidTransitionError(
                f"{stage} receipt lineage does not match its declared outputs"
            )

        required_output_found = False
        expected_output_producer = f"centinela.production_spine.{adapter_id}"
        try:
            for output_id in normalized_output_ids:
                output_ref = self.store.get_artifact(project_id, output_id)
                if (
                    output_ref.producer != expected_output_producer
                    or output_ref.metadata.get("spine_stage") != stage
                    or output_ref.metadata.get("spine_fingerprint") != fingerprint
                    or output_ref.provenance.get("spine_stage") != stage
                    or output_ref.provenance.get("spine_fingerprint") != fingerprint
                    or output_ref.provenance.get("adapter_id") != adapter_id
                ):
                    raise InvalidTransitionError(
                        f"{stage} output has non-canonical ProductionSpine lineage"
                    )
                self.store.read_bytes(
                    project_id,
                    output_id,
                    verify_integrity=True,
                )
                if output_ref.artifact_type == required_output_type:
                    required_output_found = True
        except InvalidTransitionError:
            raise
        except Exception as exc:
            raise InvalidTransitionError(
                f"{target.value} requires integrity-verified {stage} outputs"
            ) from exc

        if not required_output_found:
            raise InvalidTransitionError(
                f"{stage} receipt has no {required_output_type} output"
            )

    def _require_final_approval_evidence(
        self,
        project_id: str,
        metadata: dict[str, Any],
    ) -> None:
        if metadata.get("structured_review") is not True:
            raise InvalidTransitionError(
                "FINAL_APPROVED requires structured human-review authority"
            )
        if metadata.get("approved") is not True or metadata.get("decision") != "APPROVE":
            raise InvalidTransitionError(
                "FINAL_APPROVED requires an explicit APPROVE decision"
            )

        artifact_id = metadata.get("decision_artifact_id")
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            raise InvalidTransitionError(
                "FINAL_APPROVED requires decision_artifact_id"
            )

        reviews = self.store.list_artifacts(
            project_id,
            artifact_type=_STRUCTURED_REVIEW_TYPE,
        )
        if not reviews or reviews[-1].artifact_id != artifact_id:
            raise InvalidTransitionError(
                "FINAL_APPROVED requires the latest structured human-review record"
            )

        try:
            ref = self.store.get_artifact(project_id, artifact_id)
            if ref.artifact_type != _STRUCTURED_REVIEW_TYPE:
                raise InvalidTransitionError(
                    "FINAL_APPROVED decision artifact must be human_final_review_record"
                )
            if ref.producer != _STRUCTURED_REVIEW_PRODUCER:
                raise InvalidTransitionError(
                    "FINAL_APPROVED requires canonical structured-review provenance"
                )
            if (
                ref.provenance.get("explicit_human_decision") is not True
                or ref.provenance.get("structured_review") is not True
            ):
                raise InvalidTransitionError(
                    "FINAL_APPROVED requires canonical structured-review provenance"
                )
            if (
                ref.metadata.get("decision") != "APPROVE"
                or ref.metadata.get("all_required_gates_passed") is not True
            ):
                raise InvalidTransitionError(
                    "FINAL_APPROVED review metadata does not authorize approval"
                )

            review_receipts = [
                item
                for item in self.store.list_artifacts(
                    project_id,
                    artifact_type=_SPINE_RECEIPT_TYPE,
                )
                if item.metadata.get("spine_stage") == "REVIEW_PREP"
            ]
            if (
                not review_receipts
                or ref.input_artifact_ids != (review_receipts[-1].artifact_id,)
            ):
                raise InvalidTransitionError(
                    "FINAL_APPROVED review is not bound to the latest REVIEW_PREP receipt"
                )

            payload = self.store.read_json(
                project_id,
                artifact_id,
                verify_integrity=True,
            )
        except InvalidTransitionError:
            raise
        except Exception as exc:
            raise InvalidTransitionError(
                "FINAL_APPROVED requires integrity-verified structured review evidence"
            ) from exc

        if not isinstance(payload, dict) or payload.get("decision") != "APPROVE":
            raise InvalidTransitionError(
                "FINAL_APPROVED review evidence is not APPROVE"
            )
        if any(payload.get(gate) is not True for gate in _REVIEW_GATES):
            raise InvalidTransitionError(
                "FINAL_APPROVED requires all seven canonical review gates"
            )

    def _run_guards(
        self,
        manifest,
        current: ProjectState,
        target: ProjectState,
        metadata: dict[str, Any],
    ) -> None:
        if current not in {ProjectState.BLOCKED, ProjectState.NEEDS_INPUT}:
            requirement = _FORWARD_STAGE_REQUIREMENTS.get(target)
            if requirement is not None:
                stage, source, required_output_type = requirement
                self._require_spine_stage_evidence(
                    manifest.project_id,
                    stage=stage,
                    source=source,
                    target=target,
                    required_output_type=required_output_type,
                    metadata=metadata,
                )

        if target == ProjectState.FINAL_APPROVED:
            self._require_final_approval_evidence(manifest.project_id, metadata)

        super()._run_guards(manifest, current, target, metadata)
