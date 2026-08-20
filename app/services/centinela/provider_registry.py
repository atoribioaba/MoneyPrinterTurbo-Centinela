"""Provider registry used by Centinela Edition.

The registry is the canonical declaration of provider identity and capabilities.
Execution adapters remain in their service modules and are migrated explicitly,
but callers must validate providers against this contract instead of silently
falling back to another source.
"""

from dataclasses import dataclass
import re
from typing import Iterable

from app.services.centinela.capabilities import (
    ProviderCapability,
    ProviderKind,
)


_PROVIDER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    """Immutable description of one provider."""

    provider_id: str
    display_name: str
    kind: ProviderKind
    capabilities: frozenset[ProviderCapability]
    requires_api_key: bool = False

    def __post_init__(self) -> None:
        provider_id = str(self.provider_id or "").strip()

        if not _PROVIDER_ID_PATTERN.fullmatch(provider_id):
            raise ValueError(f"invalid provider id: {self.provider_id!r}")

        if not str(self.display_name or "").strip():
            raise ValueError("provider display_name must not be empty")

        object.__setattr__(self, "provider_id", provider_id)
        object.__setattr__(
            self,
            "capabilities",
            frozenset(self.capabilities),
        )

    def supports(self, capability: ProviderCapability) -> bool:
        return capability in self.capabilities


class ProviderRegistry:
    """In-memory registry with explicit duplicate and unknown-provider checks."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderDefinition] = {}

    def register(self, provider: ProviderDefinition) -> None:
        if provider.provider_id in self._providers:
            raise ValueError(
                f"provider already registered: {provider.provider_id}"
            )
        self._providers[provider.provider_id] = provider

    def register_many(
        self,
        providers: Iterable[ProviderDefinition],
    ) -> None:
        for provider in providers:
            self.register(provider)

    def get(self, provider_id: str) -> ProviderDefinition:
        normalized_id = str(provider_id or "").strip()

        try:
            return self._providers[normalized_id]
        except KeyError as exc:
            raise KeyError(
                f"unknown provider: {normalized_id or '<empty>'}"
            ) from exc

    def contains(self, provider_id: str) -> bool:
        return str(provider_id or "").strip() in self._providers

    def all(self) -> tuple[ProviderDefinition, ...]:
        return tuple(self._providers.values())


def build_default_provider_registry() -> ProviderRegistry:
    """Describe providers already implemented by the current MPT baseline."""

    registry = ProviderRegistry()

    registry.register_many(
        [
            ProviderDefinition(
                provider_id="pexels",
                display_name="Pexels",
                kind=ProviderKind.SEARCHABLE,
                capabilities=frozenset(
                    {
                        ProviderCapability.SEARCH,
                        ProviderCapability.DOWNLOAD,
                        ProviderCapability.REMOTE,
                        ProviderCapability.VIDEO,
                    }
                ),
                requires_api_key=True,
            ),
            ProviderDefinition(
                provider_id="pixabay",
                display_name="Pixabay",
                kind=ProviderKind.SEARCHABLE,
                capabilities=frozenset(
                    {
                        ProviderCapability.SEARCH,
                        ProviderCapability.DOWNLOAD,
                        ProviderCapability.REMOTE,
                        ProviderCapability.VIDEO,
                    }
                ),
                requires_api_key=True,
            ),
            ProviderDefinition(
                provider_id="coverr",
                display_name="Coverr",
                kind=ProviderKind.SEARCHABLE,
                capabilities=frozenset(
                    {
                        ProviderCapability.SEARCH,
                        ProviderCapability.DOWNLOAD,
                        ProviderCapability.REMOTE,
                        ProviderCapability.VIDEO,
                    }
                ),
                requires_api_key=True,
            ),
            ProviderDefinition(
                provider_id="local",
                display_name="Local",
                kind=ProviderKind.LOCAL,
                capabilities=frozenset(
                    {
                        ProviderCapability.LOCAL,
                        ProviderCapability.VIDEO,
                        ProviderCapability.IMAGE,
                    }
                ),
            ),
            ProviderDefinition(
                provider_id="loomloom",
                display_name="Shengsuan Cloud AI Video",
                kind=ProviderKind.GENERATIVE,
                capabilities=frozenset(
                    {
                        ProviderCapability.GENERATE,
                        ProviderCapability.REMOTE,
                        ProviderCapability.VIDEO,
                        ProviderCapability.PROGRESS,
                    }
                ),
                requires_api_key=True,
            ),
        ]
    )

    return registry
