from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from app.services.centinela.licensing import LicenseDecision
from app.services.centinela.wikimedia import (
    assess_wikimedia_license,
    normalize_wikimedia_extmetadata,
)

from .contracts import (
    ResearchBundle,
    ResearchContext,
    ResearchDataError,
    ResearchDatum,
    ResearchMediaRecord,
    ResearchSource,
)
from .transport import RequestsResearchTransport


_QID = re.compile(r"^Q[1-9][0-9]*$")
_PID = re.compile(r"^P[1-9][0-9]*$")
_DESIGNATION = re.compile(r"^[A-Za-z0-9 ()+./_-]{1,80}$")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _safe_adql_literal(value: str, *, maximum: int = 160) -> str:
    text = _text(value)
    if not text or len(text) > maximum:
        raise ResearchDataError("invalid TAP literal")
    return text.replace("'", "''")


class WikimediaCommonsAdapter:
    ENDPOINT = "https://commons.wikimedia.org/w/api.php"

    def __init__(self, transport: RequestsResearchTransport) -> None:
        self.transport = transport

    def search(self, context: ResearchContext, query: str, *, limit: int = 6) -> ResearchBundle:
        context.require_research()
        term = _text(query)
        if not term or len(term) > 200:
            raise ResearchDataError("Wikimedia query is empty or too long")
        limit = max(1, min(int(limit), 10))
        payload = self.transport.get_json(
            context,
            self.ENDPOINT,
            params={
                "action": "query",
                "format": "json",
                "formatversion": 2,
                "generator": "search",
                "gsrnamespace": 6,
                "gsrsearch": term,
                "gsrlimit": limit,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata|mime|size",
                "iilimit": 1,
            },
        )
        pages = ((payload or {}).get("query") or {}).get("pages")
        if not isinstance(pages, list):
            raise ResearchDataError("Wikimedia response is missing query.pages")

        media: list[ResearchMediaRecord] = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            info_list = page.get("imageinfo")
            if not isinstance(info_list, list) or not info_list:
                continue
            info = info_list[0] if isinstance(info_list[0], dict) else {}
            normalized = normalize_wikimedia_extmetadata(info.get("extmetadata"))
            assessment = assess_wikimedia_license(normalized)
            eligible = assessment.decision in {
                LicenseDecision.ACCEPT,
                LicenseDecision.ACCEPT_WITH_ATTRIBUTION,
            }
            page_id = _text(page.get("pageid")) or _text(page.get("title"))
            title = _text(page.get("title")) or f"Wikimedia {page_id}"
            source_page = _text(info.get("descriptionurl"))
            file_url = _text(info.get("url"))
            creator = normalized.get("creator")
            creator_name = (
                _text(creator.get("name"))
                if isinstance(creator, dict)
                else ""
            )
            media.append(
                ResearchMediaRecord(
                    media_id=page_id,
                    provider="wikimedia",
                    title=title,
                    source_page=source_page,
                    file_url=file_url or None,
                    mime=_text(info.get("mime")) or None,
                    width=info.get("width") if isinstance(info.get("width"), int) else None,
                    height=info.get("height") if isinstance(info.get("height"), int) else None,
                    license=_text(normalized.get("license")) or None,
                    license_url=_text(normalized.get("license_url")) or None,
                    attribution=(
                        _text(normalized.get("attribution"))
                        or _text(normalized.get("credit"))
                        or creator_name
                        or None
                    ),
                    attribution_required=bool(normalized.get("attribution_required")),
                    rights_decision=assessment.decision.value,
                    publication_eligible=eligible,
                )
            )

        return ResearchBundle(
            sources=(
                ResearchSource(
                    source_id="wikimedia_commons_api",
                    title="Wikimedia Commons API",
                    provider="Wikimedia Commons",
                    url=self.ENDPOINT,
                    classification="PRIMARY_METADATA",
                    license="content license is per item",
                    primary_source=True,
                ),
            ),
            media=tuple(media),
        )


