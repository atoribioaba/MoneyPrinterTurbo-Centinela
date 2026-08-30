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
    image = Image.new("RGB", (540, 960), (12 + marker, 18 + marker, 28 + marker))
    draw = ImageDraw.Draw(image)
    draw.line((40, 720 - marker, 500, 720 - marker), fill=(220, 170, 90), width=4)
    draw.ellipse((210, 240 + marker, 330, 360 + marker), outline=(235, 235, 225), width=4)
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
            "Owned hermetic certification fixture for the F57 SOL_TO_MOON MEDIA replay; "
            "visual classification only; no ephemeris claim; no network; no generative AI."
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
            narration="El recorrido comienza con el Sol dominando el cielo.",
            visual_requirement="Vista real del Sol y su disco sobre un cielo diurno.",
            astronomy_objects=["Sol"],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["sun", "solar", "daylight", "sun_disc"],
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
            narration="La luz desciende hasta la puesta sobre el horizonte.",
            visual_requirement="Puesta de Sol real en el horizonte durante el ocaso.",
            astronomy_objects=["Sol"],
            shot_type=ShotType.WIDE,
            material_keywords=["sunset", "horizon", "dusk", "ocaso"],
            source_priority=["OWN_MEDIA"],
            transition="Continuidad temporal.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=3,
            act=NarrativeAct.CLIMAX,
            duration_seconds=8,
            narration="El crepusculo transforma el paisaje antes de la noche.",
            visual_requirement="Cielo de crepusculo y blue hour despues de la puesta.",
            astronomy_objects=[],
            shot_type=ShotType.WIDE,
            material_keywords=["twilight", "blue_hour", "crepusculo", "afterglow"],
            source_priority=["OWN_MEDIA"],
            transition="Fundido respirado.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=4,
            act=NarrativeAct.RESOLUTION,
            duration_seconds=8,
            narration="La Luna toma el relevo en el cielo que se oscurece.",
            visual_requirement="Vista real de la Luna apareciendo en un cielo de transicion nocturna.",
            astronomy_objects=["Luna"],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["moonrise", "lunar_rise", "moon", "night_transition"],
            source_priority=["OWN_MEDIA"],
            transition="Corte de revelacion.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
        ScenePlan(
            scene_number=5,
            act=NarrativeAct.EPILOGUE,
            duration_seconds=8,
            narration="La observacion termina con la Luna como referencia luminosa.",
            visual_requirement="Plano final contemplativo de la Luna centrada en el cielo nocturno.",
            astronomy_objects=["Luna"],
            shot_type=ShotType.TELEPHOTO,
            material_keywords=["lunar_epilogue", "moon_reference", "centered_moon", "night"],
            source_priority=["OWN_MEDIA"],
            transition="Fundido final contemplativo.",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        ),
    ]

    return AstronomyVideoPlan(
        subject="Sol a Luna",
        language="es-ES",
        audience="divulgacion astronomica general",
        hook="Del Sol al ocaso, del crepusculo a la Luna.",
        scientific_context_summary=(
            "Replay hermetico para certificar continuidad visual Sol-puesta-crepusculo-Luna "
            "sin introducir efemerides ni datos astronomicos no verificados."
        ),
        narrative_arc=list(NarrativeAct),
        scenes=scenes,
        epilogue="La observacion termina en revision humana.",
        external_research_required=False,
        research_questions=[],
        context_hash="S" * 64,
        generation_origin=GenerationOrigin.DETERMINISTIC_FALLBACK,
        model_used="cloud-cert-fixture",
        repair_attempted=False,
        total_duration_seconds=40,
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


def test_sol_to_moon_media_replay_reaches_safe_5_of_5(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()

    fixtures = [
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

    paths: list[Path] = []
    for filename, marker, title, tags, objects in fixtures:
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
    assert [row["scene_number"] for row in selections] == [1, 2, 3, 4, 5]
    assert all(row["selected_publication_eligible"] is True for row in selections)
    assert all(row["selected_provider"] != "AI_GENERATED" for row in selections)
    assert len({row["selected_media_id"] for row in selections}) == 5

    expected_ids = [_media_id_for_path(catalog, path) for path in paths]
    assert [row["selected_media_id"] for row in selections] == expected_ids

    # Every selected scene must carry lexical evidence tied to its own visual class.
    for row in selections:
        reasons = list(row["reasons"])
        assert any(
            reason.startswith(("title_overlap:", "tag_overlap:"))
            for reason in reasons
        ), (row["scene_number"], reasons)

    # Spanish body names may contribute lexical aliases, but this replay does not
    # rely on fabricated strong object overlap between Sol/sun or Luna/moon.
    for scene_number in (1, 2, 4, 5):
        reasons = list(selections[scene_number - 1]["reasons"])
        assert not any(reason.startswith("object_overlap:") for reason in reasons)
