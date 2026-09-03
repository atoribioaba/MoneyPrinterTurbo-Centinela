from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import GroundingFact
from app.services.centinela.production_spine import (
    StageArtifact,
    StageDisposition,
    StageResult,
)
from app.services.centinela.research_adapters import (
    C3ExternalResearchFactLockAdapter,
    CanonicalScientificQuantity,
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
    ResearchPhase,
    ResearchPhaseViolation,
    ScientificConflictError,
    ScientificConflictResolver,
    ScientificTolerance,
    SkyfieldDE440Adapter,
    StellariumStaticRendererAdapter,
    SunPyLocalAdapter,
    WikidataAdapter,
    WikimediaCommonsAdapter,
    build_esa_gaia_tap_adapter,
    build_eso_tap_adapter,
)
from app.services.centinela.research_adapters import canonicalized as canonicalized_module
from app.services.centinela.writer_room.models import FactLock


ROOT = Path(__file__).resolve().parents[2]
_RAW_UNIT_UNCHANGED = object()


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


def research_context() -> ResearchContext:
    return ResearchContext("test-project", ResearchPhase.RESEARCH)


def _assert_raw_canonical(
    datum: ResearchDatum,
    *,
    expected_raw_unit: object = _RAW_UNIT_UNCHANGED,
) -> CanonicalScientificQuantity:
    quantity = datum.canonical_quantity
    assert isinstance(quantity, CanonicalScientificQuantity)
    assert quantity.source == datum.source_id
    assert quantity.unit == datum.unit
    assert quantity.value == pytest.approx(float(datum.value))
    assert quantity.subject
    assert quantity.quantity
    assert quantity.epoch
    assert quantity.observer
    assert quantity.frame
    assert quantity.display_precision is None or quantity.display_precision >= 0
    assert quantity.provenance["source_id"] == datum.source_id
    assert quantity.provenance["raw_fact_id"] == datum.fact_id
    if expected_raw_unit is _RAW_UNIT_UNCHANGED:
        expected_raw_unit = datum.unit
    assert quantity.provenance["raw_unit"] == expected_raw_unit
    assert quantity.provenance["auto_publication"] is False
    return quantity


def _quantity(
    *,
    value: float,
    source: str,
    unit: str = "m",
    epoch: str = "2026-09-02T00:00:00Z",
    observer: str = "test-observer",
    frame: str = "test-frame",
) -> CanonicalScientificQuantity:
    return CanonicalScientificQuantity(
        subject="test-target",
        quantity="test-distance",
        epoch=epoch,
        observer=observer,
        unit=unit,
        frame=frame,
        value=value,
        uncertainty=0.1,
        display_precision=1,
        source=source,
        provenance={"fixture": "adversarial", "auto_publication": False},
    )


def _datum(
    *,
    fact_id: str,
    quantity: CanonicalScientificQuantity,
) -> ResearchDatum:
    return ResearchDatum(
        fact_id=fact_id,
        label_es="Magnitud de prueba",
        value=quantity.value,
        source_id=quantity.source,
        unit=quantity.unit,
        canonical_quantity=quantity,
    )


def _base_fact_lock_adapter() -> Mock:
    fact_lock = FactLock(
        subject="Synthetic target",
        research_mode="GENERIC_GEOCENTRIC",
        context_hash="A" * 64,
        facts=[
            GroundingFact(
                fact_id="base-fact",
                label_es="Hecho base sintético",
                value=1,
                unit=None,
                scientific_status=ScientificStatus.NO_VERIFICADO,
                source_ids=[],
            )
        ],
        sources=[],
        source_ids=[],
        scope_note="Synthetic test fixture.",
        location_assumed=False,
        moment_basis="synthetic test",
        primary_source_verification_required_for_publication=True,
        generated_at_utc=datetime(2026, 9, 2, tzinfo=UTC),
    )
    return Mock(
        return_value=StageResult.complete(
            StageArtifact(
                artifact_type="fact_lock",
                payload=fact_lock.model_dump(mode="json"),
            )
        )
    )


