"""Fail-closed routing and low-VRAM policy for generative visual providers."""

from dataclasses import dataclass
from typing import Iterable, Mapping

from app.services.centinela.capabilities import ProviderCapability
from app.services.centinela.generative.contracts import (
    GenerationQuality,
    VisualGenerationMode,
    VisualGenerationRequest,
)
from app.services.centinela.provider_registry import ProviderDefinition


_REQUIRED_CAPABILITIES = {
    VisualGenerationMode.TEXT_TO_IMAGE: ProviderCapability.TEXT_TO_IMAGE,
    VisualGenerationMode.IMAGE_TO_VIDEO: ProviderCapability.IMAGE_TO_VIDEO,
    VisualGenerationMode.TEXT_TO_VIDEO: ProviderCapability.TEXT_TO_VIDEO,
}


class VisualProviderRoutingError(RuntimeError):
    """Raised when no explicitly ready provider can execute a request."""


@dataclass(frozen=True, slots=True)
class ProviderRuntimeState:
    """Runtime readiness is separate from a provider's declared capabilities."""

    enabled: bool = False
    adapter_registered: bool = False
    weights_available: bool = False
    hardware_certified: bool = False

    @property
    def ready(self) -> bool:
        return (
            self.enabled
            and self.adapter_registered
            and self.weights_available
            and self.hardware_certified
        )


@dataclass(frozen=True, slots=True)
class LowVramFallbackPolicy:
    """Permit at most a bounded number of quality downgrades after OOM."""

    max_retries: int = 1

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_retries, bool)
            or not isinstance(self.max_retries, int)
            or self.max_retries < 0
        ):
            raise ValueError("max_retries must be a non-negative integer")

    def next_quality(
        self,
        current: GenerationQuality,
        *,
        retries_used: int,
    ) -> GenerationQuality | None:
        if retries_used < 0:
            raise ValueError("retries_used must be non-negative")
        if retries_used >= self.max_retries:
            return None

        return {
            GenerationQuality.MASTER: GenerationQuality.STANDARD,
            GenerationQuality.STANDARD: GenerationQuality.PREVIEW,
            GenerationQuality.PREVIEW: None,
        }[current]


def required_capability(mode: VisualGenerationMode) -> ProviderCapability:
    try:
        return _REQUIRED_CAPABILITIES[mode]
    except KeyError as exc:
        raise ValueError(f"unsupported generation mode: {mode!r}") from exc


def select_provider(
    request: VisualGenerationRequest,
    providers: Iterable[ProviderDefinition],
    runtime_states: Mapping[str, ProviderRuntimeState],
    *,
    preferred_provider_id: str | None = None,
    allow_fallback: bool = False,
) -> ProviderDefinition:
    """Select an explicitly runtime-ready provider or fail closed.

    Merely declaring a model candidate is insufficient. The adapter, local
    weights and exact target hardware must all be ready before a route is
    eligible. This prevents cloud fixtures from being mistaken for RTX 2060
    certification.
    """

    capability = required_capability(request.mode)
    provider_list = tuple(providers)
    by_id = {provider.provider_id: provider for provider in provider_list}

    def eligible(provider: ProviderDefinition) -> bool:
        state = runtime_states.get(provider.provider_id)
        return (
            provider.supports(ProviderCapability.GENERATE)
            and provider.supports(capability)
            and state is not None
            and state.ready
        )

    preferred = str(preferred_provider_id or "").strip()
    if preferred:
        provider = by_id.get(preferred)
        if provider is None:
            raise VisualProviderRoutingError(
                f"unknown preferred generative provider: {preferred}"
            )
        if eligible(provider):
            return provider
        if not allow_fallback:
            raise VisualProviderRoutingError(
                f"preferred generative provider is not runtime-ready: {preferred}"
            )

    for provider in provider_list:
        if preferred and provider.provider_id == preferred:
            continue
        if eligible(provider):
            return provider

    raise VisualProviderRoutingError(
        "no runtime-ready generative provider supports "
        f"{request.mode.value}; local hardware certification is required"
    )
