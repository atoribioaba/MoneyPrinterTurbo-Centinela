from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import GroundingFact
from app.services.centinela.production_spine import (
    StageArtifact,
    StageDisposition,
    StageResult,
)
from app.services.centinela.research_adapters import C3ExternalResearchFactLockAdapter
from app.services.centinela.research_adapters import (
    ScientificConflictError,
    ScientificConflictResolver,
    ScientificTolerance,
)
from app.services.centinela.research_adapters.contracts import (
    CanonicalScientificQuantity,
    ResearchBundle,
    ResearchDatum,
    ResearchSource,
)
from app.services.centinela.writer_room.models import FactLock


def _quantity(
    *,
    value: float,
    source: str,
    unit: str = "m",
    epoch: str = "2026-09-01T00:00:00Z",
    observer: str = "synthetic-observer",
    frame: str = "synthetic-frame",
) -> CanonicalScientificQuantity:
    return CanonicalScientificQuantity(
        subject="synthetic-target",
        quantity="synthetic-distance",
        epoch=epoch,
        observer=observer,
        unit=unit,
        frame=frame,
        value=value,
        uncertainty=0.1,
        display_precision=1,
        source=source,
        provenance={"fixture": "synthetic", "auto_publication": False},
    )


def _datum(*, fact_id: str, quantity: CanonicalScientificQuantity) -> ResearchDatum:
    return ResearchDatum(
        fact_id=fact_id,
        label_es="Magnitud sintética",
        value=quantity.value,
        unit=quantity.unit,
        source_id=quantity.source,
        canonical_quantity=quantity,
    )


def _source(source_id: str) -> ResearchSource:
    return ResearchSource(
        source_id=source_id,
        title=f"Synthetic source {source_id}",
        provider=source_id,
        url=f"https://example.org/{source_id}",
    )


def _base_adapter() -> Mock:
    base_fact_lock = FactLock(
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
        generated_at_utc=datetime(2026, 9, 1, tzinfo=UTC),
    )
    return Mock(
        return_value=StageResult.complete(
            StageArtifact(
                artifact_type="fact_lock",
                payload=base_fact_lock.model_dump(mode="json"),
            )
        )
    )


def test_research_datum_converts_and_normalizes_to_canonical_quantity() -> None:
    datum = Mock()
    datum.value = "100.1"
    datum.unit = "km"
    datum.source_id = "source-a"

    quantity = CanonicalScientificQuantity.from_research_datum(
        datum,
        subject="synthetic-target",
        quantity="synthetic-distance",
        epoch="2026-09-01T00:00:00Z",
        observer="synthetic-observer",
        frame="synthetic-frame",
        uncertainty=0.2,
        display_precision=1,
        provenance={"fixture": "synthetic"},
    )
    normalized = ScientificConflictResolver().normalize(quantity)

    assert normalized.value == pytest.approx(100_100.0)
    assert normalized.unit == "m"
    assert normalized.uncertainty == pytest.approx(200.0)
    assert normalized.display_precision == 0
    assert normalized.source == "source-a"
    assert normalized.provenance["canonicalization"]["original_unit"] == "km"


def test_conflicting_sources_fail_closed_above_explicit_tolerance() -> None:
    resolver = ScientificConflictResolver(
        {
            ("synthetic-target", "synthetic-distance"): ScientificTolerance(
                absolute=10.0
            )
        }
    )
    with pytest.raises(ScientificConflictError, match="MATERIAL_DISCREPANCY"):
        resolver.resolve_conflicts(
            (
                _quantity(value=100_000.0, source="source-a"),
                _quantity(value=101_000.0, source="source-b"),
            )
        )


def test_multiple_sources_pass_inside_explicit_tolerance() -> None:
    resolver = ScientificConflictResolver(
        {
            ("synthetic-target", "synthetic-distance"): ScientificTolerance(
                relative=0.001
            )
        }
    )
    result = resolver.resolve_conflicts(
        (
            _quantity(
                value=100.0,
                unit="km",
                source="source-a",
                epoch="2026-09-01T00:00:00Z",
            ),
            _quantity(
                value=100_050.0,
                source="source-b",
                epoch="2026-09-01T00:00:00+00:00",
            ),
        )
    )
    assert [item.unit for item in result] == ["m", "m"]
    assert result[0].value == pytest.approx(100_000.0)
    assert result[1].value == pytest.approx(100_050.0)


@pytest.mark.parametrize(
    ("field", "replacement", "error_code"),
    [
        ("epoch", "2026-09-02T00:00:00Z", "EPOCH_INCOMPATIBLE"),
        ("observer", "other-observer", "OBSERVER_INCOMPATIBLE"),
        ("frame", "other-frame", "FRAME_INCOMPATIBLE"),
        ("unit", "s", "UNIT_INCOMPATIBLE"),
    ],
)
def test_semantic_incompatibilities_fail_closed(
    field: str,
    replacement: str,
    error_code: str,
) -> None:
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
    right = _quantity(**kwargs)
    with pytest.raises(ScientificConflictError, match=error_code):
        ScientificConflictResolver().resolve_conflicts((left, right))


