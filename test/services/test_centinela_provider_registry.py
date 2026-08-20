import unittest

from app.services.centinela.capabilities import (
    ProviderCapability,
    ProviderKind,
)
from app.services.centinela.provider_registry import (
    ProviderDefinition,
    ProviderRegistry,
    build_default_provider_registry,
)


class ProviderRegistryTests(unittest.TestCase):
    def test_default_registry_contains_current_mpt_sources(self):
        registry = build_default_provider_registry()

        self.assertTrue(registry.contains("pexels"))
        self.assertTrue(registry.contains("pixabay"))
        self.assertTrue(registry.contains("coverr"))
        self.assertTrue(registry.contains("wikimedia"))
        self.assertTrue(registry.contains("nasa"))
        self.assertTrue(registry.contains("local"))
        self.assertTrue(registry.contains("loomloom"))

        self.assertEqual(len(registry.all()), 7)

    def test_search_provider_capabilities(self):
        registry = build_default_provider_registry()
        pexels = registry.get("pexels")

        self.assertEqual(pexels.kind, ProviderKind.SEARCHABLE)
        self.assertTrue(pexels.supports(ProviderCapability.SEARCH))
        self.assertTrue(pexels.supports(ProviderCapability.DOWNLOAD))
        self.assertTrue(pexels.supports(ProviderCapability.REMOTE))
        self.assertTrue(pexels.supports(ProviderCapability.VIDEO))
        self.assertFalse(pexels.supports(ProviderCapability.GENERATE))

    def test_wikimedia_search_provider_capabilities(self):
        registry = build_default_provider_registry()
        provider = registry.get("wikimedia")

        self.assertEqual(
            provider.display_name,
            "Wikimedia Commons",
        )
        self.assertEqual(
            provider.kind,
            ProviderKind.SEARCHABLE,
        )
        self.assertFalse(
            provider.requires_api_key
        )

        for capability in (
            ProviderCapability.SEARCH,
            ProviderCapability.DOWNLOAD,
            ProviderCapability.REMOTE,
            ProviderCapability.VIDEO,
            ProviderCapability.LICENSE_METADATA,
        ):
            with self.subTest(
                capability=capability
            ):
                self.assertTrue(
                    provider.supports(capability)
                )

    def test_local_provider_capabilities(self):
        registry = build_default_provider_registry()
        local = registry.get("local")

        self.assertEqual(local.kind, ProviderKind.LOCAL)
        self.assertTrue(local.supports(ProviderCapability.LOCAL))
        self.assertTrue(local.supports(ProviderCapability.VIDEO))
        self.assertTrue(local.supports(ProviderCapability.IMAGE))
        self.assertFalse(local.requires_api_key)

    def test_loomloom_is_generative(self):
        registry = build_default_provider_registry()
        loomloom = registry.get("loomloom")

        self.assertEqual(loomloom.kind, ProviderKind.GENERATIVE)
        self.assertTrue(loomloom.supports(ProviderCapability.GENERATE))
        self.assertTrue(loomloom.supports(ProviderCapability.REMOTE))
        self.assertTrue(loomloom.supports(ProviderCapability.PROGRESS))

    def test_matching_selects_cli_compatible_video_sources_in_order(self):
        registry = build_default_provider_registry()

        providers = registry.matching(
            kinds=(
                ProviderKind.SEARCHABLE,
                ProviderKind.LOCAL,
            ),
            required_capabilities=(
                ProviderCapability.VIDEO,
            ),
        )

        self.assertEqual(
            [provider.provider_id for provider in providers],
            [
                "pexels",
                "pixabay",
                "coverr",
                "wikimedia",
                "nasa",
                "local",
            ],
        )

    def test_matching_can_select_all_current_video_sources(self):
        registry = build_default_provider_registry()

        providers = registry.matching(
            required_capabilities=(
                ProviderCapability.VIDEO,
            )
        )

        self.assertEqual(
            [provider.provider_id for provider in providers],
            [
                "pexels",
                "pixabay",
                "coverr",
                "wikimedia",
                "nasa",
                "local",
                "loomloom",
            ],
        )

    def test_duplicate_provider_is_rejected(self):
        registry = ProviderRegistry()

        provider = ProviderDefinition(
            provider_id="example",
            display_name="Example",
            kind=ProviderKind.SEARCHABLE,
            capabilities=frozenset({ProviderCapability.SEARCH}),
        )

        registry.register(provider)

        with self.assertRaises(ValueError):
            registry.register(provider)

    def test_unknown_provider_is_rejected(self):
        registry = build_default_provider_registry()

        with self.assertRaises(KeyError):
            registry.get("does-not-exist")

    def test_invalid_provider_id_is_rejected(self):
        with self.assertRaises(ValueError):
            ProviderDefinition(
                provider_id="Bad Provider ID",
                display_name="Bad",
                kind=ProviderKind.SEARCHABLE,
                capabilities=frozenset(),
            )



def test_nasa_search_provider_capabilities():
    from app.services.centinela import (
        ProviderCapability,
        ProviderKind,
        build_default_provider_registry,
    )

    registry = build_default_provider_registry()
    provider = registry.get("nasa")

    assert (
        provider.display_name
        == "NASA Image and Video Library"
    )

    assert (
        provider.kind
        is ProviderKind.SEARCHABLE
    )

    assert provider.requires_api_key is False

    for capability in (
        ProviderCapability.SEARCH,
        ProviderCapability.DOWNLOAD,
        ProviderCapability.REMOTE,
        ProviderCapability.VIDEO,
        ProviderCapability.LICENSE_METADATA,
    ):
        assert provider.supports(
            capability
        )

if __name__ == "__main__":
    unittest.main()
