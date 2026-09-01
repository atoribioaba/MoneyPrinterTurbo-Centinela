from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import (
    AstronomyVideoPlan,
    GenerationOrigin,
    NarrativeAct,
    ScenePlan,
    ShotType,
)
from app.models.astromedia import MediaType, Provider, Rights
from app.models.material_selection import (
    MaterialSelectionPlan,
    SceneMaterialSelection,
    SelectionStatus,
)
from app.models.video_base import VideoBasePlanRequest, VideoBaseRenderMode
from app.services.video_base_planner import (
    VideoBasePlanBlockedError,
    VideoBasePlanner,
)


def astronomy_plan():
    acts = [
        NarrativeAct.INTRODUCTION,
        NarrativeAct.DEVELOPMENT,
        NarrativeAct.CLIMAX,
        NarrativeAct.RESOLUTION,
        NarrativeAct.EPILOGUE,
    ]
    scenes = [
        ScenePlan(
            scene_number=index,
            act=acts[index - 1],
            duration_seconds=5,
            narration=f"Narration {index}",
            visual_requirement=f"Visual {index}",
            astronomy_objects=["Moon"],
            shot_type=ShotType.STATIC,
            material_keywords=["moon"],
            source_priority=["OWN_MEDIA"],
            transition="cut",
            claims=[],
            ai_recreation_allowed=index == 3,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        )
        for index in range(1, 6)
    ]
    return AstronomyVideoPlan(
        subject="Moon test",
        hook="Hook",
        scientific_context_summary="Context",
        narrative_arc=acts,
        scenes=scenes,
        epilogue="End",
        context_hash="ctx-1",
        generation_origin=GenerationOrigin.LLM_VALIDATED,
        model_used="test",
        repair_attempted=False,
        total_duration_seconds=25,
        requires_human_review=True,
        approved_for_publication=False,
        generated_at_utc=datetime.now(timezone.utc),
    )


def material_plan(statuses):
    selections = []
    for index, status in enumerate(statuses, start=1):
        selected = status in {
            SelectionStatus.SELECTED,
            SelectionStatus.MANUAL_OVERRIDE,
            SelectionStatus.SELECTED_AI_RECREATION,
        }
        selections.append(
            SceneMaterialSelection(
                scene_number=index,
                scene_key=f"ctx-1:scene:{index}",
                visual_requirement=f"Visual {index}",
                query="moon",
                status=status,
                selected_media_id=f"media-{index}" if selected else None,
                selected_local_path=f"/tmp/media-{index}.jpg" if selected else None,
                selected_provider=Provider.OWN_MEDIA if selected else None,
                selected_rights_status=Rights.CONFIRMED_OWNED if selected else None,
                selected_publication_eligible=True if selected else None,
                manual_override=status == SelectionStatus.MANUAL_OVERRIDE,
                review_required=not selected,
            )
        )
    return MaterialSelectionPlan(
        subject="Moon test",
        source_plan_context_hash="ctx-1",
        selector_version="material-selection-v0.1",
        scene_count=5,
        selected_count=sum(
            status
            in {
                SelectionStatus.SELECTED,
                SelectionStatus.MANUAL_OVERRIDE,
                SelectionStatus.SELECTED_AI_RECREATION,
            }
            for status in statuses
        ),
        manual_override_count=sum(
            status == SelectionStatus.MANUAL_OVERRIDE for status in statuses
        ),
        unresolved_count=sum(
            status
            in {
                SelectionStatus.NO_ADEQUATE_MEDIA,
                SelectionStatus.AI_RECREATION_REQUIRED,
            }
            for status in statuses
        ),
        ai_recreation_count=sum(
            status
            in {
                SelectionStatus.SELECTED_AI_RECREATION,
                SelectionStatus.AI_RECREATION_REQUIRED,
            }
            for status in statuses
        ),
        selections=selections,
        review_required=any(selection.review_required for selection in selections),
        publication_ready=False,
        generated_at_utc=datetime.now(timezone.utc),
    )


