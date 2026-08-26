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
from app.services.material_selection import (
    MaterialSelectionError,
    MaterialSelector,
)


def item(
    media_id,
    *,
    provider=Provider.LOCAL_MEDIA,
    rights=Rights.UNVERIFIED,
    title="Moon",
    tags=None,
    objects=None,
    search_term=None,
    origin=Origin.REAL_EXTERNAL,
    active=True,
    renderable=True,
    duplicate_of=None,
):
    return AstroMediaItem(
        media_id=media_id,
        local_path=(f"C:\\fixture\\{media_id}.mp4"),
        filename=(f"{media_id}.mp4"),
        media_type=(MediaType.VIDEO),
        width=1920,
        height=1080,
        fps=30.0,
        duration_seconds=5.0,
        file_size_bytes=100,
        mtime_ns=1,
        provider=provider,
        title=title,
        tags=(tags or []),
        astronomy_objects=(objects or []),
        search_term=search_term,
        rights_status=rights,
        visual_origin=origin,
        scientific_status=(ScientificStatus.NO_VERIFICADO),
        provenance_kind=(Provenance.LOCAL_LIBRARY),
        metadata_source="test",
        duplicate_of_media_id=(duplicate_of),
        renderable=renderable,
        active=active,
        indexed_at_utc=(datetime.now(timezone.utc)),
    )


class Catalog:
    def __init__(
        self,
        items,
        overrides=None,
    ):
        self.items = {value.media_id: value for value in items}

        self.overrides = overrides or {}

    def list_items(
        self,
        active_only=True,
    ):
        values = list(self.items.values())

        if active_only:
            return [value for value in values if value.active]

        return values

    def get(
        self,
        media_id,
    ):
        return self.items.get(media_id)

    def get_override(
        self,
        scene_key,
    ):
        return self.overrides.get(scene_key)


def scene(
    number=1,
    *,
    objects=None,
    keywords=None,
    visual="Moon over night sky",
    ai=False,
):
    return SimpleNamespace(
        scene_number=number,
        astronomy_objects=(["moon"] if objects is None else objects),
        material_keywords=(
            [
                "moon",
                "night sky",
            ]
            if keywords is None
            else keywords
        ),
        visual_requirement=visual,
        ai_recreation_allowed=ai,
    )


def plan(
    scenes,
):
    return SimpleNamespace(
        subject="Moon",
        context_hash="CTX",
        scenes=scenes,
    )


def request(
    plan_value,
    *,
    min_score=6.0,
    avoid=True,
    allow_ai=True,
    publication_only=False,
):
    return SimpleNamespace(
        plan=plan_value,
        min_relevance_score=min_score,
        max_alternatives=3,
        avoid_reuse=avoid,
        allow_ai_last_resort=allow_ai,
        publication_eligible_only=publication_only,
    )


def test_own_media_wins_equal_relevance():
    own = item(
        "own",
        provider=Provider.OWN_MEDIA,
        rights=Rights.CONFIRMED_OWNED,
        objects=["moon"],
        origin=Origin.REAL_OWN,
    )

    nasa = item(
        "nasa",
        provider=Provider.NASA,
        rights=Rights.VERIFIED_LICENSE,
        objects=["moon"],
    )

    result = MaterialSelector(
        Catalog(
            [
                nasa,
                own,
            ]
        )
    ).select_plan(request(plan([scene()])))

    assert result.selections[0].selected_media_id == "own"


def test_manual_override_is_hard_priority():
    normal = item(
        "normal",
        provider=Provider.OWN_MEDIA,
        rights=Rights.CONFIRMED_OWNED,
        objects=["moon"],
        origin=Origin.REAL_OWN,
    )

    manual = item(
        "manual",
        title="Unrelated title",
    )

    result = MaterialSelector(
        Catalog(
            [
                normal,
                manual,
            ],
            {"CTX:scene:1": "manual"},
        )
    ).select_plan(request(plan([scene()])))

    assert result.selections[0].status == SelectionStatus.MANUAL_OVERRIDE

    assert result.selections[0].selected_media_id == "manual"

    assert result.selections[0].review_required is True


