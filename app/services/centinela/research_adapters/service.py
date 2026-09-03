from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from app.services.centinela.provenance import sanitize_provenance

from .contracts import ResearchBundle, ResearchContext, ResearchDataError, ResearchMediaRecord
from .transport import RequestsResearchTransport


def _canonical_json(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def merge_bundles(bundles: Iterable[ResearchBundle]) -> ResearchBundle:
    data = []
    sources = []
    media = []
    warnings = []
    metadata = {}
    source_ids: set[str] = set()
    fact_ids: set[str] = set()
    media_ids: set[tuple[str, str]] = set()

    for bundle in bundles:
        for source in bundle.sources:
            if source.source_id in source_ids:
                continue
            source_ids.add(source.source_id)
            sources.append(source)
        for datum in bundle.data:
            if datum.fact_id in fact_ids:
                raise ValueError(f"duplicate research fact_id: {datum.fact_id}")
            fact_ids.add(datum.fact_id)
            data.append(datum)
        for item in bundle.media:
            key = (item.provider, item.media_id)
            if key in media_ids:
                continue
            media_ids.add(key)
            media.append(item)
        warnings.extend(bundle.warnings)
        metadata.update(bundle.metadata)

    return ResearchBundle(
        data=tuple(data),
        sources=tuple(sources),
        media=tuple(media),
        warnings=tuple(dict.fromkeys(warnings)),
        metadata=metadata,
    )


def build_provenance_manifest(bundle: ResearchBundle) -> dict:
    records = []
    for item in sorted(bundle.media, key=lambda value: (value.provider, value.media_id)):
        record = sanitize_provenance(
            item.provenance_dict(),
            provider=item.provider,
            local_path=item.local_file or "",
        )
        record["publication_eligible"] = bool(item.publication_eligible)
        records.append(record)
    payload = {
        "version": "centinela-research-provenance-v0.1",
        "records": records,
        "auto_publication": False,
    }
    payload["sha256"] = hashlib.sha256(_canonical_json(payload)).hexdigest()
    return payload


def build_licenses_manifest(bundle: ResearchBundle) -> dict:
    records = [
        item.license_dict()
        for item in sorted(bundle.media, key=lambda value: (value.provider, value.media_id))
    ]
    payload = {
        "version": "centinela-research-licenses-v0.1",
        "records": records,
        "all_publication_eligible": bool(records)
        and all(item["publication_eligible"] for item in records),
        "auto_publication": False,
    }
    payload["sha256"] = hashlib.sha256(_canonical_json(payload)).hexdigest()
    return payload


def with_download(
    item: ResearchMediaRecord,
    *,
    local_file: str | Path,
    sha256: str,
) -> ResearchMediaRecord:
    return replace(
        item,
        local_file=Path(local_file).name,
        sha256=sha256.lower(),
    )


_PROVIDER_SIDECAR = {
    "wikimedia": "WIKIMEDIA",
    "nasa_apod": "NASA",
    "nasa_epic": "NASA",
    "nasa": "NASA",
    "esa": "ESA",
    "esa_gaia_archive": "ESA",
    "eso": "OTHER",
}


def write_astromedia_sidecar(
    item: ResearchMediaRecord,
    media_path: str | Path,
) -> Path:
    """
    Persist only whitelisted per-item rights/provenance next to a RESEARCH-fetched asset.

    AstroMedia already discovers ``<filename>.astromedia.json``. Unknown/ambiguous
    rights remain UNVERIFIED, so MaterialSelector cannot silently treat them as
    publication-ready.
    """
    path = Path(media_path)
    if not path.is_file():
        raise ResearchDataError("AstroMedia sidecar requires an existing local media file")

    verified = bool(item.publication_eligible and item.license)
    payload = {
        "title": item.title,
        "description": "Fetched and sealed during Centinela RESEARCH.",
        "tags": [],
        "astronomy_objects": [],
        "ownership_confirmed": False,
        "provider": _PROVIDER_SIDECAR.get(item.provider, "OTHER"),
        "provider_asset_id": item.media_id,
        "author_name": None,
        "license_name": item.license if verified else None,
        "license_url": item.license_url,
        "rights_status": "VERIFIED_LICENSE" if verified else "UNVERIFIED",
        "attribution": item.attribution,
        "attribution_required": bool(item.attribution_required),
        "source_url": item.source_page,
    }
    sidecar = path.with_name(path.name + ".astromedia.json")
    temporary = sidecar.with_name(sidecar.name + ".part")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, sidecar)
    return sidecar


def download_and_seal_media(
    transport: RequestsResearchTransport,
    context: ResearchContext,
    item: ResearchMediaRecord,
    destination: str | Path,
) -> ResearchMediaRecord:
    """Download a pre-selected media asset during RESEARCH and create its sidecar."""
    context.require_research()
    if not item.file_url:
        raise ResearchDataError("research media has no downloadable file_url")
    sha256, _size = transport.download(context, item.file_url, destination)
    sealed = with_download(item, local_file=destination, sha256=sha256)
    write_astromedia_sidecar(sealed, destination)
    return sealed
