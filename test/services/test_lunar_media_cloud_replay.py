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
from app.services.centinela.scientific_visuals import render_factlock_scientific_visual
from app.services.centinela.writer_room import FactLock
from app.models.astronomy_director import GroundingFact


def _fact_lock() -> FactLock:
    return FactLock(
        subject="La Luna",
        research_mode="GENERIC_GEOCENTRIC",
        context_hash="C" * 64,
        facts=[
            GroundingFact(
                fact_id="moon:illuminated_fraction",
                label_es="Fraccion iluminada lunar",
                value=0.973,
                unit="fraction",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
                source_ids=["source:fixture"],
            ),
            GroundingFact(
                fact_id="moon:phase_name",
                label_es="Fase lunar",
                value="waxing gibbous",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
                source_ids=["source:fixture"],
            ),
            GroundingFact(
                fact_id="body:moon:geocentric_distance_km",
                label_es="Distancia geocentrica lunar",
                value=384400,
                unit="km",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
                source_ids=["source:fixture"],
            ),
            GroundingFact(
                fact_id="moon:angular_diameter_deg",
                label_es="Diametro angular lunar",
                value=0.5,
                unit="deg",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
                source_ids=["source:fixture"],
            ),
            GroundingFact(
                fact_id="body:moon:visual_magnitude",
                label_es="Magnitud visual lunar",
                value=-12.14,
                unit="mag",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
                source_ids=["source:fixture"],
            ),
            GroundingFact(
                fact_id="body:moon:constellation",
                label_es="Constelacion lunar",
                value="Capricornus",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
                source_ids=["source:fixture"],
            ),
            GroundingFact(
                fact_id="context:moment_utc",
                label_es="Momento UTC",
                value="2026-08-25T23:00:00Z",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
                source_ids=["source:fixture"],
            ),
        ],
        sources=[],
        source_ids=["source:fixture"],
        scope_note="Replay hermetico de las cinco clases de escena del Lunar V31.",
        location_assumed=False,
        moment_basis="fixture UTC",
        primary_source_verification_required_for_publication=True,
        generated_at_utc=datetime.now(timezone.utc),
    )


def _fixture_image(path: Path, marker: int) -> None:
    image = Image.new("RGB", (540, 960), (12 + marker, 16 + marker, 24 + marker))
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 240, 460, 620), outline=(220, 224, 232), width=4)
    draw.line((80, 720 - marker, 460, 720 - marker), fill=(100, 170, 230), width=3)
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
            "Owned hermetic certification fixture for C2.11J lunar MEDIA replay; "
            "no network; no generative AI."
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
            duration_seconds=12,
            narration="La Luna aparece casi completamente iluminada en este instante.",
            visual_requirement=(
                "Vista del satelite lunar mostrando su superficie con el 97,3 por ciento "
                "de la fraccion iluminada visible."
            ),
            astronomy_objects=["Luna"],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["Luna", "fraccion iluminada", "fase"],
            source_priority=["OWN_MEDIA", "NASA"],
            transition="Corte motivado.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=2,
            act=NarrativeAct.DEVELOPMENT,
            duration_seconds=12,
            narration="Su diametro angular aparente ronda medio grado.",
            visual_requirement=(
                "Representacion geometrica del satelite lunar mostrando su diametro "
                "angular de 0,5 grados."
            ),
            astronomy_objects=["Luna"],
            shot_type=ShotType.GRAPHIC,
            material_keywords=["Luna", "diametro angular", "geometria"],
            source_priority=["OWN_MEDIA"],
            transition="Continuidad observacional.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=3,
            act=NarrativeAct.CLIMAX,
            duration_seconds=12,
            narration="Su magnitud visual la convierte en un objeto extraordinariamente brillante.",
            visual_requirement=(
                "Diagrama de brillo comparativo indicando la magnitud visual de -12,14 "
                "para el satelite lunar."
            ),
            astronomy_objects=["Luna"],
            shot_type=ShotType.GRAPHIC,
            material_keywords=["Luna", "magnitud visual", "brillo comparativo"],
            source_priority=["OWN_MEDIA"],
            transition="Corte de enfasis.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=4,
            act=NarrativeAct.RESOLUTION,
            duration_seconds=12,
            narration="En el mapa celeste la Luna se situa dentro de Capricornus.",
            visual_requirement=(
                "Mapa estelar mostrando al satelite lunar posicionado dentro de la "
                "constelacion de Capricornus."
            ),
            astronomy_objects=["Luna"],
            shot_type=ShotType.GRAPHIC,
            material_keywords=["Luna", "Capricornus", "mapa estelar"],
            source_priority=["OWN_MEDIA"],
            transition="Corte respirado.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=5,
            act=NarrativeAct.EPILOGUE,
            duration_seconds=12,
            narration="La Luna queda como referencia luminosa para cerrar la observacion.",
            visual_requirement=(
                "Vista cenital centrada en el satelite lunar como punto de referencia estelar."
            ),
            astronomy_objects=[],
            shot_type=ShotType.WIDE,
            material_keywords=["Luna", "satelite lunar", "referencia estelar"],
            source_priority=["OWN_MEDIA"],
            transition="Fundido final contemplativo.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
    ]

    return AstronomyVideoPlan(
        subject="La Luna",
        language="es-ES",
        audience="divulgacion astronomica general",
        hook="Cinco escenas lunares con evidencia visual cientifica especifica.",
        scientific_context_summary=(
            "Replay hermetico de las clases de escenas que bloquearon MEDIA en V31."
        ),
        narrative_arc=list(NarrativeAct),
        scenes=scenes,
        epilogue="La observacion termina en revision humana.",
        external_research_required=False,
        research_questions=[],
        context_hash="C" * 64,
        generation_origin=GenerationOrigin.DETERMINISTIC_FALLBACK,
        model_used="cloud-cert-fixture",
        repair_attempted=False,
        total_duration_seconds=60,
        requires_human_review=True,
        approved_for_publication=False,
        generated_at_utc=datetime.now(timezone.utc),
    )


