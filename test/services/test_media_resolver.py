from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import (
    AstronomyVideoPlan,
    GenerationOrigin,
    NarrativeAct,
    ScenePlan,
    ShotType,
)
from app.models.astromedia import (
    AstroMediaItem,
    MediaType,
    Origin,
    Provider,
    Provenance,
    Rights,
    SearchResult,
)
from app.models.material_selection import MaterialSelectionPlan, SelectionStatus
from app.services.centinela.orchestration import (
    JobCancelled,
    ProjectState,
    ProjectStateMachine,
    ResourceClass,
)
from app.services.centinela.production_spine import (
    ProductionSpine,
    SpineStage,
    StageDisposition,
)
from app.services.centinela.project_foundation import ArtifactStore
from app.services.centinela.media_resolver import (
    MEDIA_RESOLVER_VERSION,
    AstroMediaCatalogSource,
    MediaResolutionReport,
    MediaResolver,
    MediaResolverRequest,
    MediaResolverSpineAdapter,
    ResolverGuardrails,
    build_media_stage_binding,
    scene_query,
)
from app.services.material_selection import MaterialSelector


def make_scene(
    number: int,
    *,
    keyword: str = "luna",
    object_name: str = "moon",
    ai_allowed: bool = False,
) -> ScenePlan:
    acts = (
        NarrativeAct.INTRODUCTION,
        NarrativeAct.DEVELOPMENT,
        NarrativeAct.CLIMAX,
        NarrativeAct.RESOLUTION,
        NarrativeAct.EPILOGUE,
    )
    return ScenePlan(
        scene_number=number,
        act=acts[number - 1],
        duration_seconds=10,
        narration=f"Escena {number} sobre {keyword}.",
        visual_requirement=f"Mostrar {keyword} de forma astronómicamente pertinente.",
        astronomy_objects=[object_name],
        shot_type=ShotType.WIDE,
        material_keywords=[keyword],
        source_priority=[],
        transition="corte limpio",
        claims=[],
        ai_recreation_allowed=ai_allowed,
        scientific_status=ScientificStatus.NO_VERIFICADO,
    )


def make_plan(
    *,
    keyword: str = "luna",
    object_name: str = "moon",
    ai_allowed: bool = False,
) -> AstronomyVideoPlan:
    scenes = [
        make_scene(
            number,
            keyword=keyword,
            object_name=object_name,
            ai_allowed=ai_allowed,
        )
        for number in range(1, 6)
    ]
    return AstronomyVideoPlan(
        subject=f"Plan sobre {keyword}",
        language="es-ES",
        audience="divulgación astronómica general",
        hook="Observamos el cielo.",
        scientific_context_summary="Contexto de prueba.",
        narrative_arc=list(NarrativeAct),
        scenes=scenes,
        epilogue="Cierre contemplativo.",
        external_research_required=False,
        research_questions=[],
        context_hash="CTX-R4-TEST",
        generation_origin=GenerationOrigin.DETERMINISTIC_FALLBACK,
        model_used="test",
        repair_attempted=False,
        total_duration_seconds=50,
        requires_human_review=True,
        approved_for_publication=False,
        generated_at_utc=datetime.now(timezone.utc),
    )


