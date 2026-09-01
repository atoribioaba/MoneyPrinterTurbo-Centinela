from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.services.centinela.orchestration import ResourceClass
from app.services.centinela.research_adapters import (
    MastHstJwstAdapter,
    MinorPlanetCenterAdapter,
    NasaExoplanetArchiveAdapter,
    NasaOpenAdapter,
    OptionalRuntimeUnavailable,
    RequestsResearchTransport,
    ResearchBundle,
    ResearchContext,
    ResearchDataError,
    ResearchDatum,
    ResearchMediaRecord,
    ResearchPhase,
    ResearchPhaseViolation,
    ResearchSource,
    SkyfieldDE440Adapter,
    StellariumStaticRendererAdapter,
    WikidataAdapter,
    WikimediaCommonsAdapter,
    build_c3_external_research_binding,
    build_esa_gaia_tap_adapter,
    build_eso_tap_adapter,
    build_licenses_manifest,
    build_provenance_manifest,
    download_and_seal_media,
)


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get_json(self, context, url, **kwargs):
        context.require_research()
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("unexpected fake transport call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def research_context():
    return ResearchContext("test-project", ResearchPhase.RESEARCH)


@pytest.mark.parametrize(
    "phase",
    [
        ResearchPhase.SCRIPT,
        ResearchPhase.MEDIA,
        ResearchPhase.AUDIO,
        ResearchPhase.VIDEO_BASE,
        ResearchPhase.REVIEW,
        ResearchPhase.PUBLICATION,
    ],
)
def test_transport_rejects_every_non_research_phase_before_network(monkeypatch, phase):
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network must not be reached")

    monkeypatch.setattr(
        "app.services.centinela.research_adapters.transport.requests.get",
        forbidden,
    )
    transport = RequestsResearchTransport(allowed_hosts={"example.org"})
    with pytest.raises(ResearchPhaseViolation):
        transport.get_json(
            ResearchContext("p", phase),
            "https://example.org/data",
        )
    assert called is False


def test_transport_rejects_non_allowlisted_host_before_network(monkeypatch):
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network must not be reached")

    monkeypatch.setattr(
        "app.services.centinela.research_adapters.transport.requests.get",
        forbidden,
    )
    transport = RequestsResearchTransport(allowed_hosts={"example.org"})
    with pytest.raises(ResearchDataError, match="allow-listed"):
        transport.get_json(
            research_context(),
            "https://evil.example/data",
        )
    assert called is False


def test_wikimedia_mock_accepts_explicit_cc_license():
    payload = {
        "query": {
            "pages": [
                {
                    "pageid": 42,
                    "title": "File:Venus.jpg",
                    "imageinfo": [
                        {
                            "url": "https://upload.wikimedia.org/venus.jpg",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Venus.jpg",
                            "mime": "image/jpeg",
                            "width": 4000,
                            "height": 3000,
                            "extmetadata": {
                                "LicenseShortName": {"value": "CC BY 4.0"},
                                "LicenseUrl": {
                                    "value": "https://creativecommons.org/licenses/by/4.0/"
                                },
                                "Artist": {"value": "Example Observer"},
                                "AttributionRequired": {"value": "true"},
                                "Attribution": {"value": "Example Observer"},
                                "NonFree": {"value": "false"},
                            },
                        }
                    ],
                }
            ]
        }
    }
    fake = FakeTransport([payload])
    bundle = WikimediaCommonsAdapter(fake).search(
        research_context(),
        "Venus phases",
    )
    assert len(fake.calls) == 1
    assert len(bundle.media) == 1
    assert bundle.media[0].publication_eligible is True
    assert bundle.media[0].attribution_required is True
    assert bundle.media[0].rights_decision in {
        "accept",
        "accept_with_attribution",
    }


def test_wikimedia_mock_unknown_license_fails_closed_for_publication():
    payload = {
        "query": {
            "pages": [
                {
                    "pageid": 42,
                    "title": "File:Venus.jpg",
                    "imageinfo": [
                        {
                            "url": "https://upload.wikimedia.org/venus.jpg",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Venus.jpg",
                            "mime": "image/jpeg",
                            "width": 4000,
                            "height": 3000,
                            "extmetadata": {},
                        }
                    ],
                }
            ]
        }
    }
    bundle = WikimediaCommonsAdapter(FakeTransport([payload])).search(
        research_context(),
        "Venus",
    )
    assert bundle.media[0].publication_eligible is False
    assert bundle.media[0].rights_decision == "review"


def test_wikidata_ids_are_validated_before_transport():
    fake = FakeTransport([])
    adapter = WikidataAdapter(fake)
    with pytest.raises(ResearchDataError, match="entity id"):
        adapter.property_value(
            research_context(),
            entity_id="Q42 } UNION { ?s ?p ?o",
            property_id="P31",
            label_es="tipo",
        )
    assert fake.calls == []


def test_wikidata_mock_is_secondary_and_requires_primary_source():
    fake = FakeTransport(
        [
            {
                "results": {
                    "bindings": [
                        {"value": {"type": "literal", "value": "1969-07-16"}}
                    ]
                }
            }
        ]
    )
    bundle = WikidataAdapter(fake).property_value(
        research_context(),
        entity_id="Q43653",
        property_id="P619",
        label_es="fecha de lanzamiento",
    )
    assert bundle.data[0].verified is False
    assert bundle.data[0].primary_source_required is True
    assert bundle.sources[0].primary_source is False
    assert "IAU" in bundle.warnings[0]


def test_nasa_apod_mock_is_not_eligible_when_copyright_is_present():
    fake = FakeTransport(
        [
            {
                "date": "2026-01-01",
                "title": "Example APOD",
                "hdurl": "https://apod.nasa.gov/example.jpg",
                "copyright": "Third Party Author",
            }
        ]
    )
    bundle = NasaOpenAdapter(fake).apod(
        research_context(),
        day=date(2026, 1, 1),
    )
    assert bundle.media[0].publication_eligible is False
    assert bundle.media[0].rights_decision == "review"


def test_nasa_apod_mock_public_domain_signal_is_accepted():
    fake = FakeTransport(
        [
            {
                "date": "2026-01-01",
                "title": "Example APOD",
                "hdurl": "https://apod.nasa.gov/example.jpg",
            }
        ]
    )
    bundle = NasaOpenAdapter(fake).apod(
        research_context(),
        day=date(2026, 1, 1),
    )
    assert bundle.media[0].publication_eligible is True
    assert bundle.media[0].rights_decision == "accept"


def test_nasa_epic_mock_stays_rights_review():
    fake = FakeTransport(
        [
            [
                {
                    "image": "epic_1b_20260101000000",
                    "caption": "Earth",
                    "date": "2026-01-01 00:00:00",
                }
            ]
        ]
    )
    bundle = NasaOpenAdapter(fake).epic(
        research_context(),
        day=date(2026, 1, 1),
    )
    assert len(bundle.media) == 1
    assert bundle.media[0].publication_eligible is False
    assert bundle.media[0].rights_decision == "review"


def test_exoplanet_mock_produces_grounded_facts():
    fake = FakeTransport(
        [
            [
                {
                    "pl_name": "Proxima Cen b",
                    "hostname": "Proxima Centauri",
                    "disc_year": 2016,
                    "pl_rade": 1.03,
                    "pl_bmasse": 1.07,
                    "pl_orbper": 11.186,
                }
            ]
        ]
    )
    bundle = NasaExoplanetArchiveAdapter(fake).planet(
        research_context(),
        "Proxima Cen b",
    )
    assert len(bundle.data) == 6
    assert all(item.verified for item in bundle.data)
    query = fake.calls[0][1]["params"]["query"]
    assert "from pscomppars" in query
    assert "Proxima Cen b" in query


def test_mast_hst_jwst_mock_discovery_remains_rights_review():
    fake = FakeTransport(
        [
            {
                "data": [
                    {
                        "obsid": "123",
                        "obs_collection": "JWST",
                        "obs_id": "jw-example",
                        "target_name": "M 42",
                    }
                ]
            }
        ]
    )
    bundle = MastHstJwstAdapter(fake).search(
        research_context(),
        mission="JWST",
        target="M 42",
        limit=5,
    )
    assert bundle.sources[0].provider == "MAST/STScI"
    assert len(bundle.media) == 1
    assert bundle.media[0].publication_eligible is False
    request_json = fake.calls[0][1]["params"]["request"]
    assert '"service":"Mast.Caom.Filtered"' in request_json
    assert '"JWST"' in request_json

def test_mpc_mock_requires_one_designation_and_seals_count():
    fake = FakeTransport(
        [
            [
                {
                    "ADES_DF": [
                        {"obsTime": "2026-01-01T00:00:00Z"},
                        {"obsTime": "2026-01-02T00:00:00Z"},
                    ]
                }
            ]
        ]
    )
    bundle = MinorPlanetCenterAdapter(fake).observations(
        research_context(),
        "Bennu",
    )
    assert bundle.data[0].value == 2
    assert fake.calls[0][1]["json_body"]["desigs"] == ["Bennu"]


@pytest.mark.parametrize(
    "builder,provider",
    [
        (build_eso_tap_adapter, "ESO"),
        (build_esa_gaia_tap_adapter, "ESA Gaia Archive"),
    ],
)
def test_tap_archive_calls_are_mocked_and_media_remain_review(builder, provider):
    fake = FakeTransport([[{"source_id": "1", "obs_title": "test"}]])
    bundle = builder(fake).query_fixed(
        research_context(),
        query="SELECT TOP 1 source_id FROM example.table",
        title="archive test",
        maximum_rows=1,
    )
    assert bundle.sources[0].provider == provider
    assert bundle.media[0].publication_eligible is False
    assert bundle.media[0].rights_decision == "review"


def test_skyfield_requires_preexisting_local_bsp_and_never_downloads(tmp_path):
    adapter = SkyfieldDE440Adapter(tmp_path / "de440s.bsp")
    with pytest.raises(OptionalRuntimeUnavailable, match="pre-downloaded"):
        adapter.position(
            research_context(),
            body="venus",
            moment=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ),
        )