def _media_id_for_path(catalog: AstroMediaCatalog, path: Path) -> str:
    resolved = path.resolve()
    for item in catalog.list_items(True):
        if Path(item.local_path).resolve() == resolved:
            return item.media_id
    raise AssertionError(f"indexed item not found for {path}")


def test_v31_class_lunar_media_replay_reaches_safe_5_of_5(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()

    fact_lock = _fact_lock()
    angular = render_factlock_scientific_visual(
        fact_lock,
        "moon:angular_diameter_deg",
        media_root,
    )
    magnitude = render_factlock_scientific_visual(
        fact_lock,
        "body:moon:visual_magnitude",
        media_root,
    )

    phase = media_root / "moon-phase-973.png"
    _fixture_image(phase, 7)
    _write_sidecar(
        phase,
        title="Moon phase illuminated fraction 97.3 percent",
        tags=["moon", "phase", "fraction", "illuminated", "lunar"],
        objects=["moon"],
    )

    capricornus = media_root / "moon-capricornus-map.png"
    _fixture_image(capricornus, 19)
    _write_sidecar(
        capricornus,
        title="Moon in Capricornus star map",
        tags=["moon", "capricornus", "constellation", "map", "star map"],
        objects=["moon", "capricornus"],
    )

    epilogue = media_root / "moon-centered-reference.png"
    _fixture_image(epilogue, 31)
    _write_sidecar(
        epilogue,
        title="Moon centered lunar reference view",
        tags=["moon", "lunar", "centered", "reference", "stellar", "satellite"],
        objects=["moon"],
    )

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

    outcome = MediaResolver(catalog=catalog).resolve(
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
    assert len(selections) == 5
    assert all(row["selected_publication_eligible"] is True for row in selections)
    assert all(row["selected_provider"] != "AI_GENERATED" for row in selections)

    angular_id = _media_id_for_path(catalog, angular.image_path)
    magnitude_id = _media_id_for_path(catalog, magnitude.image_path)
    capricornus_id = _media_id_for_path(catalog, capricornus)

    assert selections[1]["selected_media_id"] == angular_id
    assert selections[2]["selected_media_id"] == magnitude_id
    assert selections[3]["selected_media_id"] == capricornus_id

    # No scene may be certified solely because of a strong astronomy-object overlap.
    for row in selections:
        reasons = list(row["reasons"])
        secondary = [
            reason
            for reason in reasons
            if reason.startswith(
                (
                    "title_overlap:",
                    "tag_overlap:",
                    "search_overlap:",
                    "description_overlap:",
                    "filename_overlap:",
                    "specificity_overlap:",
                )
            )
        ]
        assert secondary, (row["scene_number"], reasons)

    # The V31 scene-5 class has no strong structured object, but remains safely
    # selectable because its generic lunar visual is explicitly lexically anchored.
    scene5 = selections[4]
    assert not any(reason.startswith("object_overlap:") for reason in scene5["reasons"])
    assert any(
        reason.startswith(("title_overlap:", "tag_overlap:"))
        for reason in scene5["reasons"]
    )
