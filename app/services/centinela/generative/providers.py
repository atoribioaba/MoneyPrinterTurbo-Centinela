"""Declared local generative candidates that are not runtime-enabled yet."""

from app.services.centinela.capabilities import (
    ProviderCapability,
    ProviderKind,
)
from app.services.centinela.provider_registry import ProviderDefinition


def build_local_generative_provider_definitions() -> tuple[
    ProviderDefinition, ...
]:
    """Return the V1 local AI candidates without registering them globally.

    Keeping these definitions outside ``build_default_provider_registry`` is a
    deliberate safety gate. Until the real RTX 2060 runtimes are implemented and
    certified, MPT's existing source selectors must not expose providers that can
    only fail at execution time.
    """

    return (
        ProviderDefinition(
            provider_id="zimage_local",
            display_name="Z-Image-Turbo (local candidate)",
            kind=ProviderKind.GENERATIVE,
            capabilities=frozenset(
                {
                    ProviderCapability.GENERATE,
                    ProviderCapability.LOCAL,
                    ProviderCapability.IMAGE,
                    ProviderCapability.TEXT_TO_IMAGE,
                    ProviderCapability.LOCAL_INFERENCE,
                }
            ),
            requires_api_key=False,
        ),
        ProviderDefinition(
            provider_id="ltx_local",
            display_name="LTX-Video 2B 0.9.8 Distilled (local candidate)",
            kind=ProviderKind.GENERATIVE,
            capabilities=frozenset(
                {
                    ProviderCapability.GENERATE,
                    ProviderCapability.LOCAL,
                    ProviderCapability.VIDEO,
                    ProviderCapability.IMAGE_TO_VIDEO,
                    ProviderCapability.TEXT_TO_VIDEO,
                    ProviderCapability.LOCAL_INFERENCE,
                    ProviderCapability.PROGRESS,
                }
            ),
            requires_api_key=False,
        ),
    )
