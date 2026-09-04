from datetime import datetime, timezone
from pathlib import Path

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import (
    AstronomyVideoPlan,
    GenerationOrigin,
    NarrativeAct,
    ScenePlan,
    ShotType,
)
from app.models.astromedia import MediaType, Provider, Rights
from app.services.centinela.generative.contracts import (
    GeneratedMediaType,
    GeneratedVisualAsset,
    GenerationQuality,
    SceneAssetIndex,
    ScientificVisualStatus,
    VisualGenerationMode,
)
from app.services.centinela.generative.router import ProviderRuntimeState
from app.services.centinela.media_resolver.models import (
    FocalEvidence,
    MediaResolutionReport,
    ResolverGuardrails,
    SceneMediaEvidence,
    SemanticEvidence,
)
from webui.product.visual_generation import (
    AI_SCIENTIFIC_STATUS,
    VISUAL_SOURCE_ONLINE,
    VISUAL_SOURCE_OWN,
    asset_can_enter_mpt,
    build_visual_request,
    can_execute_visual_generation,
    candidate_matches_visual_source,
    correlate_scene_contexts,
    current_upscale_contract_supported,
    image_source_options,
    provider_for_mode,
    quality_attempts_label,
)


def _scene(number: int) -> ScenePlan:
    return ScenePlan(
        scene_number=number,
        act=list(NarrativeAct)[number - 1],
        duration_seconds=12,
        narration=f"Narración escena {number}",
        visual_requirement=f"Visual escena {number}",
        astronomy_objects=["Luna"],
        shot_type=ShotType.WIDE,
        material_keywords=["Luna"],
        source_priority=["OWN_MEDIA", "NASA"],
        transition="Corte.",
        claims=[],
        ai_recreation_allowed=False,
        scientific_status=ScientificStatus.APROXIMACION_DIVULGATIVA,
    )


def _plan() -> AstronomyVideoPlan:
    now = datetime.now(timezone.utc)
    return AstronomyVideoPlan(
        subject="Prueba visual lunar",
        language="es-ES",
        audience="divulgación astronómica general",
        hook="Una historia lunar",
        scientific_context_summary="Contexto científico para una prueba controlada.",
        narrative_arc=list(NarrativeAct),
        scenes=[_scene(index) for index in range(1, 6)],
        epilogue="Cierre",
        external_research_required=False,
        research_questions=[],
        context_hash="a" * 64,
        generation_origin=GenerationOrigin.LLM_VALIDATED,
        model_used="fixture",
        repair_attempted=False,
        total_duration_seconds=60,
        requires_human_review=True,
        approved_for_publication=False,
        generated_at_utc=now,
    )


def _report() -> MediaResolutionReport:
    now = datetime.now(timezone.utc)
    scenes = [
        SceneMediaEvidence(
            scene_number=index,
            scene_key=f"{'a' * 64}:scene:{index}",
            query="Luna",
            candidate_count=0,
            candidates=[],
            semantic=SemanticEvidence(
                requested=False,
                analyzed=False,
                method="disabled_by_test",
            ),
            selection_status="NO_ADEQUATE_MEDIA",
            selected_media_id=None,
            selected_provider=None,
            selected_rights_status=None,
            selected_publication_eligible=None,
            focal=FocalEvidence(
                applicable=False,
                method="not_selected",
            ),
        )
        for index in range(1, 6)
    ]
    return MediaResolutionReport(
        subject="Prueba visual lunar",
        source_plan_context_hash="a" * 64,
        selector_version="fixture",
        catalog_item_count=0,
        catalog_provider_counts={},
        catalog_refreshed=False,
        catalog_index_report=None,
        scene_count=5,
        selected_count=0,
        unresolved_count=5,
        rights_review_count=0,
        review_required=True,
        publication_ready=False,
        scenes=scenes,
        guardrails=ResolverGuardrails(),
        generated_at_utc=now,
    )


def _candidate(
    *,
    provider: Provider,
    rights: Rights,
    publication_eligible: bool,
    media_type: MediaType = MediaType.IMAGE,
) -> object:
    from app.services.centinela.media_resolver.models import NormalizedMediaCandidate

    return NormalizedMediaCandidate(
        media_id=f"{provider.value.lower()}-1",
        local_path=f"/tmp/{provider.value.lower()}-1.png",
        media_type=media_type,
        provider=provider,
        rights_status=rights,
        publication_eligible=publication_eligible,
        renderable=True,
        title="Luna",
        scientific_status="NO_VERIFICADO",
        content_sha256="b" * 64,
    )


def _asset(media_type: GeneratedMediaType) -> GeneratedVisualAsset:
    return GeneratedVisualAsset(
        asset_id=f"asset-{media_type.value}",
        scene_id=f"{'a' * 64}:scene:1",
        provider_id="ltx_local" if media_type is GeneratedMediaType.VIDEO else "zimage_local",
        model_id="fixture",
        media_type=media_type,
        local_path=f"/tmp/asset.{ 'mp4' if media_type is GeneratedMediaType.VIDEO else 'png'}",
        sha256="c" * 64,
        width=512,
        height=768,
        duration_seconds=4.0 if media_type is GeneratedMediaType.VIDEO else None,
    )


def test_scene_mapping_uses_existing_media_resolution_scene_key() -> None:
    contexts = correlate_scene_contexts(_plan(), _report())

    assert len(contexts) == 5
    assert contexts[0].scene_id == f"{'a' * 64}:scene:1"
    assert contexts[-1].scene_number == 5