class WikidataAdapter:
    ENDPOINT = "https://query.wikidata.org/sparql"

    def __init__(self, transport: RequestsResearchTransport) -> None:
        self.transport = transport

    def property_value(
        self,
        context: ResearchContext,
        *,
        entity_id: str,
        property_id: str,
        label_es: str,
        unit: str | None = None,
    ) -> ResearchBundle:
        context.require_research()
        if not _QID.fullmatch(entity_id):
            raise ResearchDataError("invalid Wikidata entity id")
        if not _PID.fullmatch(property_id):
            raise ResearchDataError("invalid Wikidata property id")
        query = (
            "SELECT ?value WHERE { "
            f"wd:{entity_id} wdt:{property_id} ?value . "
            "} LIMIT 5"
        )
        payload = self.transport.get_json(
            context,
            self.ENDPOINT,
            params={"query": query, "format": "json"},
            headers={"Accept": "application/sparql-results+json"},
        )
        bindings = (((payload or {}).get("results") or {}).get("bindings"))
        if not isinstance(bindings, list) or len(bindings) != 1:
            raise ResearchDataError(
                "Wikidata lookup must resolve to exactly one deterministic value"
            )
        value = ((bindings[0].get("value") or {}).get("value"))
        if value in (None, ""):
            raise ResearchDataError("Wikidata value is empty")
        source_id = f"wikidata_{entity_id}_{property_id}".lower()
        return ResearchBundle(
            data=(
                ResearchDatum(
                    fact_id=source_id,
                    label_es=label_es,
                    value=value,
                    unit=unit,
                    source_id=source_id,
                    verified=False,
                    primary_source_required=True,
                ),
            ),
            sources=(
                ResearchSource(
                    source_id=source_id,
                    title=f"Wikidata {entity_id} / {property_id}",
                    provider="Wikidata",
                    url=self.ENDPOINT,
                    classification="SECONDARY_CORROBORATION",
                    license="CC0",
                    primary_source=False,
                ),
            ),
            warnings=(
                "Wikidata is corroborative metadata, not IAU naming authority; "
                "official naming claims still require an IAU primary source.",
            ),
        )