def make_item(
    media_id: str,
    *,
    path: str | None = None,
    media_type: MediaType = MediaType.VIDEO,
    provider: Provider = Provider.OWN_MEDIA,
    rights: Rights = Rights.CONFIRMED_OWNED,
    title: str = "Luna",
    tags: list[str] | None = None,
    objects: list[str] | None = None,
    renderable: bool = True,
    duplicate_of: str | None = None,
) -> AstroMediaItem:
    origin = (
        Origin.AI_GENERATED
        if provider == Provider.AI_GENERATED
        else Origin.REAL_OWN
        if provider == Provider.OWN_MEDIA
        else Origin.REAL_EXTERNAL
    )
    return AstroMediaItem(
        media_id=media_id,
        local_path=path or f"C:/media/{media_id}.mp4",
        filename=f"{media_id}.mp4",
        media_type=media_type,
        width=1920,
        height=1080,
        fps=30.0 if media_type == MediaType.VIDEO else 0.0,
        duration_seconds=20.0 if media_type == MediaType.VIDEO else 0.0,
        provider=provider,
        title=title,
        tags=tags or ["luna"],
        astronomy_objects=objects or ["moon"],
        rights_status=rights,
        visual_origin=origin,
        scientific_status=ScientificStatus.NO_VERIFICADO,
        provenance_kind=Provenance.LOCAL_LIBRARY,
        renderable=renderable,
        duplicate_of_media_id=duplicate_of,
        indexed_at_utc=datetime.now(timezone.utc),
    )


class FakeCatalog:
    def __init__(self, items=()):
        self.items = list(items)
        self.overrides = {}
        self.search_requests = []
        self.index_requests = []

    def list_items(self, active_only=True):
        if not active_only:
            return list(self.items)
        return [item for item in self.items if item.active]

    def get(self, media_id):
        return next(
            (item for item in self.items if item.media_id == media_id),
            None,
        )

    def get_override(self, scene_key):
        return self.overrides.get(scene_key)

    def search(self, request):
        self.search_requests.append(request)
        output = []
        for index, item in enumerate(self.list_items(True)):
            if request.renderable_only and not item.renderable:
                continue
            if not request.include_duplicates and item.duplicate_of_media_id:
                continue
            if request.publication_eligible_only and not item.publication_eligible:
                continue
            output.append(
                SearchResult(
                    score=float(100 - index),
                    reasons=["fake_search"],
                    item=item,
                )
            )
        return output[: request.limit]

    def index_library(self, request):
        self.index_requests.append(request)
        return SimpleNamespace(
            model_dump=lambda mode="json": {
                "root": request.root,
                "indexed_items": len(self.items),
            }
        )


def make_resolver(
    items=(),
    *,
    semantic=None,
    focal=None,
):
    catalog = FakeCatalog(items)
    selector = MaterialSelector(catalog)
    kwargs = {
        "catalog": catalog,
        "selector": selector,
    }
    if semantic is not None:
        kwargs["semantic_reorder"] = semantic
    if focal is not None:
        kwargs["focal_analyzer"] = focal
    return MediaResolver(**kwargs), catalog


def test_version_constant():
    assert MEDIA_RESOLVER_VERSION == "media-resolver-v0.1"


def test_request_defaults_are_local_and_conservative():
    request = MediaResolverRequest()
    assert request.refresh_catalog is False
    assert request.semantic_evidence is False
    assert request.analyze_selected_focal is True
    assert request.publication_eligible_only is False


def test_request_rejects_empty_catalog_root():
    with pytest.raises(ValidationError):
        MediaResolverRequest(catalog_root="   ")


def test_scene_query_contains_keywords_objects_and_visual():
    query = scene_query(make_scene(1))
    assert "luna" in query
    assert "moon" in query
    assert "Mostrar" in query


def test_scene_query_deduplicates_repeated_terms():
    scene = make_scene(1)
    scene.material_keywords = ["luna", "luna"]
    assert "luna luna" not in scene_query(scene)


def test_catalog_source_normalizes_candidate():
    item = make_item("m1")
    catalog = FakeCatalog([item])
    source = AstroMediaCatalogSource(catalog)
    result = source.search_scene(make_scene(1), MediaResolverRequest())
    assert result[0].media_id == "m1"
    assert result[0].provider == Provider.OWN_MEDIA
    assert result[0].rights_status == Rights.CONFIRMED_OWNED


def test_catalog_source_honors_candidate_limit():
    catalog = FakeCatalog([make_item(f"m{index}") for index in range(5)])
    source = AstroMediaCatalogSource(catalog)
    request = MediaResolverRequest(max_candidates_per_scene=2)
    assert len(source.search_scene(make_scene(1), request)) == 2