def test_non_identical_values_without_tolerance_fail_closed() -> None:
    with pytest.raises(
        ScientificConflictError,
        match="MISSING_SCIENTIFIC_TOLERANCE",
    ):
        ScientificConflictResolver().resolve_conflicts(
            (
                _quantity(value=100.0, source="source-a"),
                _quantity(value=100.1, source="source-b"),
            )
        )


def test_two_provider_quantities_reach_conflict_resolver_and_pass_within_tolerance() -> None:
    class RecordingResolver(ScientificConflictResolver):
        def __init__(self):
            super().__init__(
                {
                    ("synthetic-target", "synthetic-distance"): ScientificTolerance(
                        absolute=100.0
                    )
                }
            )
            self.received = ()

        def resolve_conflicts(self, quantities):
            self.received = tuple(quantities)
            return super().resolve_conflicts(self.received)

    resolver = RecordingResolver()
    runner = Mock(
        return_value=ResearchBundle(
            data=(
                _datum(
                    fact_id="external-a",
                    quantity=_quantity(value=100_000.0, source="source-a"),
                ),
                _datum(
                    fact_id="external-b",
                    quantity=_quantity(value=100_050.0, source="source-b"),
                ),
            ),
            sources=(_source("source-a"), _source("source-b")),
        )
    )
    adapter = C3ExternalResearchFactLockAdapter(
        runner,
        base_adapter=_base_adapter(),
        conflict_resolver=resolver,
    )

    result = adapter(
        Mock(project_id="synthetic-project"),
        {"external_research": {"fixture": "synthetic"}},
    )

    assert result.disposition is StageDisposition.COMPLETE
    assert [item.source for item in resolver.received] == ["source-a", "source-b"]
    assert result.details["auto_publication"] is False


def test_conflict_blocks_external_fact_lock_before_writer_room() -> None:
    runner = Mock(
        return_value=ResearchBundle(
            data=(
                _datum(
                    fact_id="external-a",
                    quantity=_quantity(value=100.0, source="source-a"),
                ),
                _datum(
                    fact_id="external-b",
                    quantity=_quantity(value=200.0, source="source-b"),
                ),
            )
        )
    )
    adapter = C3ExternalResearchFactLockAdapter(
        runner,
        base_adapter=_base_adapter(),
        conflict_resolver=ScientificConflictResolver(
            {
                ("synthetic-target", "synthetic-distance"): ScientificTolerance(
                    absolute=1.0
                )
            }
        ),
    )
    result = adapter(
        Mock(project_id="synthetic-project"),
        {"external_research": {"fixture": "synthetic"}},
    )
    assert result.disposition is StageDisposition.BLOCKED
    assert result.message == "scientific research conflict blocks Fact Lock enrichment"
    assert result.details["error_code"] == "MATERIAL_DISCREPANCY"
    assert result.details["writer_room_allowed"] is False
    assert result.details["auto_publication"] is False
    runner.assert_called_once()


@pytest.mark.parametrize(
    ("second", "error_code"),
    [
        (_quantity(value=100.0, source="source-b", unit="s"), "UNIT_INCOMPATIBLE"),
        (
            _quantity(
                value=100.0,
                source="source-b",
                epoch="2026-09-02T00:00:00Z",
            ),
            "EPOCH_INCOMPATIBLE",
        ),
    ],
)
def test_semantic_conflict_blocks_enriched_lock_and_writer_room(second, error_code) -> None:
    runner = Mock(
        return_value=ResearchBundle(
            data=(
                _datum(
                    fact_id="external-a",
                    quantity=_quantity(value=100.0, source="source-a"),
                ),
                _datum(fact_id="external-b", quantity=second),
            )
        )
    )
    adapter = C3ExternalResearchFactLockAdapter(
        runner,
        base_adapter=_base_adapter(),
    )
    result = adapter(
        Mock(project_id="synthetic-project"),
        {"external_research": {"fixture": "semantic-conflict"}},
    )
    assert result.disposition is StageDisposition.BLOCKED
    assert result.details["error_code"] == error_code
    assert result.details["writer_room_allowed"] is False
    assert result.details["auto_publication"] is False


def test_missing_canonical_quantity_for_comparable_scalar_fails_closed() -> None:
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
        base_adapter=_base_adapter(),
    )
    result = adapter(
        Mock(project_id="synthetic-project"),
        {"external_research": {"fixture": "missing-canonical"}},
    )
    assert result.disposition is StageDisposition.BLOCKED
    assert result.details["error_code"] == "MISSING_CANONICAL_QUANTITY"
    assert result.details["writer_room_allowed"] is False
    assert result.details["auto_publication"] is False