def test_t2i_form_maps_only_to_existing_visual_generation_request_fields() -> None:
    request = build_visual_request(
        scene_id="scene-1",
        mode=VisualGenerationMode.TEXT_TO_IMAGE,
        prompt="Eclipse solar cinematográfico",
        quality=GenerationQuality.MASTER,
        aspect_ratio="9:16",
        seed=42,
        negative_prompt="texto, artefactos",
    )

    assert request.mode is VisualGenerationMode.TEXT_TO_IMAGE
    assert request.quality is GenerationQuality.MASTER
    assert request.aspect_ratio == "9:16"
    assert request.seed == 42
    assert request.negative_prompt == "texto, artefactos"
    assert request.duration_seconds is None


def test_i2v_requires_real_source_image_and_maps_duration() -> None:
    request = build_visual_request(
        scene_id="scene-2",
        mode=VisualGenerationMode.IMAGE_TO_VIDEO,
        prompt="Movimiento lento y contenido",
        source_image="/tmp/master.png",
        duration_seconds=5.0,
    )

    assert request.source_image == "/tmp/master.png"
    assert request.duration_seconds == 5.0


def test_t2v_maps_duration_without_inventing_motion_profiles() -> None:
    request = build_visual_request(
        scene_id="scene-3",
        mode=VisualGenerationMode.TEXT_TO_VIDEO,
        prompt="Cielo nocturno cinematográfico",
        duration_seconds=6.0,
        quality=GenerationQuality.STANDARD,
    )

    assert request.mode is VisualGenerationMode.TEXT_TO_VIDEO
    assert request.duration_seconds == 6.0
    assert not hasattr(request, "motion_profile")


def test_provider_mapping_is_capability_driven_and_unambiguous() -> None:
    assert provider_for_mode(VisualGenerationMode.TEXT_TO_IMAGE).provider_id == "zimage_local"
    assert provider_for_mode(VisualGenerationMode.IMAGE_TO_VIDEO).provider_id == "ltx_local"
    assert provider_for_mode(VisualGenerationMode.TEXT_TO_VIDEO).provider_id == "ltx_local"


def test_executability_requires_all_four_runtime_flags() -> None:
    assert not can_execute_visual_generation(
        ProviderRuntimeState(
            enabled=False,
            adapter_registered=True,
            weights_available=True,
            hardware_certified=True,
        )
    )
    assert not can_execute_visual_generation(
        ProviderRuntimeState(
            enabled=True,
            adapter_registered=False,
            weights_available=True,
            hardware_certified=True,
        )
    )
    assert not can_execute_visual_generation(
        ProviderRuntimeState(
            enabled=True,
            adapter_registered=True,
            weights_available=False,
            hardware_certified=True,
        )
    )
    assert not can_execute_visual_generation(
        ProviderRuntimeState(
            enabled=True,
            adapter_registered=True,
            weights_available=True,
            hardware_certified=False,
        )
    )
    assert can_execute_visual_generation(
        ProviderRuntimeState(
            enabled=True,
            adapter_registered=True,
            weights_available=True,
            hardware_certified=True,
        )
    )


def test_current_selected_provider_set_does_not_expose_upscale() -> None:
    assert current_upscale_contract_supported() is False


def test_ai_scientific_label_is_fixed_to_recreacion_visual() -> None:
    assert AI_SCIENTIFIC_STATUS is ScientificVisualStatus.RECREACION_VISUAL


def test_visual_source_filters_preserve_rights_semantics() -> None:
    own = _candidate(
        provider=Provider.OWN_MEDIA,
        rights=Rights.CONFIRMED_OWNED,
        publication_eligible=True,
    )
    online = _candidate(
        provider=Provider.NASA,
        rights=Rights.VERIFIED_LICENSE,
        publication_eligible=True,
    )
    unverified = _candidate(
        provider=Provider.ESA,
        rights=Rights.UNVERIFIED,
        publication_eligible=False,
    )

    assert candidate_matches_visual_source(own, VISUAL_SOURCE_OWN)
    assert not candidate_matches_visual_source(own, VISUAL_SOURCE_ONLINE)
    assert candidate_matches_visual_source(online, VISUAL_SOURCE_ONLINE)
    assert not candidate_matches_visual_source(unverified, VISUAL_SOURCE_ONLINE)


def test_i2v_source_options_include_generated_image_with_hash_and_lineage() -> None:
    context = correlate_scene_contexts(_plan(), _report())[0]
    index = SceneAssetIndex()
    image = _asset(GeneratedMediaType.IMAGE)
    index.register(image)

    options = image_source_options(context, index)

    generated = next(item for item in options if item.generated_asset_id == image.asset_id)
    assert generated.local_path == image.local_path
    assert generated.sha256 == image.sha256
    assert generated.provider == image.provider_id


def test_only_generated_video_is_ui_eligible_for_mpt_handoff() -> None:
    assert asset_can_enter_mpt(_asset(GeneratedMediaType.VIDEO))
    assert not asset_can_enter_mpt(_asset(GeneratedMediaType.IMAGE))


def test_oom_attempt_sequence_is_presentable_without_hiding_downgrade() -> None:
    assert quality_attempts_label(
        [GenerationQuality.STANDARD, GenerationQuality.PREVIEW]
    ) == "STANDARD → PREVIEW"


def test_ai_visual_ui_uses_mobile_safe_native_layout() -> None:
    source = Path("webui/product/visual_generation.py").read_text(encoding="utf-8")

    assert "st.columns(" not in source
    assert "use_container_width=True" in source
    assert "Generación local pendiente de certificación" in source
    assert "RECREACIÓN VISUAL" in source