def test_restricted_never_auto_selected():
    restricted = item(
        "restricted",
        provider=Provider.NASA,
        rights=Rights.RESTRICTED,
        objects=["moon"],
    )

    result = MaterialSelector(Catalog([restricted])).select_plan(
        request(plan([scene()]))
    )

    assert result.selections[0].status == SelectionStatus.NO_ADEQUATE_MEDIA


def test_reuse_penalty_prefers_equal_second_clip():
    first = item(
        "first",
        provider=Provider.OWN_MEDIA,
        rights=Rights.CONFIRMED_OWNED,
        objects=["moon"],
        origin=Origin.REAL_OWN,
    )

    second = item(
        "second",
        provider=Provider.OWN_MEDIA,
        rights=Rights.CONFIRMED_OWNED,
        objects=["moon"],
        origin=Origin.REAL_OWN,
    )

    result = MaterialSelector(
        Catalog(
            [
                first,
                second,
            ]
        )
    ).select_plan(
        request(
            plan(
                [
                    scene(1),
                    scene(2),
                ]
            ),
            avoid=True,
        )
    )

    assert (
        result.selections[0].selected_media_id != result.selections[1].selected_media_id
    )


def test_best_reused_clip_can_beat_weak_alternative():
    strong = item(
        "strong",
        provider=Provider.OWN_MEDIA,
        rights=Rights.CONFIRMED_OWNED,
        title="Moon moon night sky",
        tags=[
            "moon",
            "night sky",
        ],
        objects=["moon"],
        origin=Origin.REAL_OWN,
    )

    weak = item(
        "weak",
        provider=Provider.OWN_MEDIA,
        rights=Rights.CONFIRMED_OWNED,
        title="Moon",
        objects=[],
        origin=Origin.REAL_OWN,
    )

    result = MaterialSelector(
        Catalog(
            [
                strong,
                weak,
            ]
        )
    ).select_plan(
        request(
            plan(
                [
                    scene(1),
                    scene(2),
                ]
            ),
            avoid=True,
        )
    )

    assert result.selections[0].selected_media_id == "strong"

    assert result.selections[1].selected_media_id == "strong"


def test_no_adequate_media_requests_ai_only_if_scene_allows():
    weak = item(
        "weak",
        title="Clouds",
        objects=[],
    )

    selector = MaterialSelector(Catalog([weak]))

    allowed = selector.select_plan(request(plan([scene(ai=True)])))

    forbidden = selector.select_plan(request(plan([scene(ai=False)])))

    assert allowed.selections[0].status == SelectionStatus.AI_RECREATION_REQUIRED

    assert forbidden.selections[0].status == SelectionStatus.NO_ADEQUATE_MEDIA


def test_existing_ai_is_last_resort_when_allowed():
    ai = item(
        "ai",
        provider=Provider.AI_GENERATED,
        rights=Rights.VERIFIED_LICENSE,
        objects=["moon"],
        origin=Origin.AI_GENERATED,
    )

    result = MaterialSelector(Catalog([ai])).select_plan(
        request(plan([scene(ai=True)]))
    )

    assert result.selections[0].status == SelectionStatus.SELECTED_AI_RECREATION

    assert result.selections[0].review_required is True


def test_existing_ai_not_selected_when_scene_disallows():
    ai = item(
        "ai-forbidden",
        provider=Provider.AI_GENERATED,
        rights=Rights.VERIFIED_LICENSE,
        objects=["moon"],
        origin=Origin.AI_GENERATED,
    )

    result = MaterialSelector(Catalog([ai])).select_plan(
        request(plan([scene(ai=False)]))
    )

    assert result.selections[0].status == SelectionStatus.NO_ADEQUATE_MEDIA

    assert result.selections[0].selected_media_id is None


def test_unverified_selection_not_publication_ready():
    candidate = item(
        "candidate",
        provider=Provider.NASA,
        rights=Rights.UNVERIFIED,
        objects=["moon"],
    )

    result = MaterialSelector(Catalog([candidate])).select_plan(
        request(plan([scene()]))
    )

    assert result.selected_count == 1

    assert result.review_required is True

    assert result.publication_ready is False


