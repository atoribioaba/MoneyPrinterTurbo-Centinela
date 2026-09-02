from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .contracts import (
    CanonicalScientificQuantity,
    ResearchBundle,
    ResearchDataError,
    ResearchDatum,
)
from .local import SkyfieldDE440Adapter as _SkyfieldDE440Adapter
from .local import SunPyLocalAdapter as _SunPyLocalAdapter
from .remote import MinorPlanetCenterAdapter as _MinorPlanetCenterAdapter
from .remote import NasaExoplanetArchiveAdapter as _NasaExoplanetArchiveAdapter
from .remote import WikidataAdapter as _WikidataAdapter


def _finite_number(value: Any) -> float:
    if isinstance(value, bool):
        raise ResearchDataError("boolean values are not scientific scalar quantities")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ResearchDataError("scientific scalar cannot be normalized to float") from exc
    if not math.isfinite(number):
        raise ResearchDataError("scientific scalar must be finite")
    return number


def _display_precision(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    exponent = decimal.as_tuple().exponent
    return max(0, -int(exponent))


def _canonicalize(
    datum: ResearchDatum,
    *,
    subject: str,
    quantity: str,
    epoch: str,
    observer: str,
    frame: str,
    uncertainty: float | None = None,
    unit: str | None = None,
    provenance: dict[str, Any] | None = None,
) -> ResearchDatum:
    resolved_unit = str(unit if unit is not None else datum.unit or "").strip()
    if not resolved_unit:
        raise ResearchDataError(
            f"canonical mapping for {datum.fact_id} requires an explicit unit"
        )
    number = _finite_number(datum.value)
    canonical = CanonicalScientificQuantity(
        subject=str(subject).strip(),
        quantity=str(quantity).strip(),
        epoch=str(epoch).strip(),
        observer=str(observer).strip(),
        unit=resolved_unit,
        frame=str(frame).strip(),
        value=number,
        uncertainty=uncertainty,
        display_precision=_display_precision(datum.value),
        source=datum.source_id,
        provenance={
            "raw_fact_id": datum.fact_id,
            "raw_value": datum.value,
            "raw_unit": datum.unit,
            "source_id": datum.source_id,
            "auto_publication": False,
            **dict(provenance or {}),
        },
    )
    return replace(
        datum,
        unit=resolved_unit,
        canonical_quantity=canonical,
    )


def _suffix(datum: ResearchDatum) -> str:
    marker = datum.source_id + ":"
    return datum.fact_id[len(marker) :] if datum.fact_id.startswith(marker) else datum.fact_id


_EXOPLANET_QUANTITIES = {
    "disc_year": "discovery_year",
    "pl_rade": "planet_radius",
    "pl_radeerr1": "planet_radius_uncertainty_upper",
    "pl_radeerr2": "planet_radius_uncertainty_lower",
    "pl_bmasse": "planet_mass",
    "pl_bmasseerr1": "planet_mass_uncertainty_upper",
    "pl_bmasseerr2": "planet_mass_uncertainty_lower",
    "pl_orbper": "orbital_period",
    "pl_orbpererr1": "orbital_period_uncertainty_upper",
    "pl_orbpererr2": "orbital_period_uncertainty_lower",
}

_EXOPLANET_UNCERTAINTY_FIELDS = {
    "pl_rade": ("pl_radeerr1", "pl_radeerr2"),
    "pl_bmasse": ("pl_bmasseerr1", "pl_bmasseerr2"),
    "pl_orbper": ("pl_orbpererr1", "pl_orbpererr2"),
}

_EXOPLANET_REFERENCE_FIELDS = {
    "pl_rade": "pl_rade_reflink",
    "pl_bmasse": "pl_bmasse_reflink",
    "pl_orbper": "pl_orbper_reflink",
}


class NasaExoplanetArchiveAdapter(_NasaExoplanetArchiveAdapter):
    """NASA Exoplanet Archive adapter with systematic canonical scalar mapping."""

    def planet(self, context, planet_name: str) -> ResearchBundle:
        bundle = super().planet(context, planet_name)
        by_field = {_suffix(item): item for item in bundle.data}
        subject = str(planet_name).strip()
        mapped: list[ResearchDatum] = []
        for datum in bundle.data:
            field = _suffix(datum)
            quantity = _EXOPLANET_QUANTITIES.get(field)
            if quantity is None or datum.unit is None:
                mapped.append(datum)
                continue
            uncertainty = None
            error_fields = _EXOPLANET_UNCERTAINTY_FIELDS.get(field)
            if error_fields:
                candidates = []
                for error_field in error_fields:
                    error_datum = by_field.get(error_field)
                    if error_datum is not None:
                        candidates.append(abs(_finite_number(error_datum.value)))
                if candidates:
                    uncertainty = max(candidates)
            mapped.append(
                _canonicalize(
                    datum,
                    subject=subject,
                    quantity=quantity,
                    epoch="catalog:NASA_EXOPLANET_ARCHIVE_PSCOMPPARS",
                    observer="not_applicable:catalog",
                    frame="NASA_EXOPLANET_ARCHIVE_PSCOMPPARS",
                    uncertainty=uncertainty,
                    provenance={
                        "provider": "NASA Exoplanet Archive",
                        "raw_field": field,
                        "reference": (
                            None
                            if _EXOPLANET_REFERENCE_FIELDS.get(field) is None
                            else getattr(
                                by_field.get(_EXOPLANET_REFERENCE_FIELDS[field]),
                                "value",
                                None,
                            )
                        ),
                        "record_semantics": "pscomppars composite parameter record",
                    },
                )
            )
        return replace(
            bundle,
            data=tuple(mapped),
            metadata={
                **bundle.metadata,
                "canonical_mapping": "systematic-v0.2",
                "auto_publication": False,
            },
        )


_MPC_QUANTITIES = {
    "a": ("semi_major_axis", "AU"),
    "e": ("eccentricity", "1"),
    "i": ("inclination", "deg"),
    "node": ("longitude_ascending_node", "deg"),
    "argperi": ("argument_perihelion", "deg"),
    "meananomaly": ("mean_anomaly", "deg"),
    "q": ("perihelion_distance", "AU"),
}


class MinorPlanetCenterAdapter(_MinorPlanetCenterAdapter):
    """MPC adapter that seals comparable counts/orbital scalars canonically."""

    def observations(self, context, designation: str) -> ResearchBundle:
        bundle = super().observations(context, designation)
        mapped = tuple(
            _canonicalize(
                datum,
                subject=str(designation).strip(),
                quantity="observation_count",
                epoch=f"source-record:{datum.source_id}",
                observer="global:MPC_ADES_archive",
                frame="MPC_ADES",
                provenance={
                    "provider": "Minor Planet Center",
                    "designation": str(designation).strip(),
                    "epoch_basis": "source record; observation timestamps are not exposed by v0.1 datum",
                },
            )
            if datum.unit is not None
            else datum
            for datum in bundle.data
        )
        return replace(bundle, data=mapped)

    def orbit(self, context, designation: str) -> ResearchBundle:
        bundle = super().orbit(context, designation)
        by_suffix = {_suffix(item): item for item in bundle.data}
        mapped: list[ResearchDatum] = []
        for datum in bundle.data:
            suffix = _suffix(datum)
            is_uncertainty = suffix.endswith(":uncertainty")
            field = suffix.removesuffix(":uncertainty")
            spec = _MPC_QUANTITIES.get(field)
            if spec is None:
                mapped.append(datum)
                continue
            quantity_name, unit = spec
            uncertainty = None
            if not is_uncertainty:
                uncertainty_datum = by_suffix.get(f"{field}:uncertainty")
                if uncertainty_datum is not None:
                    uncertainty = abs(_finite_number(uncertainty_datum.value))
            mapped.append(
                _canonicalize(
                    datum,
                    subject=str(designation).strip(),
                    quantity=(
                        f"{quantity_name}_uncertainty"
                        if is_uncertainty
                        else quantity_name
                    ),
                    epoch=f"source-record:{datum.source_id}",
                    observer="heliocentric:orbit_solution",
                    frame="MPC_OSCULATING_ORBIT_ELEMENTS",
                    uncertainty=uncertainty,
                    unit=unit,
                    provenance={
                        "provider": "Minor Planet Center",
                        "designation": str(designation).strip(),
                        "raw_orbit_field": field,
                        "epoch_basis": "source record; explicit solution epoch is not exposed by v0.1 datum",
                    },
                )
            )
        return replace(bundle, data=tuple(mapped))


class SkyfieldDE440Adapter(_SkyfieldDE440Adapter):
    """Offline Skyfield/JPL adapter with canonical ephemeris quantities."""

    def position(self, context, *, body: str, moment: datetime) -> ResearchBundle:
        bundle = super().position(context, body=body, moment=moment)
        epoch = moment.astimezone(UTC).isoformat()
        mapping = {
            "ra_hours": ("right_ascension", "ICRF_J2000"),
            "dec_deg": ("declination", "ICRF_J2000"),
            "distance_au": ("geocentric_distance", "ICRF_J2000"),
        }
        mapped: list[ResearchDatum] = []
        for datum in bundle.data:
            field = datum.fact_id.rsplit(":", 1)[-1]
            spec = mapping.get(field)
            if spec is None:
                mapped.append(datum)
                continue
            quantity_name, frame = spec
            mapped.append(
                _canonicalize(
                    datum,
                    subject=str(body).strip().casefold(),
                    quantity=quantity_name,
                    epoch=epoch,
                    observer="earth-geocenter",
                    frame=frame,
                    provenance={
                        "provider": "Skyfield/JPL",
                        "kernel": self.bsp_path.name,
                        "moment_utc": epoch,
                        "network_required": False,
                    },
                )
            )
        return replace(bundle, data=tuple(mapped))

    def moon_phase(self, context, *, moment: datetime) -> ResearchBundle:
        bundle = super().moon_phase(context, moment=moment)
        epoch = moment.astimezone(UTC).isoformat()
        mapped = tuple(
            _canonicalize(
                datum,
                subject="moon",
                quantity="phase_angle",
                epoch=epoch,
                observer="earth-geocenter",
                frame="GEOCENTRIC_ECLIPTIC",
                provenance={
                    "provider": "Skyfield/JPL",
                    "kernel": self.bsp_path.name,
                    "moment_utc": epoch,
                    "network_required": False,
                },
            )
            if datum.unit is not None
            else datum
            for datum in bundle.data
        )
        return replace(bundle, data=mapped)


class SunPyLocalAdapter(_SunPyLocalAdapter):
    """Local SunPy geometry with canonical solar-orientation scalars."""

    def solar_orientation(self, context, *, moment: datetime) -> ResearchBundle:
        bundle = super().solar_orientation(context, moment=moment)
        epoch = moment.astimezone(UTC).isoformat()
        mapping = {
            "sunpy:sun:b0_deg": (
                "heliographic_latitude_disk_center",
                "HELIOGRAPHIC_STONYHURST",
            ),
            "sunpy:sun:l0_deg": (
                "carrington_longitude_disk_center",
                "HELIOGRAPHIC_CARRINGTON",
            ),
        }
        mapped = tuple(
            _canonicalize(
                datum,
                subject="sun",
                quantity=mapping[datum.fact_id][0],
                epoch=epoch,
                observer="earth-observer",
                frame=mapping[datum.fact_id][1],
                provenance={
                    "provider": "SunPy",
                    "moment_utc": epoch,
                    "network_required": False,
                },
            )
            if datum.fact_id in mapping
            else datum
            for datum in bundle.data
        )
        return replace(bundle, data=mapped)


class WikidataAdapter(_WikidataAdapter):
    """Secondary corroboration; numeric unit-bearing values are still canonicalized."""

    def property_value(
        self,
        context,
        *,
        entity_id: str,
        property_id: str,
        label_es: str,
        unit: str | None = None,
    ) -> ResearchBundle:
        bundle = super().property_value(
            context,
            entity_id=entity_id,
            property_id=property_id,
            label_es=label_es,
            unit=unit,
        )
        if unit is None:
            return bundle
        mapped: list[ResearchDatum] = []
        for datum in bundle.data:
            try:
                _finite_number(datum.value)
            except ResearchDataError:
                mapped.append(datum)
                continue
            mapped.append(
                _canonicalize(
                    datum,
                    subject=entity_id,
                    quantity=property_id,
                    epoch="wikidata:current-statement",
                    observer="not_applicable:knowledge_graph",
                    frame="WIKIDATA_STATEMENT",
                    provenance={
                        "provider": "Wikidata",
                        "secondary_corroboration": True,
                    },
                )
            )
        return replace(bundle, data=tuple(mapped))
