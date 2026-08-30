from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import (
    AstronomyVideoPlan,
    GenerationOrigin,
    NarrativeAct,
    ScenePlan,
    ShotType,
)
from app.models.astromedia import (
    HashMode,
    IndexRequest,
    Origin,
    Provider,
    Rights,
    Sidecar,
)
from app.models.material_selection import MaterialSelectionPlan, SelectionStatus
from app.models.video_base import VideoBasePlanRequest, VideoBaseRenderMode
from app.services.astromedia import AstroMediaCatalog
from app.services.centinela.media_resolver import MediaResolver, MediaResolverRequest
from app.services.video_base_planner import VideoBasePlanBlockedError, VideoBasePlanner


def _fixture_image(path: Path, marker: int) -> None:
    """Create a deterministic synthetic plate; never production astronomy media."""
    image = Image.new("RGB", (540, 960), (10 + marker, 13 + marker, 20 + marker))
    draw = ImageDraw.Draw(image)
    draw.rectangle((42, 70, 498, 890), outline=(225, 225, 215), width=4)
    draw.ellipse((145, 245, 395, 495), outline=(235, 225, 190), width=5)
    draw.text((58, 810), f"VR-{marker:02d}", fill=(235, 235, 225))
    image.save(path, format="PNG", optimize=False, compress_level=9)
    image.close()


