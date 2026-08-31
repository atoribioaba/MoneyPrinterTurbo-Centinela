from __future__ import annotations

from typing import Any

from .models import ProjectState
from .state_machine import InvalidTransitionError
from .state_machine import ProjectStateMachine as _RawProjectStateMachine

_STRUCTURED_REVIEW_TYPE = "human_final_review_record"
_STRUCTURED_REVIEW_PRODUCER = "centinela.human_review.structured"
_PUBLICATION_RECEIPT_TYPE = "spine_stage_receipt"
_PUBLICATION_RECEIPT_PRODUCER = "centinela.production_spine"
_PUBLICATION_OUTPUT_TYPE = "publication_package_manifest"
_REVIEW_GATES = (
    "science_passed",
    "visual_passed",
    "audio_passed",
    "subtitles_passed",
    "rights_passed",
    "thumbnail_passed",
    "copy_passed",
)


class ProjectStateMachine(_RawProjectStateMachine):
    """Project state machine with mandatory evidence guards for protected targets.

    Optional caller-provided guards remain supported, but FINAL_APPROVED and
    PUBLICATION_PACKAGE_READY can never rely on optional guards or caller metadata
    alone. Durable ArtifactStore evidence and canonical lineage are verified before
    either transition.
    """

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

    def _require_publication_package_evidence(
        self,
        project_id: str,
        metadata: dict[str, Any],
    ) -> None:
        if metadata.get("spine_stage") != "PUBLICATION_PACKAGE":
            raise InvalidTransitionError(
                "PUBLICATION_PACKAGE_READY requires ProductionSpine publication evidence"
            )

        receipt_id = metadata.get("receipt_artifact_id")
        if not isinstance(receipt_id, str) or not receipt_id.strip():
            raise InvalidTransitionError(
                "PUBLICATION_PACKAGE_READY requires receipt_artifact_id"
            )

        try:
            receipt_ref = self.store.get_artifact(project_id, receipt_id)
            if receipt_ref.artifact_type != _PUBLICATION_RECEIPT_TYPE:
                raise InvalidTransitionError(
                    "PUBLICATION_PACKAGE_READY requires a spine_stage_receipt"
                )
            if receipt_ref.producer != _PUBLICATION_RECEIPT_PRODUCER:
                raise InvalidTransitionError(
                    "publication receipt has non-canonical producer"
                )
            fingerprint = receipt_ref.metadata.get("spine_fingerprint")
            if not isinstance(fingerprint, str) or not fingerprint.strip():
                raise InvalidTransitionError(
                    "publication receipt is missing canonical fingerprint metadata"
                )
            provenance = receipt_ref.provenance
            adapter_id = provenance.get("adapter_id")
            if (
                receipt_ref.metadata.get("spine_stage") != "PUBLICATION_PACKAGE"
                or provenance.get("spine_stage") != "PUBLICATION_PACKAGE"
                or provenance.get("spine_fingerprint") != fingerprint
                or not isinstance(provenance.get("spine_job_id"), str)
                or not str(provenance.get("spine_job_id")).strip()
                or not isinstance(adapter_id, str)
                or not adapter_id.strip()
            ):
                raise InvalidTransitionError(
                    "publication receipt has non-canonical ProductionSpine provenance"
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
                "PUBLICATION_PACKAGE_READY requires an integrity-verified receipt"
            ) from exc

        if not isinstance(receipt, dict):
            raise InvalidTransitionError("publication receipt must be a JSON object")
        if receipt.get("stage") != "PUBLICATION_PACKAGE":
            raise InvalidTransitionError("publication receipt has the wrong stage")
        if receipt.get("source_state") != ProjectState.FINAL_APPROVED.value:
            raise InvalidTransitionError("publication receipt has the wrong source state")
        if receipt.get("target_state") != ProjectState.PUBLICATION_PACKAGE_READY.value:
            raise InvalidTransitionError("publication receipt has the wrong target state")
        if receipt.get("fingerprint") != fingerprint:
            raise InvalidTransitionError("publication receipt fingerprint does not match lineage")
        if receipt.get("adapter_id") != adapter_id:
            raise InvalidTransitionError("publication receipt adapter does not match lineage")

        required_types = receipt.get("required_artifact_types")
        if not isinstance(required_types, list) or _PUBLICATION_OUTPUT_TYPE not in required_types:
            raise InvalidTransitionError(
                "publication receipt does not require publication_package_manifest"
            )

        output_ids = receipt.get("output_artifact_ids")
        if not isinstance(output_ids, list) or not output_ids:
            raise InvalidTransitionError("publication receipt has no outputs")
        normalized_output_ids = [str(output_id) for output_id in output_ids]
        if len(set(normalized_output_ids)) != len(normalized_output_ids):
            raise InvalidTransitionError("publication receipt contains duplicate outputs")
        if tuple(normalized_output_ids) != receipt_ref.input_artifact_ids:
            raise InvalidTransitionError(
                "publication receipt lineage does not match its declared outputs"
            )

        publication_manifest_found = False
        expected_output_producer = f"centinela.production_spine.{adapter_id}"
        try:
            for output_id in normalized_output_ids:
                output_ref = self.store.get_artifact(project_id, output_id)
                if (
                    output_ref.producer != expected_output_producer
                    or output_ref.metadata.get("spine_stage") != "PUBLICATION_PACKAGE"
                    or output_ref.metadata.get("spine_fingerprint") != fingerprint
                    or output_ref.provenance.get("spine_stage") != "PUBLICATION_PACKAGE"
                    or output_ref.provenance.get("spine_fingerprint") != fingerprint
                    or output_ref.provenance.get("adapter_id") != adapter_id
                ):
                    raise InvalidTransitionError(
                        "publication receipt output has non-canonical ProductionSpine lineage"
                    )
                self.store.read_bytes(
                    project_id,
                    output_id,
                    verify_integrity=True,
                )
                if output_ref.artifact_type == _PUBLICATION_OUTPUT_TYPE:
                    publication_manifest_found = True
        except InvalidTransitionError:
            raise
        except Exception as exc:
            raise InvalidTransitionError(
                "PUBLICATION_PACKAGE_READY requires integrity-verified receipt outputs"
            ) from exc

        if not publication_manifest_found:
            raise InvalidTransitionError(
                "publication receipt has no publication_package_manifest output"
            )

    def _run_guards(
        self,
        manifest,
        current: ProjectState,
        target: ProjectState,
        metadata: dict[str, Any],
    ) -> None:
        if target == ProjectState.FINAL_APPROVED:
            self._require_final_approval_evidence(manifest.project_id, metadata)
        elif target == ProjectState.PUBLICATION_PACKAGE_READY:
            self._require_publication_package_evidence(manifest.project_id, metadata)
        super()._run_guards(manifest, current, target, metadata)
