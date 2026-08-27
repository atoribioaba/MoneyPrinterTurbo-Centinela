from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import (
    AstronomyVideoPlan,
    GenerationOrigin,
    NarrativeAct,
    ScenePlan,
    ShotType,
)
from app.models.astromedia import HashMode, IndexRequest, Sidecar
from app.services.astromedia import AstroMediaCatalog
from app.services.centinela.media_resolver import MediaResolver, MediaResolverRequest


def _fixture_image(path: Path, marker: int) -> None:
    """Create a deterministic certification plate, never production eclipse media."""
    image = Image.new("RGB", (540, 960), (8 + marker, 10 + marker, 16 + marker))
    draw = ImageDraw.Draw(image)
    center = (270, 360)
    radius = 118
    draw.ellipse(
        (center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius),
        outline=(235, 220, 175),
        width=5,
    )
    if marker == 9:  # partial class marker
        draw.ellipse((235, 235, 420, 420), fill=(8, 10, 16), outline=(180, 180, 180), width=3)
    elif marker == 14:  # totality/corona class marker
        draw.ellipse((170, 260, 370, 460), fill=(5, 6, 10))
        draw.ellipse((150, 240, 390, 480), outline=(220, 220, 210), width=3)
    elif marker == 19:  # diamond-ring class marker
        draw.ellipse((170, 260, 370, 460), fill=(5, 6, 10))
        draw.ellipse((356, 346, 374, 364), fill=(245, 245, 230))
    elif marker == 24:  # filtered telescope-observation class marker
        draw.rectangle((150, 610, 390, 625), outline=(210, 210, 200), width=4)
        draw.line((270, 625, 220, 790), fill=(210, 210, 200), width=5)
        draw.line((270, 625, 320, 790), fill=(210, 210, 200), width=5)
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
            "Owned hermetic certification fixture; static visual classification only; "
            "not production astronomy media; no event date, location, ephemeris, network, "
            "or generative AI."
        ),
        tags=tags,
        astronomy_objects=objects,
        ownership_confirmed=True,
        author_name="EL CENTINELA DEL UNIVERSO",
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
            narration="La secuencia comienza con el disco solar completo como referencia visual.",
            visual_requirement="Disco completo del Sol antes de la secuencia de eclipse.",
            astronomy_objects=["Sun"],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["sun", "full_disk_reference"],
            source_priority=["OWN_MEDIA"],
            transition="Corte motivado.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=2,
            act=NarrativeAct.DEVELOPMENT,
            duration_seconds=8,
            narration="Después aparece la clase visual de eclipse solar parcial.",
            visual_requirement=(
                "Eclipse solar parcial como clase visual estática, sin asociarlo a fecha, "
                "lugar ni efemérides."
            ),
            astronomy_objects=["Sun"],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["sun", "partial_eclipse", "eclipse"],
            source_priority=["OWN_MEDIA"],
            transition="Progresión observacional.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=3,
            act=NarrativeAct.CLIMAX,
            duration_seconds=8,
            narration="El clímax usa la clase visual de totalidad con corona.",
            visual_requirement=(
                "Totalidad de eclipse solar con corona como clase visual estática; "
                "sin atribuirla a un evento real concreto."
            ),
            astronomy_objects=["Sun"],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["sun", "totality_corona", "eclipse"],
            source_priority=["OWN_MEDIA"],
            transition="Corte de clímax.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=4,
            act=NarrativeAct.RESOLUTION,
            duration_seconds=8,
            narration="La resolución muestra la clase visual conocida como anillo de diamante.",
            visual_requirement=(
                "Anillo de diamante de eclipse solar como clase visual estática, "
                "sin cronología ni localización de un evento."
            ),
            astronomy_objects=["Sun"],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["sun", "diamond_ring", "eclipse"],
            source_priority=["OWN_MEDIA"],
            transition="Salida del clímax.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=5,
            act=NarrativeAct.EPILOGUE,
            duration_seconds=8,
            narration="El epílogo vuelve al contexto de observación solar con filtrado apropiado.",
            visual_requirement="Contexto telescópico de observación solar con filtrado apropiado.",
            astronomy_objects=[],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["solar_filter_observation", "filtered_telescope"],
            source_priority=["OWN_MEDIA"],
            transition="Fundido final.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
    ]

    return AstronomyVideoPlan(
        subject="Eclipse solar — clases visuales estáticas",
        language="es-ES",
        audience="divulgacion astronomica general",
        hook="Del disco solar a las principales clases visuales de un eclipse total.",
        scientific_context_summary=(
            "Replay hermético de clases visuales estáticas de eclipse solar; no representa "
            "un evento real concreto y no usa fechas, localizaciones, coordenadas, "
            "efemérides ni valores numéricos."
        ),
        narrative_arc=list(NarrativeAct),
        scenes=scenes,
        epilogue="La secuencia termina en revisión humana.",
        external_research_required=False,
        research_questions=[],
        context_hash="E" * 64,
        generation_origin=GenerationOrigin.DETERMINISTIC_FALLBACK,
        model_used="cloud-cert-fixture",
        repair_attempted=False,
        total_duration_seconds=40,
        requires_human_review=True,
        approved_for_publication=False,
        generated_at_utc=datetime.now(timezone.utc),
    )


