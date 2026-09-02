from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

from .canonicalized import (
    MinorPlanetCenterAdapter,
    NasaExoplanetArchiveAdapter,
    SkyfieldDE440Adapter,
    SunPyLocalAdapter,
    WikidataAdapter,
)
from .contracts import ResearchBundle, ResearchContext, ResearchDataError
from .remote import (
    MastHstJwstAdapter,
    NasaOpenAdapter,
    WikimediaCommonsAdapter,
    build_esa_gaia_tap_adapter,
    build_eso_tap_adapter,
)
from .service import merge_bundles
from .transport import RequestsResearchTransport


DEFAULT_RESEARCH_HOSTS = frozenset(
    {
        "commons.wikimedia.org",
        "upload.wikimedia.org",
        "query.wikidata.org",
        "api.nasa.gov",
        "epic.gsfc.nasa.gov",
        "exoplanetarchive.ipac.caltech.edu",
        "data.minorplanetcenter.net",
        "mast.stsci.edu",
        "archive.eso.org",
        "gea.esac.esa.int",
    }
)


def _date(value: Any, field_name: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ResearchDataError(f"{field_name} must be YYYY-MM-DD") from exc


def _datetime(value: Any, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ResearchDataError(f"{field_name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ResearchDataError(f"{field_name} must include a timezone")
    return parsed


class C3AstronomyResearchRouter:
    """Explicit allow-list router for C3 RESEARCH-only astronomy adapters."""

    def __init__(
        self,
        transport: RequestsResearchTransport | None = None,
        *,
        nasa_api_key: str | None = None,
    ) -> None:
        self.transport = transport or RequestsResearchTransport(
            allowed_hosts=DEFAULT_RESEARCH_HOSTS
        )
        self.nasa_api_key = nasa_api_key or os.getenv("NASA_API_KEY") or "DEMO_KEY"

    def __call__(
        self,
        context: ResearchContext,
        request: dict[str, Any],
    ) -> ResearchBundle:
        context.require_research()
        if not isinstance(request, dict):
            raise ResearchDataError("external research request must be an object")

        bundles: list[ResearchBundle] = []
        known = {
            "wikimedia",
            "wikidata",
            "nasa_apod",
            "nasa_epic",
            "nasa_exoplanet",
            "mpc",
            "mast",
            "eso_tap",
            "esa_gaia_tap",
            "skyfield",
            "sunpy",
        }
        unknown = sorted(set(request) - known)
        if unknown:
            raise ResearchDataError(
                "unknown external research adapters: " + ", ".join(unknown)
            )

        if "wikimedia" in request:
            spec = request["wikimedia"]
            if not isinstance(spec, dict):
                raise ResearchDataError("wikimedia request must be an object")
            bundles.append(
                WikimediaCommonsAdapter(self.transport).search(
                    context,
                    str(spec.get("query") or ""),
                    limit=int(spec.get("limit", 6)),
                )
            )

        if "wikidata" in request:
            specs = request["wikidata"]
            if not isinstance(specs, list) or not specs:
                raise ResearchDataError("wikidata request must be a non-empty list")
            adapter = WikidataAdapter(self.transport)
            for spec in specs:
                if not isinstance(spec, dict):
                    raise ResearchDataError("each wikidata lookup must be an object")
                bundles.append(
                    adapter.property_value(
                        context,
                        entity_id=str(spec.get("entity_id") or ""),
                        property_id=str(spec.get("property_id") or ""),
                        label_es=str(spec.get("label_es") or ""),
                        unit=spec.get("unit"),
                    )
                )

        nasa = NasaOpenAdapter(self.transport, api_key=self.nasa_api_key)
        if "nasa_apod" in request:
            spec = request["nasa_apod"]
            if not isinstance(spec, dict):
                raise ResearchDataError("nasa_apod request must be an object")
            bundles.append(
                nasa.apod(context, day=_date(spec.get("date"), "nasa_apod.date"))
            )

        if "nasa_epic" in request:
            spec = request["nasa_epic"]
            if not isinstance(spec, dict):
                raise ResearchDataError("nasa_epic request must be an object")
            bundles.append(
                nasa.epic(context, day=_date(spec.get("date"), "nasa_epic.date"))
            )

        if "nasa_exoplanet" in request:
            spec = request["nasa_exoplanet"]
            if not isinstance(spec, dict):
                raise ResearchDataError("nasa_exoplanet request must be an object")
            bundles.append(
                NasaExoplanetArchiveAdapter(self.transport).planet(
                    context,
                    str(spec.get("planet_name") or ""),
                )
            )

        if "mpc" in request:
            spec = request["mpc"]
            if not isinstance(spec, dict):
                raise ResearchDataError("mpc request must be an object")
            designation = str(spec.get("designation") or "")
            adapter = MinorPlanetCenterAdapter(self.transport)
            bundles.append(adapter.observations(context, designation))
            if bool(spec.get("include_orbit")):
                bundles.append(adapter.orbit(context, designation))

        if "mast" in request:
            spec = request["mast"]
            if not isinstance(spec, dict):
                raise ResearchDataError("mast request must be an object")
            bundles.append(
                MastHstJwstAdapter(self.transport).search(
                    context,
                    mission=str(spec.get("mission") or ""),
                    target=str(spec.get("target") or ""),
                    limit=int(spec.get("limit", 10)),
                )
            )

        if "eso_tap" in request:
            spec = request["eso_tap"]
            if not isinstance(spec, dict):
                raise ResearchDataError("eso_tap request must be an object")
            bundles.append(
                build_eso_tap_adapter(self.transport).query_fixed(
                    context,
                    query=str(spec.get("query") or ""),
                    title=str(spec.get("title") or "ESO public archive query"),
                    maximum_rows=int(spec.get("maximum_rows", 20)),
                )
            )

        if "esa_gaia_tap" in request:
            spec = request["esa_gaia_tap"]
            if not isinstance(spec, dict):
                raise ResearchDataError("esa_gaia_tap request must be an object")
            bundles.append(
                build_esa_gaia_tap_adapter(self.transport).query_fixed(
                    context,
                    query=str(spec.get("query") or ""),
                    title=str(spec.get("title") or "ESA Gaia public archive query"),
                    maximum_rows=int(spec.get("maximum_rows", 20)),
                )
            )

        if "skyfield" in request:
            spec = request["skyfield"]
            if not isinstance(spec, dict):
                raise ResearchDataError("skyfield request must be an object")
            adapter = SkyfieldDE440Adapter(str(spec.get("bsp_path") or ""))
            moment = _datetime(spec.get("moment"), "skyfield.moment")
            if spec.get("body"):
                bundles.append(
                    adapter.position(
                        context,
                        body=str(spec["body"]),
                        moment=moment,
                    )
                )
            if bool(spec.get("moon_phase")):
                bundles.append(adapter.moon_phase(context, moment=moment))
            eclipse_end = spec.get("lunar_eclipses_until")
            if eclipse_end:
                bundles.append(
                    adapter.lunar_eclipses(
                        context,
                        start=moment,
                        end=_datetime(
                            eclipse_end,
                            "skyfield.lunar_eclipses_until",
                        ),
                    )
                )

        if "sunpy" in request:
            spec = request["sunpy"]
            if not isinstance(spec, dict):
                raise ResearchDataError("sunpy request must be an object")
            bundles.append(
                SunPyLocalAdapter().solar_orientation(
                    context,
                    moment=_datetime(spec.get("moment"), "sunpy.moment"),
                )
            )

        if not bundles:
            raise ResearchDataError("external research request selected no adapters")
        return merge_bundles(bundles)
