from __future__ import annotations

from typing import Iterable

from .conflicts import (
    ScientificConflictError,
    ScientificConflictResolver as _BaseScientificConflictResolver,
    ScientificTolerance,
)
from .contracts import CanonicalScientificQuantity


class ScientificConflictResolver(_BaseScientificConflictResolver):
    """Explicit C3 conflict-gate API while retaining the proven resolver semantics."""

    def resolve_conflicts(
        self,
        quantities: Iterable[CanonicalScientificQuantity],
    ) -> tuple[CanonicalScientificQuantity, ...]:
        return super().resolve(quantities)


__all__ = [
    "ScientificConflictError",
    "ScientificConflictResolver",
    "ScientificTolerance",
]
