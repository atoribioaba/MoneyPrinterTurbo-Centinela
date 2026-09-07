from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.astronomy import ScientificStatus, SourceReference
from app.models.astronomy_director import GroundingFact
from app.services.centinela.writer_room import (
    FactLock,
    WriterRoom,
    WriterRoomError,
    WriterRoomRequest,
    compute_fact_lock_context_hash,
)


class NeverCalledRuntime:
    def resolve_model(self, requested):
        raise AssertionError("runtime must not be reached for a tampered FactLock")

    def generate(self, *args, **kwargs):
        raise AssertionError("LLM generation must not be reached for a tampered FactLock")


def _valid_fact_lock() -> FactLock:
    source_id = "source:test"
    facts = [
        GroundingFact(
            fact_id="body:saturn:constellation",
            label_es="Constelación de Saturno",
            value="Pisces",
            unit=None,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
            source_ids=[source_id],
        )
    ]
    return FactLock(
        subject="Saturno",
        research_mode="GENERIC_GEOCENTRIC",
        context_hash=compute_fact_lock_context_hash(facts, [source_id]),
        facts=facts,
        sources=[
            SourceReference(
                source_id=source_id,
                title="C16 pre-LLM validation fixture",
                provider="TEST",
                url="https://example.invalid/factlock",
                license="TEST",
                classification="PRIMARY_TEST_SOURCE",
                role="scientific_fixture",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
            )
        ],
        source_ids=[source_id],
        scope_note="C16 pre-LLM semantic-integrity fixture.",
        location_assumed=False,
        moment_basis="fixture",
        primary_source_verification_required_for_publication=True,
        generated_at_utc=datetime.now(timezone.utc),
    )


def test_tampered_model_copy_is_rejected_before_runtime_resolution() -> None:
    tampered = _valid_fact_lock().model_copy(update={"context_hash": "B" * 64})

    with pytest.raises(WriterRoomError, match="semantic integrity"):
        WriterRoom(runtime=NeverCalledRuntime()).generate(
            WriterRoomRequest(subject="Saturno"),
            tampered,
        )
