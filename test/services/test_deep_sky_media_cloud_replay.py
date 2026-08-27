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
    """Create a deterministic deep-sky classification plate, never real sky media."""
    image = Image.new("RGB", (540, 960), (4 + marker, 5 + marker, 11 + marker))
    draw = ImageDraw.Draw(image)
    for index in range(18):
        x = 35 + ((index * 97 + marker * 11) % 465)
        y = 60 + ((index * 151 + marker * 17) % 820)
        r = 1 + ((index + marker) % 3)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(225, 225, 220))
    if marker == 9:
        draw.ellipse((120, 390, 420, 550), outline=(180, 185, 195), width=8)
        draw.ellipse((185, 430, 355, 510), outline=(210, 210, 205), width=5)
    elif marker == 14:
        draw.ellipse((155, 350, 385, 600), outline=(190, 195, 205), width=10)
        draw.ellipse((220, 420, 320, 530), outline=(225, 225, 220), width=6)
    elif marker == 19:
        for x, y in [(190, 410), (260, 350), (330, 430), (235, 520), (355, 545), (155, 560)]:
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=(240, 240, 230))
    elif marker == 24:
        draw.ellipse((165, 355, 375, 585), outline=(210, 210, 205), width=14)
        draw.ellipse((220, 415, 320, 525), outline=(20, 22, 32), width=12)
    image.save(path, format="PNG", optimize=False, compress_level=9)
    image.close()