def test_transport_rejects_every_non_research_phase_before_network(monkeypatch):
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
    for phase in (
        ResearchPhase.SCRIPT,
        ResearchPhase.MEDIA,
        ResearchPhase.AUDIO,
        ResearchPhase.VIDEO_BASE,
        ResearchPhase.REVIEW,
        ResearchPhase.PUBLICATION,
    ):
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


def test_nasa_exoplanet_emits_semantic_canonical_quantities():
    fake = FakeTransport(
        [
            [
                {
                    "pl_name": "Proxima Cen b",
                    "hostname": "Proxima Centauri",
                    "disc_year": 2016,
                    "discoverymethod": "Radial Velocity",
                    "disc_refname": "Discovery Reference",
                    "pl_rade": 1.03,
                    "pl_radeerr1": 0.05,
                    "pl_radeerr2": -0.04,
                    "pl_rade_reflink": "Radius Reference",
                    "pl_bmasse": 1.07,
                    "pl_bmasseerr1": 0.06,
                    "pl_bmasseerr2": -0.05,
                    "pl_bmasse_reflink": "Mass Reference",
                    "pl_orbper": 11.186,
                    "pl_orbpererr1": 0.002,
                    "pl_orbpererr2": -0.002,
                    "pl_orbper_reflink": "Period Reference",
                }
            ]
        ]
    )
    bundle = NasaExoplanetArchiveAdapter(fake).planet(
        research_context(),
        "Proxima Cen b",
    )
    facts = {item.fact_id.rsplit(":", 1)[-1]: item for item in bundle.data}

    radius = _assert_raw_canonical(facts["pl_rade"])
    assert radius.subject == "Proxima Cen b"
    assert radius.quantity == "planet_radius"
    assert radius.epoch == "catalog:NASA_EXOPLANET_ARCHIVE_PSCOMPPARS"
    assert radius.observer == "not_applicable:catalog"
    assert radius.frame == "NASA_EXOPLANET_ARCHIVE_PSCOMPPARS"
    assert radius.uncertainty == pytest.approx(0.05)
    assert radius.provenance["provider"] == "NASA Exoplanet Archive"
    assert radius.provenance["raw_field"] == "pl_rade"

    period = _assert_raw_canonical(facts["pl_orbper"])
    assert period.quantity == "orbital_period"
    assert period.uncertainty == pytest.approx(0.002)

    discovery_year = _assert_raw_canonical(facts["disc_year"])
    assert discovery_year.quantity == "discovery_year"
    assert discovery_year.value == 2016.0


def test_mpc_observations_and_orbit_emit_canonical_quantities():
    fake = FakeTransport(
        [
            [{"ADES_DF": [{"obsTime": "2026-01-01T00:00:00Z"}]}],
            [
                {
                    "mpc_orb": [
                        {
                            "COM": {
                                "coefficient_names": [
                                    "a",
                                    "e",
                                    "i",
                                    "node",
                                    "argperi",
                                    "meananomaly",
                                ],
                                "coefficient_values": [
                                    1.1264,
                                    0.2037,
                                    6.0349,
                                    2.0609,
                                    66.2231,
                                    101.7,
                                ],
                                "coefficient_uncertainties": [
                                    1e-7,
                                    1e-7,
                                    1e-5,
                                    1e-5,
                                    1e-5,
                                    1e-4,
                                ],
                            }
                        }
                    ]
                }
            ],
        ]
    )
    adapter = MinorPlanetCenterAdapter(fake)
    observations = adapter.observations(research_context(), "Bennu")
    count = _assert_raw_canonical(observations.data[0])
    assert count.subject == "Bennu"
    assert count.quantity == "observation_count"
    assert count.observer == "global:MPC_ADES_archive"
    assert count.frame == "MPC_ADES"

    orbit = adapter.orbit(research_context(), "Bennu")
    facts = {item.fact_id: item for item in orbit.data}
    semi_major = _assert_raw_canonical(facts["mpc_orbit_bennu:a"])
    assert semi_major.quantity == "semi_major_axis"
    assert semi_major.unit == "AU"
    assert semi_major.frame == "MPC_OSCULATING_ORBIT_ELEMENTS"
    assert semi_major.uncertainty == pytest.approx(1e-7)

    eccentricity = _assert_raw_canonical(
        facts["mpc_orbit_bennu:e"],
        expected_raw_unit=None,
    )
    assert eccentricity.quantity == "eccentricity"
    assert eccentricity.unit == "1"
    assert eccentricity.provenance["raw_unit"] is None