def test_publication_only_filters_unverified():
    candidate = item(
        "unverified",
        provider=Provider.NASA,
        rights=Rights.UNVERIFIED,
        objects=["moon"],
    )

    result = MaterialSelector(Catalog([candidate])).select_plan(
        request(
            plan([scene()]),
            publication_only=True,
        )
    )

    assert result.selected_count == 0


def test_duplicate_item_not_selected():
    canonical = item(
        "canonical",
        provider=Provider.OWN_MEDIA,
        rights=Rights.CONFIRMED_OWNED,
        objects=["moon"],
        origin=Origin.REAL_OWN,
    )

    duplicate = item(
        "duplicate",
        provider=Provider.OWN_MEDIA,
        rights=Rights.CONFIRMED_OWNED,
        objects=["moon"],
        origin=Origin.REAL_OWN,
        duplicate_of=("canonical"),
    )

    result = MaterialSelector(
        Catalog(
            [
                duplicate,
                canonical,
            ]
        )
    ).select_plan(request(plan([scene()])))

    assert result.selections[0].selected_media_id == "canonical"


def test_invalid_manual_override_raises():
    selector = MaterialSelector(
        Catalog(
            [],
            {"CTX:scene:1": "missing"},
        )
    )

    with pytest.raises(MaterialSelectionError):
        selector.select_plan(request(plan([scene()])))


# C2.11J specificity contract. A generic one-object requirement may use generic
# Moon media, but a scene-specific scientific requirement must not be satisfied
# solely because both sides contain the Moon object label.
def test_scientific_selector_keeps_generic_single_object_requirement():
    generic_moon = item(
        "generic-moon",
        provider=Provider.NASA,
        rights=Rights.VERIFIED_LICENSE,
        title="Moon",
        tags=["moon"],
        objects=["moon"],
    )

    generic_scene = scene(
        objects=["moon"],
        keywords=["moon"],
        visual="Vista centrada de la Luna.",
    )

    result = MaterialSelector(Catalog([generic_moon])).select_plan(
        request(plan([generic_scene]), publication_only=True)
    )

    assert result.selections[0].status == SelectionStatus.SELECTED
    assert result.selections[0].selected_media_id == "generic-moon"


def test_scientific_selector_rejects_generic_object_only_for_specific_scene():
    generic_moon = item(
        "generic-moon",
        provider=Provider.NASA,
        rights=Rights.VERIFIED_LICENSE,
        title="Moon",
        tags=["moon"],
        objects=["moon"],
    )

    specific_scene = scene(
        objects=["moon"],
        keywords=["moon", "capricornus", "mapa estelar"],
        visual=(
            "Mapa estelar mostrando a la Luna posicionada dentro de "
            "la constelacion de Capricornus."
        ),
    )

    result = MaterialSelector(Catalog([generic_moon])).select_plan(
        request(plan([specific_scene]), publication_only=True)
    )

    assert result.selections[0].status == SelectionStatus.NO_ADEQUATE_MEDIA
    assert result.selections[0].selected_media_id is None


def test_scientific_selector_accepts_specific_secondary_visual_evidence():
    specific_map = item(
        "moon-capricornus-map",
        provider=Provider.NASA,
        rights=Rights.VERIFIED_LICENSE,
        title="Moon in Capricornus star map",
        tags=["moon", "capricornus", "star map"],
        objects=["moon", "capricornus"],
    )

    specific_scene = scene(
        objects=["moon"],
        keywords=["moon", "capricornus", "mapa estelar"],
        visual=(
            "Mapa estelar mostrando a la Luna posicionada dentro de "
            "la constelacion de Capricornus."
        ),
    )

    result = MaterialSelector(Catalog([specific_map])).select_plan(
        request(plan([specific_scene]), publication_only=True)
    )

    assert result.selections[0].status == SelectionStatus.SELECTED
    assert result.selections[0].selected_media_id == "moon-capricornus-map"
