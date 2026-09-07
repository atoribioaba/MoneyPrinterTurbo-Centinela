from __future__ import annotations

from typing import Any

from app.models.astronomy import ScientificStatus, SourceReference
from app.models.astronomy_director import GroundingFact
from app.services.centinela.writer_room import FactLock, compute_fact_lock_context_hash


def make_semantically_valid_fact_lock(
    *,
    facts: list[GroundingFact],
    context_hash: str | None = None,
    sources: list[SourceReference] | None = None,
    source_ids: list[str] | None = None,
    **kwargs: Any,
) -> FactLock:
    """Build a test FactLock with canonical hash/provenance.

    Legacy fixture placeholders for context_hash/source_ids are intentionally
    ignored: semantic identity is derived from the supplied facts. Existing
    SourceReference objects are preserved and missing test-only references are
    synthesized so production validation is exercised rather than bypassed.
    """
    del context_hash, source_ids
    canonical_source_ids = sorted(
        {
            source_id.strip()
            for fact in facts
            for source_id in fact.source_ids
            if source_id.strip()
        }
    )
    resolved_sources = list(sources or [])
    known = {source.source_id for source in resolved_sources}
    for source_id in canonical_source_ids:
        if source_id in known:
            continue
        resolved_sources.append(
            SourceReference(
                source_id=source_id,
                title=f"Synthetic test source {source_id}",
                provider="TEST_FIXTURE",
                url=f"https://example.invalid/{source_id}",
                license=None,
                classification="TEST_FIXTURE",
                role="test_fixture_only",
                scientific_status=ScientificStatus.NO_VERIFICADO,
            )
        )
    return FactLock(
        facts=facts,
        sources=resolved_sources,
        source_ids=canonical_source_ids,
        context_hash=compute_fact_lock_context_hash(facts, canonical_source_ids),
        **kwargs,
    )