def test_catalog_source_requests_no_duplicates():
    catalog = FakeCatalog([make_item("m1")])
    source = AstroMediaCatalogSource(catalog)
    source.search_scene(make_scene(1), MediaResolverRequest())
    assert catalog.search_requests[-1].include_duplicates is False


def test_catalog_source_requests_renderable_only():
    catalog = FakeCatalog([make_item("m1")])
    source = AstroMediaCatalogSource(catalog)
    source.search_scene(make_scene(1), MediaResolverRequest())
    assert catalog.search_requests[-1].renderable_only is True


def test_resolver_requires_astronomy_video_plan():
    resolver, _ = make_resolver()
    with pytest.raises(TypeError):
        resolver.resolve(object())


def test_resolver_rejects_selector_using_another_catalog():
    first = FakeCatalog()
    second = FakeCatalog()
    selector = MaterialSelector(second)
    with pytest.raises(ValueError):
        MediaResolver(catalog=first, selector=selector)


def test_semantic_disabled_by_resolver_request():
    resolver, _ = make_resolver([make_item("a"), make_item("b")])
    outcome = resolver.resolve(
        make_plan(),
        MediaResolverRequest(
            semantic_evidence=False,
            analyze_selected_focal=False,
        ),
    )
    assert outcome.report.scenes[0].semantic.method == "disabled_by_resolver"


def test_semantic_needs_two_video_candidates():
    resolver, _ = make_resolver([make_item("a")])
    outcome = resolver.resolve(
        make_plan(),
        MediaResolverRequest(
            semantic_evidence=True,
            analyze_selected_focal=False,
        ),
    )
    assert outcome.report.scenes[0].semantic.method == "not_enough_video_candidates"


def test_semantic_reordering_is_recorded_as_rank():
    items = [
        make_item("a", path="C:/media/a.mp4"),
        make_item("b", path="C:/media/b.mp4"),
    ]

    def semantic(**kwargs):
        return SimpleNamespace(
            video_paths=tuple(reversed(kwargs["video_paths"])),
            queries=("q",),
            matches=(),
            method="siglip2_test",
            error="",
            analyzed=True,
        )

    resolver, _ = make_resolver(items, semantic=semantic)
    outcome = resolver.resolve(
        make_plan(),
        MediaResolverRequest(
            semantic_evidence=True,
            analyze_selected_focal=False,
        ),
    )
    candidates = outcome.report.scenes[0].candidates
    ranks = {item.media_id: item.semantic_rank for item in candidates}
    assert ranks["b"] == 1
    assert ranks["a"] == 2


def test_semantic_failure_is_secondary_and_nonfatal():
    def semantic(**kwargs):
        raise RuntimeError("sidecar boom")

    resolver, _ = make_resolver(
        [make_item("a"), make_item("b")],
        semantic=semantic,
    )
    outcome = resolver.resolve(
        make_plan(),
        MediaResolverRequest(
            semantic_evidence=True,
            analyze_selected_focal=False,
        ),
    )
    evidence = outcome.report.scenes[0].semantic
    assert evidence.method == "semantic_evidence_failed"
    assert "sidecar boom" in evidence.error
    assert outcome.report.selected_count == 5


def test_semantic_only_receives_video_candidates():
    items = [
        make_item("video-a"),
        make_item("video-b"),
        make_item("image", media_type=MediaType.IMAGE),
    ]
    seen = {}

    def semantic(**kwargs):
        seen["paths"] = kwargs["video_paths"]
        return SimpleNamespace(
            video_paths=tuple(kwargs["video_paths"]),
            queries=(),
            matches=(),
            method="disabled",
            error="",
            analyzed=False,
        )

    resolver, _ = make_resolver(items, semantic=semantic)
    resolver.resolve(
        make_plan(),
        MediaResolverRequest(
            semantic_evidence=True,
            analyze_selected_focal=False,
        ),
    )
    assert len(seen["paths"]) == 2
    assert all("image" not in path for path in seen["paths"])


