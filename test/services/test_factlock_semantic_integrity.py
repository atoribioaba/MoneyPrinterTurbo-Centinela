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


def _fact(fact_id: str, value: object, source_ids: list[str]) -> GroundingFact:
    return GroundingFact(
        fact_id=fact_id,
        label_es=fact_id,
        value=value,
        unit=None,
        scientific_status=ScientificStatus.HECHO_VERIFICADO,
        source_ids=source_ids,
    )


def _source(source_id: str) -> SourceReference:
    return SourceReference(
        source_id=source_id,
        title=f"Source {source_id}",
        provider="TEST_PRIMARY",
        url="https://example.invalid/source",
        license=None,
        classification="DOCUMENTACION_OFICIAL",
        role="primary scientific evidence",
        scientific_status=ScientificStatus.HECHO_VERIFICADO,
    )


def _payload() -> dict[str, object]:
    facts = [
        _fact("fact:a", 1, ["src:b", "src:a"]),
        _fact("fact:b", 2, ["src:a"]),
    ]
    source_ids = ["src:a", "src:b"]
    return {
        "subject": "Saturno",
        "research_mode": "OBSERVATION_CONTEXT",
        "context_hash": compute_fact_lock_context_hash(facts, source_ids),
        "facts": facts,
        "sources": [_source("src:a"), _source("src:b")],
        "source_ids": source_ids,
        "scope_note": "semantic integrity test",
        "location_assumed": False,
        "moment_basis": "explicit_project_moment",
        "generated_at_utc": datetime.now(timezone.utc),
    }


def test_fact_lock_accepts_canonical_semantic_payload() -> None:
    value = FactLock.model_validate(_payload())
    assert value.source_ids == ["src:a", "src:b"]
    assert value.context_hash == compute_fact_lock_context_hash(
        value.facts, value.source_ids
    )


def test_fact_lock_canonicalizes_source_id_order_before_hash_check() -> None:
    payload = _payload()
    payload["source_ids"] = ["src:b", "src:a", "src:a"]
    value = FactLock.model_validate(payload)
    assert value.source_ids == ["src:a", "src:b"]


def test_fact_lock_rejects_duplicate_fact_ids() -> None:
    payload = _payload()
    facts = list(payload["facts"])
    facts[1] = facts[1].model_copy(update={"fact_id": "fact:a"})
    payload["facts"] = facts
    payload["context_hash"] = compute_fact_lock_context_hash(
        facts, ["src:a", "src:b"]
    )
    with pytest.raises(ValidationError, match="fact_id values must be unique"):
        FactLock.model_validate(payload)


def test_fact_lock_rejects_source_union_mismatch() -> None:
    payload = _payload()
    payload["source_ids"] = ["src:a"]
    payload["context_hash"] = compute_fact_lock_context_hash(
        list(payload["facts"]), ["src:a"]
    )
    with pytest.raises(ValidationError, match="canonical union"):
        FactLock.model_validate(payload)


def test_fact_lock_rejects_missing_source_reference() -> None:
    payload = _payload()
    payload["sources"] = [_source("src:a")]
    with pytest.raises(ValidationError, match="missing SourceReference"):
        FactLock.model_validate(payload)


def test_fact_lock_rejects_duplicate_source_references() -> None:
    payload = _payload()
    payload["sources"] = [_source("src:a"), _source("src:a"), _source("src:b")]
    with pytest.raises(ValidationError, match="SourceReference source_id values must be unique"):
        FactLock.model_validate(payload)


@pytest.mark.parametrize("context_hash", ["a" * 64, "Z" * 64])
def test_fact_lock_rejects_noncanonical_hash_shape(context_hash: str) -> None:
    payload = _payload()
    payload["context_hash"] = context_hash
    with pytest.raises(ValidationError, match="uppercase SHA-256"):
        FactLock.model_validate(payload)


def test_fact_lock_rejects_wrong_hash_length() -> None:
    payload = _payload()
    payload["context_hash"] = "A" * 63
    with pytest.raises(ValidationError):
        FactLock.model_validate(payload)


def test_fact_lock_rejects_fact_mutation_with_stale_hash() -> None:
    payload = _payload()
    facts = list(payload["facts"])
    facts[0] = facts[0].model_copy(update={"value": 999})
    payload["facts"] = facts
    with pytest.raises(ValidationError, match="does not match facts/source_ids"):
        FactLock.model_validate(payload)
