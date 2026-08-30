from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from numbers import Real
from typing import Any, Iterable

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import GroundingFact

from .models import FactLock, FinalScriptCandidate, ScriptClaim


class FactLockQuantitativeError(ValueError):
    """Raised when generated quantitative text escapes the cited Fact Lock."""


_NUMBER_RE = re.compile(
    r"(?<![\w])[-+]?(?:\d{1,3}(?:[.,\s\u00a0\u202f]\d{3})+|\d+)"
    r"(?:[.,]\d+)?(?:[eE][-+]?\d+)?"
)

_UNIT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("percent", re.compile(r"%|\bpor\s+ciento\b", re.IGNORECASE)),
    (
        "arcsec",
        re.compile(r"\barcsec\b|\bsegundos?\s+de\s+arco\b", re.IGNORECASE),
    ),
    (
        "arcmin",
        re.compile(r"\barcmin\b|\bminutos?\s+de\s+arco\b", re.IGNORECASE),
    ),
    (
        "km",
        re.compile(r"\bkm\b|\bkil[oó]metros?\b", re.IGNORECASE),
    ),
    (
        "m",
        re.compile(r"\bmetros?\b|(?<![\w])m(?![\w])", re.IGNORECASE),
    ),
    (
        "deg",
        re.compile(r"[°º]|\bdeg\b|\bgrados?\b", re.IGNORECASE),
    ),
    (
        "mag",
        re.compile(r"\bmag\b|\bmagnitud(?:\s+visual)?\b", re.IGNORECASE),
    ),
    (
        "au",
        re.compile(r"\bau\b|\bua\b|\bunidades?\s+astron[oó]micas?\b", re.IGNORECASE),
    ),
)

_UNIT_ALIASES = {
    "km": "km",
    "kilometer": "km",
    "kilometre": "km",
    "m": "m",
    "meter": "m",
    "metre": "m",
    "deg": "deg",
    "degree": "deg",
    "degrees": "deg",
    "mag": "mag",
    "magnitude": "mag",
    "fraction": "fraction",
    "%": "percent",
    "percent": "percent",
    "arcmin": "arcmin",
    "arcsec": "arcsec",
    "au": "au",
    "ua": "au",
}


@dataclass(frozen=True)
class _Quantity:
    value: float
    unit: str | None


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(
        ch for ch in normalized if not unicodedata.combining(ch)
    ).casefold()


def _canonical_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    folded = _fold(unit).strip()
    return _UNIT_ALIASES.get(folded, folded or None)


def _number_candidates(token: str) -> tuple[float, ...]:
    raw = (
        token.strip()
        .replace("\u00a0", "")
        .replace("\u202f", "")
        .replace(" ", "")
    )
    if not raw:
        return ()

    result: list[float] = []

    def add(candidate: str) -> None:
        try:
            value = float(candidate)
        except ValueError:
            return
        if math.isfinite(value) and value not in result:
            result.append(value)

    if "e" in raw.casefold():
        add(raw.replace(",", "."))
        return tuple(result)

    dot_count = raw.count(".")
    comma_count = raw.count(",")

    if dot_count and comma_count:
        last_dot = raw.rfind(".")
        last_comma = raw.rfind(",")
        decimal = "." if last_dot > last_comma else ","
        thousands = "," if decimal == "." else "."
        add(raw.replace(thousands, "").replace(decimal, "."))
        return tuple(result)

    separator = "." if dot_count else "," if comma_count else None
    if separator is None:
        add(raw)
        return tuple(result)

    count = raw.count(separator)
    if count == 1:
        add(raw.replace(separator, "."))
        head, tail = raw.rsplit(separator, 1)
        if len(tail) == 3 and head.lstrip("+-").isdigit():
            add(raw.replace(separator, ""))
    else:
        pieces = raw.split(separator)
        if all(piece.lstrip("+-").isdigit() for piece in pieces):
            add("".join(pieces))

    return tuple(result)


def _extract_string_quantities(value: str) -> list[_Quantity]:
    result: list[_Quantity] = []
    for match in _NUMBER_RE.finditer(value):
        for candidate in _number_candidates(match.group(0)):
            result.append(_Quantity(candidate, None))
    return result


def _fact_quantities(fact: GroundingFact) -> list[_Quantity]:
    unit = _canonical_unit(fact.unit)
    value = fact.value

    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, Real):
        number = float(value)
        return [_Quantity(number, unit)] if math.isfinite(number) else []
    if isinstance(value, str):
        return _extract_string_quantities(value)
    if isinstance(value, dict):
        result: list[_Quantity] = []
        for nested in value.values():
            result.extend(_value_quantities(nested))
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for nested in value:
            result.extend(_value_quantities(nested))
        return result
    return []


def _value_quantities(value: Any) -> list[_Quantity]:
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, Real):
        number = float(value)
        return [_Quantity(number, None)] if math.isfinite(number) else []
    if isinstance(value, str):
        return _extract_string_quantities(value)
    if isinstance(value, dict):
        result: list[_Quantity] = []
        for nested in value.values():
            result.extend(_value_quantities(nested))
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for nested in value:
            result.extend(_value_quantities(nested))
        return result
    return []


