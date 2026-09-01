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
from app.services.centinela.research_adapters.conflicts import (
    ScientificConflictError,
    ScientificConflictResolver,
    ScientificTolerance,
)
from app.services.centinela.research_adapters.contracts import (
    CanonicalScientificQuantity,
    ResearchBundle,
    ResearchDatum,
)
from app.services.centinela.research_adapters.spine_adapter import (
    C3ExternalResearchFactLockAdapter,
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
        provenance={"fixture": "synthetic"},
    )


def _datum(
    *,
    fact_id: str,
    quantity: CanonicalScientificQuantity,
) -> ResearchDatum:
    return ResearchDatum(
        fact_id=fact_id,
        label_es="Magnitud sintética",
        value=quantity.value,
        unit=quantity.unit,
        source_id=quantity.source,
        canonical_quantity=quantity,
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
        resolver.resolve(
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

    result = resolver.resolve(
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
        ScientificConflictResolver().resolve((left, right))


def test_non_identical_values_without_tolerance_fail_closed() -> None:
    with pytest.raises(
        ScientificConflictError,
        match="MISSING_SCIENTIFIC_TOLERANCE",
    ):
        ScientificConflictResolver().resolve(
            (
                _quantity(value=100.0, source="source-a"),
                _quantity(value=100.1, source="source-b"),
            )
        )


def test_conflict_blocks_external_fact_lock_before_writer_room() -> None:
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
    base_adapter = Mock(
        return_value=StageResult.complete(
            StageArtifact(
                artifact_type="fact_lock",
                payload=base_fact_lock.model_dump(mode="json"),
            )
        )
    )
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
        base_adapter=base_adapter,
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
