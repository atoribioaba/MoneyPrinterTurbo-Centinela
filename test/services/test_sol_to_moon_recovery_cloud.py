from __future__ import annotations

from pathlib import Path

import pytest

from app.models.astromedia import HashMode, IndexRequest
from app.models.material_selection import MaterialSelectionPlan
from app.models.video_base import VideoBasePlanRequest, VideoBaseRenderMode
from app.services.astromedia import AstroMediaCatalog
from app.services.centinela.media_resolver import MediaResolver, MediaResolverRequest
from app.services.video_base_planner import VideoBasePlanBlockedError, VideoBasePlanner
from test.services.test_sol_to_moon_media_cloud_replay import (
    _fixture_image,
    _plan,
    _write_sidecar,
)


_SOLAR_FIXTURES = [
    (
        "01-sun-daylight.png",
        5,
        "Sun solar daylight sun_disc",
        ["sun", "solar", "daylight", "sun_disc"],
        ["sun"],
    ),
    (
        "02-sunset-horizon.png",
        11,
        "Sunset horizon dusk ocaso",
        ["sunset", "horizon", "dusk", "ocaso"],
        ["sun"],
    ),
    (
        "03-twilight-blue-hour.png",
        17,
        "Twilight blue_hour crepusculo afterglow",
        ["twilight", "blue_hour", "crepusculo", "afterglow"],
        [],
    ),
]

_LUNAR_FIXTURES = [
    (
        "04-moonrise-transition.png",
        23,
        "Moonrise lunar_rise moon night_transition",
        ["moonrise", "lunar_rise", "moon", "night_transition"],
        ["moon"],
    ),
    (
        "05-moon-epilogue.png",
        29,
        "Lunar_epilogue moon_reference centered_moon night",
        ["lunar_epilogue", "moon_reference", "centered_moon", "night"],
        ["moon"],
    ),
]


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


def _resolve(catalog: AstroMediaCatalog, media_root: Path):
    return MediaResolver(catalog=catalog).resolve(
        _plan(),
        MediaResolverRequest(
            refresh_catalog=False,
            catalog_root=str(media_root),
            import_task_artifacts=False,
            semantic_evidence=False,
            analyze_selected_focal=False,
            min_relevance_score=6.0,
            max_alternatives=4,
            max_candidates_per_scene=12,
            avoid_reuse=True,
            allow_ai_last_resort=False,
            publication_eligible_only=True,
        ),
    )


def _clean_base_request(outcome) -> VideoBasePlanRequest:
    return VideoBasePlanRequest(
        plan=_plan(),
        materials=MaterialSelectionPlan.model_validate(outcome.selection),
        render_mode=VideoBaseRenderMode.CLEAN_BASE,
        requested_codec="libx264",
    )


def test_sol_to_moon_recovery_blocks_then_recovers_without_irrelevant_broll(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()
    _add_fixtures(media_root, _SOLAR_FIXTURES)

    catalog = AstroMediaCatalog(
        db_path=tmp_path / "catalog.sqlite3",
        json_path=tmp_path / "catalog.json",
        allowed_roots=[media_root],
        tasks_root=tmp_path / "tasks",
    )
    _index(catalog, media_root)
    assert len(catalog.list_items(True)) == 3

    initial = _resolve(catalog, media_root)
    assert initial.report.scene_count == 5
    assert initial.report.selected_count == 3
    assert initial.report.unresolved_count == 2
    assert initial.report.publication_ready is False
    assert initial.report.guardrails.material_selector_is_final_authority is True
    assert initial.report.guardrails.irrelevant_broll_fallback is False
    assert initial.report.guardrails.ai_generation_triggered is False
    assert initial.report.guardrails.network_discovery_default is False

    initial_selections = initial.selection["selections"]
    assert [row["scene_number"] for row in initial_selections] == [1, 2, 3, 4, 5]
    assert [row["status"] for row in initial_selections[3:]] == [
        "NO_ADEQUATE_MEDIA",
        "NO_ADEQUATE_MEDIA",
    ]
    assert all(row["selected_media_id"] is None for row in initial_selections[3:])

    planner = VideoBasePlanner(catalog=catalog)
    with pytest.raises(VideoBasePlanBlockedError) as blocked:
        planner.build(_clean_base_request(initial))

    assert blocked.value.blockers == [
        "scene 4: NO_ADEQUATE_MEDIA",
        "scene 5: NO_ADEQUATE_MEDIA",
    ]

    _add_fixtures(media_root, _LUNAR_FIXTURES)
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
    assert len({row["selected_media_id"] for row in recovered_selections}) == 5
    assert all(row["selected_provider"] != "AI_GENERATED" for row in recovered_selections)
    assert all(row["selected_publication_eligible"] is True for row in recovered_selections)

    clean = planner.build(_clean_base_request(recovered))
    assert clean.clean_base_eligible is True
    assert clean.scene_count == 5
    assert clean.unresolved_count == 0
    assert clean.placeholder_count == 0
    assert len({scene.selected_media_id for scene in clean.scenes}) == 5
