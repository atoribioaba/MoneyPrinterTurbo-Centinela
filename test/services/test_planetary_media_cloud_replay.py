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
    """Create a deterministic renderable test plate, not an astronomy recreation."""
    image = Image.new("RGB", (540, 960), (15 + marker, 20 + marker, 30 + marker))
    draw = ImageDraw.Draw(image)
    draw.ellipse((150, 220, 390, 460), outline=(230, 220, 190), width=5)
    draw.line((165, 300 + marker, 375, 300 + marker), fill=(180, 170, 150), width=5)
    draw.line((165, 350 + marker, 375, 350 + marker), fill=(180, 170, 150), width=5)
    draw.ellipse((305, 345, 340, 365), outline=(235, 150, 120), width=4)
    for offset in (0, 55, 110, 165):
        draw.ellipse((70 + offset, 600, 82 + offset, 612), outline=(220, 220, 210), width=2)
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
            "Owned hermetic certification fixture; visual classification only; "
            "no ephemeris or numeric claim; no network; no generative AI."
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
            narration="Jupiter abre la observacion como un planeta de disco bien definido.",
            visual_requirement="Vista real generica del disco completo de Jupiter.",
            astronomy_objects=["Jupiter"],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["jupiter", "planet_disc", "full_disk"],
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
            narration="Sus bandas nubosas organizan visualmente la atmosfera del planeta.",
            visual_requirement=(
                "Bandas nubosas ecuatoriales de Jupiter distribuidas por latitud, "
                "sin datos numericos."
            ),
            astronomy_objects=["Jupiter"],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["jupiter", "equatorial_cloud_bands", "latitude"],
            source_priority=["OWN_MEDIA"],
            transition="Acercamiento observacional.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=3,
            act=NarrativeAct.CLIMAX,
            duration_seconds=8,
            narration="La Gran Mancha Roja destaca como rasgo atmosferico reconocible.",
            visual_requirement=(
                "Vista de Jupiter con la Gran Mancha Roja identificable en su atmosfera; "
                "referencia de latitud sin coordenadas ni efemerides."
            ),
            astronomy_objects=["Jupiter"],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["jupiter", "great_red_spot", "latitude"],
            source_priority=["OWN_MEDIA"],
            transition="Corte de detalle.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=4,
            act=NarrativeAct.RESOLUTION,
            duration_seconds=8,
            narration="El sistema galileano amplia la observacion alrededor de Jupiter.",
            visual_requirement=(
                "Sistema de satelites galileanos en orbita alrededor de Jupiter, "
                "sin afirmar posiciones actuales."
            ),
            astronomy_objects=["Jupiter"],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["jupiter", "galilean_moons", "orbit"],
            source_priority=["OWN_MEDIA"],
            transition="Apertura del encuadre.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=5,
            act=NarrativeAct.EPILOGUE,
            duration_seconds=8,
            narration="La secuencia termina en el contexto de observacion telescopica.",
            visual_requirement="Encuadre telescopico de observacion planetaria de Jupiter.",
            astronomy_objects=[],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["telescope_observation", "eyepiece_jupiter"],
            source_priority=["OWN_MEDIA"],
            transition="Fundido final contemplativo.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
    ]

    return AstronomyVideoPlan(
        subject="Jupiter — observacion planetaria",
        language="es-ES",
        audience="divulgacion astronomica general",
        hook="Del disco de Jupiter a sus rasgos atmosfericos y su sistema galileano.",
        scientific_context_summary=(
            "Replay hermetico de categorias visuales planetarias estaticas; no usa "
            "posiciones actuales, coordenadas, efemerides ni valores numericos."
        ),
        narrative_arc=list(NarrativeAct),
        scenes=scenes,
        epilogue="La observacion termina en revision humana.",
        external_research_required=False,
        research_questions=[],
        context_hash="P" * 64,
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
        "01-jupiter-full-disk.png",
        4,
        "Jupiter planet_disc full_disk",
        ["jupiter", "planet_disc", "full_disk"],
        ["jupiter"],
    ),
    (
        "02-jupiter-cloud-bands.png",
        9,
        "Jupiter equatorial_cloud_bands",
        ["jupiter", "equatorial_cloud_bands"],
        ["jupiter"],
    ),
    (
        "03-jupiter-great-red-spot.png",
        14,
        "Jupiter great_red_spot",
        ["jupiter", "great_red_spot"],
        ["jupiter"],
    ),
    (
        "04-jupiter-galilean-system.png",
        19,
        "Jupiter galilean_moons",
        ["jupiter", "galilean_moons"],
        ["jupiter"],
    ),
    (
        "05-telescope-jupiter.png",
        24,
        "Telescope_observation eyepiece_jupiter",
        ["telescope_observation", "eyepiece_jupiter"],
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


def test_planetary_media_replay_reaches_safe_5_of_5(tmp_path):
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
        2: "equatorial_cloud_bands",
        3: "great_red_spot",
        4: "galilean_moons",
    }
    generic_id = expected_ids[0]
    for scene_number, required_token in expected_specificity.items():
        row = selections[scene_number - 1]
        reasons = list(row["reasons"])
        assert any(
            reason.startswith("specificity_overlap:") and required_token in reason
            for reason in reasons
        ), (scene_number, reasons)
        assert all(
            alternative["media_id"] != generic_id
            for alternative in row.get("alternatives", [])
        ), "generic Jupiter must not survive a scientifically specific visual gate"