def test_skyfield_wrapper_canonicalizes_runtime_boundary(monkeypatch):
    moment = datetime(2026, 9, 2, 20, 0, tzinfo=UTC)

    def fake_position(self, context, *, body, moment):
        context.require_research()
        return ResearchBundle(
            data=(
                ResearchDatum(
                    "skyfield:venus:ra_hours",
                    "Ascensión recta",
                    12.25,
                    "skyfield_de440",
                    "hour",
                ),
                ResearchDatum(
                    "skyfield:venus:dec_deg",
                    "Declinación",
                    -3.5,
                    "skyfield_de440",
                    "deg",
                ),
                ResearchDatum(
                    "skyfield:venus:distance_au",
                    "Distancia",
                    0.72,
                    "skyfield_de440",
                    "au",
                ),
            )
        )

    monkeypatch.setattr(
        canonicalized_module._SkyfieldDE440Adapter,
        "position",
        fake_position,
    )
    bundle = SkyfieldDE440Adapter("de440.bsp").position(
        research_context(),
        body="venus",
        moment=moment,
    )
    quantities = {
        item.canonical_quantity.quantity: _assert_raw_canonical(item)
        for item in bundle.data
    }
    assert quantities["right_ascension"].subject == "venus"
    assert quantities["right_ascension"].epoch == moment.isoformat()
    assert quantities["right_ascension"].observer == "earth-geocenter"
    assert quantities["right_ascension"].frame == "ICRF_J2000"
    assert quantities["declination"].unit == "deg"
    assert quantities["geocentric_distance"].unit == "au"
    assert quantities["geocentric_distance"].provenance["network_required"] is False


def test_sunpy_wrapper_canonicalizes_runtime_boundary(monkeypatch):
    moment = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)

    def fake_orientation(self, context, *, moment):
        context.require_research()
        return ResearchBundle(
            data=(
                ResearchDatum(
                    "sunpy:sun:b0_deg",
                    "B0",
                    7.1,
                    "sunpy_local",
                    "deg",
                ),
                ResearchDatum(
                    "sunpy:sun:l0_deg",
                    "L0",
                    123.4,
                    "sunpy_local",
                    "deg",
                ),
            )
        )

    monkeypatch.setattr(
        canonicalized_module._SunPyLocalAdapter,
        "solar_orientation",
        fake_orientation,
    )
    bundle = SunPyLocalAdapter().solar_orientation(
        research_context(),
        moment=moment,
    )
    quantities = {
        item.canonical_quantity.quantity: _assert_raw_canonical(item)
        for item in bundle.data
    }
    b0 = quantities["heliographic_latitude_disk_center"]
    assert b0.subject == "sun"
    assert b0.epoch == moment.isoformat()
    assert b0.observer == "earth-observer"
    assert b0.frame == "HELIOGRAPHIC_STONYHURST"

    l0 = quantities["carrington_longitude_disk_center"]
    assert l0.frame == "HELIOGRAPHIC_CARRINGTON"
    assert l0.provenance["provider"] == "SunPy"


def test_numeric_wikidata_corroboration_is_canonicalized():
    fake = FakeTransport(
        [
            {
                "results": {
                    "bindings": [
                        {"value": {"type": "literal", "value": "42.5"}}
                    ]
                }
            }
        ]
    )
    bundle = WikidataAdapter(fake).property_value(
        research_context(),
        entity_id="Q42",
        property_id="P2048",
        label_es="altura",
        unit="m",
    )
    quantity = _assert_raw_canonical(bundle.data[0])
    assert quantity.subject == "Q42"
    assert quantity.quantity == "P2048"
    assert quantity.frame == "WIKIDATA_STATEMENT"
    assert quantity.provenance["secondary_corroboration"] is True