class NasaOpenAdapter:
    APOD_ENDPOINT = "https://api.nasa.gov/planetary/apod"
    EPIC_BASE = "https://epic.gsfc.nasa.gov"

    def __init__(
        self,
        transport: RequestsResearchTransport,
        *,
        api_key: str = "DEMO_KEY",
    ) -> None:
        self.transport = transport
        self.api_key = _text(api_key) or "DEMO_KEY"

    def apod(self, context: ResearchContext, *, day: date) -> ResearchBundle:
        payload = self.transport.get_json(
            context,
            self.APOD_ENDPOINT,
            params={"date": day.isoformat(), "api_key": self.api_key, "thumbs": "true"},
        )
        if not isinstance(payload, dict):
            raise ResearchDataError("NASA APOD response must be an object")
        title = _text(payload.get("title"))
        url = _text(payload.get("hdurl") or payload.get("url"))
        if not title or not url:
            raise ResearchDataError("NASA APOD response lacks title or media URL")
        copyright_notice = _text(payload.get("copyright"))
        # NASA documents that 'copyright' is returned when the image is not public domain.
        eligible = not bool(copyright_notice)
        media = ResearchMediaRecord(
            media_id=f"apod-{day.isoformat()}",
            provider="nasa_apod",
            title=title,
            source_page="https://apod.nasa.gov/apod/",
            file_url=url,
            license="NASA public-domain candidate" if eligible else None,
            attribution=copyright_notice or "NASA/APOD",
            attribution_required=bool(copyright_notice),
            rights_decision="accept" if eligible else "review",
            publication_eligible=eligible,
        )
        return ResearchBundle(
            sources=(
                ResearchSource(
                    source_id=f"nasa_apod_{day.isoformat()}",
                    title=f"NASA Astronomy Picture of the Day {day.isoformat()}",
                    provider="NASA",
                    url=self.APOD_ENDPOINT,
                    classification="PRIMARY_METADATA",
                    license="NASA media policy; verify per item",
                    primary_source=True,
                ),
            ),
            media=(media,),
        )

    def epic(self, context: ResearchContext, *, day: date) -> ResearchBundle:
        endpoint = f"{self.EPIC_BASE}/api/natural/date/{day.isoformat()}"
        payload = self.transport.get_json(context, endpoint)
        if not isinstance(payload, list):
            raise ResearchDataError("NASA EPIC response must be a list")
        media: list[ResearchMediaRecord] = []
        for item in payload[:12]:
            if not isinstance(item, dict):
                continue
            image = _text(item.get("image"))
            timestamp = _text(item.get("date"))
            if not image:
                continue
            y, m, d = day.strftime("%Y %m %d").split()
            file_url = f"{self.EPIC_BASE}/archive/natural/{y}/{m}/{d}/png/{image}.png"
            media.append(
                ResearchMediaRecord(
                    media_id=image,
                    provider="nasa_epic",
                    title=_text(item.get("caption")) or f"DSCOVR EPIC {timestamp}",
                    source_page=endpoint,
                    file_url=file_url,
                    license="NASA media policy; verify per item",
                    attribution="NASA/DSCOVR EPIC",
                    attribution_required=False,
                    rights_decision="review",
                    publication_eligible=False,
                )
            )
        return ResearchBundle(
            sources=(
                ResearchSource(
                    source_id=f"nasa_epic_{day.isoformat()}",
                    title=f"NASA DSCOVR EPIC {day.isoformat()}",
                    provider="NASA",
                    url=endpoint,
                    classification="PRIMARY_METADATA",
                    license="NASA media policy; verify per item",
                    primary_source=True,
                ),
            ),
            media=tuple(media),
            warnings=(
                "EPIC discovery is sealed in RESEARCH; individual media remain "
                "publication-ineligible until rights/provenance review.",
            ),
        )


class NasaExoplanetArchiveAdapter:
    ENDPOINT = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
    _FIELDS = (
        ("pl_name", "Nombre del planeta", None),
        ("hostname", "Estrella anfitriona", None),
        ("disc_year", "Año de descubrimiento", "year"),
        ("pl_rade", "Radio planetario", "Earth radii"),
        ("pl_bmasse", "Masa planetaria", "Earth masses"),
        ("pl_orbper", "Periodo orbital", "day"),
    )

    def __init__(self, transport: RequestsResearchTransport) -> None:
        self.transport = transport

    def planet(self, context: ResearchContext, planet_name: str) -> ResearchBundle:
        literal = _safe_adql_literal(planet_name)
        columns = ",".join(field for field, _, _ in self._FIELDS)
        query = (
            f"select {columns} from pscomppars "
            f"where pl_name='{literal}'"
        )
        payload = self.transport.get_json(
            context,
            self.ENDPOINT,
            params={"query": query, "format": "json"},
        )
        if not isinstance(payload, list) or len(payload) != 1:
            raise ResearchDataError(
                "NASA Exoplanet Archive lookup must resolve to exactly one row"
            )
        row = payload[0]
        if not isinstance(row, dict):
            raise ResearchDataError("NASA Exoplanet Archive row is invalid")
        source_id = "nasa_exoplanet_" + re.sub(
            r"[^a-z0-9]+", "_", literal.casefold()
        ).strip("_")
        data: list[ResearchDatum] = []
        for field, label, unit in self._FIELDS:
            value = row.get(field)
            if value is None:
                continue
            data.append(
                ResearchDatum(
                    fact_id=f"{source_id}:{field}",
                    label_es=label,
                    value=value,
                    unit=unit,
                    source_id=source_id,
                    verified=True,
                )
            )
        if not data:
            raise ResearchDataError("NASA Exoplanet Archive returned no usable fields")
        return ResearchBundle(
            data=tuple(data),
            sources=(
                ResearchSource(
                    source_id=source_id,
                    title=f"NASA Exoplanet Archive: {literal}",
                    provider="NASA Exoplanet Archive",
                    url=self.ENDPOINT,
                    classification="PRIMARY_ARCHIVE",
                    primary_source=True,
                ),
            ),
        )