def _write_sidecar(path: Path, *, title: str, tags: list[str], objects: list[str]) -> None:
    sidecar = Sidecar(
        title=title,
        description=(
            "Owned hermetic certification fixture; static deep-sky classification only; "
            "not production astronomy media; no coordinates, observation time, network, or generative AI."
        ),
        tags=tags,
        astronomy_objects=objects,
        ownership_confirmed=True,
        author_name="EL CENTINELA DEL UNIVERSO",
        attribution_required=False,
    )
    path.with_name(path.name + ".astromedia.json").write_text(
        json.dumps(sidecar.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _plan() -> AstronomyVideoPlan:
    scenes = [
        ScenePlan(
            scene_number=1,
            act=NarrativeAct.INTRODUCTION,
            duration_seconds=8,
            narration="La secuencia abre con un campo profundo genérico como contexto visual.",
            visual_requirement="Campo de cielo profundo genérico sin identificar un objeto concreto.",
            astronomy_objects=[],
            shot_type=ShotType.WIDE,
            material_keywords=["deep_sky_field", "star_field"],
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
            narration="La segunda placa identifica M31 como objeto profundo específico.",
            visual_requirement="M31 Andromeda galaxy identificada como placa estática, sin coordenadas ni fecha.",
            astronomy_objects=["M31", "Andromeda"],
            shot_type=ShotType.WIDE,
            material_keywords=["m31", "andromeda_galaxy", "galaxy"],
            source_priority=["OWN_MEDIA"],
            transition="Corte de identificación.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=3,
            act=NarrativeAct.DEVELOPMENT,
            duration_seconds=8,
            narration="La tercera placa identifica M42 sin reutilizar otra nebulosa genérica.",
            visual_requirement="M42 Orion nebula identificada como placa estática, sin coordenadas ni fecha.",
            astronomy_objects=["M42", "Orion Nebula"],
            shot_type=ShotType.MEDIUM,
            material_keywords=["m42", "orion_nebula", "nebula"],
            source_priority=["OWN_MEDIA"],
            transition="Corte de identificación.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=4,
            act=NarrativeAct.CLIMAX,
            duration_seconds=8,
            narration="La cuarta placa identifica M45 como objetivo de cúmulo específico.",
            visual_requirement="M45 Pleiades open cluster identificada como placa estática, sin coordenadas ni fecha.",
            astronomy_objects=["M45", "Pleiades"],
            shot_type=ShotType.MEDIUM,
            material_keywords=["m45", "pleiades", "open_cluster", "cluster"],
            source_priority=["OWN_MEDIA"],
            transition="Corte de identificación.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=5,
            act=NarrativeAct.RESOLUTION,
            duration_seconds=8,
            narration="La secuencia termina con M57 como objetivo profundo específico.",
            visual_requirement="M57 Ring nebula identificada como placa estática, sin coordenadas ni fecha.",
            astronomy_objects=["M57", "Ring Nebula"],
            shot_type=ShotType.CLOSE_UP,
            material_keywords=["m57", "ring_nebula", "nebula"],
            source_priority=["OWN_MEDIA"],
            transition="Fundido final.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
    ]
    return AstronomyVideoPlan(
        subject="Cielo profundo — identificación visual de clases estáticas",
        language="es-ES",
        audience="divulgacion astronomica general",
        hook="Del campo profundo a cuatro objetivos identificados.",
        scientific_context_summary=(
            "Replay hermético de etiquetas visuales estáticas de cielo profundo; no usa coordenadas, "
            "hora, fecha, efemérides, distancias, magnitudes ni posiciones actuales."
        ),
        narrative_arc=list(NarrativeAct),
        scenes=scenes,
        epilogue="La secuencia termina en revisión humana.",
        external_research_required=False,
        research_questions=[],
        context_hash="D" * 64,
        generation_origin=GenerationOrigin.DETERMINISTIC_FALLBACK,
        model_used="cloud-cert-fixture",
        repair_attempted=False,
        total_duration_seconds=40,
        requires_human_review=True,
        approved_for_publication=False,
        generated_at_utc=datetime.now(timezone.utc),
    )


_FIXTURES = [
    ("01-deep-sky-field.png", 4, "deep_sky_field star_field", ["deep_sky_field", "star_field"], []),
    ("02-m31-andromeda.png", 9, "M31 andromeda_galaxy galaxy", ["m31", "andromeda_galaxy", "galaxy"], ["m31", "andromeda"]),
    ("03-m42-orion-nebula.png", 14, "M42 orion_nebula nebula", ["m42", "orion_nebula", "nebula"], ["m42", "orion nebula"]),
    ("04-m45-pleiades.png", 19, "M45 Pleiades open_cluster", ["m45", "pleiades", "open_cluster", "cluster"], ["m45", "pleiades"]),
    ("05-m57-ring-nebula.png", 24, "M57 ring_nebula nebula", ["m57", "ring_nebula", "nebula"], ["m57", "ring nebula"]),
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


def test_deep_sky_media_replay_reaches_specific_5_of_5(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()
    paths = []
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
        IndexRequest(root=str(media_root), recursive=True, hash_mode=HashMode.NONE, import_task_artifacts=False)
    )
    assert index.indexed_items == 5
    assert index.non_renderable_items == 0
    assert index.errors == []

    outcome = _resolve(catalog, media_root)
    assert outcome.report.scene_count == 5
    assert outcome.report.selected_count == 5
    assert outcome.report.unresolved_count == 0
    assert outcome.report.publication_ready is True
    assert outcome.report.guardrails.material_selector_is_final_authority is True
    assert outcome.report.guardrails.irrelevant_broll_fallback is False
    assert outcome.report.guardrails.ai_generation_triggered is False
    assert outcome.report.guardrails.auto_publication is False
    assert outcome.report.guardrails.network_discovery_default is False

    selections = outcome.selection["selections"]
    expected_ids = [_media_id_for_path(catalog, path) for path in paths]
    assert [row["selected_media_id"] for row in selections] == expected_ids
    assert len({row["selected_media_id"] for row in selections}) == 5
    assert all(row["selected_publication_eligible"] is True for row in selections)

    expected_specificity = {
        2: "andromeda_galaxy",
        3: "orion_nebula",
        4: "open_cluster",
        5: "ring_nebula",
    }
    for scene_number, required_token in expected_specificity.items():
        reasons = list(selections[scene_number - 1]["reasons"])
        assert any(
            reason.startswith("specificity_overlap:") and required_token in reason
            for reason in reasons
        ), (scene_number, reasons)
