import pytest

from app.services.centinela import ProviderCapability
from app.services.centinela.generative import (
    ProviderRuntimeState,
    VisualGenerationMode,
    VisualGenerationRequest,
    VisualProviderRoutingError,
    build_local_generative_provider_definitions,
    select_provider,
)
from app.services.centinela.provider_registry import build_default_provider_registry


def _i2v_request() -> VisualGenerationRequest:
    return VisualGenerationRequest(
        scene_id="scene-004",
        mode=VisualGenerationMode.IMAGE_TO_VIDEO,
        prompt="Very slow camera push, keep Moon geometry stable",
        source_image="scene-004-master.png",
        duration_seconds=5,
    )


def test_local_ai_candidates_declare_expected_capabilities() -> None:
    providers = {
        provider.provider_id: provider
        for provider in build_local_generative_provider_definitions()
    }

    assert providers["zimage_local"].supports(ProviderCapability.TEXT_TO_IMAGE)
    assert providers["zimage_local"].supports(ProviderCapability.LOCAL_INFERENCE)
    assert providers["ltx_local"].supports(ProviderCapability.IMAGE_TO_VIDEO)
    assert providers["ltx_local"].supports(ProviderCapability.TEXT_TO_VIDEO)


def test_uncertified_ai_candidates_are_not_exposed_by_default_registry() -> None:
    registry = build_default_provider_registry()

    assert not registry.contains("zimage_local")
    assert not registry.contains("ltx_local")


def test_router_fails_closed_without_local_hardware_certification() -> None:
    providers = build_local_generative_provider_definitions()
    runtime_states = {
        "ltx_local": ProviderRuntimeState(
            enabled=True,
            adapter_registered=True,
            weights_available=True,
            hardware_certified=False,
        )
    }

    with pytest.raises(VisualProviderRoutingError, match="hardware certification"):
        select_provider(_i2v_request(), providers, runtime_states)


def test_router_selects_only_fully_ready_provider() -> None:
    providers = build_local_generative_provider_definitions()
    runtime_states = {
        "ltx_local": ProviderRuntimeState(
            enabled=True,
            adapter_registered=True,
            weights_available=True,
            hardware_certified=True,
        )
    }

    selected = select_provider(_i2v_request(), providers, runtime_states)

    assert selected.provider_id == "ltx_local"


def test_preferred_unready_provider_does_not_silently_fallback() -> None:
    providers = build_local_generative_provider_definitions()
    runtime_states = {
        "ltx_local": ProviderRuntimeState(enabled=False),
    }

    with pytest.raises(VisualProviderRoutingError, match="not runtime-ready"):
        select_provider(
            _i2v_request(),
            providers,
            runtime_states,
            preferred_provider_id="ltx_local",
        )
