from __future__ import annotations

from app.models.astromedia import HashMode, IndexRequest
from app.models.material_selection import MaterialSelectionPlan, SelectionStatus
from app.models.video_base import VideoBasePlanRequest, VideoBaseRenderMode
from app.services.astromedia import AstroMediaCatalog
from app.services.video_base_planner import VideoBasePlanner
from test.services.test_deep_sky_media_cloud_replay import (
    _FIXTURES,
    _fixture_image,
    _plan,
    _resolve,
    _write_sidecar,
)


_INITIAL_FIXTURES = _FIXTURES[:-1]
_RECOVERY_FIXTURE = _FIXTURES[-1]


def _add_fixtures(media_root, fixtures):
    for filename, marker, title, tags, objects in fixtures:
        path = media_root / filename
        _fixture_image(path, marker)
        _write_sidecar(path, title=title, tags=tags, objects=objects)


def _index(catalog, media_root):
    return catalog.index_library(
        IndexRequest(
            root=str(media_root),
            recursive=True,
            hash_mode=HashMode.NONE,
            import_task_artifacts=False,
        )
    )


def test_deep_sky_recovery_blocks_then_recovers_without_generic_nebula_broll(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()
    _add_fixtures(media_root, _INITIAL_FIXTURES)

    catalog = AstroMediaCatalog(
        db_path=tmp_path / "catalog.sqlite3",
        json_path=tmp_path / "catalog.json",
        allowed_roots=[media_root],
        tasks_root=tmp_path / "tasks",
    )
    initial_index = _index(catalog, media_root)
    assert initial_index.indexed_items == 4
    assert initial_index.non_renderable_items == 0
    assert initial_index.errors == []

    initial = _resolve(catalog, media_root)
    assert initial.report.scene_count == 5
    scene5 = initial.selection["selections"][4]
    diagnostic = (
        f"media_id={scene5.get('selected_media_id')} | "
        f"path={scene5.get('selected_local_path')} | "
        f"status={scene5.get('status')} | "
        f"selected_score={scene5.get('selected_score')} | "
        f"relevance_score={scene5.get('relevance_score')} | "
        f"reasons={scene5.get('reasons')}"
    )
    assert initial.report.selected_count == 4, diagnostic
    assert initial.report.unresolved_count == 1
    assert initial.report.publication_ready is False
    assert scene5["status"] == SelectionStatus.NO_ADEQUATE_MEDIA.value
    assert scene5["selected_media_id"] is None

    m42_id = next(
        item.media_id
        for item in catalog.list_items(True)
        if item.title and "M42" in item.title
    )
    assert all(
        alternative["media_id"] != m42_id for alternative in scene5.get("alternatives", [])
    ), "M42 must not be accepted as a substitute for M57 just because both are nebulae"

    initial_materials = MaterialSelectionPlan.model_validate(initial.selection)
    initial_plan = VideoBasePlanner(catalog=catalog).build(
        VideoBasePlanRequest(
            plan=_plan(),
            materials=initial_materials,
            render_mode=VideoBaseRenderMode.CLEAN_BASE,
            requested_codec="libx264",
        )
    )
    assert initial_plan.clean_base_eligible is False
    assert initial_plan.unresolved_count == 1
    assert "scene 5: NO_ADEQUATE_MEDIA" in initial_plan.blockers

    _add_fixtures(media_root, [_RECOVERY_FIXTURE])
    recovery_index = _index(catalog, media_root)
    assert recovery_index.indexed_items == 5
    assert recovery_index.non_renderable_items == 0
    assert recovery_index.errors == []

    recovered = _resolve(catalog, media_root)
    assert recovered.report.selected_count == 5
    assert recovered.report.unresolved_count == 0
    assert recovered.report.publication_ready is True
    recovered_scene5 = recovered.selection["selections"][4]
    assert recovered_scene5["status"] == SelectionStatus.SELECTED.value
    assert "m57" in " ".join(recovered_scene5["reasons"])

    recovered_materials = MaterialSelectionPlan.model_validate(recovered.selection)
    recovered_plan = VideoBasePlanner(catalog=catalog).build(
        VideoBasePlanRequest(
            plan=_plan(),
            materials=recovered_materials,
            render_mode=VideoBaseRenderMode.CLEAN_BASE,
            requested_codec="libx264",
        )
    )
    assert recovered_plan.clean_base_eligible is True
    assert recovered_plan.unresolved_count == 0
    assert recovered_plan.placeholder_count == 0