def test_material_selector_remains_final_authority_over_semantic_order():
    own = make_item("own", path="C:/z-own.mp4", provider=Provider.OWN_MEDIA)
    stock = make_item(
        "stock",
        path="C:/a-stock.mp4",
        provider=Provider.PEXELS,
        rights=Rights.VERIFIED_LICENSE,
    )

    def semantic(**kwargs):
        return SimpleNamespace(
            video_paths=tuple(reversed(kwargs["video_paths"])),
            queries=(),
            matches=(),
            method="siglip2_test",
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
    assert selection.selections[0].selected_media_id == "own"


def test_restricted_media_is_not_selected():
    resolver, _ = make_resolver(
        [make_item("restricted", rights=Rights.RESTRICTED)]
    )
    outcome = resolver.resolve(
        make_plan(),
        MediaResolverRequest(analyze_selected_focal=False),
    )
    selection = MaterialSelectionPlan.model_validate(outcome.selection)
    assert selection.unresolved_count == 5


def test_unverified_media_allowed_in_draft_but_requires_review():
    resolver, _ = make_resolver(
        [
            make_item(
                "unverified",
                provider=Provider.LOCAL_MEDIA,
                rights=Rights.UNVERIFIED,
            )
        ]
    )
    outcome = resolver.resolve(
        make_plan(),
        MediaResolverRequest(analyze_selected_focal=False),
    )
    assert outcome.report.unresolved_count == 0
    assert outcome.report.review_required is True
    assert outcome.report.rights_review_count == 5


def test_publication_only_rejects_unverified_media():
    resolver, _ = make_resolver(
        [
            make_item(
                "unverified",
                provider=Provider.LOCAL_MEDIA,
                rights=Rights.UNVERIFIED,
            )
        ]
    )
    outcome = resolver.resolve(
        make_plan(),
        MediaResolverRequest(
            publication_eligible_only=True,
            analyze_selected_focal=False,
        ),
    )
    assert outcome.report.unresolved_count == 5


def test_ai_media_requires_scene_permission():
    resolver, _ = make_resolver(
        [
            make_item(
                "ai",
                provider=Provider.AI_GENERATED,
                rights=Rights.VERIFIED_LICENSE,
            )
        ]
    )
    outcome = resolver.resolve(
        make_plan(ai_allowed=False),
        MediaResolverRequest(analyze_selected_focal=False),
    )
    assert outcome.report.unresolved_count == 5


def test_ai_media_can_be_last_resort_when_scene_allows():
    resolver, _ = make_resolver(
        [
            make_item(
                "ai",
                provider=Provider.AI_GENERATED,
                rights=Rights.VERIFIED_LICENSE,
            )
        ]
    )
    outcome = resolver.resolve(
        make_plan(ai_allowed=True),
        MediaResolverRequest(analyze_selected_focal=False),
    )
    selection = MaterialSelectionPlan.model_validate(outcome.selection)
    assert selection.selections[0].status == SelectionStatus.SELECTED_AI_RECREATION


def test_ai_generation_is_never_triggered_by_resolver():
    resolver, _ = make_resolver([])
    outcome = resolver.resolve(
        make_plan(ai_allowed=True),
        MediaResolverRequest(analyze_selected_focal=False),
    )
    assert outcome.report.guardrails.ai_generation_triggered is False
    assert outcome.report.guardrails.wangp_triggered is False


def test_image_selection_has_no_smartfocal_analysis():
    resolver, _ = make_resolver(
        [make_item("image", media_type=MediaType.IMAGE)]
    )
    outcome = resolver.resolve(make_plan())
    focal = outcome.report.scenes[0].focal
    assert focal.applicable is False
    assert focal.method == "not_applicable_image"


def test_video_focal_can_be_disabled():
    resolver, _ = make_resolver([make_item("video")])
    outcome = resolver.resolve(
        make_plan(),
        MediaResolverRequest(analyze_selected_focal=False),
    )
    focal = outcome.report.scenes[0].focal
    assert focal.applicable is False
    assert focal.method == "disabled_by_resolver"


def test_video_focal_uses_injected_analyzer():
    def focal(path):
        return SimpleNamespace(
            focal_x=0.25,
            focal_y=0.75,
            confidence=0.9,
            method="test_focal",
            error="",
        )

    resolver, _ = make_resolver([make_item("video")], focal=focal)
    outcome = resolver.resolve(make_plan())
    focal_evidence = outcome.report.scenes[0].focal
    assert focal_evidence.applicable is True
    assert focal_evidence.focal_x == pytest.approx(0.25)
    assert focal_evidence.method == "test_focal"


def test_focal_analyzer_failure_falls_back_to_center():
    def focal(path):
        raise RuntimeError("bad frame")

    resolver, _ = make_resolver([make_item("video")], focal=focal)
    outcome = resolver.resolve(make_plan())
    focal_evidence = outcome.report.scenes[0].focal
    assert focal_evidence.focal_x == pytest.approx(0.5)
    assert focal_evidence.focal_y == pytest.approx(0.5)
    assert focal_evidence.method == "fallback_center"
    assert "bad frame" in focal_evidence.error


def test_catalog_refresh_is_explicit():
    resolver, catalog = make_resolver([make_item("video")])
    resolver.resolve(
        make_plan(),
        MediaResolverRequest(
            refresh_catalog=True,
            analyze_selected_focal=False,
        ),
    )
    assert len(catalog.index_requests) == 1


def test_catalog_not_refreshed_by_default():
    resolver, catalog = make_resolver([make_item("video")])
    resolver.resolve(
        make_plan(),
        MediaResolverRequest(analyze_selected_focal=False),
    )
    assert catalog.index_requests == []


def test_refresh_report_is_persistable_json():
    resolver, _ = make_resolver([make_item("video")])
    outcome = resolver.resolve(
        make_plan(),
        MediaResolverRequest(
            refresh_catalog=True,
            analyze_selected_focal=False,
        ),
    )
    assert outcome.report.catalog_index_report["indexed_items"] == 1


def test_report_catalog_item_count():
    resolver, _ = make_resolver([make_item("a"), make_item("b")])
    outcome = resolver.resolve(
        make_plan(),
        MediaResolverRequest(analyze_selected_focal=False),
    )
    assert outcome.report.catalog_item_count == 2
    assert outcome.report.catalog_provider_counts["OWN_MEDIA"] == 2


def test_report_counts_selected_and_unresolved():
    resolver, _ = make_resolver([make_item("a")])
    outcome = resolver.resolve(
        make_plan(),
        MediaResolverRequest(analyze_selected_focal=False),
    )
    assert outcome.report.selected_count == 5
    assert outcome.report.unresolved_count == 0


def test_report_counts_are_schema_guarded():
    resolver, _ = make_resolver([make_item("a")])
    report = resolver.resolve(
        make_plan(),
        MediaResolverRequest(analyze_selected_focal=False),
    ).report
    payload = report.model_dump(mode="json")
    payload["selected_count"] = 4
    with pytest.raises(ValidationError):
        MediaResolutionReport.model_validate(payload)


def test_resolver_guardrails_forbid_irrelevant_broll():
    guardrails = ResolverGuardrails()
    assert guardrails.irrelevant_broll_fallback is False
    assert guardrails.material_selector_is_final_authority is True


def test_resolver_guardrails_semantic_is_secondary():
    guardrails = ResolverGuardrails()
    assert guardrails.semantic_matcher_is_secondary_evidence_only is True


def test_resolver_guardrails_smartfocal_after_selection():
    guardrails = ResolverGuardrails()
    assert guardrails.smartfocal_runs_after_selection_only is True


def test_progress_callback_receives_monotonic_phase_values():
    resolver, _ = make_resolver([make_item("a")])
    seen = []
    resolver.resolve(
        make_plan(),
        MediaResolverRequest(analyze_selected_focal=False),
        report_progress=lambda value, message: seen.append(value),
    )
    assert seen == sorted(seen)
    assert seen[0] == 15
    assert seen[-1] == 60


def test_cancellation_callback_is_invoked():
    resolver, _ = make_resolver([make_item("a")])
    calls = {"count": 0}

    def cancel():
        calls["count"] += 1

    resolver.resolve(
        make_plan(),
        MediaResolverRequest(analyze_selected_focal=False),
        check_cancelled=cancel,
    )
    assert calls["count"] > 5


class FakeStore:
    def __init__(self, refs=None, payloads=None):
        self.refs = refs or {}
        self.payloads = payloads or {}

    def get_artifact(self, project_id, artifact_id):
        return self.refs[artifact_id]

    def read_json(self, project_id, artifact_id):
        return self.payloads[artifact_id]


class FakeContext:
    def __init__(self, store, previous_receipt=None):
        self.store = store
        self.project_id = "project"
        self.previous_receipt = previous_receipt
        self.progress = []

    def report_progress(self, value, message=None):
        self.progress.append((value, message))

    def check_cancelled(self):
        return None


def make_ref(artifact_id, artifact_type):
    return SimpleNamespace(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
    )


def test_adapter_missing_scene_plan_needs_input():
    adapter = MediaResolverSpineAdapter(SimpleNamespace())
    context = FakeContext(FakeStore())
    result = adapter(context, {})
    assert result.disposition == StageDisposition.NEEDS_INPUT


def test_adapter_explicit_wrong_artifact_type_is_blocked():
    store = FakeStore(refs={"x": make_ref("x", "final_script")})
    adapter = MediaResolverSpineAdapter(SimpleNamespace())
    result = adapter(FakeContext(store), {"plan_artifact_id": "x"})
    assert result.disposition == StageDisposition.BLOCKED


def test_adapter_invalid_plan_payload_is_blocked():
    ref = make_ref("plan", "scene_plan")
    store = FakeStore(
        refs={"plan": ref},
        payloads={"plan": {"not": "a plan"}},
    )
    adapter = MediaResolverSpineAdapter(SimpleNamespace())
    result = adapter(
        FakeContext(store),
        {"plan_artifact_id": "plan"},
    )
    assert result.disposition == StageDisposition.BLOCKED


def test_adapter_invalid_resolver_request_is_blocked():
    ref = make_ref("plan", "scene_plan")
    plan = make_plan()
    store = FakeStore(
        refs={"plan": ref},
        payloads={"plan": plan.model_dump(mode="json")},
    )
    adapter = MediaResolverSpineAdapter(SimpleNamespace())
    result = adapter(
        FakeContext(store),
        {
            "plan_artifact_id": "plan",
            "resolver": {"catalog_root": ""},
        },
    )
    assert result.disposition == StageDisposition.BLOCKED


def test_adapter_discovers_plan_from_previous_scene_receipt():
    plan_ref = make_ref("plan", "scene_plan")
    receipt_ref = make_ref("receipt", "spine_stage_receipt")
    store = FakeStore(
        refs={"plan": plan_ref},
        payloads={
            "receipt": {"output_artifact_ids": ["plan"]},
            "plan": make_plan().model_dump(mode="json"),
        },
    )
    resolver, _ = make_resolver([])
    adapter = MediaResolverSpineAdapter(resolver)
    result = adapter(FakeContext(store, receipt_ref), {})
    assert result.disposition == StageDisposition.NEEDS_INPUT


def test_adapter_multiple_scene_plans_is_blocked():
    first = make_ref("p1", "scene_plan")
    second = make_ref("p2", "scene_plan")
    receipt = make_ref("r", "spine_stage_receipt")
    store = FakeStore(
        refs={"p1": first, "p2": second},
        payloads={"r": {"output_artifact_ids": ["p1", "p2"]}},
    )
    adapter = MediaResolverSpineAdapter(SimpleNamespace())
    result = adapter(FakeContext(store, receipt), {})
    assert result.disposition == StageDisposition.BLOCKED


def test_adapter_explicit_plan_takes_priority_over_previous_receipt():
    explicit = make_ref("explicit", "scene_plan")
    wrong = make_ref("wrong", "final_script")
    receipt = make_ref("r", "spine_stage_receipt")
    store = FakeStore(
        refs={"explicit": explicit, "wrong": wrong},
        payloads={
            "explicit": make_plan().model_dump(mode="json"),
            "r": {"output_artifact_ids": ["wrong"]},
        },
    )
    resolver, _ = make_resolver([])
    adapter = MediaResolverSpineAdapter(resolver)
    result = adapter(
        FakeContext(store, receipt),
        {"plan_artifact_id": "explicit"},
    )
    assert result.disposition == StageDisposition.NEEDS_INPUT


def test_adapter_unresolved_persists_evidence_without_broll():
    ref = make_ref("plan", "scene_plan")
    plan = make_plan()
    store = FakeStore(
        refs={"plan": ref},
        payloads={"plan": plan.model_dump(mode="json")},
    )
    resolver, _ = make_resolver([])
    adapter = MediaResolverSpineAdapter(resolver)
    result = adapter(
        FakeContext(store),
        {
            "plan_artifact_id": "plan",
            "resolver": {"analyze_selected_focal": False},
        },
    )
    assert result.disposition == StageDisposition.NEEDS_INPUT
    assert {item.artifact_type for item in result.artifacts} == {
        "material_selection",
        "media_resolution",
    }
    assert result.details["irrelevant_broll_substituted"] is False


def test_adapter_resolved_returns_complete_material_selection():
    ref = make_ref("plan", "scene_plan")
    plan = make_plan()
    store = FakeStore(
        refs={"plan": ref},
        payloads={"plan": plan.model_dump(mode="json")},
    )
    resolver, _ = make_resolver([make_item("moon")])
    adapter = MediaResolverSpineAdapter(resolver)
    result = adapter(
        FakeContext(store),
        {
            "plan_artifact_id": "plan",
            "resolver": {"analyze_selected_focal": False},
        },
    )
    assert result.disposition == StageDisposition.COMPLETE
    material = next(
        item
        for item in result.artifacts
        if item.artifact_type == "material_selection"
    )
    MaterialSelectionPlan.model_validate(material.payload)


def test_adapter_media_resolution_payload_validates():
    ref = make_ref("plan", "scene_plan")
    plan = make_plan()
    store = FakeStore(
        refs={"plan": ref},
        payloads={"plan": plan.model_dump(mode="json")},
    )
    resolver, _ = make_resolver([make_item("moon")])
    result = MediaResolverSpineAdapter(resolver)(
        FakeContext(store),
        {
            "plan_artifact_id": "plan",
            "resolver": {"analyze_selected_focal": False},
        },
    )
    report = next(
        item
        for item in result.artifacts
        if item.artifact_type == "media_resolution"
    )
    MediaResolutionReport.model_validate(report.payload)


def test_adapter_propagates_job_cancellation():
    ref = make_ref("plan", "scene_plan")
    plan = make_plan()
    store = FakeStore(
        refs={"plan": ref},
        payloads={"plan": plan.model_dump(mode="json")},
    )

    class CancellingResolver:
        def resolve(self, *args, **kwargs):
            raise JobCancelled("stop")

    adapter = MediaResolverSpineAdapter(CancellingResolver())
    with pytest.raises(JobCancelled):
        adapter(
            FakeContext(store),
            {"plan_artifact_id": "plan"},
        )


def test_binding_is_medium_and_offline():
    binding = build_media_stage_binding(
        make_resolver([make_item("moon")])[0]
    )
    assert binding.resource_class == ResourceClass.MEDIUM
    assert binding.invokes_network is False
    assert binding.invokes_llm is False


def test_binding_forbids_render_and_auto_publication():
    binding = build_media_stage_binding(
        make_resolver([make_item("moon")])[0]
    )
    assert binding.invokes_render is False
    assert binding.auto_publication is False


def test_r3_media_stage_integration_advances_only_when_resolved(tmp_path):
    store = ArtifactStore(tmp_path / "centinela")
    store.create_project("R4 integration", project_id="r4-integration")
    plan = make_plan()
    plan_ref = store.put_json(
        "r4-integration",
        "scene_plan",
        plan.model_dump(mode="json"),
        producer="test.scenes",
    )

    state = ProjectStateMachine(store)
    state.transition(
        "r4-integration",
        ProjectState.RESEARCH_READY,
        reason="test",
        actor="test",
    )
    state.transition(
        "r4-integration",
        ProjectState.SCRIPT_READY,
        reason="test",
        actor="test",
    )
    state.transition(
        "r4-integration",
        ProjectState.SCENES_READY,
        reason="test",
        actor="test",
    )

    resolver, _ = make_resolver([make_item("moon")])
    with ProductionSpine(store, max_workers=1) as spine:
        spine.register_adapter(
            SpineStage.MEDIA,
            build_media_stage_binding(resolver),
        )
        scheduled = spine.schedule_stage(
            "r4-integration",
            SpineStage.MEDIA,
            request={
                "plan_artifact_id": plan_ref.artifact_id,
                "resolver": {
                    "semantic_evidence": False,
                    "analyze_selected_focal": False,
                },
            },
        )
        completed = spine.wait(scheduled.job_id, timeout=10)
        assert completed.status.value == "SUCCEEDED"
        assert (
            spine.state_machine.current_state("r4-integration")
            == ProjectState.MEDIA_READY
        )
        assert len(
            store.list_artifacts(
                "r4-integration",
                artifact_type="material_selection",
            )
        ) == 1
        assert len(
            store.list_artifacts(
                "r4-integration",
                artifact_type="media_resolution",
            )
        ) == 1


def test_r3_media_stage_unresolved_goes_to_needs_input(tmp_path):
    store = ArtifactStore(tmp_path / "centinela")
    store.create_project("R4 unresolved", project_id="r4-unresolved")
    plan_ref = store.put_json(
        "r4-unresolved",
        "scene_plan",
        make_plan().model_dump(mode="json"),
        producer="test.scenes",
    )

    state = ProjectStateMachine(store)
    for target in (
        ProjectState.RESEARCH_READY,
        ProjectState.SCRIPT_READY,
        ProjectState.SCENES_READY,
    ):
        state.transition(
            "r4-unresolved",
            target,
            reason="test",
            actor="test",
        )

    resolver, _ = make_resolver([])
    with ProductionSpine(store, max_workers=1) as spine:
        spine.register_adapter(
            SpineStage.MEDIA,
            build_media_stage_binding(resolver),
        )
        scheduled = spine.schedule_stage(
            "r4-unresolved",
            SpineStage.MEDIA,
            request={
                "plan_artifact_id": plan_ref.artifact_id,
                "resolver": {
                    "semantic_evidence": False,
                    "analyze_selected_focal": False,
                },
            },
        )
        completed = spine.wait(scheduled.job_id, timeout=10)
        assert completed.status.value == "SUCCEEDED"
        assert (
            spine.state_machine.current_state("r4-unresolved")
            == ProjectState.NEEDS_INPUT
        )
        assert len(
            store.list_artifacts(
                "r4-unresolved",
                artifact_type="material_selection",
            )
        ) == 1