def _write_sidecar(
    path: Path,
    *,
    title: str,
    tags: list[str],
    objects: list[str],
) -> None:
    sidecar = Sidecar(
        title=title,
        description=(
            "TEST FIXTURE — RECREACION VISUAL — AI_GENERATED — NOT REAL OBSERVATION — "
            "NOT PRODUCTION ASTRONOMY MEDIA. Hermetic certification asset owned by the "
            "project; no event date, location, ephemeris or network discovery."
        ),
        tags=tags,
        astronomy_objects=objects,
        provider=Provider.AI_GENERATED,
        rights_status=Rights.CONFIRMED_OWNED,
        author_name="EL CENTINELA DEL UNIVERSO — CI FIXTURE",
        attribution_required=False,
    )
    path.with_name(path.name + ".astromedia.json").write_text(
        json.dumps(
            sidecar.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _plan() -> AstronomyVideoPlan:
    scenes = [
        ScenePlan(
            scene_number=1,
            act=NarrativeAct.INTRODUCTION,
            duration_seconds=8,
            narration="Recreación visual de la superficie lunar, no una observación real.",
            visual_requirement="Superficie lunar con un cráter claramente visible.",
            astronomy_objects=["moon"],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["moon", "crater"],
            source_priority=["AI_GENERATED"],
            transition="Corte motivado.",
            claims=[],
            ai_recreation_allowed=True,
            scientific_status=ScientificStatus.RECREACION_VISUAL,
        ),
        ScenePlan(
            scene_number=2,
            act=NarrativeAct.DEVELOPMENT,
            duration_seconds=8,
            narration="Recreación visual de las bandas de Júpiter, no una captura telescópica.",
            visual_requirement="Júpiter con bandas ecuatoriales diferenciadas.",
            astronomy_objects=["jupiter"],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["jupiter", "latitude", "equatorial_bands"],
            source_priority=["AI_GENERATED"],
            transition="Progresión observacional.",
            claims=[],
            ai_recreation_allowed=True,
            scientific_status=ScientificStatus.RECREACION_VISUAL,
        ),
        ScenePlan(
            scene_number=3,
            act=NarrativeAct.CLIMAX,
            duration_seconds=8,
            narration="Recreación visual de una totalidad y su corona, sin atribuirla a un evento real.",
            visual_requirement="Totalidad de eclipse solar con corona como clase visual estática.",
            astronomy_objects=["sun"],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["sun", "eclipse", "totality_corona"],
            source_priority=["AI_GENERATED"],
            transition="Corte de clímax.",
            claims=[],
            ai_recreation_allowed=True,
            scientific_status=ScientificStatus.RECREACION_VISUAL,
        ),
        ScenePlan(
            scene_number=4,
            act=NarrativeAct.RESOLUTION,
            duration_seconds=8,
            narration="Recreación visual del Cinturón de Orión, no un campo estelar observado.",
            visual_requirement="Figura de Orión con el Cinturón de Orión explícitamente identificado.",
            astronomy_objects=["orion"],
            shot_type=ShotType.WIDE,
            material_keywords=["constellation", "orion_belt"],
            source_priority=["AI_GENERATED"],
            transition="Salida del clímax.",
            claims=[],
            ai_recreation_allowed=True,
            scientific_status=ScientificStatus.RECREACION_VISUAL,
        ),
        ScenePlan(
            scene_number=5,
            act=NarrativeAct.EPILOGUE,
            duration_seconds=8,
            narration="Recreación visual de M57; la pieza mantiene explícita su condición de recreación.",
            visual_requirement="M57 como nebulosa del Anillo con morfología anular diferenciada.",
            astronomy_objects=["m57"],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["nebula", "ring_nebula", "m57"],
            source_priority=["AI_GENERATED"],
            transition="Fundido final.",
            claims=[],
            ai_recreation_allowed=True,
            scientific_status=ScientificStatus.RECREACION_VISUAL,
        ),
    ]
    return AstronomyVideoPlan(
        subject="Recreaciones visuales astronómicas — contrato de etiquetado",
        language="es-ES",
        audience="divulgacion astronomica general",
        hook="Cinco recreaciones visuales que nunca se presentan como observaciones reales.",
        scientific_context_summary=(
            "Replay hermético para certificar procedencia, etiquetado y revisión humana de "
            "recreaciones visuales. No representa observaciones ni eventos reales."
        ),
        narrative_arc=list(NarrativeAct),
        scenes=scenes,
        epilogue="La secuencia termina en revisión humana obligatoria.",
        external_research_required=False,
        research_questions=[],
        context_hash="V" * 64,
        generation_origin=GenerationOrigin.DETERMINISTIC_FALLBACK,
        model_used="cloud-cert-visual-recreation-fixture",
        repair_attempted=False,
        total_duration_seconds=40,
        requires_human_review=True,
        approved_for_publication=False,
        generated_at_utc=datetime.now(timezone.utc),
    )


_FIXTURES = [
    ("01-moon-crater-recreation.png", 4, "moon_crater_recreation", ["crater"], ["moon"]),
    (
        "02-jupiter-bands-recreation.png",
        9,
        "jupiter_equatorial_bands_recreation",
        ["latitude", "equatorial_bands"],
        ["jupiter"],
    ),
    (
        "03-totality-corona-recreation.png",
        14,
        "totality_corona_recreation",
        ["totality_corona"],
        ["sun"],
    ),
    (
        "04-orion-belt-recreation.png",
        19,
        "orion_belt_recreation",
        ["orion_belt"],
        ["orion"],
    ),
    (
        "05-m57-ring-nebula-recreation.png",
        24,
        "m57_ring_nebula_recreation",
        ["ring_nebula"],
        ["m57"],
    ),
]

_INITIAL_FIXTURES = _FIXTURES[:-1]
_RECOVERY_FIXTURE = _FIXTURES[-1]


def _add_fixtures(media_root: Path, fixtures) -> None:
    for filename, marker, title, tags, objects in fixtures:
        path = media_root / filename
        _fixture_image(path, marker)
        _write_sidecar(path, title=title, tags=tags, objects=objects)


def _index(catalog: AstroMediaCatalog, media_root: Path):
    return catalog.index_library(
        IndexRequest(
            root=str(media_root),
            recursive=True,
            hash_mode=HashMode.NONE,
            import_task_artifacts=False,
        )
    )


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
            allow_ai_last_resort=True,
            publication_eligible_only=True,
        ),
    )


def _assert_recreation_catalog_contract(catalog: AstroMediaCatalog) -> None:
    items = catalog.list_items(True)
    assert items
    assert all(item.provider == Provider.AI_GENERATED for item in items)
    assert all(item.visual_origin == Origin.AI_GENERATED for item in items)
    assert all(item.scientific_status == ScientificStatus.RECREACION_VISUAL for item in items)
    assert all(item.rights_status == Rights.CONFIRMED_OWNED for item in items)
    assert all(item.publication_eligible is True for item in items)
    assert all("NOT REAL OBSERVATION" in item.description for item in items)


