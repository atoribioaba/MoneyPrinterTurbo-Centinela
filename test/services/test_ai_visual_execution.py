from dataclasses import dataclass

import pytest

from app.services.centinela.generative.contracts import (
    GeneratedMediaType,
    GeneratedVisualAsset,
    GenerationQuality,
    VisualGenerationMode,
    VisualGenerationRequest,
)
from app.services.centinela.generative.execution import (
    VisualGenerationExecutionError,
    VisualOutOfMemoryError,
    execute_visual_request,
)
from app.services.centinela.generative.providers import (
    build_local_generative_provider_definitions,
)
from app.services.centinela.generative.router import (
    LowVramFallbackPolicy,
    ProviderRuntimeState,
    VisualProviderRoutingError,
)


READY = ProviderRuntimeState(
    enabled=True,
    adapter_registered=True,
    weights_available=True,
    hardware_certified=True,
)


def _video_asset(provider_id: str = "ltx_local") -> GeneratedVisualAsset:
    return GeneratedVisualAsset(
        asset_id="asset-1",
        scene_id="scene-1",
        provider_id=provider_id,
        model_id="test-model",
        media_type=GeneratedMediaType.VIDEO,
        local_path="scene-1.mp4",
        sha256="a" * 64,
        width=512,
        height=768,
        duration_seconds=3.0,
    )


@dataclass
class FakeAdapter:
    provider_id: str
    results: list[object]

    def __post_init__(self) -> None:
        self.qualities: list[GenerationQuality] = []

    def generate(self, request: VisualGenerationRequest) -> GeneratedVisualAsset:
        self.qualities.append(request.quality)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        assert isinstance(result, GeneratedVisualAsset)
        return result


def _request() -> VisualGenerationRequest:
    return VisualGenerationRequest(
        scene_id="scene-1",
        mode=VisualGenerationMode.IMAGE_TO_VIDEO,
        prompt="Slow cinematic push toward the Moon",
        source_image="moon.png",
        duration_seconds=3,
    )


def test_execution_refuses_uncertified_runtime_before_adapter_call() -> None:
    providers = build_local_generative_provider_definitions()
    adapter = FakeAdapter("ltx_local", [_video_asset()])

    with pytest.raises(VisualProviderRoutingError):
        execute_visual_request(
            _request(),
            providers=providers,
            runtime_states={"ltx_local": ProviderRuntimeState(enabled=True)},
            adapters={"ltx_local": adapter},
            preferred_provider_id="ltx_local",
        )

    assert adapter.qualities == []


def test_execution_performs_only_one_bounded_quality_fallback() -> None:
    providers = build_local_generative_provider_definitions()
    adapter = FakeAdapter(
        "ltx_local",
        [VisualOutOfMemoryError("oom"), _video_asset()],
    )

    asset = execute_visual_request(
        _request(),
        providers=providers,
        runtime_states={"ltx_local": READY},
        adapters={"ltx_local": adapter},
        preferred_provider_id="ltx_local",
        low_vram_policy=LowVramFallbackPolicy(max_retries=1),
    )

    assert asset.asset_id == "asset-1"
    assert adapter.qualities == [
        GenerationQuality.STANDARD,
        GenerationQuality.PREVIEW,
    ]


def test_execution_stops_after_bounded_oom_retry() -> None:
    providers = build_local_generative_provider_definitions()
    adapter = FakeAdapter(
        "ltx_local",
        [VisualOutOfMemoryError("oom-1"), VisualOutOfMemoryError("oom-2")],
    )

    with pytest.raises(VisualOutOfMemoryError, match="oom-2"):
        execute_visual_request(
            _request(),
            providers=providers,
            runtime_states={"ltx_local": READY},
            adapters={"ltx_local": adapter},
            preferred_provider_id="ltx_local",
        )

    assert len(adapter.qualities) == 2


def test_execution_rejects_provider_mismatch() -> None:
    providers = build_local_generative_provider_definitions()
    adapter = FakeAdapter("ltx_local", [_video_asset("other-provider")])

    with pytest.raises(VisualGenerationExecutionError, match="provider_id"):
        execute_visual_request(
            _request(),
            providers=providers,
            runtime_states={"ltx_local": READY},
            adapters={"ltx_local": adapter},
            preferred_provider_id="ltx_local",
        )