def test_resolver_accepts_compatible_units_inside_explicit_tolerance():
    resolver = ScientificConflictResolver(
        {
            ("test-target", "test-distance"): ScientificTolerance(
                absolute=100.0
            )
        }
    )
    result = resolver.resolve_conflicts(
        (
            _quantity(value=100.0, unit="km", source="source-a"),
            _quantity(value=100_050.0, unit="m", source="source-b"),
        )
    )
    assert [item.unit for item in result] == ["m", "m"]
    assert result[0].value == pytest.approx(100_000.0)
    assert result[1].value == pytest.approx(100_050.0)


@pytest.mark.parametrize(
    ("field", "replacement", "error_code"),
    [
        ("unit", "s", "UNIT_INCOMPATIBLE"),
        ("epoch", "2026-09-03T00:00:00Z", "EPOCH_INCOMPATIBLE"),
        ("frame", "other-frame", "FRAME_INCOMPATIBLE"),
        ("observer", "other-observer", "OBSERVER_INCOMPATIBLE"),
    ],
)
def test_resolver_fails_closed_on_semantic_incompatibility(
    field,
    replacement,
    error_code,
):
    left = _quantity(value=100.0, source="source-a")
    kwargs = {
        "value": 100.0,
        "source": "source-b",
        "unit": left.unit,
        "epoch": left.epoch,
        "observer": left.observer,
        "frame": left.frame,
    }
    kwargs[field] = replacement
    with pytest.raises(ScientificConflictError, match=error_code):
        ScientificConflictResolver().resolve_conflicts(
            (left, _quantity(**kwargs))
        )


def test_resolver_fails_closed_on_material_numerical_conflict():
    resolver = ScientificConflictResolver(
        {
            ("test-target", "test-distance"): ScientificTolerance(
                absolute=1.0
            )
        }
    )
    with pytest.raises(ScientificConflictError, match="MATERIAL_DISCREPANCY"):
        resolver.resolve_conflicts(
            (
                _quantity(value=100.0, source="source-a"),
                _quantity(value=200.0, source="source-b"),
            )
        )


def test_required_canonical_metadata_cannot_be_empty():
    with pytest.raises(ResearchDataError, match="epoch must be a non-empty string"):
        CanonicalScientificQuantity(
            subject="target",
            quantity="distance",
            epoch=" ",
            observer="observer",
            unit="m",
            frame="frame",
            value=1.0,
            uncertainty=None,
            display_precision=1,
            source="source",
            provenance={},
        )


@pytest.mark.parametrize(
    ("mutator", "error_code"),
    [
        (
            lambda q: ResearchDatum(
                "raw",
                "raw",
                q.value,
                "different-source",
                q.unit,
                canonical_quantity=q,
            ),
            "SOURCE_PROVENANCE_MISMATCH",
        ),
        (
            lambda q: ResearchDatum(
                "raw",
                "raw",
                q.value,
                q.source,
                "km",
                canonical_quantity=q,
            ),
            "RAW_CANONICAL_UNIT_MISMATCH",
        ),
        (
            lambda q: ResearchDatum(
                "raw",
                "raw",
                q.value + 1.0,
                q.source,
                q.unit,
                canonical_quantity=q,
            ),
            "RAW_CANONICAL_VALUE_MISMATCH",
        ),
    ],
)
def test_fact_lock_gate_rejects_raw_canonical_mismatch(mutator, error_code):
    quantity = _quantity(value=100.0, source="source-a")
    runner = Mock(return_value=ResearchBundle(data=(mutator(quantity),)))
    adapter = C3ExternalResearchFactLockAdapter(
        runner,
        base_adapter=_base_fact_lock_adapter(),
    )
    result = adapter(
        Mock(project_id="synthetic-project"),
        {"external_research": {"fixture": "mismatch"}},
    )
    assert result.disposition is StageDisposition.BLOCKED
    assert result.details["error_code"] == error_code
    assert result.details["writer_room_allowed"] is False
    assert result.details["auto_publication"] is False


