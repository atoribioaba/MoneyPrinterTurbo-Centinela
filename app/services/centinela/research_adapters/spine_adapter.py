from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from app.models.astronomy import ScientificStatus, SourceReference
from app.models.astronomy_director import GroundingFact
from app.services.centinela.orchestration import ResourceClass
from app.services.centinela.production_spine import (
    StageArtifact,
    StageBinding,
    StageResult,
)
from app.services.centinela.writer_room.models import FactLock
from app.services.centinela.writer_room.spine_adapter import FactLockStageAdapter

from .conflicts import ScientificConflictError, ScientificConflictResolver
from .contracts import (
    ResearchAdapterError,
    ResearchBundle,
    ResearchContext,
    ResearchPhase,
)
from .service import (
    build_licenses_manifest,
    build_provenance_manifest,
    merge_bundles,
)


ExternalResearchRunner = Callable[[ResearchContext, dict[str, Any]], ResearchBundle]


def _hash_fact_lock(facts: list[GroundingFact], source_ids: list[str]) -> str:
    payload = {
        "facts": [item.model_dump(mode="json") for item in facts],
        "source_ids": list(source_ids),
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


class C3ExternalResearchFactLockAdapter:
    """
    Enrich deterministic Astronomy Core Fact Lock with sealed RESEARCH evidence.

    The supplied runner is the only component allowed to perform external I/O.
    Nothing downstream receives a transport or external adapter handle.
    """

    def __init__(
        self,
        runner: ExternalResearchRunner,
        *,
        base_adapter: FactLockStageAdapter | None = None,
        conflict_resolver: ScientificConflictResolver | None = None,
    ) -> None:
        self.runner = runner
        self.base_adapter = base_adapter or FactLockStageAdapter()
        self.conflict_resolver = conflict_resolver or ScientificConflictResolver()

    def __call__(self, context: Any, payload: dict[str, Any]) -> StageResult:
        base = self.base_adapter(context, payload)
        if base.disposition.value != "COMPLETE":
            return base

        external_request = payload.get("external_research")
        if external_request in (None, {}):
            return base
        if not isinstance(external_request, dict):
            return StageResult.blocked("external_research request must be an object")

        fact_artifacts = [
            item for item in base.artifacts if item.artifact_type == "fact_lock"
        ]
        if len(fact_artifacts) != 1 or not isinstance(fact_artifacts[0].payload, dict):
            return StageResult.blocked("base Fact Lock output is invalid")

        try:
            fact_lock = FactLock.model_validate(fact_artifacts[0].payload)
            research_context = ResearchContext(
                project_id=context.project_id,
                phase=ResearchPhase.RESEARCH,
            )
            external = self.runner(research_context, external_request)
            if not isinstance(external, ResearchBundle):
                raise TypeError("external research runner must return ResearchBundle")
            self._resolve_external_quantities(external)
        except ScientificConflictError as exc:
            return StageResult.blocked(
                "scientific research conflict blocks Fact Lock enrichment",
                details={
                    "error_type": type(exc).__name__,
                    "error_code": exc.code,
                    "error": str(exc)[:1200],
                    "subject": exc.subject,
                    "quantity": exc.quantity,
                    "network_phase": "RESEARCH_ONLY",
                    "writer_room_allowed": False,
                    "auto_publication": False,
                },
            )
        except ResearchAdapterError as exc:
            return StageResult.blocked(
                "external astronomy research failed closed",
                details={
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1200],
                    "network_phase": "RESEARCH_ONLY",
                },
            )
        except Exception as exc:
            return StageResult.blocked(
                "external astronomy research produced invalid evidence",
                details={
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1200],
                    "network_phase": "RESEARCH_ONLY",
                },
            )

        facts = list(fact_lock.facts)
        source_ids = list(fact_lock.source_ids)
        sources = list(fact_lock.sources)
        known_fact_ids = {item.fact_id for item in facts}
        known_source_ids = {item.source_id for item in sources}
        primary_required = (
            fact_lock.primary_source_verification_required_for_publication
        )

        for source in external.sources:
            if source.source_id in known_source_ids:
                continue
            sources.append(
                SourceReference(
                    source_id=source.source_id,
                    title=source.title,
                    provider=source.provider,
                    url=source.url,
                    license=source.license,
                    classification=source.classification,
                    role="external_research",
                    scientific_status=(
                        ScientificStatus.HECHO_VERIFICADO
                        if source.primary_source
                        else ScientificStatus.NO_VERIFICADO
                    ),
                )
            )
            known_source_ids.add(source.source_id)
            source_ids.append(source.source_id)
            if not source.primary_source:
                primary_required = True

        for datum in external.data:
            if datum.fact_id in known_fact_ids:
                return StageResult.blocked(
                    f"external research duplicates Fact Lock fact_id: {datum.fact_id}"
                )
            facts.append(
                GroundingFact(
                    fact_id=datum.fact_id,
                    label_es=datum.label_es,
                    value=datum.value,
                    unit=datum.unit,
                    scientific_status=(
                        ScientificStatus.HECHO_VERIFICADO
                        if datum.verified and not datum.primary_source_required
                        else ScientificStatus.NO_VERIFICADO
                    ),
                    source_ids=[datum.source_id],
                )
            )
            known_fact_ids.add(datum.fact_id)
            if datum.primary_source_required or not datum.verified:
                primary_required = True

        source_ids = list(dict.fromkeys(source_ids))
        if len(facts) > 256 or len(sources) > 128 or len(source_ids) > 128:
            return StageResult.blocked(
                "external research exceeds Fact Lock evidence limits"
            )

        enriched_payload = fact_lock.model_dump(mode="json")
        enriched_payload.update(
            {
                "facts": [item.model_dump(mode="json") for item in facts],
                "sources": [item.model_dump(mode="json") for item in sources],
                "source_ids": source_ids,
                "context_hash": _hash_fact_lock(facts, source_ids),
                "primary_source_verification_required_for_publication": (
                    primary_required
                ),
                "generated_at_utc": datetime.now(timezone.utc),
                "scope_note": (
                    fact_lock.scope_note
                    + " External research was sealed during RESEARCH only; "
                    "downstream stages receive immutable artifacts, not network "
                    "clients."
                )[:4000],
            }
        )
        enriched = FactLock.model_validate(enriched_payload)

        provenance = build_provenance_manifest(external)
        licenses = build_licenses_manifest(external)
        external_payload = external.as_dict()

        return StageResult.complete(
            StageArtifact(
                artifact_type="fact_lock",
                payload=enriched.model_dump(mode="json"),
                provenance={
                    "research_mode": enriched.research_mode,
                    "context_hash": enriched.context_hash,
                    "external_research": True,
                    "network_phase": "RESEARCH_ONLY",
                },
                metadata={
                    "fact_count": len(enriched.facts),
                    "source_count": len(enriched.sources),
                    "primary_source_verification_required_for_publication": (
                        primary_required
                    ),
                    "auto_publication": False,
                },
            ),
            StageArtifact(
                artifact_type="external_research_bundle",
                payload=external_payload,
                provenance={"network_phase": "RESEARCH_ONLY"},
                metadata={"auto_publication": False},
            ),
            StageArtifact(
                artifact_type="provenance_manifest",
                payload=provenance,
                provenance={"generated_from": "external_research_bundle"},
                metadata={"auto_publication": False},
            ),
            StageArtifact(
                artifact_type="licenses_manifest",
                payload=licenses,
                provenance={"generated_from": "external_research_bundle"},
                metadata={
                    "auto_publication": False,
                    "all_publication_eligible": licenses["all_publication_eligible"],
                },
            ),
            message="Astronomy Core Fact Lock enriched with sealed C3 research",
            details={
                "context_hash": enriched.context_hash,
                "network_phase": "RESEARCH_ONLY",
                "external_fact_count": len(external.data),
                "external_source_count": len(external.sources),
                "external_media_count": len(external.media),
                "auto_publication": False,
            },
        )

    def _resolve_external_quantities(self, bundle: ResearchBundle) -> None:
        quantities = []
        for datum in bundle.data:
            quantity = datum.canonical_quantity
            if quantity is None:
                continue
            if quantity.source.strip().casefold() != datum.source_id.strip().casefold():
                raise ScientificConflictError(
                    "SOURCE_PROVENANCE_MISMATCH",
                    (
                        f"canonical quantity source {quantity.source!r} does not match "
                        f"research datum source_id {datum.source_id!r}"
                    ),
                    subject=quantity.subject,
                    quantity=quantity.quantity,
                )
            quantities.append(quantity)
        self.conflict_resolver.resolve(quantities)


def build_c3_external_research_binding(
    runner: ExternalResearchRunner,
) -> StageBinding:
    return StageBinding(
        adapter_id="c3_astronomy_open_data_research_v01",
        handler=C3ExternalResearchFactLockAdapter(runner),
        resource_class=ResourceClass.LIGHT,
        producer_version="c3-astronomy-open-data-v0.1",
        invokes_network=True,
        invokes_llm=False,
        invokes_render=False,
        auto_publication=False,
    )


def compose_runners(
    runners: Iterable[ExternalResearchRunner],
) -> ExternalResearchRunner:
    items = tuple(runners)

    def run(context: ResearchContext, request: dict[str, Any]) -> ResearchBundle:
        context.require_research()
        return merge_bundles(runner(context, request) for runner in items)

    return run