def _nearest_explicit_unit(text: str, start: int, end: int) -> str | None:
    left = max(0, start - 24)
    right = min(len(text), end + 32)
    window = text[left:right]
    best: tuple[int, str] | None = None

    for unit, pattern in _UNIT_PATTERNS:
        for match in pattern.finditer(window):
            unit_start = left + match.start()
            unit_end = left + match.end()
            if unit_end <= start:
                distance = start - unit_end
            elif unit_start >= end:
                distance = unit_start - end
            else:
                distance = 0
            if best is None or distance < best[0]:
                best = (distance, unit)

    if best is None or best[0] > 16:
        return None
    return best[1]


def _multiplier_after(text: str, end: int) -> float:
    tail = _fold(text[end : end + 28]).lstrip()
    if re.match(r"^mil(?:\b|\s)", tail):
        if re.match(r"^mil\s+millones?\b", tail):
            return 1_000_000_000.0
        return 1_000.0
    if re.match(r"^mill[oó]n(?:es)?\b", tail):
        return 1_000_000.0
    return 1.0


def _expected_in_text_unit(quantity: _Quantity, text_unit: str | None) -> float | None:
    source_unit = _canonical_unit(quantity.unit)
    if text_unit is None:
        return quantity.value
    if source_unit == text_unit:
        return quantity.value
    if source_unit == "fraction" and text_unit == "percent":
        return quantity.value * 100.0
    if source_unit == "km" and text_unit == "m":
        return quantity.value * 1000.0
    if source_unit == "m" and text_unit == "km":
        return quantity.value / 1000.0
    if source_unit == "deg" and text_unit == "arcmin":
        return quantity.value * 60.0
    if source_unit == "deg" and text_unit == "arcsec":
        return quantity.value * 3600.0
    return None


def _equivalent(actual: float, expected: float, *, strict: bool) -> bool:
    scale = max(abs(expected), 1.0)
    relative_limit = 0.01 if strict else 0.02
    absolute_limit = 0.01 if scale <= 1.0 else 0.05
    return abs(actual - expected) <= max(
        absolute_limit,
        scale * relative_limit,
    )


def _validate_numeric_text(
    text: str,
    facts: Iterable[GroundingFact],
    *,
    surface: str,
    strict: bool,
) -> None:
    matches = list(_NUMBER_RE.finditer(text))
    if not matches:
        return

    quantities: list[_Quantity] = []
    fact_ids: list[str] = []
    for fact in facts:
        fact_ids.append(fact.fact_id)
        quantities.extend(_fact_quantities(fact))

    if not quantities:
        raise FactLockQuantitativeError(
            f"{surface} contains numeric text without quantitative Fact Lock support; "
            f"fact_ids={fact_ids}"
        )

    for match in matches:
        token = match.group(0)
        candidates = _number_candidates(token)
        multiplier = _multiplier_after(text, match.end())
        text_unit = _nearest_explicit_unit(text, match.start(), match.end())
        accepted = False

        for candidate in candidates:
            actual = candidate * multiplier
            for quantity in quantities:
                expected = _expected_in_text_unit(quantity, text_unit)
                if expected is None:
                    continue
                if _equivalent(actual, expected, strict=strict):
                    accepted = True
                    break
            if accepted:
                break

        if not accepted:
            raise FactLockQuantitativeError(
                f"{surface} contains unsupported quantitative token {token!r}; "
                f"unit={text_unit or 'unspecified'}; fact_ids={fact_ids}"
            )


def validate_quantitative_claims(
    claims: list[ScriptClaim],
    fact_lock: FactLock,
) -> None:
    by_id = {fact.fact_id: fact for fact in fact_lock.facts}
    for index, claim in enumerate(claims):
        facts = [by_id[fact_id] for fact_id in claim.fact_ids if fact_id in by_id]
        _validate_numeric_text(
            claim.statement,
            facts,
            surface=f"claim {index}",
            strict=claim.scientific_status == ScientificStatus.HECHO_VERIFICADO,
        )


def validate_final_candidate_quantities(
    candidate: FinalScriptCandidate,
    fact_lock: FactLock,
) -> None:
    by_id = {fact.fact_id: fact for fact in fact_lock.facts}
    all_facts = [
        by_id[fact_id]
        for claim in candidate.claims
        for fact_id in claim.fact_ids
        if fact_id in by_id
    ]

    for surface, text in (
        ("final hook", candidate.hook),
        ("final narration", candidate.narration),
        ("social_30s", candidate.social_30s),
        ("social_15s", candidate.social_15s),
        ("closing_line", candidate.closing_line),
    ):
        _validate_numeric_text(
            text,
            all_facts,
            surface=surface,
            strict=False,
        )

    for segment_index, segment in enumerate(candidate.segments):
        segment_facts: list[GroundingFact] = []
        for claim_index in segment.claim_indices:
            if claim_index < 0 or claim_index >= len(candidate.claims):
                continue
            claim = candidate.claims[claim_index]
            segment_facts.extend(
                by_id[fact_id]
                for fact_id in claim.fact_ids
                if fact_id in by_id
            )
        _validate_numeric_text(
            segment.narration,
            segment_facts,
            surface=f"segment {segment_index} narration",
            strict=False,
        )
