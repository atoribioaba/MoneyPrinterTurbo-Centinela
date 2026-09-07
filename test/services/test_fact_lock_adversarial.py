from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import (
    GroundingFact,
    GroundingPacket,
    compute_grounding_context_hash,
)
from app.services.centinela.writer_room.models import FactLock
from app.services.centinela.writer_room.spine_adapter import (
    WriterRoomSpineError,
    _validated_grounding_context_hash,
)


def _facts() -> list[GroundingFact]:
    return [
        GroundingFact(
            fact_id="fact:a",
            label_es="Hecho A",
            value=42,
            unit="km",
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
            source_ids=["source:a"],
        ),
        GroundingFact(
            fact_id="fact:b",
            label_es="Hecho B",
            value="dato",
            unit=None,
            scientific_status=ScientificStatus.APROXIMACION_DIVULGATIVA,
            source_ids=["source:b"],
        ),
    ]


def _fact_lock(*, facts=None, source_ids=None, context_hash=None) -> FactLock:
    facts = list(facts or _facts())
    source_ids = list(source_ids or ["source:a", "source:b"])
    context_hash = context_hash or compute_grounding_context_hash(
        facts, source_ids
    )
    return FactLock(
        subject="Luna y Júpiter",
        research_mode="OBSERVATION_CONTEXT",
        context_hash=context_hash,
        facts=facts,
        source_ids=source_ids,
        scope_note="Contexto científico bloqueado para escritura.",
        location_assumed=False,
        moment_basis="explicit_project_moment",
        generated_at_utc=datetime.now(timezone.utc),
    )


def test_canonical_hash_vector_is_stable():
    digest = compute_grounding_context_hash(
        _facts(), ["source:a", "source:b"]
    )
    assert digest == (
        "7E581B8FA645AB9A632905727795A4C1"
        "B8FE0222FDC8412A4559104CF71BADDA"
    )


def test_valid_fact_lock_accepts_canonical_hash():
    lock = _fact_lock()
    assert lock.context_hash == compute_grounding_context_hash(
        lock.facts, lock.source_ids
    )


def test_arbitrary_64_character_hash_is_rejected():
    with pytest.raises(ValidationError, match="context_hash does not match"):
        _fact_lock(context_hash="A" * 64)


def test_one_character_hash_tamper_is_rejected():
    digest = compute_grounding_context_hash(_facts(), ["source:a", "source:b"])
    tampered = ("0" if digest[0] != "0" else "1") + digest[1:]
    with pytest.raises(ValidationError, match="context_hash does not match"):
        _fact_lock(context_hash=tampered)


def test_reordering_source_ids_invalidates_previous_hash():
    digest = compute_grounding_context_hash(_facts(), ["source:a", "source:b"])
    with pytest.raises(ValidationError, match="context_hash does not match"):
        _fact_lock(
            source_ids=["source:b", "source:a"],
            context_hash=digest,
        )


def test_reordering_facts_invalidates_previous_hash():
    facts = _facts()
    digest = compute_grounding_context_hash(facts, ["source:a", "source:b"])
    with pytest.raises(ValidationError, match="context_hash does not match"):
        _fact_lock(
            facts=list(reversed(facts)),
            context_hash=digest,
        )


def test_source_id_normalization_is_part_of_fact_lock_hash_contract():
    normalized = ["source:a", "source:b"]
    digest = compute_grounding_context_hash(_facts(), normalized)
    lock = _fact_lock(
        source_ids=[" source:a ", "source:a", "source:b"],
        context_hash=digest,
    )
    assert lock.source_ids == normalized


def test_valid_grounding_packet_hash_is_accepted_by_spine():
    facts = _facts()
    source_ids = ["source:a", "source:b"]
    packet = GroundingPacket(
        context_hash=compute_grounding_context_hash(facts, source_ids),
        facts=facts,
        source_ids=source_ids,
    )
    assert _validated_grounding_context_hash(packet) == packet.context_hash


def test_tampered_grounding_packet_fails_closed_before_fact_lock():
    packet = GroundingPacket(
        context_hash="F" * 64,
        facts=_facts(),
        source_ids=["source:a", "source:b"],
    )
    with pytest.raises(
        WriterRoomSpineError,
        match="GroundingPacket context_hash does not match",
    ):
        _validated_grounding_context_hash(packet)