def test_visual_recreation_requires_explicit_ai_path_and_preserves_labels(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()
    _add_fixtures(media_root, _FIXTURES)

    catalog = AstroMediaCatalog(
        db_path=tmp_path / "catalog.sqlite3",
        json_path=tmp_path / "catalog.json",
        allowed_roots=[media_root],
        tasks_root=tmp_path / "tasks",
    )
    index = _index(catalog, media_root)
    assert index.indexed_items == 5
    assert index.non_renderable_items == 0
    assert index.errors == []
    _assert_recreation_catalog_contract(catalog)

    outcome = _resolve(catalog, media_root)
    assert outcome.report.scene_count == 5
    assert outcome.report.selected_count == 5
    assert outcome.report.unresolved_count == 0
    assert outcome.report.publication_ready is False
    assert outcome.report.guardrails.material_selector_is_final_authority is True
    assert outcome.report.guardrails.irrelevant_broll_fallback is False
    assert outcome.report.guardrails.auto_publication is False
    assert outcome.report.guardrails.network_discovery_default is False

    selections = outcome.selection["selections"]
    assert len({row["selected_media_id"] for row in selections}) == 5
    assert all(row["status"] == SelectionStatus.SELECTED_AI_RECREATION.value for row in selections)
    assert all(row["selected_provider"] == Provider.AI_GENERATED.value for row in selections)
    assert all(row["selected_rights_status"] == Rights.CONFIRMED_OWNED.value for row in selections)
    assert all(row["selected_publication_eligible"] is True for row in selections)
    assert all(row["selected_scientific_status"] == ScientificStatus.RECREACION_VISUAL.value for row in selections)
    assert outcome.selection["ai_recreation_count"] == 5
    assert outcome.selection["review_required"] is True
    assert outcome.selection["publication_ready"] is False


def test_visual_recreation_recovery_blocks_until_specific_labeled_asset_exists(tmp_path):
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
    _assert_recreation_catalog_contract(catalog)

    initial = _resolve(catalog, media_root)
    assert initial.report.selected_count == 4
    assert initial.report.unresolved_count == 1
    assert initial.report.publication_ready is False
    scene5 = initial.selection["selections"][4]
    assert scene5["status"] == SelectionStatus.AI_RECREATION_REQUIRED.value
    assert scene5["selected_media_id"] is None

    initial_materials = MaterialSelectionPlan.model_validate(initial.selection)
    planner = VideoBasePlanner(catalog=catalog)
    with pytest.raises(VideoBasePlanBlockedError) as blocked:
        planner.build(
            VideoBasePlanRequest(
                plan=_plan(),
                materials=initial_materials,
                render_mode=VideoBaseRenderMode.CLEAN_BASE,
                requested_codec="libx264",
            )
        )
    assert blocked.value.blockers == ["scene 5: AI_RECREATION_REQUIRED"]

    _add_fixtures(media_root, [_RECOVERY_FIXTURE])
    recovery_index = _index(catalog, media_root)
    assert recovery_index.indexed_items == 5
    assert recovery_index.non_renderable_items == 0
    assert recovery_index.errors == []
    _assert_recreation_catalog_contract(catalog)

    recovered = _resolve(catalog, media_root)
    assert recovered.report.selected_count == 5
    assert recovered.report.unresolved_count == 0
    assert recovered.report.publication_ready is False
    recovered_scene5 = recovered.selection["selections"][4]
    assert recovered_scene5["status"] == SelectionStatus.SELECTED_AI_RECREATION.value
    assert recovered_scene5["selected_provider"] == Provider.AI_GENERATED.value
    assert recovered_scene5["selected_scientific_status"] == ScientificStatus.RECREACION_VISUAL.value
    assert any("ring_nebula" in reason for reason in recovered_scene5["reasons"])

    recovered_materials = MaterialSelectionPlan.model_validate(recovered.selection)
    recovered_plan = planner.build(
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
