from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from itertools import combinations
from typing import Iterable, Mapping

from .contracts import CanonicalScientificQuantity, ResearchDataError


class ScientificConflictError(ResearchDataError):
    """Fail-closed blocker for incompatible multi-source scientific quantities."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        subject: str,
        quantity: str,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.subject = subject
        self.quantity = quantity


@dataclass(frozen=True, slots=True)
class ScientificTolerance:
    """Explicit comparison tolerance; no implicit universal tolerance is assumed."""

    absolute: float = 0.0
    relative: float = 0.0

    def __post_init__(self) -> None:
        for name in ("absolute", "relative"):
            raw = getattr(self, name)
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ResearchDataError(f"{name} tolerance must be a finite number")
            value = float(raw)
            if not math.isfinite(value) or value < 0:
                raise ResearchDataError(
                    f"{name} tolerance must be finite and non-negative"
                )
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class _UnitRule:
    canonical_unit: str
    scale: float


_UNIT_RULES: dict[str, _UnitRule] = {
    "m": _UnitRule("m", 1.0),
    "meter": _UnitRule("m", 1.0),
    "meters": _UnitRule("m", 1.0),
    "metre": _UnitRule("m", 1.0),
    "metres": _UnitRule("m", 1.0),
    "km": _UnitRule("m", 1000.0),
    "kilometer": _UnitRule("m", 1000.0),
    "kilometers": _UnitRule("m", 1000.0),
    "kilometre": _UnitRule("m", 1000.0),
    "kilometres": _UnitRule("m", 1000.0),
}


def _text_key(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _epoch_key(value: str) -> str:
    raw = value.strip()
    iso_candidate = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        parsed = datetime.fromisoformat(iso_candidate)
    except ValueError:
        return _text_key(raw)
    if parsed.tzinfo is None:
        return _text_key(raw)
    return parsed.astimezone(UTC).isoformat()


def _unit_rule(unit: str) -> _UnitRule:
    key = _text_key(unit)
    return _UNIT_RULES.get(key, _UnitRule(key, 1.0))


class ScientificConflictResolver:
    """
    Normalize and validate multi-source scientific quantities without choosing a winner.

    Non-identical values require an explicit subject/quantity tolerance. Semantic
    mismatches always block before external evidence can enrich the Fact Lock.
    """

    def __init__(
        self,
        tolerances: Mapping[tuple[str, str], ScientificTolerance] | None = None,
    ) -> None:
        self._tolerances = {
            (_text_key(subject), _text_key(quantity)): tolerance
            for (subject, quantity), tolerance in (tolerances or {}).items()
        }

    def normalize(
        self,
        quantity: CanonicalScientificQuantity,
    ) -> CanonicalScientificQuantity:
        rule = _unit_rule(quantity.unit)
        scale = rule.scale
        uncertainty = (
            None
            if quantity.uncertainty is None
            else quantity.uncertainty * abs(scale)
        )
        precision = quantity.display_precision
        if precision is not None and scale >= 1 and float(scale).is_integer():
            power = math.log10(scale)
            if power.is_integer():
                precision = max(0, precision - int(power))

        provenance = dict(quantity.provenance)
        provenance["canonicalization"] = {
            "original_unit": quantity.unit,
            "canonical_unit": rule.canonical_unit,
            "scale": scale,
        }
        return replace(
            quantity,
            unit=rule.canonical_unit,
            value=quantity.value * scale,
            uncertainty=uncertainty,
            display_precision=precision,
            provenance=provenance,
        )

    def resolve(
        self,
        quantities: Iterable[CanonicalScientificQuantity],
    ) -> tuple[CanonicalScientificQuantity, ...]:
        normalized = tuple(self.normalize(item) for item in quantities)
        groups: dict[
            tuple[str, str],
            list[CanonicalScientificQuantity],
        ] = {}
        for item in normalized:
            key = (_text_key(item.subject), _text_key(item.quantity))
            groups.setdefault(key, []).append(item)

        for key, group in groups.items():
            if len(group) < 2:
                continue
            for left, right in combinations(group, 2):
                self._validate_semantics(left, right)
                self._validate_values(key, left, right)
        return normalized

    def _validate_semantics(
        self,
        left: CanonicalScientificQuantity,
        right: CanonicalScientificQuantity,
    ) -> None:
        checks = (
            ("UNIT_INCOMPATIBLE", "unit", _text_key(left.unit), _text_key(right.unit)),
            (
                "EPOCH_INCOMPATIBLE",
                "epoch",
                _epoch_key(left.epoch),
                _epoch_key(right.epoch),
            ),
            (
                "OBSERVER_INCOMPATIBLE",
                "observer",
                _text_key(left.observer),
                _text_key(right.observer),
            ),
            (
                "FRAME_INCOMPATIBLE",
                "frame",
                _text_key(left.frame),
                _text_key(right.frame),
            ),
        )
        for code, field, left_value, right_value in checks:
            if left_value != right_value:
                raise ScientificConflictError(
                    code,
                    (
                        f"{field} mismatch between sources {left.source!r} "
                        f"and {right.source!r}"
                    ),
                    subject=left.subject,
                    quantity=left.quantity,
                )

    def _validate_values(
        self,
        key: tuple[str, str],
        left: CanonicalScientificQuantity,
        right: CanonicalScientificQuantity,
    ) -> None:
        difference = abs(left.value - right.value)
        if difference == 0.0:
            return

        tolerance = self._tolerances.get(key)
        if tolerance is None:
            raise ScientificConflictError(
                "MISSING_SCIENTIFIC_TOLERANCE",
                (
                    "non-identical multi-source values require an explicit "
                    "scientific tolerance"
                ),
                subject=left.subject,
                quantity=left.quantity,
            )

        threshold = max(
            tolerance.absolute,
            tolerance.relative * max(abs(left.value), abs(right.value)),
        )
        if difference > threshold:
            raise ScientificConflictError(
                "MATERIAL_DISCREPANCY",
                (
                    f"sources {left.source!r} and {right.source!r} differ by "
                    f"{difference:g} {left.unit}; accepted threshold is "
                    f"{threshold:g} {left.unit}"
                ),
                subject=left.subject,
                quantity=left.quantity,
            )
