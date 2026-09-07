from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import GroundingFact
from app.services.centinela.production_spine import (
    StageArtifact,
    StageDisposition,
    StageResult,
)
from app.services.centinela.research_adapters import (
    C3ExternalResearchFactLockAdapter,
    ResearchBundle,
    ResearchDatum,
    ResearchSource,
)
from app.services.centinela.writer_room import (
    FactLock,
    compute_fact_lock_context_hash,
)


def _base_adapter() -> Mock:
    facts = [
        GroundingFact(
            fact_id="base:fact",
            label_es="Hecho base",
            value="ok",
            unit=None,
            scientific_status=ScientificStatus.NO_VERIFICADO,
            source_ids=[],
        )
    ]
    fact_lock = FactLock(
        subject="Synthetic target",
        research_mode="GENERIC_GEOCENTRIC",
        context_hash=compute_fact_lock_context_hash(facts, []),
        facts=facts,
        sources=[],
        source_ids=[],
        scope_note="C16 external-research hash fixture.",
        location_assumed=False,
        moment_basis="fixture",
        primary_source_verification_required_for_publication=True,
        generated_at_utc=datetime(2026, 9, 7, tzinfo=UTC),
    )
    return Mock(
        return_value=StageResult.complete(
            StageArtifact(
                artifact_type="fact_lock",
                payload=fact_lock.model_dump(mode="json"),
            )
        )
    )


def _source(source_id: str) -> ResearchSource:
    return ResearchSource(
        source_id=source_id,
        title=f"Source {source_id}",
        provider="TEST",
        url="https://example.invalid/source",
        classification="TEST_PRIMARY",
        license="TEST",
        primary_source=True,
    )


def test_unused_external_source_does_not_poison_factlock_source_union() -> None:
    runner = Mock(return_value=ResearchBundle(sources=(_source("unused:source"),)))
    result = C3ExternalResearchFactLockAdapter(
        runner,
        base_adapter=_base_adapter(),
    )(
        Mock(project_id="synthetic-project"),
        {"external_research": {"fixture": "unused-source"}},
    )

    assert result.disposition is StageDisposition.COMPLETE
    artifact = next(item for item in result.artifacts if item.artifact_type == "fact_lock")
    value = FactLock.model_validate(artifact.payload)
    assert value.source_ids == []
    assert value.context_hash == compute_fact_lock_context_hash(value.facts, [])


def test_external_datum_with_missing_source_reference_is_blocked() -> None:
    runner = Mock(
        return_value=ResearchBundle(
            data=(
                ResearchDatum(
                    fact_id="external:orphan",
                    label_es="Dato huérfano",
                    value="unsupported",
                    source_id="missing:source",
                    unit=None,
                ),
            )
        )
    )
    result = C3ExternalResearchFactLockAdapter(
        runner,
        base_adapter=_base_adapter(),
    )(
        Mock(project_id="synthetic-project"),
        {"external_research": {"fixture": "dangling-source"}},
    )

    assert result.disposition is StageDisposition.BLOCKED
