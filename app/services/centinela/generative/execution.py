"""Cloud-safe execution contract for local generative visual adapters.

The module contains orchestration only. Real model loading stays in future
hardware-specific adapters and cannot be enabled merely by importing this file.
"""

from dataclasses import replace
from typing import Mapping, Protocol

from app.services.centinela.generative.contracts import (
    GeneratedMediaType,
    GeneratedVisualAsset,
    VisualGenerationMode,
    VisualGenerationRequest,
)
from app.services.centinela.generative.router import (
    LowVramFallbackPolicy,
    ProviderRuntimeState,
    VisualProviderRoutingError,
    select_provider,
)
from app.services.centinela.provider_registry import ProviderDefinition


class VisualGenerationExecutionError(RuntimeError):
    """Raised when a selected local visual adapter cannot safely complete."""


class VisualOutOfMemoryError(VisualGenerationExecutionError):
    """Normalized OOM signal used by hardware adapters."""


class VisualGenerationAdapter(Protocol):
    """Minimal contract implemented by a model-specific local runtime."""

    provider_id: str

    def generate(self, request: VisualGenerationRequest) -> GeneratedVisualAsset:
        """Generate exactly one asset for the supplied scene request."""


def _expected_media_type(mode: VisualGenerationMode) -> GeneratedMediaType:
    if mode is VisualGenerationMode.TEXT_TO_IMAGE:
        return GeneratedMediaType.IMAGE
    if mode in (
        VisualGenerationMode.IMAGE_TO_VIDEO,
        VisualGenerationMode.TEXT_TO_VIDEO,
    ):
        return GeneratedMediaType.VIDEO
    raise ValueError(f"unsupported generation mode: {mode!r}")


def _validate_result(
    request: VisualGenerationRequest,
    provider: ProviderDefinition,
    asset: GeneratedVisualAsset,
) -> None:
    if asset.scene_id != request.scene_id:
        raise VisualGenerationExecutionError(
            "generated asset scene_id does not match the request"
        )
    if asset.provider_id != provider.provider_id:
        raise VisualGenerationExecutionError(
            "generated asset provider_id does not match the selected provider"
        )
    if asset.media_type is not _expected_media_type(request.mode):
        raise VisualGenerationExecutionError(
            "generated asset media type does not match generation mode"
        )


def execute_visual_request(
    request: VisualGenerationRequest,
    *,
    providers: tuple[ProviderDefinition, ...],
    runtime_states: Mapping[str, ProviderRuntimeState],
    adapters: Mapping[str, VisualGenerationAdapter],
    preferred_provider_id: str | None = None,
    allow_provider_fallback: bool = False,
    low_vram_policy: LowVramFallbackPolicy | None = None,
) -> GeneratedVisualAsset:
    """Execute through one explicitly ready adapter with bounded OOM fallback.

    Provider routing must first prove that the adapter, weights and exact target
    hardware are certified. OOM fallback may only lower the quality profile; it
    never silently changes provider or performs an unbounded retry loop.
    """

    provider = select_provider(
        request,
        providers,
        runtime_states,
        preferred_provider_id=preferred_provider_id,
        allow_fallback=allow_provider_fallback,
    )
    adapter = adapters.get(provider.provider_id)
    if adapter is None:
        raise VisualProviderRoutingError(
            "runtime-ready provider has no registered execution adapter: "
            f"{provider.provider_id}"
        )
    if str(getattr(adapter, "provider_id", "")).strip() != provider.provider_id:
        raise VisualProviderRoutingError(
            "execution adapter identity does not match selected provider"
        )

    policy = low_vram_policy or LowVramFallbackPolicy()
    effective_request = request
    retries_used = 0

    while True:
        try:
            asset = adapter.generate(effective_request)
        except VisualOutOfMemoryError:
            next_quality = policy.next_quality(
                effective_request.quality,
                retries_used=retries_used,
            )
            if next_quality is None:
                raise
            retries_used += 1
            effective_request = replace(
                effective_request,
                quality=next_quality,
            )
            continue

        _validate_result(effective_request, provider, asset)
        return asset
