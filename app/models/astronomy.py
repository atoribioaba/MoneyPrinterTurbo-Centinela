from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.models.schema import BaseResponse


class StrictAstronomyModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class ScientificStatus(str, Enum):
    HECHO_VERIFICADO = "HECHO_VERIFICADO"
    APROXIMACION_DIVULGATIVA = (
        "APROXIMACION_DIVULGATIVA"
    )
    HIPOTESIS = "HIPOTESIS"
    RECREACION_VISUAL = "RECREACION_VISUAL"
    INFERENCIA = "INFERENCIA"
    NO_VERIFICADO = "NO_VERIFICADO"


class AstronomyBody(str, Enum):
    SUN = "sun"
    MOON = "moon"
    MERCURY = "mercury"
    VENUS = "venus"
    MARS = "mars"
    JUPITER = "jupiter"
    SATURN = "saturn"
    URANUS = "uranus"
    NEPTUNE = "neptune"
    PLUTO = "pluto"


class AstronomyEventType(str, Enum):
    MOON_NEW = "moon_new"
    MOON_FIRST_QUARTER = (
        "moon_first_quarter"
    )
    MOON_FULL = "moon_full"
    MOON_THIRD_QUARTER = (
        "moon_third_quarter"
    )

    MOON_PERIGEE = "moon_perigee"
    MOON_APOGEE = "moon_apogee"

    MARCH_EQUINOX = "march_equinox"
    JUNE_SOLSTICE = "june_solstice"
    SEPTEMBER_EQUINOX = (
        "september_equinox"
    )
    DECEMBER_SOLSTICE = (
        "december_solstice"
    )

    LOCAL_SOLAR_ECLIPSE = (
        "local_solar_eclipse"
    )

    LUNAR_ECLIPSE = "lunar_eclipse"


class SourceReference(
    StrictAstronomyModel
):
    source_id: str
    title: str
    provider: str
    url: str
    license: str | None = None
    classification: str
    role: str
    scientific_status: ScientificStatus


class ScientificClaim(
    StrictAstronomyModel
):
    statement: str
    scientific_status: ScientificStatus

    source_ids: list[str] = Field(
        default_factory=list
    )

    method: str | None = None
    precision_note: str | None = None

    publication_primary_source_required: (
        bool
    ) = True


class ObserverContext(
    StrictAstronomyModel
):
    latitude_deg: float = Field(
        ge=-90.0,
        le=90.0,
    )

    longitude_deg: float = Field(
        ge=-180.0,
        le=180.0,
    )

    elevation_m: float = Field(
        default=0.0,
        ge=-500.0,
        le=100000.0,
    )

    timezone: str = "UTC"

    name: str | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(
        cls,
        value,
    ):
        value = value.strip()

        if not value:
            raise ValueError(
                "timezone cannot be empty"
            )

        try:
            ZoneInfo(value)

        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                "Unknown IANA timezone: "
                + value
            ) from exc

        return value


class EventTime(
    StrictAstronomyModel
):
    utc: datetime
    local: datetime
    timezone: str


class BodyPosition(
    StrictAstronomyModel
):
    body: AstronomyBody

    right_ascension_hours_of_date: float
    declination_deg_of_date: float

    right_ascension_hours_j2000: float
    declination_deg_j2000: float

    azimuth_deg: float

    altitude_airless_deg: float
    altitude_apparent_deg: float

    center_above_horizon_apparent: bool

    topocentric_distance_au: float
    topocentric_distance_km: float

    geocentric_distance_au: float
    geocentric_distance_km: float

    constellation_symbol: str
    constellation_name: str

    visual_magnitude: float

    phase_angle_deg: float
    illuminated_fraction: float

    ring_tilt_deg: float | None = None

    solar_elongation_deg: float | None = None

    ecliptic_separation_deg: (
        float | None
    ) = None

    elongation_visibility: (
        str | None
    ) = None

    next_rise: EventTime | None = None
    next_set: EventTime | None = None

    next_culmination: (
        EventTime | None
    ) = None

    scientific_status: ScientificStatus

    source_ids: list[str] = Field(
        default_factory=list
    )


class MoonContext(
    StrictAstronomyModel
):
    phase_longitude_deg: float
    phase_name_es: str

    phase_angle_deg: float
    illuminated_fraction: float

    visual_magnitude: float

    geocentric_distance_au: float
    geocentric_distance_km: float

    apparent_angular_diameter_deg: float

    libration_latitude_deg: float
    libration_longitude_deg: float

    geocentric_ecliptic_latitude_deg: float
    geocentric_ecliptic_longitude_deg: float

    scientific_status: ScientificStatus

    source_ids: list[str] = Field(
        default_factory=list
    )


class TwilightContext(
    StrictAstronomyModel
):
    next_sunrise: EventTime | None
    next_sunset: EventTime | None

    next_civil_dawn: EventTime | None
    next_civil_dusk: EventTime | None

    next_nautical_dawn: EventTime | None
    next_nautical_dusk: EventTime | None

    next_astronomical_dawn: (
        EventTime | None
    )

    next_astronomical_dusk: (
        EventTime | None
    )

    next_solar_noon: EventTime | None

    search_window_days: float

    scientific_status: ScientificStatus

    refraction_model: str


class AstronomyEvent(
    StrictAstronomyModel
):
    event_type: AstronomyEventType

    label_es: str

    time: EventTime

    body: AstronomyBody | None = None

    details: dict[str, Any] = Field(
        default_factory=dict
    )

    scientific_status: ScientificStatus

    source_ids: list[str] = Field(
        default_factory=list
    )


class AstronomyContextRequest(
    StrictAstronomyModel
):
    observer: ObserverContext

    moment: datetime | None = None

    bodies: list[AstronomyBody] = Field(
        default_factory=lambda: list(
            AstronomyBody
        )
    )

    event_window_days: int = Field(
        default=35,
        ge=0,
        le=400,
    )

    include_eclipses: bool = False

    @field_validator("moment")
    @classmethod
    def validate_moment(
        cls,
        value,
    ):
        if value is None:
            return None

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "moment must contain an "
                "explicit UTC offset/timezone"
            )

        return value

    @field_validator("bodies")
    @classmethod
    def unique_bodies(
        cls,
        value,
    ):
        if not value:
            raise ValueError(
                "at least one body is required"
            )

        result = []
        seen = set()

        for body in value:
            if body not in seen:
                seen.add(body)
                result.append(body)

        return result


class AstronomyContext(
    StrictAstronomyModel
):
    engine: str
    engine_version: str

    generated_at_utc: datetime

    moment_utc: datetime
    moment_local: datetime

    observer: ObserverContext

    bodies: list[BodyPosition]

    moon: MoonContext

    twilight: TwilightContext

    events: list[AstronomyEvent]

    claims: list[ScientificClaim]

    sources: list[SourceReference]

    scientific_status: ScientificStatus

    accuracy_note: str
    refraction_note: str
    scope_note: str

    primary_source_verification_required_for_publication: (
        bool
    ) = True


class AstronomyHealth(
    StrictAstronomyModel
):
    status: str

    engine: str
    engine_version: str

    license: str
    classification: str

    cpu_only: bool

    network_required_at_runtime: bool

    supported_bodies: list[AstronomyBody]


class AstronomyHealthResponse(
    BaseResponse
):
    data: AstronomyHealth


class AstronomyContextResponse(
    BaseResponse
):
    data: AstronomyContext
