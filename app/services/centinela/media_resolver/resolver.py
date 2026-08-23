from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.models.astronomy_director import AstronomyVideoPlan
from app.models.astromedia import HashMode, IndexRequest, MediaType
from app.models.material_selection import (
    MaterialSelectionPlan,
    MaterialSelectionRequest,
    SelectionStatus,
)
from app.services.astromedia import AstroMediaCatalog
from app.services.material_selection import MaterialSelector
from app.services.semantic_matcher import reorder_videos_for_script
from app.services.smart_focal import fallback_focal_decision

from .models import (
    FocalEvidence,
    MediaResolutionReport,
    MediaResolveOutcome,
    MediaResolverRequest,
    ResolverGuardrails,
    SceneMediaEvidence,
    SemanticEvidence,
)
from .sources import AstroMediaCatalogSource, scene_query


ProgressCallback = Callable[[int, str], None] | None
CancelCallback = Callable[[], None] | None


@dataclass(slots=True)
class _FocalResult:
    focal_x: float
    focal_y: float
    confidence: float
    method: str
    error: str = ""


def _safe_call(callback: Callable[..., Any] | None, *args: Any) -> None:
    if callback is not None:
        callback(*args)


def _path_key(value: str) -> str:
    try:
        return os.path.normcase(str(Path(value).resolve()))
    except OSError:
        return os.path.normcase(str(value))


def _default_focal_analyzer(path: str) -> _FocalResult:
    clip = None
    try:
        from moviepy import VideoFileClip

        from app.services.smart_focal import safe_focal_decision_from_clip

        clip = VideoFileClip(path)
        decision = safe_focal_decision_from_clip(
            clip,
            target_width=1080,
            target_height=1920,
        )
        return _FocalResult(
            focal_x=decision.focal_x,
            focal_y=decision.focal_y,
            confidence=decision.confidence,
            method=decision.method,
        )
    except Exception as exc:
        decision = fallback_focal_decision()
        return _FocalResult(
            focal_x=decision.focal_x,
            focal_y=decision.focal_y,
            confidence=decision.confidence,
            method=decision.method,
            error=f"{type(exc).__name__}: {exc}"[:1000],
        )
    finally:
        if clip is not None:
            try:
                clip.close()
            except Exception:
                pass


