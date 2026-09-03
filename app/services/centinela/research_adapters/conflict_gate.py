from __future__ import annotations

import math
from app.services.centinela.orchestration import ResourceClass
from app.services.centinela.production_spine import StageBinding

from .conflict_resolver import ScientificConflictError, ScientificConflictResolver
from .contracts import ResearchBundle, ResearchDataError
from .spine_adapter import (
    C3ExternalResearchFactLockAdapter as _BaseC3ExternalResearchFactLockAdapter,
)
from .spine_adapter import ExternalResearchRunner


def _comparable_scalar(datum) -> bool:
    if datum.unit is None or not str(datum.unit).strip() or isinstance(datum.value, bool):
        return False
    try:
        value = float(datum.value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(value)


class C3ExternalResearchFactLockAdapter(_BaseC3ExternalResearchFactLockAdapter):
    """Fail-closed C3 gate requiring canonical metadata for comparable scalars."""

    def __init__(
        self,
        runner: ExternalResearchRunner,
        *,
        base_adapter=None,
        conflict_resolver=None,
    ) -> None:
        super().__init__(
            runner,
            base_adapter=base_adapter,
            conflict_resolver=conflict_resolver or ScientificConflictResolver(),
        )

    def _resolve_external_quantities(self, bundle: ResearchBundle) -> None:
        quantities = []
        for datum in bundle.data:
            quantity = datum.canonical_quantity
            if quantity is None:
                if _comparable_scalar(datum):
                    raise ScientificConflictError(
                        "MISSING_CANONICAL_QUANTITY",
                        (
                            f"comparable datum {datum.fact_id!r} reached Fact Lock "
                            "enrichment without CanonicalScientificQuantity"
                        ),
                        subject=datum.fact_id,
                        quantity=datum.label_es,
                    )
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

            if datum.unit is None or str(datum.unit).strip().casefold() != quantity.unit.strip().casefold():
                raise ScientificConflictError(
                    "RAW_CANONICAL_UNIT_MISMATCH",
                    "raw ResearchDatum unit does not match its canonical quantity unit",
                    subject=quantity.subject,
                    quantity=quantity.quantity,
                )

            try:
                raw_value = float(datum.value)
            except (TypeError, ValueError) as exc:
                raise ResearchDataError(
                    "canonical scientific datum must preserve a numeric raw value"
                ) from exc
            if not math.isfinite(raw_value) or raw_value != quantity.value:
                raise ScientificConflictError(
                    "RAW_CANONICAL_VALUE_MISMATCH",
                    "raw ResearchDatum value does not match its canonical quantity value",
                    subject=quantity.subject,
                    quantity=quantity.quantity,
                )
            quantities.append(quantity)

        self.conflict_resolver.resolve_conflicts(tuple(quantities))


def build_c3_external_research_binding(
    runner: ExternalResearchRunner,
) -> StageBinding:
    return StageBinding(
        adapter_id="c3_astronomy_open_data_research_v02_canonical_conflict_gate",
        handler=C3ExternalResearchFactLockAdapter(runner),
        resource_class=ResourceClass.LIGHT,
        producer_version="c3-astronomy-open-data-v0.2",
        invokes_network=True,
        invokes_llm=False,
        invokes_render=False,
        auto_publication=False,
    )
