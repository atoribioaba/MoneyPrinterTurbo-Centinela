from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.models.astronomy_director import AstronomyVideoPlan
from app.services.centinela.orchestration import JobCancelled, ResourceClass
from app.services.centinela.production_spine import (
    StageArtifact,
    StageBinding,
    StageResult,
)

from .models import MEDIA_RESOLVER_VERSION, MediaResolverRequest
from .resolver import MediaResolver, UNRESOLVED_SELECTION_STATUSES


class MediaResolverSpineAdapter:
    def __init__(self, resolver: MediaResolver | None = None) -> None:
        self.resolver = resolver or MediaResolver()

    @staticmethod
    def _plan_artifact(context: Any, payload: dict[str, Any]):
        explicit = payload.get("plan_artifact_id")
        if explicit is not None:
            ref = context.store.get_artifact(context.project_id, str(explicit))
            if ref.artifact_type != "scene_plan":
                raise ValueError("plan_artifact_id must reference artifact_type=scene_plan")
            return ref

        receipt = context.previous_receipt
        if receipt is None:
            return None

        receipt_payload = context.store.read_json(
            context.project_id,
            receipt.artifact_id,
        )
        output_ids = (
            receipt_payload.get("output_artifact_ids")
            if isinstance(receipt_payload, dict)
            else None
        )
        if not isinstance(output_ids, list):
            return None

        matches = []
        for artifact_id in output_ids:
            ref = context.store.get_artifact(context.project_id, str(artifact_id))
            if ref.artifact_type == "scene_plan":
                matches.append(ref)

        if len(matches) > 1:
            raise ValueError("previous SCENES receipt contains multiple scene_plan artifacts")
        return matches[0] if matches else None

    def __call__(self, context: Any, payload: dict[str, Any]) -> StageResult:
        try:
            plan_ref = self._plan_artifact(context, payload)
        except Exception as exc:
            return StageResult.blocked(
                "scene_plan artifact reference is invalid",
                details={
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1000],
                },
            )

        if plan_ref is None:
            return StageResult.needs_input(
                "scene_plan artifact is required for MEDIA resolution",
                details={"required_artifact_type": "scene_plan"},
            )

        try:
            plan_payload = context.store.read_json(
                context.project_id,
                plan_ref.artifact_id,
            )
            plan = AstronomyVideoPlan.model_validate(plan_payload)
        except (ValidationError, TypeError, ValueError) as exc:
            return StageResult.blocked(
                "scene_plan is not a valid AstronomyVideoPlan",
                details={
                    "plan_artifact_id": plan_ref.artifact_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1000],
                },
            )

        raw_request = payload.get("resolver")
        if raw_request is None:
            raw_request = {}
        if not isinstance(raw_request, dict):
            return StageResult.blocked(
                "resolver request must be an object",
                details={"field": "resolver"},
            )

        try:
            request = MediaResolverRequest.model_validate(raw_request)
        except ValidationError as exc:
            return StageResult.blocked(
                "invalid media resolver request",
                details={
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1000],
                },
            )

        context.report_progress(12, "MEDIA: resolver started")
        try:
            outcome = self.resolver.resolve(
                plan,
                request,
                report_progress=context.report_progress,
                check_cancelled=context.check_cancelled,
            )
        except JobCancelled:
            raise
        except Exception as exc:
            return StageResult.blocked(
                "media resolver execution failed",
                details={
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1000],
                },
            )

        selection = outcome.selection
        report = outcome.report

        artifacts = (
            StageArtifact(
                artifact_type="material_selection",
                payload=selection,
                input_artifact_ids=(plan_ref.artifact_id,),
                provenance={
                    "media_resolver_version": MEDIA_RESOLVER_VERSION,
                    "material_selector_final_authority": True,
                },
                metadata={
                    "unresolved_count": report.unresolved_count,
                    "review_required": report.review_required,
                    "publication_ready": report.publication_ready,
                },
            ),
            StageArtifact(
                artifact_type="media_resolution",
                payload=report.model_dump(mode="json"),
                input_artifact_ids=(plan_ref.artifact_id,),
                provenance={
                    "media_resolver_version": MEDIA_RESOLVER_VERSION,
                    "semantic_evidence_secondary_only": True,
                    "smartfocal_after_selection_only": True,
                },
                metadata={
                    "unresolved_count": report.unresolved_count,
                    "rights_review_count": report.rights_review_count,
                },
            ),
        )

        unresolved = [
            scene.scene_number
            for scene in plan.scenes
            if next(
                item
                for item in report.scenes
                if item.scene_number == scene.scene_number
            ).selection_status
            in {status.value for status in UNRESOLVED_SELECTION_STATUSES}
        ]

        if unresolved:
            return StageResult.needs_input(
                "one or more scenes have no adequate media",
                artifacts=artifacts,
                details={
                    "unresolved_scene_numbers": unresolved,
                    "irrelevant_broll_substituted": False,
                    "ai_generation_triggered": False,
                },
            )

        return StageResult.complete(
            *artifacts,
            message="media resolved with MaterialSelector authority",
            details={
                "selected_count": report.selected_count,
                "review_required": report.review_required,
                "publication_ready": report.publication_ready,
                "auto_publication": False,
            },
        )


def build_media_stage_binding(
    resolver: MediaResolver | None = None,
) -> StageBinding:
    adapter = MediaResolverSpineAdapter(resolver)
    return StageBinding(
        adapter_id="media_resolver_v01",
        handler=adapter,
        resource_class=ResourceClass.MEDIUM,
        producer_version=MEDIA_RESOLVER_VERSION,
        invokes_network=False,
        invokes_llm=False,
        invokes_render=False,
        auto_publication=False,
    )