def test_fact_lock_gate_rejects_unit_scalar_without_canonical_quantity():
    runner = Mock(
        return_value=ResearchBundle(
            data=(
                ResearchDatum(
                    fact_id="source-a:distance",
                    label_es="Distancia",
                    value=42.0,
                    unit="km",
                    source_id="source-a",
                ),
            )
        )
    )
    adapter = C3ExternalResearchFactLockAdapter(
        runner,
        base_adapter=_base_fact_lock_adapter(),
    )
    result = adapter(
        Mock(project_id="synthetic-project"),
        {"external_research": {"fixture": "missing-canonical"}},
    )
    assert result.disposition is StageDisposition.BLOCKED
    assert result.details["error_code"] == "MISSING_CANONICAL_QUANTITY"
    assert result.details["writer_room_allowed"] is False
    assert result.details["auto_publication"] is False


def test_fact_lock_gate_blocks_provider_conflict_before_writer_room():
    resolver = ScientificConflictResolver(
        {
            ("test-target", "test-distance"): ScientificTolerance(
                absolute=1.0
            )
        }
    )
    runner = Mock(
        return_value=ResearchBundle(
            data=(
                _datum(
                    fact_id="source-a:distance",
                    quantity=_quantity(value=100.0, source="source-a"),
                ),
                _datum(
                    fact_id="source-b:distance",
                    quantity=_quantity(value=200.0, source="source-b"),
                ),
            )
        )
    )
    adapter = C3ExternalResearchFactLockAdapter(
        runner,
        base_adapter=_base_fact_lock_adapter(),
        conflict_resolver=resolver,
    )
    result = adapter(
        Mock(project_id="synthetic-project"),
        {"external_research": {"fixture": "conflict"}},
    )
    assert result.disposition is StageDisposition.BLOCKED
    assert result.details["error_code"] == "MATERIAL_DISCREPANCY"
    assert result.details["writer_room_allowed"] is False
    assert result.details["auto_publication"] is False


def test_wikimedia_rights_gate_stays_fail_closed_for_unknown_license():
    payload = {
        "query": {
            "pages": [
                {
                    "pageid": 42,
                    "title": "File:Venus.jpg",
                    "imageinfo": [
                        {
                            "url": "https://upload.wikimedia.org/venus.jpg",
                            "descriptionurl": (
                                "https://commons.wikimedia.org/wiki/File:Venus.jpg"
                            ),
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


def test_nasa_apod_rights_gate_stays_fail_closed_when_copyright_present():
    bundle = NasaOpenAdapter(FakeTransport([
        {
            "date": "2026-01-01",
            "title": "Example APOD",
            "hdurl": "https://apod.nasa.gov/example.jpg",
            "copyright": "Third Party Author",
        }
    ])).apod(research_context(), day=date(2026, 1, 1))
    assert bundle.media[0].publication_eligible is False
    assert bundle.media[0].rights_decision == "review"


def test_mast_discovery_remains_non_publication_eligible():
    bundle = MastHstJwstAdapter(FakeTransport([
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
    ])).search(
        research_context(),
        mission="JWST",
        target="M 42",
        limit=5,
    )
    assert bundle.sources[0].provider == "MAST/STScI"
    assert bundle.media[0].publication_eligible is False


@pytest.mark.parametrize(
    ("builder", "provider"),
    [
        (build_eso_tap_adapter, "ESO"),
        (build_esa_gaia_tap_adapter, "ESA Gaia Archive"),
    ],
)
def test_tap_discovery_remains_non_publication_eligible(builder, provider):
    bundle = builder(
        FakeTransport([[{"source_id": "1", "obs_title": "test"}]])
    ).query_fixed(
        research_context(),
        query="SELECT TOP 1 source_id FROM example.table",
        title="archive test",
        maximum_rows=1,
    )
    assert bundle.sources[0].provider == provider
    assert bundle.media[0].publication_eligible is False


def test_skyfield_requires_preexisting_local_bsp_and_never_downloads(tmp_path):
    adapter = SkyfieldDE440Adapter(tmp_path / "de440s.bsp")
    with pytest.raises(OptionalRuntimeUnavailable, match="pre-downloaded"):
        adapter.position(
            research_context(),
            body="venus",
            moment=datetime.now(UTC),
        )


def test_stellarium_bridge_has_no_assumed_cli():
    adapter = StellariumStaticRendererAdapter()
    with pytest.raises(OptionalRuntimeUnavailable, match="not configured"):
        adapter.render(research_context(), {"target": "Venus"})
