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
    """Create a deterministic test plate; never production sky media."""
    image = Image.new("RGB", (540, 960), (5 + marker, 8 + marker, 16 + marker))
    draw = ImageDraw.Draw(image)
    stars = [(120, 200), (210, 300), (270, 385), (330, 470), (420, 575), (185, 520)]
    for index, (x, y) in enumerate(stars):
        r = 3 + ((index + marker) % 3)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(235, 235, 225))
    if marker in {9, 14}:
        for a, b in zip(stars[:-1], stars[1:]):
            draw.line((*a, *b), fill=(150, 165, 185), width=2)
    if marker == 14:
        for x, y in [(220, 430), (270, 430), (320, 430)]:
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(245, 245, 235))
    image.save(path, format="PNG", optimize=False, compress_level=9)
    image.close()


def _write_sidecar(path: Path, *, title: str, tags: list[str], objects: list[str]) -> None:
    sidecar = Sidecar(
        title=title,
        description=(
            "Owned hermetic certification fixture; static sky-classification only; "
            "not production astronomy media; no coordinates, event time, network, or generative AI."
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
            narration="La secuencia abre con un campo estelar amplio como contexto de observación.",
            visual_requirement="Campo estelar amplio sin identificación de una constelación concreta.",
            astronomy_objects=[],
            shot_type=ShotType.WIDE,
            material_keywords=["wide_star_field", "night_sky"],
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
            narration="Después identificamos la figura de Orión sin fijar coordenadas ni una hora concreta.",
            visual_requirement="Figura de la constelación de Orión como mapa estático sin coordenadas.",
            astronomy_objects=["Orion"],
            shot_type=ShotType.WIDE,
            material_keywords=["orion", "constellation_figure", "constellation"],
            source_priority=["OWN_MEDIA"],
            transition="Superposición conceptual.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=3,
            act=NarrativeAct.CLIMAX,
            duration_seconds=8,
            narration="El cinturón de Orión concentra la atención en su asterismo más reconocible.",
            visual_requirement="Cinturón de Orión identificable dentro de la constelación, sin posiciones actuales.",
            astronomy_objects=["Orion"],
            shot_type=ShotType.MEDIUM,
            material_keywords=["orion", "orion_belt", "constellation"],
            source_priority=["OWN_MEDIA"],
            transition="Acercamiento de detalle.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=4,
            act=NarrativeAct.RESOLUTION,
            duration_seconds=8,
            narration="Betelgeuse sirve como referencia estelar dentro de la narración de Orión.",
            visual_requirement="Betelgeuse identificada como referencia estelar, sin magnitud ni posición actual.",
            astronomy_objects=["Betelgeuse"],
            shot_type=ShotType.MEDIUM,
            material_keywords=["betelgeuse", "star_reference"],
            source_priority=["OWN_MEDIA"],
            transition="Corte de referencia.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=5,
            act=NarrativeAct.EPILOGUE,
            duration_seconds=8,
            narration="El epílogo devuelve la secuencia a la observación del cielo a simple vista.",
            visual_requirement="Contexto de observación del cielo a simple vista.",
            astronomy_objects=[],
            shot_type=ShotType.WIDE,
            material_keywords=["naked_eye_observation", "night_sky_context"],
            source_priority=["OWN_MEDIA"],
            transition="Fundido final.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
    ]
    return AstronomyVideoPlan(
        subject="Orión — lectura visual de una constelación",
        language="es-ES",
        audience="divulgacion astronomica general",
        hook="Del campo estelar al cinturón de Orión.",
        scientific_context_summary=(
            "Replay hermético de clases visuales estáticas de constelación; no usa coordenadas, "
            "hora, fecha, efemérides, magnitudes ni posiciones actuales."
        ),
        narrative_arc=list(NarrativeAct),
        scenes=scenes,
        epilogue="La secuencia termina en revisión humana.",
        external_research_required=False,
        research_questions=[],
        context_hash="C" * 64,
        generation_origin=GenerationOrigin.DETERMINISTIC_FALLBACK,
        model_used="cloud-cert-fixture",
        repair_attempted=False,
        total_duration_seconds=40,
        requires_human_review=True,
        approved_for_publication=False,
        generated_at_utc=datetime.now(timezone.utc),
    )


_FIXTURES = [
    ("01-wide-star-field.png", 4, "wide_star_field night_sky", ["wide_star_field", "night_sky"], []),
    ("02-orion-constellation.png", 9, "Orion constellation_figure", ["orion", "constellation_figure", "constellation"], ["orion"]),
    ("03-orion-belt.png", 14, "Orion orion_belt", ["orion", "orion_belt"], ["orion"]),
    ("04-betelgeuse.png", 19, "Betelgeuse star_reference", ["betelgeuse", "star_reference"], ["betelgeuse"]),
    ("05-naked-eye.png", 24, "naked_eye_observation night_sky_context", ["naked_eye_observation", "night_sky_context"], []),
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


def test_constellation_media_replay_reaches_safe_5_of_5(tmp_path):
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
    index = catalog.index_library(IndexRequest(root=str(media_root), recursive=True, hash_mode=HashMode.NONE, import_task_artifacts=False))
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

    expected_specificity = {2: "constellation_figure", 3: "orion_belt"}
    for scene_number, required_token in expected_specificity.items():
        reasons = list(selections[scene_number - 1]["reasons"])
        assert any(
            reason.startswith("specificity_overlap:") and required_token in reason
            for reason in reasons
        ), (scene_number, reasons)

    generic_orion_id = expected_ids[1]
    assert all(
        alt["media_id"] != generic_orion_id for alt in selections[2].get("alternatives", [])
    ), "generic Orion constellation media must not satisfy the Orion Belt subtype"
