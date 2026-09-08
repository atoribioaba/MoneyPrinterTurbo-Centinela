from __future__ import annotations

from app.models.deep_sky import DeepSkyObject


OPENNGC_SOURCE_URL = "https://github.com/mattiaverga/OpenNGC"
OPENNGC_LICENSE = "CC-BY-SA-4.0"


def _float_or_none(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def _split_names(value) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    separators = (",", ";")
    values = [text]
    for separator in separators:
        if separator in text:
            values = [part.strip() for part in text.split(separator)]
            break
    return [item for item in values if item]


def parse_hms_hours(value: str) -> float:
    parts = str(value).strip().split(":")
    if len(parts) != 3:
        raise ValueError("RA must use HH:MM:SS[.ss]")
    hours, minutes, seconds = (float(part) for part in parts)
    result = hours + minutes / 60.0 + seconds / 3600.0
    if not 0.0 <= result < 24.0:
        raise ValueError("RA out of range")
    return result


def parse_dms_deg(value: str) -> float:
    text = str(value).strip()
    sign = -1.0 if text.startswith("-") else 1.0
    unsigned = text.lstrip("+-")
    parts = unsigned.split(":")
    if len(parts) != 3:
        raise ValueError("Dec must use [+/-]DD:MM:SS[.ss]")
    degrees, minutes, seconds = (float(part) for part in parts)
    result = sign * (degrees + minutes / 60.0 + seconds / 3600.0)
    if not -90.0 <= result <= 90.0:
        raise ValueError("declination out of range")
    return result


def parse_openngc_row(row: dict[str, str]) -> DeepSkyObject:
    """Parse one OpenNGC CSV-style row using the repository's documented fields.

    `NonEx` and `Dup` records are rejected here because they are not independent
    physical observing targets. Callers should resolve duplicates to the master
    NGC/IC identity before creating a Centinela target.
    """
    name = str(row.get("Name", "")).strip()
    object_type = str(row.get("Type", "")).strip()
    if not name:
        raise ValueError("OpenNGC row missing Name")
    if object_type in {"NonEx", "Dup"}:
        raise ValueError(f"OpenNGC {object_type} row is not a physical target")

    ra = str(row.get("RA", "")).strip()
    dec = str(row.get("Dec", "")).strip()
    constellation = str(row.get("Const", "")).strip()
    if not ra or not dec or not constellation:
        raise ValueError("OpenNGC row missing RA/Dec/Const")

    messier_raw = str(row.get("M", "")).strip()
    messier = int(messier_raw) if messier_raw else None

    return DeepSkyObject(
        catalog_name=name,
        object_type=object_type,
        right_ascension_j2000_hours=parse_hms_hours(ra),
        declination_j2000_deg=parse_dms_deg(dec),
        constellation=constellation,
        major_axis_arcmin=_float_or_none(row.get("MajAx")),
        minor_axis_arcmin=_float_or_none(row.get("MinAx")),
        position_angle_deg=_float_or_none(row.get("PosAng")),
        b_magnitude=_float_or_none(row.get("B-Mag")),
        v_magnitude=_float_or_none(row.get("V-Mag")),
        surface_brightness_mag_arcsec2=_float_or_none(row.get("SurfBr")),
        messier_number=messier,
        common_names=_split_names(row.get("Common names")),
        identifiers=_split_names(row.get("Identifiers")),
        source_codes=_split_names(row.get("Sources")),
    )
