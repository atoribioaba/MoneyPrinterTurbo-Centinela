from __future__ import annotations

from types import SimpleNamespace

from app.models.astronomy import ScientificStatus
from app.models.astromedia import Origin, Provider, Rights
from app.models.material_selection import MaterialSelectionPlan, SelectionStatus
from app.services.centinela.media_resolver import MediaResolverRequest
from app.services.material_selection import MaterialSelector
from test.services.test_material_selection import Catalog, item, plan, request, scene
from test.services.test_media_resolver import make_item, make_plan, make_resolver


def test_c17_guardrail_manifest_is_fail_closed_and_publication_neutral():
    resolver, _ = make_resolver([make_item("moon")])
    outcome = resolver.resolve(
        make_plan(),
        MediaResolverRequest(
            semantic_evidence=False,
            analyze_selected_focal=False,
        ),
    )

    guardrails = outcome.report.guardrails
    assert guardrails.material_selector_is_final_authority is True
    assert guardrails.semantic_matcher_is_secondary_evidence_only is True
    assert guardrails.smartfocal_runs_after_selection_only is True
    assert guardrails.restricted_media_rejected_by_selector is True
    assert guardrails.irrelevant_broll_fallback is False
    assert guardrails.ai_generation_triggered is False
    assert guardrails.wangp_triggered is False
    assert guardrails.auto_publication is False
    assert guardrails.network_discovery_default is False


def test_c17_semantic_rank_cannot_override_material_selector_authority():
    own = make_item(
        "own-authority",
        path="C:/z-own-authority.mp4",
        provider=Provider.OWN_MEDIA,
        rights=Rights.CONFIRMED_OWNED,
    )
    stock = make_item(
        "semantic-favorite",
        path="C:/a-semantic-favorite.mp4",
        provider=Provider.PEXELS,
        rights=Rights.VERIFIED_LICENSE,
    )

    def semantic(**kwargs):
        return SimpleNamespace(
            video_paths=tuple(reversed(kwargs["video_paths"])),
            queries=("semantic favorite first",),
            matches=(),
            method="c17_adversarial_semantic_order",
            error="",
            analyzed=True,
        )

    resolver, _ = make_resolver([own, stock], semantic=semantic)
    outcome = resolver.resolve(
        make_plan(),
        MediaResolverRequest(
            semantic_evidence=True,
            analyze_selected_focal=False,
        ),
    )
    selection = MaterialSelectionPlan.model_validate(outcome.selection)

    assert outcome.report.scenes[0].candidates[0].semantic_rank in {1, 2}
    assert selection.selections[0].selected_media_id == "own-authority"


def test_c17_smartfocal_is_not_called_until_a_material_is_selected():
    calls: list[str] = []

    def focal(path):
        calls.append(path)
        raise AssertionError("SmartFocal must not run for an unresolved scene")

    resolver, _ = make_resolver([], focal=focal)
    outcome = resolver.resolve(
        make_plan(),
        MediaResolverRequest(analyze_selected_focal=True),
    )

    assert outcome.report.unresolved_count == 5
    assert calls == []
    assert all(scene_row.focal.method == "not_selected" for scene_row in outcome.report.scenes)


def test_c17_no_adequate_media_recovers_only_after_relevant_m57_is_added():
    moon = item(
        "moon-generic",
        provider=Provider.OWN_MEDIA,
        rights=Rights.CONFIRMED_OWNED,
        title="Moon",
        tags=["moon"],
        objects=["moon"],
        origin=Origin.REAL_OWN,
    )
    scenes = [scene(number=index) for index in range(1, 5)]
    scenes.append(
        scene(
            number=5,
            objects=["messier57"],
            keywords=["messier57", "ring nebula"],
            visual="Messier 57 Ring Nebula in Lyra",
        )
    )
    plan_value = plan(scenes)
    catalog = Catalog([moon])
    selector = MaterialSelector(catalog)

    blocked = selector.select_plan(request(plan_value, allow_ai=False))
    assert blocked.selected_count == 4
    assert blocked.unresolved_count == 1
    assert blocked.selections[4].status == SelectionStatus.NO_ADEQUATE_MEDIA
    assert blocked.publication_ready is False

    m57 = item(
        "m57-relevant",
        provider=Provider.OWN_MEDIA,
        rights=Rights.CONFIRMED_OWNED,
        title="Messier 57 Ring Nebula",
        tags=["messier57", "ring nebula", "lyra"],
        objects=["messier57"],
        origin=Origin.REAL_OWN,
    )
    catalog.items[m57.media_id] = m57

    recovered = selector.select_plan(request(plan_value, allow_ai=False))
    assert recovered.selected_count == 5
    assert recovered.unresolved_count == 0
    assert recovered.selections[4].selected_media_id == "m57-relevant"


def test_c17_scientific_specificity_rejects_generic_object_broll():
    generic_moon = item(
        "generic-object-only",
        provider=Provider.NASA,
        rights=Rights.VERIFIED_LICENSE,
        title="Moon",
        tags=["moon"],
        objects=["moon"],
    )
    specific = scene(
        objects=["moon"],
        keywords=["moon", "capricornus", "star map"],
        visual="Star map showing the Moon positioned inside Capricornus",
    )

    result = MaterialSelector(Catalog([generic_moon])).select_plan(
        request(plan([specific]), publication_only=True)
    )

    assert result.selections[0].status == SelectionStatus.NO_ADEQUATE_MEDIA
    assert result.selections[0].selected_media_id is None
    assert result.publication_ready is False


def test_c17_ai_recreation_requires_both_gates_and_never_becomes_publication_ready():
    ai = item(
        "ai-recreation",
        provider=Provider.AI_GENERATED,
        rights=Rights.VERIFIED_LICENSE,
        title="Moon recreation",
        tags=["moon"],
        objects=["moon"],
        origin=Origin.AI_GENERATED,
    )
    ai.scientific_status = ScientificStatus.RECREACION_VISUAL
    selector = MaterialSelector(Catalog([ai]))

    request_blocked = selector.select_plan(
        request(plan([scene(ai=True)]), allow_ai=False)
    )
    scene_blocked = selector.select_plan(
        request(plan([scene(ai=False)]), allow_ai=True)
    )
    allowed = selector.select_plan(
        request(plan([scene(ai=True)]), allow_ai=True)
    )

    assert request_blocked.selections[0].status == SelectionStatus.NO_ADEQUATE_MEDIA
    assert scene_blocked.selections[0].status == SelectionStatus.NO_ADEQUATE_MEDIA
    assert allowed.selections[0].status == SelectionStatus.SELECTED_AI_RECREATION
    assert allowed.selections[0].selected_scientific_status == "RECREACION_VISUAL"
    assert allowed.selections[0].review_required is True
    assert allowed.review_required is True
    assert allowed.publication_ready is False
