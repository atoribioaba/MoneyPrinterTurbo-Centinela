from __future__ import annotations

from datetime import UTC, datetime

from app.models.observation import EvidenceKind, WeatherSnapshot


OPEN_METEO_SOURCE_ID = "open_meteo_forecast"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_LICENSE = "CC BY 4.0"
OPEN_METEO_ATTRIBUTION = "Weather data by Open-Meteo.com"

_OPEN_METEO_HOURLY_FIELDS = (
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "wind_speed_10m",
    "wind_gusts_10m",
    "precipitation_probability",
)


def build_open_meteo_params(
    latitude_deg: float,
    longitude_deg: float,
    *,
    forecast_days: int = 7,
) -> dict[str, str | float | int]:
    if not -90.0 <= latitude_deg <= 90.0:
        raise ValueError("latitude out of range")
    if not -180.0 <= longitude_deg <= 180.0:
        raise ValueError("longitude out of range")
    if not 1 <= forecast_days <= 16:
        raise ValueError("forecast_days must be between 1 and 16")
    return {
        "latitude": latitude_deg,
        "longitude": longitude_deg,
        "hourly": ",".join(_OPEN_METEO_HOURLY_FIELDS),
        "timezone": "UTC",
        "forecast_days": forecast_days,
    }


def _parse_utc_hour(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _nearest_hour_index(times: list[str], requested_at: datetime) -> int:
    if not times:
        raise ValueError("Open-Meteo response has no hourly times")
    if requested_at.tzinfo is None:
        raise ValueError("requested_at must be timezone-aware")
    requested_utc = requested_at.astimezone(UTC)
    parsed = [_parse_utc_hour(value) for value in times]
    return min(range(len(parsed)), key=lambda index: abs(parsed[index] - requested_utc))


def _hourly_value(hourly: dict, key: str, index: int):
    values = hourly.get(key)
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def weather_snapshot_age_hours(snapshot: WeatherSnapshot, now: datetime) -> float:
    """Return age since retrieval; callers choose their own stale threshold."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    delta = now.astimezone(UTC) - snapshot.retrieved_at.astimezone(UTC)
    return delta.total_seconds() / 3600.0


def weather_snapshot_is_stale(
    snapshot: WeatherSnapshot,
    *,
    now: datetime,
    max_retrieval_age_hours: float,
) -> bool:
    """Check staleness without hard-coding a universal astronomy threshold."""
    if max_retrieval_age_hours <= 0:
        raise ValueError("max_retrieval_age_hours must be positive")
    age = weather_snapshot_age_hours(snapshot, now)
    return age < 0 or age > max_retrieval_age_hours


def parse_open_meteo_snapshot(
    payload: dict,
    *,
    requested_at: datetime,
    retrieved_at: datetime | None = None,
) -> WeatherSnapshot:
    """Parse a forecast response without inventing seeing or transparency.

    Open-Meteo's ordinary forecast variables are meteorological model output.
    `seeing_arcsec` and `transparency_percent` therefore intentionally remain
    unset until an independently sourced astronomy-weather provider supplies
    them.
    """
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise ValueError("Open-Meteo response missing hourly object")
    times = hourly.get("time")
    if not isinstance(times, list):
        raise ValueError("Open-Meteo response missing hourly time list")

    index = _nearest_hour_index(times, requested_at)
    valid_at = _parse_utc_hour(times[index])
    retrieved_at = (retrieved_at or datetime.now(UTC)).astimezone(UTC)

    return WeatherSnapshot(
        source_id=OPEN_METEO_SOURCE_ID,
        valid_at=valid_at,
        retrieved_at=retrieved_at,
        evidence_kind=EvidenceKind.FORECAST,
        temperature_c=_hourly_value(hourly, "temperature_2m", index),
        relative_humidity_percent=_hourly_value(
            hourly, "relative_humidity_2m", index
        ),
        dew_point_c=_hourly_value(hourly, "dew_point_2m", index),
        cloud_cover_percent=_hourly_value(hourly, "cloud_cover", index),
        cloud_low_percent=_hourly_value(hourly, "cloud_cover_low", index),
        cloud_mid_percent=_hourly_value(hourly, "cloud_cover_mid", index),
        cloud_high_percent=_hourly_value(hourly, "cloud_cover_high", index),
        wind_speed_kph=_hourly_value(hourly, "wind_speed_10m", index),
        wind_gust_kph=_hourly_value(hourly, "wind_gusts_10m", index),
        precipitation_probability_percent=_hourly_value(
            hourly, "precipitation_probability", index
        ),
        seeing_arcsec=None,
        transparency_percent=None,
    )