def test_stellarium_bridge_has_no_assumed_cli():
    adapter = StellariumStaticRendererAdapter()
    with pytest.raises(OptionalRuntimeUnavailable, match="not configured"):
        adapter.render(research_context(), {"target": "Venus"})


def test_manifests_are_deterministic_and_never_enable_auto_publication():
    bundle = ResearchBundle(
        media=(
            ResearchMediaRecord(
                media_id="venus",
                provider="wikimedia",
                title="Venus",
                source_page="https://commons.wikimedia.org/wiki/File:Venus.jpg",
                file_url="https://upload.wikimedia.org/venus.jpg",
                license="CC BY 4.0",
                license_url="https://creativecommons.org/licenses/by/4.0/",
                attribution="Example",
                attribution_required=True,
                rights_decision="accept_with_attribution",
                publication_eligible=True,
            ),
        )
    )
    p1 = build_provenance_manifest(bundle)
    p2 = build_provenance_manifest(bundle)
    l1 = build_licenses_manifest(bundle)
    l2 = build_licenses_manifest(bundle)
    assert p1 == p2
    assert l1 == l2
    assert p1["auto_publication"] is False
    assert l1["auto_publication"] is False
    assert l1["all_publication_eligible"] is True


def test_download_and_sidecar_use_mock_transport_only(tmp_path):
    class DownloadTransport:
        def download(self, context, url, destination):
            context.require_research()
            Path(destination).write_bytes(b"image-bytes")
            return ("a" * 64, 11)

    item = ResearchMediaRecord(
        media_id="venus",
        provider="wikimedia",
        title="Venus",
        source_page="https://commons.wikimedia.org/wiki/File:Venus.jpg",
        file_url="https://upload.wikimedia.org/venus.jpg",
        license="CC BY 4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        attribution="Example",
        attribution_required=True,
        rights_decision="accept_with_attribution",
        publication_eligible=True,
    )
    destination = tmp_path / "venus.jpg"
    sealed = download_and_seal_media(
        DownloadTransport(),
        research_context(),
        item,
        destination,
    )
    sidecar = tmp_path / "venus.jpg.astromedia.json"
    assert destination.is_file()
    assert sidecar.is_file()
    assert sealed.sha256 == "a" * 64
    text = sidecar.read_text(encoding="utf-8")
    assert '"rights_status": "VERIFIED_LICENSE"' in text
    assert '"provider": "WIKIMEDIA"' in text


def test_c3_binding_declares_network_only_at_research_boundary():
    binding = build_c3_external_research_binding(
        lambda context, request: ResearchBundle(
            data=(
                ResearchDatum(
                    "test:fact",
                    "hecho",
                    1,
                    "test_source",
                ),
            ),
            sources=(
                ResearchSource(
                    "test_source",
                    "Test source",
                    "Test",
                    "https://example.org/",
                ),
            ),
        )
    )
    assert binding.resource_class == ResourceClass.LIGHT
    assert binding.invokes_network is True
    assert binding.invokes_llm is False
    assert binding.invokes_render is False
    assert binding.auto_publication is False