_FIXTURES = [
    (
        "01-sun-full-disk.png",
        4,
        "sun_full_disk_reference",
        ["sun", "full_disk_reference"],
        ["sun"],
    ),
    (
        "02-partial-eclipse.png",
        9,
        "partial_eclipse",
        ["partial_eclipse"],
        ["sun"],
    ),
    (
        "03-totality-corona.png",
        14,
        "totality_corona",
        ["totality_corona"],
        ["sun"],
    ),
    (
        "04-diamond-ring.png",
        19,
        "diamond_ring",
        ["diamond_ring"],
        ["sun"],
    ),
    (
        "05-filtered-telescope.png",
        24,
        "solar_filter_observation",
        ["solar_filter_observation", "filtered_telescope"],
        [],
    ),
]


def _media_id_for_path(catalog: AstroMediaCatalog, path: Path) -> str:
    resolved = path.resolve()
    for item in catalog.list_items(True):
        if Path(item.local_path).resolve() == resolved:
            return item.media_id
    raise AssertionError(f"indexed item not found for {path}")


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


def test_eclipse_media_replay_reaches_safe_5_of_5(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()

    paths: list[Path] = []
    for filename, marker, title, tags, objects in _FIXTURES:
        path = media_root / filename
        _fixture_image(path, marker)
        _write_sidecar(path, title=title, tags=tags, objects=objects)
        paths.append(path)

    catalog = AstroMediaCatalog(
        db_path=tmp_path / "catalog.sqlite3",
        json_path=tmp_path / "catalog.json",
        allowed_roots=[media_root],
        tasks_root=tmp_path / "tasks",
    )
    index = catalog.index_library(
        IndexRequest(
            root=str(media_root),
            recursive=True,
            hash_mode=HashMode.NONE,
            import_task_artifacts=False,
        )
    )

    assert index.indexed_items == 5
    assert index.non_renderable_items == 0
    assert index.errors == []
    assert all(item.publication_eligible for item in catalog.list_items(True))

    outcome = _resolve(catalog, media_root)
    assert outcome.report.scene_count == 5
    assert outcome.report.selected_count == 5
    assert outcome.report.unresolved_count == 0
    assert outcome.report.rights_review_count == 0
    assert outcome.report.publication_ready is True
    assert outcome.report.guardrails.material_selector_is_final_authority is True
    assert outcome.report.guardrails.semantic_matcher_is_secondary_evidence_only is True
    assert outcome.report.guardrails.irrelevant_broll_fallback is False
    assert outcome.report.guardrails.ai_generation_triggered is False
    assert outcome.report.guardrails.wangp_triggered is False
    assert outcome.report.guardrails.auto_publication is False
    assert outcome.report.guardrails.network_discovery_default is False

    selections = outcome.selection["selections"]
    assert [row["scene_number"] for row in selections] == [1, 2, 3, 4, 5]
    expected_ids = [_media_id_for_path(catalog, path) for path in paths]
    assert [row["selected_media_id"] for row in selections] == expected_ids
    assert len({row["selected_media_id"] for row in selections}) == 5
    assert all(row["selected_publication_eligible"] is True for row in selections)
    assert all(row["selected_provider"] != "AI_GENERATED" for row in selections)

    expected_specificity = {
        2: "partial_eclipse",
        3: "totality_corona",
        4: "diamond_ring",
    }
    generic_sun_id = expected_ids[0]
    for scene_number, required_token in expected_specificity.items():
        row = selections[scene_number - 1]
        reasons = list(row["reasons"])
        assert any(
            reason.startswith("specificity_overlap:") and required_token in reason
            for reason in reasons
        ), (scene_number, reasons)
        assert all(
            alternative["media_id"] != generic_sun_id
            for alternative in row.get("alternatives", [])
        ), "generic Sun must not survive an eclipse-specific visual gate"
