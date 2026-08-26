from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.astronomy import ScientificStatus
from app.models.astromedia import (
    AstroMediaItem,
    MediaType,
    Origin,
    Provider,
    Provenance,
    Rights,
)
from app.models.material_selection import SelectionStatus
from app.services.material_selection import MaterialSelector


def _item(
    media_id: str,
    *,
    title: str = "Moon",
    tags: list[str] | None = None,
    objects: list[str] | None = None,
) -> AstroMediaItem:
    return AstroMediaItem(
        media_id=media_id,
        local_path=f"C:\\fixture\\{media_id}.mp4",
        filename=f"{media_id}.mp4",
        media_type=MediaType.VIDEO,
        width=1920,
        height=1080,
        fps=30.0,
        duration_seconds=5.0,
        file_size_bytes=100,
        mtime_ns=1,
        provider=Provider.NASA,
        title=title,
        tags=tags or [],
        astronomy_objects=objects or [],
        search_term=None,
        rights_status=Rights.VERIFIED_LICENSE,
        visual_origin=Origin.REAL_EXTERNAL,
        scientific_status=ScientificStatus.NO_VERIFICADO,
        provenance_kind=Provenance.LOCAL_LIBRARY,
        metadata_source="c2.11j-contract",
        renderable=True,
        active=True,
        indexed_at_utc=datetime.now(timezone.utc),
    )


class _Catalog:
    def __init__(self, items: list[AstroMediaItem]):
        self._items = {item.media_id: item for item in items}

    def list_items(self, active_only=True):
        values = list(self._items.values())
        return [item for item in values if item.active] if active_only else values

    def get(self, media_id):
        return self._items.get(media_id)

    def get_override(self, scene_key):
        return None


def _scene(*, objects, keywords, visual):
    return SimpleNamespace(
        scene_number=1,
        astronomy_objects=objects,
        material_keywords=keywords,
        visual_requirement=visual,
        ai_recreation_allowed=False,
    )


def _request(scene):
    plan = SimpleNamespace(subject="Luna", context_hash="C2_11J", scenes=[scene])
    return SimpleNamespace(
        plan=plan,
        min_relevance_score=6.0,
        max_alternatives=3,
        avoid_reuse=True,
        allow_ai_last_resort=False,
        publication_eligible_only=True,
    )


def _select(candidate, scene):
    return MaterialSelector(_Catalog([candidate])).select_plan(_request(scene))


def test_c2_11j_spanish_luna_alias_is_lexical_not_strong_object_overlap():
    generic_moon = _item(
        "generic-moon",
        title="Moon",
        tags=["moon"],
        objects=["moon"],
    )
    generic_scene = _scene(
        objects=["Luna"],
        keywords=["Luna"],
        visual="Vista centrada de la Luna.",
    )

    result = _select(generic_moon, generic_scene)
    selection = result.selections[0]

    assert selection.status == SelectionStatus.SELECTED
    assert selection.selected_media_id == "generic-moon"
    assert all(
        reason != "object_overlap:moon" for reason in selection.reasons
    ), "Luna->moon must remain lexical evidence, not synthetic strong overlap"


@pytest.mark.parametrize(
    ("keywords", "visual"),
    [
        (
            ["moon", "fraccion iluminada", "fase"],
            "Vista de la Luna mostrando una fraccion iluminada del 97 por ciento.",
        ),
        (
            ["moon", "diametro angular", "geometria"],
            "Representacion geometrica del diametro angular lunar de 0,5 grados.",
        ),
        (
            ["moon", "magnitud visual", "brillo comparativo"],
            "Diagrama de brillo comparativo para una magnitud visual de -12,14.",
        ),
        (
            ["moon", "capricornus", "mapa estelar"],
            "Mapa estelar de la Luna dentro de la constelacion de Capricornus.",
        ),
    ],
)
def test_c2_11j_generic_moon_rejected_for_specific_lunar_requirements(
    keywords,
    visual,
):
    generic_moon = _item(
        "generic-moon",
        title="Moon",
        tags=["moon"],
        objects=["moon"],
    )
    specific_scene = _scene(
        objects=["moon"],
        keywords=keywords,
        visual=visual,
    )

    result = _select(generic_moon, specific_scene)
    selection = result.selections[0]

    assert selection.status == SelectionStatus.NO_ADEQUATE_MEDIA
    assert selection.selected_media_id is None


def test_c2_11j_specific_secondary_evidence_is_accepted_and_auditable():
    moon_capricornus = _item(
        "moon-capricornus-map",
        title="Moon in Capricornus star map",
        tags=["moon", "capricornus", "star map"],
        objects=["moon", "capricornus"],
    )
    specific_scene = _scene(
        objects=["moon"],
        keywords=["moon", "capricornus", "mapa estelar"],
        visual="Mapa estelar de la Luna dentro de la constelacion de Capricornus.",
    )

    result = _select(moon_capricornus, specific_scene)
    selection = result.selections[0]

    assert selection.status == SelectionStatus.SELECTED
    assert selection.selected_media_id == "moon-capricornus-map"
    assert any(
        reason.startswith("specificity_overlap:")
        and "capricornus" in reason
        for reason in selection.reasons
    )


def test_c2_11j_generic_epilogue_can_use_lexically_anchored_moon_without_object():
    generic_moon = _item(
        "generic-moon",
        title="Moon",
        tags=["moon"],
        objects=["moon"],
    )
    epilogue_scene = _scene(
        objects=[],
        keywords=["Luna", "satelite lunar"],
        visual=(
            "Vista cenital centrada en el satelite lunar como punto de "
            "referencia estelar."
        ),
    )

    result = _select(generic_moon, epilogue_scene)
    selection = result.selections[0]

    assert selection.status == SelectionStatus.SELECTED
    assert selection.selected_media_id == "generic-moon"
    assert not any(reason.startswith("object_overlap:") for reason in selection.reasons)


def test_c2_11j_missing_structured_object_does_not_bypass_specificity():
    """V31 scene-5 class guard: lexical Luna cannot satisfy a specific demand alone."""

    generic_moon = _item(
        "generic-moon",
        title="Moon",
        tags=["moon"],
        objects=["moon"],
    )
    ungrounded_specific_scene = _scene(
        objects=[],
        keywords=["Luna", "magnitud visual", "brillo comparativo"],
        visual=(
            "Diagrama de brillo comparativo de la Luna para una magnitud "
            "visual de -12,14."
        ),
    )

    result = _select(generic_moon, ungrounded_specific_scene)
    selection = result.selections[0]

    assert selection.status == SelectionStatus.NO_ADEQUATE_MEDIA
    assert selection.selected_media_id is None
    assert not any(reason.startswith("object_overlap:") for reason in selection.reasons)
