from __future__ import annotations

from datetime import UTC

from app.models.small_body import HorizonsQueryPlan, SmallBodyObserverRequest


HORIZONS_ENDPOINT = "https://ssd.jpl.nasa.gov/api/horizons.api"
HORIZONS_DOCUMENTATION = "https://ssd-api.jpl.nasa.gov/doc/horizons.html"
HORIZONS_SOURCE_ID = "jpl_horizons"


def _quote(value: str) -> str:
    return f"'{value}'"


def build_horizons_observer_query(request: SmallBodyObserverRequest) -> HorizonsQueryPlan:
    """Build a topocentric JPL Horizons observer-table request.

    The query is intentionally planned but not executed here. Network retrieval
    belongs to a source adapter that records the returned bytes and their hash.
    `target_command` is passed to Horizons as the authoritative object selector;
    this module never propagates a comet/asteroid orbit locally.
    """
    moment = request.observed_at.astimezone(UTC)
    site_height_km = request.observer.elevation_m / 1000.0
    site_coord = (
        f"{request.observer.longitude_deg:.8f},"
        f"{request.observer.latitude_deg:.8f},"
        f"{site_height_km:.6f}"
    )
    time_text = moment.strftime("%Y-%m-%d %H:%M:%S")

    params = {
        "format": "json",
        "COMMAND": _quote(request.target_command),
        "OBJ_DATA": _quote("YES"),
        "MAKE_EPHEM": _quote("YES"),
        "EPHEM_TYPE": _quote("OBSERVER"),
        "CENTER": _quote("coord@399"),
        "COORD_TYPE": _quote("GEODETIC"),
        "SITE_COORD": _quote(site_coord),
        "TLIST": _quote(time_text),
        "TLIST_TYPE": _quote("CAL"),
        "TIME_TYPE": _quote("UT"),
        "REF_SYSTEM": _quote("ICRF"),
        "ANG_FORMAT": _quote("DEG"),
        "APPARENT": _quote("AIRLESS"),
        "RANGE_UNITS": _quote("AU"),
        "CSV_FORMAT": _quote("YES"),
        "EXTRA_PREC": _quote("YES"),
        # Apparent RA/DEC, Az/El, airmass/extinction, magnitude/surface
        # brightness, illuminated fraction, angular diameter and sky motion.
        "QUANTITIES": _quote("2,4,8,9,10,13,47"),
    }

    return HorizonsQueryPlan(
        endpoint=HORIZONS_ENDPOINT,
        params=params,
        source_id=request.source_id,
        documentation_url=HORIZONS_DOCUMENTATION,
        source_note=(
            "JPL Horizons observer tables provide perspective-dependent observables; "
            "the returned result must be stored with retrieval time and SHA-256 before publication use."
        ),
    )