class MediaResolver:
    """R4 coordinator around AstroMedia, MaterialSelector, SemanticMatcher and SmartFocal.

    MaterialSelector remains the final selection authority. SemanticMatcher only adds
    secondary evidence. SmartFocal runs only after a material has been selected.
    """

    def __init__(
        self,
        *,
        catalog: AstroMediaCatalog | None = None,
        selector: MaterialSelector | None = None,
        semantic_reorder: Callable[..., Any] = reorder_videos_for_script,
        focal_analyzer: Callable[[str], Any] = _default_focal_analyzer,
    ) -> None:
        self.catalog = catalog or AstroMediaCatalog()
        self.selector = selector or MaterialSelector(self.catalog)
        if getattr(self.selector, "catalog", self.catalog) is not self.catalog:
            raise ValueError("selector and resolver must share the same AstroMedia catalog")
        self.source = AstroMediaCatalogSource(self.catalog)
        self.semantic_reorder = semantic_reorder
        self.focal_analyzer = focal_analyzer

    def _semantic_evidence(
        self,
        scene: Any,
        candidates: list[Any],
        request: MediaResolverRequest,
    ) -> SemanticEvidence:
        if not request.semantic_evidence:
            return SemanticEvidence(
                requested=False,
                analyzed=False,
                method="disabled_by_resolver",
            )

        video_candidates = [
            candidate
            for candidate in candidates
            if candidate.media_type == MediaType.VIDEO
        ]

        if len(video_candidates) < 2:
            return SemanticEvidence(
                requested=True,
                analyzed=False,
                method="not_enough_video_candidates",
                ordered_media_ids=[candidate.media_id for candidate in video_candidates],
            )

        paths = [candidate.local_path for candidate in video_candidates]
        try:
            outcome = self.semantic_reorder(
                video_script=(
                    str(getattr(scene, "narration", "") or "")
                    + " "
                    + str(getattr(scene, "visual_requirement", "") or "")
                ).strip(),
                video_terms=[
                    *list(getattr(scene, "material_keywords", None) or []),
                    *list(getattr(scene, "astronomy_objects", None) or []),
                ],
                video_paths=paths,
            )
        except Exception as exc:
            return SemanticEvidence(
                requested=True,
                analyzed=False,
                method="semantic_evidence_failed",
                error=f"{type(exc).__name__}: {exc}"[:2000],
                ordered_media_ids=[
                    candidate.media_id
                    for candidate in video_candidates
                ],
            )

        by_path = {
            _path_key(candidate.local_path): candidate.media_id
            for candidate in video_candidates
        }
        ordered_ids = [
            by_path[key]
            for key in (_path_key(path) for path in outcome.video_paths)
            if key in by_path
        ]

        return SemanticEvidence(
            requested=True,
            analyzed=bool(getattr(outcome, "analyzed", False)),
            method=str(getattr(outcome, "method", "unknown")),
            error=str(getattr(outcome, "error", "") or "")[:2000],
            queries=[str(value) for value in (getattr(outcome, "queries", ()) or ())],
            ordered_media_ids=ordered_ids,
            matches=[
                dict(value)
                for value in (getattr(outcome, "matches", ()) or ())
                if isinstance(value, dict)
            ],
        )

    @staticmethod
    def _apply_semantic_ranks(
        candidates: list[Any],
        evidence: SemanticEvidence,
    ) -> None:
        ranks = {
            media_id: index
            for index, media_id in enumerate(evidence.ordered_media_ids, start=1)
        }
        for candidate in candidates:
            candidate.semantic_rank = ranks.get(candidate.media_id)

    def _focal_evidence(
        self,
        selected_media_id: str | None,
        request: MediaResolverRequest,
    ) -> FocalEvidence:
        if not selected_media_id:
            return FocalEvidence(
                applicable=False,
                method="not_selected",
            )

        item = self.catalog.get(selected_media_id)
        if item is None:
            return FocalEvidence(
                applicable=False,
                media_id=selected_media_id,
                method="selected_media_missing_from_catalog",
                error="selected media_id is not present in AstroMedia catalog",
            )

        if item.media_type != MediaType.VIDEO:
            return FocalEvidence(
                applicable=False,
                media_id=item.media_id,
                method="not_applicable_image",
            )

        if not request.analyze_selected_focal:
            return FocalEvidence(
                applicable=False,
                media_id=item.media_id,
                method="disabled_by_resolver",
            )

        try:
            result = self.focal_analyzer(item.local_path)
            return FocalEvidence(
                applicable=True,
                media_id=item.media_id,
                focal_x=float(result.focal_x),
                focal_y=float(result.focal_y),
                confidence=float(result.confidence),
                method=str(result.method),
                error=str(getattr(result, "error", "") or "")[:1000],
            )
        except Exception as exc:
            decision = fallback_focal_decision()
            return FocalEvidence(
                applicable=True,
                media_id=item.media_id,
                focal_x=decision.focal_x,
                focal_y=decision.focal_y,
                confidence=decision.confidence,
                method=decision.method,
                error=f"{type(exc).__name__}: {exc}"[:1000],
            )

    def resolve(
        self,
        plan: AstronomyVideoPlan,
        request: MediaResolverRequest | None = None,
        *,
        report_progress: ProgressCallback = None,
        check_cancelled: CancelCallback = None,
    ) -> MediaResolveOutcome:
        if not isinstance(plan, AstronomyVideoPlan):
            raise TypeError("plan must be AstronomyVideoPlan")
        request = request or MediaResolverRequest()

        _safe_call(check_cancelled)
        _safe_call(report_progress, 15, "MEDIA: catalog preflight")

        index_report = None
        if request.refresh_catalog:
            index_report = self.catalog.index_library(
                IndexRequest(
                    root=request.catalog_root,
                    recursive=True,
                    hash_mode=HashMode.DUPLICATE_CANDIDATES,
                    import_task_artifacts=request.import_task_artifacts,
                )
            )

        _safe_call(check_cancelled)
        catalog_items = self.catalog.list_items(True)
        catalog_item_count = len(catalog_items)
        provider_counts: dict[str, int] = {}
        for item in catalog_items:
            provider_counts[item.provider.value] = (
                provider_counts.get(item.provider.value, 0) + 1
            )

        evidence_rows: list[tuple[Any, list[Any], SemanticEvidence]] = []
        for index, scene in enumerate(plan.scenes, start=1):
            _safe_call(check_cancelled)
            candidates = self.source.search_scene(scene, request)
            semantic = self._semantic_evidence(scene, candidates, request)
            self._apply_semantic_ranks(candidates, semantic)
            evidence_rows.append((scene, candidates, semantic))
            progress = 20 + round(15 * index / len(plan.scenes))
            _safe_call(report_progress, min(progress, 35), f"MEDIA: candidates scene {index}")

        _safe_call(check_cancelled)
        _safe_call(report_progress, 40, "MEDIA: MaterialSelector final decision")

        selection = self.selector.select_plan(
            MaterialSelectionRequest(
                plan=plan,
                min_relevance_score=request.min_relevance_score,
                max_alternatives=request.max_alternatives,
                avoid_reuse=request.avoid_reuse,
                allow_ai_last_resort=request.allow_ai_last_resort,
                publication_eligible_only=request.publication_eligible_only,
            )
        )

        if not isinstance(selection, MaterialSelectionPlan):
            raise TypeError("MaterialSelector must return MaterialSelectionPlan")

        selected_by_number = {
            item.scene_number: item
            for item in selection.selections
        }

        scenes: list[SceneMediaEvidence] = []
        rights_review_count = 0

        for index, (scene, candidates, semantic) in enumerate(evidence_rows, start=1):
            _safe_call(check_cancelled)
            selected = selected_by_number[int(scene.scene_number)]
            if (
                selected.selected_media_id is not None
                and selected.selected_publication_eligible is not True
            ):
                rights_review_count += 1

            focal = self._focal_evidence(selected.selected_media_id, request)
            scenes.append(
                SceneMediaEvidence(
                    scene_number=int(scene.scene_number),
                    scene_key=selected.scene_key,
                    query=scene_query(scene),
                    candidate_count=len(candidates),
                    candidates=candidates,
                    semantic=semantic,
                    selection_status=selected.status.value,
                    selected_media_id=selected.selected_media_id,
                    selected_provider=selected.selected_provider,
                    selected_rights_status=selected.selected_rights_status,
                    selected_publication_eligible=selected.selected_publication_eligible,
                    focal=focal,
                )
            )
            progress = 45 + round(10 * index / len(evidence_rows))
            _safe_call(report_progress, min(progress, 55), f"MEDIA: focal/evidence scene {index}")

        report = MediaResolutionReport(
            subject=selection.subject,
            source_plan_context_hash=selection.source_plan_context_hash,
            selector_version=selection.selector_version,
            catalog_item_count=catalog_item_count,
            catalog_provider_counts=dict(sorted(provider_counts.items())),
            catalog_refreshed=request.refresh_catalog,
            catalog_index_report=(
                None
                if index_report is None
                else index_report.model_dump(mode="json")
            ),
            scene_count=selection.scene_count,
            selected_count=selection.selected_count,
            unresolved_count=selection.unresolved_count,
            rights_review_count=rights_review_count,
            review_required=selection.review_required,
            publication_ready=selection.publication_ready,
            scenes=scenes,
            guardrails=ResolverGuardrails(),
            generated_at_utc=datetime.now(timezone.utc),
        )

        _safe_call(report_progress, 60, "MEDIA: resolution report ready")
        return MediaResolveOutcome(
            selection=selection.model_dump(mode="json"),
            report=report,
        )


UNRESOLVED_SELECTION_STATUSES = frozenset(
    {
        SelectionStatus.NO_ADEQUATE_MEDIA,
        SelectionStatus.AI_RECREATION_REQUIRED,
    }
)
