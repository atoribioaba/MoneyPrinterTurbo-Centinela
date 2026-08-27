from __future__ import annotations

from pathlib import Path

import pytest

from app.models.astromedia import HashMode, IndexRequest
from app.models.material_selection import MaterialSelectionPlan
from app.models.video_base import VideoBasePlanRequest, VideoBaseRenderMode
from app.services.astromedia import AstroMediaCatalog
from app.services.video_base_planner import VideoBasePlanBlockedError, VideoBasePlanner
from test.services.test_eclipse_media_cloud_replay import (
    _FIXTURES,
    _fixture_image,
    _plan,
    _resolve,
    _write_sidecar,
)

_INITIAL_FIXTURES = [_FIXTURES[index] for index in (0, 1, 2, 4)]
_RECOVERY_FIXTURE = _FIXTURES[3]


def _add_fixtures(media_root: Path, fixtures: list[tuple]) -> None:
    for filename, marker, title, tags, objects in fixtures:
        path = media_root / filename
        _fixture_image(path, marker)
        _write_sidecar(path, title=title, tags=tags, objects=objects)


def _index(catalog: AstroMediaCatalog, media_root: Path) -> None:
    result = catalog.index_library(
        IndexRequest(
            root=str(media_root),
            recursive=True,
            hash_mode=HashMode.NONE,
            import_task_artifacts=False,
        )
    )
    assert result.non_renderable_items == 0
    assert result.errors == []


def _clean_base_request(outcome) -> VideoBasePlanRequest:
    return VideoBasePlanRequest(
        plan=_plan(),
        materials=MaterialSelectionPlan.model_validate(outcome.selection),
        render_mode=VideoBaseRenderMode.CLEAN_BASE,
        requested_codec="libx264",
    )


def test_eclipse_recovery_blocks_then_recovers_without_irrelevant_broll(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()
    _add_fixtures(media_root, _INITIAL_FIXTURES)

    catalog = AstroMediaCatalog(
        db_path=tmp_path / "catalog.sqlite3",
        json_path=tmp_path / "catalog.json",
        allowed_roots=[media_root],
        tasks_root=tmp_path / "tasks",
    )
    _index(catalog, media_root)
    assert len(catalog.list_items(True)) == 4

    initial = _resolve(catalog, media_root)
    assert initial.report.scene_count == 5
    assert initial.report.selected_count == 4
    assert initial.report.unresolved_count == 1
    assert initial.report.publication_ready is False
    assert initial.report.guardrails.material_selector_is_final_authority is True
    assert initial.report.guardrails.irrelevant_broll_fallback is False
    assert initial.report.guardrails.ai_generation_triggered is False
    assert initial.report.guardrails.wangp_triggered is False
    assert initial.report.guardrails.auto_publication is False
    assert initial.report.guardrails.network_discovery_default is False

    selections = initial.selection["selections"]
    assert [row["scene_number"] for row in selections] == [1, 2, 3, 4, 5]
    assert selections[3]["status"] == "NO_ADEQUATE_MEDIA"
    assert selections[3]["selected_media_id"] is None

    planner = VideoBasePlanner(catalog=catalog)
    with pytest.raises(VideoBasePlanBlockedError) as blocked:
        planner.build(_clean_base_request(initial))
    assert blocked.value.blockers == ["scene 4: NO_ADEQUATE_MEDIA"]

    _add_fixtures(media_root, [_RECOVERY_FIXTURE])
    _index(catalog, media_root)
    assert len(catalog.list_items(True)) == 5

    recovered = _resolve(catalog, media_root)
    assert recovered.report.scene_count == 5
    assert recovered.report.selected_count == 5
    assert recovered.report.unresolved_count == 0
    assert recovered.report.rights_review_count == 0
    assert recovered.report.publication_ready is True
    assert recovered.report.guardrails.material_selector_is_final_authority is True
    assert recovered.report.guardrails.irrelevant_broll_fallback is False
    assert recovered.report.guardrails.ai_generation_triggered is False
    assert recovered.report.guardrails.wangp_triggered is False
    assert recovered.report.guardrails.auto_publication is False
    assert recovered.report.guardrails.network_discovery_default is False

    recovered_selections = recovered.selection["selections"]
    assert recovered_selections[3]["selected_media_id"] is not None
    assert any(
        reason.startswith("specificity_overlap:") and "diamond_ring" in reason
        for reason in recovered_selections[3]["reasons"]
    )
    assert len({row["selected_media_id"] for row in recovered_selections}) == 5
    assert all(row["selected_provider"] != "AI_GENERATED" for row in recovered_selections)
    assert all(row["selected_publication_eligible"] is True for row in recovered_selections)

    clean = planner.build(_clean_base_request(recovered))
    assert clean.clean_base_eligible is True
    assert clean.scene_count == 5
    assert clean.unresolved_count == 0
    assert clean.placeholder_count == 0
    assert len({scene.selected_media_id for scene in clean.scenes}) == 5