class GetOnlyCatalog:
    def __init__(self, items=None):
        self.items = items or {}

    def get(self, media_id):
        return self.items.get(media_id)

    def list_items(self, *args, **kwargs):
        raise AssertionError("F6 must never list/rank AstroMedia")

    def search(self, *args, **kwargs):
        raise AssertionError("F6 must never search AstroMedia")


def test_review_partial_unresolved_becomes_placeholders():
    materials = material_plan([SelectionStatus.NO_ADEQUATE_MEDIA] * 5)
    result = VideoBasePlanner(GetOnlyCatalog()).build(
        VideoBasePlanRequest(plan=astronomy_plan(), materials=materials)
    )
    assert result.scene_count == 5
    assert result.placeholder_count == 5
    assert result.clean_base_eligible is False
    assert all(scene.placeholder for scene in result.scenes)


def test_clean_base_blocks_unresolved_before_renderer():
    materials = material_plan([SelectionStatus.NO_ADEQUATE_MEDIA] * 5)
    with pytest.raises(VideoBasePlanBlockedError):
        VideoBasePlanner(GetOnlyCatalog()).build(
            VideoBasePlanRequest(
                plan=astronomy_plan(),
                materials=materials,
                render_mode=VideoBaseRenderMode.CLEAN_BASE,
            )
        )


def test_selected_images_are_clean_base_eligible(tmp_path):
    items = {}
    statuses = [SelectionStatus.SELECTED] * 5
    materials = material_plan(statuses)
    for index in range(1, 6):
        path = tmp_path / f"media-{index}.jpg"
        path.write_bytes(b"not-decoded-by-planner")
        materials.selections[index - 1].selected_local_path = str(path)
        items[f"media-{index}"] = SimpleNamespace(
            media_id=f"media-{index}",
            local_path=str(path),
            active=True,
            renderable=True,
            probe_error=None,
            width=1920,
            height=1080,
            rotation_deg=0,
            duration_seconds=0.0,
            media_type=MediaType.IMAGE,
            provider=Provider.OWN_MEDIA,
            rights_status=Rights.CONFIRMED_OWNED,
            publication_eligible=True,
            content_sha256=None,
            file_size_bytes=path.stat().st_size,
            mtime_ns=path.stat().st_mtime_ns,
        )

    result = VideoBasePlanner(GetOnlyCatalog(items)).build(
        VideoBasePlanRequest(
            plan=astronomy_plan(),
            materials=materials,
            render_mode=VideoBaseRenderMode.CLEAN_BASE,
        )
    )
    assert result.clean_base_eligible is True
    assert result.placeholder_count == 0


def test_short_video_is_placeholder_in_review_mode(tmp_path):
    materials = material_plan(
        [SelectionStatus.SELECTED] + [SelectionStatus.NO_ADEQUATE_MEDIA] * 4
    )
    path = tmp_path / "media-1.mp4"
    path.write_bytes(b"planner-only")
    materials.selections[0].selected_local_path = str(path)
    item = SimpleNamespace(
        media_id="media-1",
        local_path=str(path),
        active=True,
        renderable=True,
        probe_error=None,
        width=1080,
        height=1920,
        rotation_deg=0,
        duration_seconds=2.0,
        media_type=MediaType.VIDEO,
        provider=Provider.OWN_MEDIA,
        rights_status=Rights.CONFIRMED_OWNED,
        publication_eligible=True,
        content_sha256=None,
        file_size_bytes=path.stat().st_size,
        mtime_ns=path.stat().st_mtime_ns,
    )
    result = VideoBasePlanner(GetOnlyCatalog({"media-1": item})).build(
        VideoBasePlanRequest(plan=astronomy_plan(), materials=materials)
    )
    assert result.scenes[0].placeholder is True
    assert result.scenes[0].placeholder_reason.value == "SOURCE_TOO_SHORT"