class MinorPlanetCenterAdapter:
    ENDPOINT = "https://data.minorplanetcenter.net/api/get-obs"

    def __init__(self, transport: RequestsResearchTransport) -> None:
        self.transport = transport

    def observations(self, context: ResearchContext, designation: str) -> ResearchBundle:
        target = _text(designation)
        if not _DESIGNATION.fullmatch(target):
            raise ResearchDataError("invalid MPC designation")
        payload = self.transport.get_json(
            context,
            self.ENDPOINT,
            json_body={"desigs": [target], "output_format": ["ADES_DF"]},
        )
        if not isinstance(payload, list) or len(payload) != 1:
            raise ResearchDataError("MPC lookup must return exactly one object")
        observations = payload[0].get("ADES_DF") if isinstance(payload[0], dict) else None
        if not isinstance(observations, list):
            raise ResearchDataError("MPC response lacks ADES_DF observations")
        source_id = "mpc_" + re.sub(r"[^a-z0-9]+", "_", target.casefold()).strip("_")
        return ResearchBundle(
            data=(
                ResearchDatum(
                    fact_id=f"{source_id}:observation_count",
                    label_es="Número de observaciones MPC",
                    value=len(observations),
                    unit="observation",
                    source_id=source_id,
                    verified=True,
                ),
            ),
            sources=(
                ResearchSource(
                    source_id=source_id,
                    title=f"Minor Planet Center observations: {target}",
                    provider="Minor Planet Center",
                    url=self.ENDPOINT,
                    classification="PRIMARY_ARCHIVE",
                    primary_source=True,
                ),
            ),
        )


class MastHstJwstAdapter:
    """MAST CAOM discovery for public HST/JWST observations; rights remain review-gated."""

    ENDPOINT = "https://mast.stsci.edu/api/v0/invoke"

    def __init__(self, transport: RequestsResearchTransport) -> None:
        self.transport = transport

    def search(
        self,
        context: ResearchContext,
        *,
        mission: str,
        target: str,
        limit: int = 10,
    ) -> ResearchBundle:
        context.require_research()
        mission_key = _text(mission).upper()
        if mission_key not in {"HST", "JWST"}:
            raise ResearchDataError("MAST mission must be HST or JWST")
        target_text = _text(target)
        if not target_text or len(target_text) > 160:
            raise ResearchDataError("MAST target is empty or too long")
        limit = max(1, min(int(limit), 25))
        request_object = {
            "service": "Mast.Caom.Filtered",
            "params": {
                "columns": (
                    "obsid,obs_collection,obs_id,target_name,dataproduct_type,"
                    "s_ra,s_dec,t_min,t_max"
                ),
                "filters": [
                    {"paramName": "obs_collection", "values": [mission_key]},
                    {
                        "paramName": "target_name",
                        "values": [],
                        "freeText": target_text,
                    },
                ],
            },
            "format": "json",
            "pagesize": limit,
            "page": 1,
            "removenullcolumns": True,
        }
        payload = self.transport.get_json(
            context,
            self.ENDPOINT,
            params={"request": json.dumps(request_object, separators=(",", ":"))},
        )
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ResearchDataError("MAST response is missing data rows")
        source_id = f"mast_{mission_key.casefold()}_{re.sub(r'[^a-z0-9]+', '_', target_text.casefold()).strip('_')}"
        media = []
        for index, row in enumerate(rows[:limit]):
            if not isinstance(row, dict):
                continue
            obsid = _text(row.get("obsid") or row.get("obs_id") or index)
            media.append(
                ResearchMediaRecord(
                    media_id=obsid,
                    provider=f"mast_{mission_key.casefold()}",
                    title=_text(row.get("target_name") or row.get("obs_id") or target_text),
                    source_page=self.ENDPOINT,
                    rights_decision="review",
                    publication_eligible=False,
                )
            )
        return ResearchBundle(
            sources=(
                ResearchSource(
                    source_id=source_id,
                    title=f"MAST {mission_key}: {target_text}",
                    provider="MAST/STScI",
                    url=self.ENDPOINT,
                    classification="PRIMARY_ARCHIVE_METADATA",
                    primary_source=True,
                ),
            ),
            media=tuple(media),
            warnings=(
                "MAST HST/JWST observations are discovery metadata only; "
                "product dataRights and per-item reuse terms must be resolved "
                "before download/publication.",
            ),
        )

