from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.astronomy import ScientificStatus, SourceReference
from app.models.astronomy_director import GroundingFact
from app.services.centinela.writer_room import (
    FactLock,
    compute_fact_lock_context_hash,
)


def _source(source_id: str = "source:test") -> SourceReference:
    return SourceReference(
        source_id=source_id,
        title="FactLock semantic integrity fixture",
        provider="TEST",
        url="https://example.invalid/factlock",
        license="TEST",
        classification="PRIMARY_TEST_SOURCE",
        role="scientific_fixture",
        scientific_status=ScientificStatus.HECHO_VERIFICADO,
    )


def _fact(source_id: str = "source:test", value: float = 42.0) -> GroundingFact:
    return GroundingFact(
        fact_id="moon:distance_km",
        label_es="Distancia lunar",
        value=value,
        unit="km",
        scientific_status=ScientificStatus.HECHO_VERIFICADO,
        source_ids=[source_id],
    )


def _payload():
    facts = [_fact()]
    source_ids = ["source:test"]
    return {
        "subject": "La Luna",
        "research_mode": "GENERIC_GEOCENTRIC",
        "context_hash": compute_fact_lock_context_hash(facts, source_ids),
        "facts": facts,
        "sources": [_source()],
        "source_ids": source_ids,
        "scope_note": "C16 semantic-integrity fixture.",
        "location_assumed": False,
        "moment_basis": "fixture",
        "primary_source_verification_required_for_publication": True,
        "generated_at_utc": datetime.now(timezone.utc),
    }


def test_factlock_accepts_canonical_semantic_hash():
    lock = FactLock(**_payload())
    assert lock.context_hash == compute_fact_lock_context_hash(
        lock.facts, lock.source_ids
    )


def test_factlock_rejects_well_formed_but_forged_hash():
    payload = _payload()
    payload["context_hash"] = "A" * 64
    with pytest.raises(ValidationError, match="does not match facts/source_ids"):
        FactLock(**payload)


def test_factlock_rejects_fact_mutation_after_hash_was_computed():
    payload = _payload()
    payload["facts"] = [_fact(value=43.0)]
    with pytest.raises(ValidationError, match="does not match facts/source_ids"):
        FactLock(**payload)


def test_factlock_rejects_missing_or_extra_source_ids():
    for source_ids in ([], ["source:test", "source:extra"]):
        payload = _payload()
        payload["source_ids"] = source_ids
        with pytest.raises(ValidationError, match="canonical union"):
            FactLock(**payload)


def test_factlock_rejects_missing_source_reference():
    payload = _payload()
    payload["sources"] = []
    with pytest.raises(ValidationError, match="missing SourceReference"):
        FactLock(**payload)


def test_factlock_rejects_duplicate_fact_ids():
    payload = _payload()
    duplicate = _fact(value=43.0)
    payload["facts"] = [payload["facts"][0], duplicate]
    payload["context_hash"] = compute_fact_lock_context_hash(
        payload["facts"], payload["source_ids"]
    )
    with pytest.raises(ValidationError, match="fact_id values must be unique"):
        FactLock(**payload)


def test_factlock_rejects_lowercase_hash_even_if_semantically_equal():
    payload = _payload()
    payload["context_hash"] = payload["context_hash"].lower()
    with pytest.raises(ValidationError, match="uppercase SHA-256"):
        FactLock(**payload)


def test_hash_canonicalizes_source_id_order_and_duplicates():
    facts = [_fact()]
    assert compute_fact_lock_context_hash(
        facts, ["source:test", "source:test"]
    ) == compute_fact_lock_context_hash(facts, ["source:test"])
