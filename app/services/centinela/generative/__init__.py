"""Cloud-safe contracts for Centinela local generative visual providers.

This package intentionally contains no model loading or GPU inference. It defines
only the contracts, routing policy and provenance required before local hardware
certification is available.
"""

from app.services.centinela.generative.contracts import (
    GeneratedMediaType,
    GeneratedVisualAsset,
    GenerationQuality,
    SceneAssetIndex,
    ScientificVisualStatus,
    VisualGenerationMode,
    VisualGenerationRequest,
)
from app.services.centinela.generative.providers import (
    build_local_generative_provider_definitions,
)
from app.services.centinela.generative.router import (
    LowVramFallbackPolicy,
    ProviderRuntimeState,
    VisualProviderRoutingError,
    required_capability,
    select_provider,
)

__all__ = [
    "GeneratedMediaType",
    "GeneratedVisualAsset",
    "GenerationQuality",
    "LowVramFallbackPolicy",
    "ProviderRuntimeState",
    "SceneAssetIndex",
    "ScientificVisualStatus",
    "VisualGenerationMode",
    "VisualGenerationRequest",
    "VisualProviderRoutingError",
    "build_local_generative_provider_definitions",
    "required_capability",
    "select_provider",
]