class TapArchiveAdapter:
    """Fixed-query TAP adapter for public ESO/ESA archive discovery."""

    def __init__(
        self,
        transport: RequestsResearchTransport,
        *,
        endpoint: str,
        provider: str,
        source_id: str,
    ) -> None:
        self.transport = transport
        self.endpoint = endpoint
        self.provider = provider
        self.source_id = source_id

    def query_fixed(
        self,
        context: ResearchContext,
        *,
        query: str,
        title: str,
        maximum_rows: int = 20,
    ) -> ResearchBundle:
        context.require_research()
        normalized = " ".join(_text(query).split())
        if (
            not normalized.lower().startswith("select ")
            or ";" in normalized
            or len(normalized) > 1600
        ):
            raise ResearchDataError("TAP adapter accepts one bounded SELECT only")
        if " top " not in f" {normalized.casefold()} ":
            raise ResearchDataError("TAP query must include an explicit TOP limit")
        if maximum_rows < 1 or maximum_rows > 50:
            raise ResearchDataError("invalid TAP row limit")
        payload = self.transport.get_json(
            context,
            self.endpoint,
            params={
                "REQUEST": "doQuery",
                "LANG": "ADQL",
                "FORMAT": "json",
                "QUERY": normalized,
            },
        )
        if not isinstance(payload, list):
            raise ResearchDataError(f"{self.provider} TAP response must be JSON rows")
        rows = payload[:maximum_rows]
        return ResearchBundle(
            sources=(
                ResearchSource(
                    source_id=self.source_id,
                    title=title,
                    provider=self.provider,
                    url=self.endpoint,
                    classification="PRIMARY_ARCHIVE_METADATA",
                    primary_source=True,
                ),
            ),
            media=tuple(
                ResearchMediaRecord(
                    media_id=f"{self.source_id}_{index}",
                    provider=self.provider.casefold().replace(" ", "_"),
                    title=_text(row.get("obs_title") or row.get("source_id") or title),
                    source_page=self.endpoint,
                    rights_decision="review",
                    publication_eligible=False,
                )
                for index, row in enumerate(rows)
                if isinstance(row, dict)
            ),
            warnings=(
                f"{self.provider} TAP results are discovery metadata only; "
                "per-item rights must be resolved before publication.",
            ),
        )


def build_eso_tap_adapter(transport: RequestsResearchTransport) -> TapArchiveAdapter:
    return TapArchiveAdapter(
        transport,
        endpoint="https://archive.eso.org/tap_obs/sync",
        provider="ESO",
        source_id="eso_tap_obs",
    )


def build_esa_gaia_tap_adapter(transport: RequestsResearchTransport) -> TapArchiveAdapter:
    return TapArchiveAdapter(
        transport,
        endpoint="https://gea.esac.esa.int/tap-server/tap/sync",
        provider="ESA Gaia Archive",
        source_id="esa_gaia_tap",
    )
