from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from importlib.metadata import version
from zoneinfo import ZoneInfo

import astronomy as ae

from app.models.astronomy import (
    AstronomyBody,
    AstronomyContext,
    AstronomyEvent,
    AstronomyEventType,
    AstronomyHealth,
    BodyPosition,
    EventTime,
    MoonContext,
    ScientificClaim,
    ScientificStatus,
    SourceReference,
    TwilightContext,
)


ENGINE_NAME = "Astronomy Engine"

ENGINE_DISTRIBUTION = (
    "astronomy-engine"
)

ENGINE_VERSION = version(
    ENGINE_DISTRIBUTION
)

ENGINE_SOURCE_ID = (
    "astronomy-engine-"
    + ENGINE_VERSION
)

RISE_SET_SEARCH_DAYS = 7.0

TWILIGHT_SEARCH_DAYS = 7.0


ENGINE_SOURCE = SourceReference(
    source_id=ENGINE_SOURCE_ID,

    title=(
        "Astronomy Engine "
        + ENGINE_VERSION
    ),

    provider=(
        "CosineKitty / Donald Cross"
    ),

    url=(
        "https://github.com/"
        "cosinekitty/astronomy"
    ),

    license="MIT",

    classification=(
        "OPEN SOURCE + "
        "100 % GRATUITA"
    ),

    role=(
        "Local deterministic "
        "ephemeris calculation"
    ),

    scientific_status=(
        ScientificStatus
        .HECHO_VERIFICADO
    ),
)


BODY_MAP = {
    AstronomyBody.SUN:
        ae.Body.Sun,

    AstronomyBody.MOON:
        ae.Body.Moon,

    AstronomyBody.MERCURY:
        ae.Body.Mercury,

    AstronomyBody.VENUS:
        ae.Body.Venus,

    AstronomyBody.MARS:
        ae.Body.Mars,

    AstronomyBody.JUPITER:
        ae.Body.Jupiter,

    AstronomyBody.SATURN:
        ae.Body.Saturn,

    AstronomyBody.URANUS:
        ae.Body.Uranus,

    AstronomyBody.NEPTUNE:
        ae.Body.Neptune,

    AstronomyBody.PLUTO:
        ae.Body.Pluto,
}


MOON_QUARTERS = {
    0: (
        AstronomyEventType.MOON_NEW,
        "Luna nueva",
    ),

    1: (
        AstronomyEventType
        .MOON_FIRST_QUARTER,

        "Cuarto creciente",
    ),

    2: (
        AstronomyEventType.MOON_FULL,
        "Luna llena",
    ),

    3: (
        AstronomyEventType
        .MOON_THIRD_QUARTER,

        "Cuarto menguante",
    ),
}


SEASON_EVENTS = (
    (
        "mar_equinox",
        AstronomyEventType
        .MARCH_EQUINOX,
        "Equinoccio de marzo",
    ),

    (
        "jun_solstice",
        AstronomyEventType
        .JUNE_SOLSTICE,
        "Solsticio de junio",
    ),

    (
        "sep_equinox",
        AstronomyEventType
        .SEPTEMBER_EQUINOX,
        "Equinoccio de septiembre",
    ),

    (
        "dec_solstice",
        AstronomyEventType
        .DECEMBER_SOLSTICE,
        "Solsticio de diciembre",
    ),
)


class AstronomyCoreError(
    RuntimeError
):
    pass


def _observer(context):
    return ae.Observer(
        context.latitude_deg,
        context.longitude_deg,
        context.elevation_m,
    )


def _to_utc(moment):
    if moment is None:
        return datetime.now(
            timezone.utc
        )

    if (
        moment.tzinfo is None
        or moment.utcoffset() is None
    ):
        raise AstronomyCoreError(
            "Astronomy calculations require "
            "a timezone-aware datetime."
        )

    return moment.astimezone(
        timezone.utc
    )


def _to_ae_time(value):
    value = value.astimezone(
        timezone.utc
    )

    seconds = (
        value.second
        + value.microsecond
        / 1_000_000.0
    )

    return ae.Time.Make(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        seconds,
    )


def _from_ae_time(value):
    # Time.Utc() avoids reducing precision by
    # converting through Time.__str__.
    return value.Utc().astimezone(
        timezone.utc
    )


def _event_time(
    value,
    timezone_name,
):
    if value is None:
        return None

    utc_value = _from_ae_time(
        value
    )

    return EventTime(
        utc=utc_value,

        local=utc_value.astimezone(
            ZoneInfo(
                timezone_name
            )
        ),

        timezone=timezone_name,
    )


def _moon_phase_name_es(
    longitude,
):
    names = (
        "Luna nueva",
        "Creciente",
        "Cuarto creciente",
        "Gibosa creciente",
        "Luna llena",
        "Gibosa menguante",
        "Cuarto menguante",
        "Menguante",
    )

    index = int(
        (longitude + 22.5)
        // 45.0
    ) % 8

    return names[index]


def _rise_set_culmination(
    engine_body,
    observer,
    start_time,
    timezone_name,
):
    rise = ae.SearchRiseSet(
        engine_body,
        observer,
        ae.Direction.Rise,
        start_time,
        RISE_SET_SEARCH_DAYS,
    )

    setting = ae.SearchRiseSet(
        engine_body,
        observer,
        ae.Direction.Set,
        start_time,
        RISE_SET_SEARCH_DAYS,
    )

    culmination = ae.SearchHourAngle(
        engine_body,
        observer,
        0.0,
        start_time,
        +1,
    )

    return (
        _event_time(
            rise,
            timezone_name,
        ),

        _event_time(
            setting,
            timezone_name,
        ),

        _event_time(
            culmination.time,
            timezone_name,
        ),
    )


def build_body_position(
    body,
    observer_context,
    moment_utc,
):
    engine_body = BODY_MAP[
        body
    ]

    engine_time = _to_ae_time(
        moment_utc
    )

    observer = _observer(
        observer_context
    )

    # True equator/equinox of date:
    # required for Horizon().
    equator_date = ae.Equator(
        engine_body,
        engine_time,
        observer,
        True,
        True,
    )

    # J2000:
    # required for Constellation().
    equator_j2000 = ae.Equator(
        engine_body,
        engine_time,
        observer,
        False,
        True,
    )

    airless = ae.Horizon(
        engine_time,
        observer,
        equator_date.ra,
        equator_date.dec,
        ae.Refraction.Airless,
    )

    apparent = ae.Horizon(
        engine_time,
        observer,
        equator_date.ra,
        equator_date.dec,
        ae.Refraction.Normal,
    )

    constellation = ae.Constellation(
        equator_j2000.ra,
        equator_j2000.dec,
    )

    illumination = ae.Illumination(
        engine_body,
        engine_time,
    )

    elongation_deg = None
    ecliptic_separation = None
    elongation_visibility = None

    if body != AstronomyBody.SUN:
        elongation = ae.Elongation(
            engine_body,
            engine_time,
        )

        elongation_deg = (
            elongation.elongation
        )

        ecliptic_separation = (
            elongation.ecliptic_separation
        )

        elongation_visibility = (
            elongation
            .visibility
            .name
            .lower()
        )

    (
        next_rise,
        next_set,
        next_culmination,
    ) = _rise_set_culmination(
        engine_body,
        observer,
        engine_time,
        observer_context.timezone,
    )

    return BodyPosition(
        body=body,

        right_ascension_hours_of_date=(
            equator_date.ra
        ),

        declination_deg_of_date=(
            equator_date.dec
        ),

        right_ascension_hours_j2000=(
            equator_j2000.ra
        ),

        declination_deg_j2000=(
            equator_j2000.dec
        ),

        azimuth_deg=(
            apparent.azimuth
        ),

        altitude_airless_deg=(
            airless.altitude
        ),

        altitude_apparent_deg=(
            apparent.altitude
        ),

        center_above_horizon_apparent=(
            apparent.altitude > 0.0
        ),

        topocentric_distance_au=(
            equator_date.dist
        ),

        topocentric_distance_km=(
            equator_date.dist
            * ae.KM_PER_AU
        ),

        geocentric_distance_au=(
            illumination.geo_dist
        ),

        geocentric_distance_km=(
            illumination.geo_dist
            * ae.KM_PER_AU
        ),

        constellation_symbol=(
            constellation.symbol
        ),

        constellation_name=(
            constellation.name
        ),

        visual_magnitude=(
            illumination.mag
        ),

        phase_angle_deg=(
            illumination.phase_angle
        ),

        illuminated_fraction=(
            illumination.phase_fraction
        ),

        ring_tilt_deg=(
            illumination.ring_tilt
        ),

        solar_elongation_deg=(
            elongation_deg
        ),

        ecliptic_separation_deg=(
            ecliptic_separation
        ),

        elongation_visibility=(
            elongation_visibility
        ),

        next_rise=next_rise,
        next_set=next_set,

        next_culmination=(
            next_culmination
        ),

        scientific_status=(
            ScientificStatus
            .HECHO_VERIFICADO
        ),

        source_ids=[
            ENGINE_SOURCE_ID
        ],
    )


def build_moon_context(
    moment_utc,
):
    engine_time = _to_ae_time(
        moment_utc
    )

    phase_longitude = ae.MoonPhase(
        engine_time
    )

    illumination = ae.Illumination(
        ae.Body.Moon,
        engine_time,
    )

    libration = ae.Libration(
        engine_time
    )

    return MoonContext(
        phase_longitude_deg=(
            phase_longitude
        ),

        phase_name_es=(
            _moon_phase_name_es(
                phase_longitude
            )
        ),

        phase_angle_deg=(
            illumination.phase_angle
        ),

        illuminated_fraction=(
            illumination.phase_fraction
        ),

        visual_magnitude=(
            illumination.mag
        ),

        geocentric_distance_au=(
            libration.dist_km
            / ae.KM_PER_AU
        ),

        geocentric_distance_km=(
            libration.dist_km
        ),

        apparent_angular_diameter_deg=(
            libration.diam_deg
        ),

        libration_latitude_deg=(
            libration.elat
        ),

        libration_longitude_deg=(
            libration.elon
        ),

        geocentric_ecliptic_latitude_deg=(
            libration.mlat
        ),

        geocentric_ecliptic_longitude_deg=(
            libration.mlon
        ),

        scientific_status=(
            ScientificStatus
            .HECHO_VERIFICADO
        ),

        source_ids=[
            ENGINE_SOURCE_ID
        ],
    )


def _search_sun_altitude(
    altitude,
    direction,
    observer,
    start_time,
    timezone_name,
):
    value = ae.SearchAltitude(
        ae.Body.Sun,
        observer,
        direction,
        start_time,
        TWILIGHT_SEARCH_DAYS,
        altitude,
    )

    return _event_time(
        value,
        timezone_name,
    )


def build_twilight_context(
    observer_context,
    moment_utc,
):
    observer = _observer(
        observer_context
    )

    engine_time = _to_ae_time(
        moment_utc
    )

    timezone_name = (
        observer_context.timezone
    )

    sunrise = ae.SearchRiseSet(
        ae.Body.Sun,
        observer,
        ae.Direction.Rise,
        engine_time,
        TWILIGHT_SEARCH_DAYS,
    )

    sunset = ae.SearchRiseSet(
        ae.Body.Sun,
        observer,
        ae.Direction.Set,
        engine_time,
        TWILIGHT_SEARCH_DAYS,
    )

    solar_noon = ae.SearchHourAngle(
        ae.Body.Sun,
        observer,
        0.0,
        engine_time,
        +1,
    )

    return TwilightContext(
        next_sunrise=_event_time(
            sunrise,
            timezone_name,
        ),

        next_sunset=_event_time(
            sunset,
            timezone_name,
        ),

        next_civil_dawn=(
            _search_sun_altitude(
                -6.0,
                ae.Direction.Rise,
                observer,
                engine_time,
                timezone_name,
            )
        ),

        next_civil_dusk=(
            _search_sun_altitude(
                -6.0,
                ae.Direction.Set,
                observer,
                engine_time,
                timezone_name,
            )
        ),

        next_nautical_dawn=(
            _search_sun_altitude(
                -12.0,
                ae.Direction.Rise,
                observer,
                engine_time,
                timezone_name,
            )
        ),

        next_nautical_dusk=(
            _search_sun_altitude(
                -12.0,
                ae.Direction.Set,
                observer,
                engine_time,
                timezone_name,
            )
        ),

        next_astronomical_dawn=(
            _search_sun_altitude(
                -18.0,
                ae.Direction.Rise,
                observer,
                engine_time,
                timezone_name,
            )
        ),

        next_astronomical_dusk=(
            _search_sun_altitude(
                -18.0,
                ae.Direction.Set,
                observer,
                engine_time,
                timezone_name,
            )
        ),

        next_solar_noon=(
            _event_time(
                solar_noon.time,
                timezone_name,
            )
        ),

        search_window_days=(
            TWILIGHT_SEARCH_DAYS
        ),

        scientific_status=(
            ScientificStatus
            .HECHO_VERIFICADO
        ),

        refraction_model=(
            "Sunrise/sunset use Astronomy "
            "Engine's standard near-horizon "
            "refraction. Twilight crossings "
            "at -6/-12/-18 degrees are "
            "geometric and intentionally "
            "not refraction-corrected."
        ),
    )


def _append_moon_quarters(
    events,
    start_time,
    end_utc,
    timezone_name,
):
    quarter = ae.SearchMoonQuarter(
        start_time
    )

    for _ in range(80):
        event_utc = _from_ae_time(
            quarter.time
        )

        if event_utc > end_utc:
            break

        event_type, label = (
            MOON_QUARTERS[
                quarter.quarter
            ]
        )

        events.append(
            AstronomyEvent(
                event_type=event_type,

                label_es=label,

                time=_event_time(
                    quarter.time,
                    timezone_name,
                ),

                body=(
                    AstronomyBody.MOON
                ),

                details={
                    "quarter":
                        quarter.quarter,

                    "phase_longitude_deg":
                        90.0
                        * quarter.quarter,
                },

                scientific_status=(
                    ScientificStatus
                    .HECHO_VERIFICADO
                ),

                source_ids=[
                    ENGINE_SOURCE_ID
                ],
            )
        )

        quarter = ae.NextMoonQuarter(
            quarter
        )


def _append_lunar_apsides(
    events,
    start_time,
    end_utc,
    timezone_name,
):
    apsis = ae.SearchLunarApsis(
        start_time
    )

    for _ in range(80):
        event_utc = _from_ae_time(
            apsis.time
        )

        if event_utc > end_utc:
            break

        if (
            apsis.kind
            == ae.ApsisKind.Pericenter
        ):
            event_type = (
                AstronomyEventType
                .MOON_PERIGEE
            )

            label = (
                "Perigeo lunar"
            )

        else:
            event_type = (
                AstronomyEventType
                .MOON_APOGEE
            )

            label = (
                "Apogeo lunar"
            )

        events.append(
            AstronomyEvent(
                event_type=event_type,

                label_es=label,

                time=_event_time(
                    apsis.time,
                    timezone_name,
                ),

                body=(
                    AstronomyBody.MOON
                ),

                details={
                    "distance_au":
                        apsis.dist_au,

                    "distance_km":
                        apsis.dist_km,
                },

                scientific_status=(
                    ScientificStatus
                    .HECHO_VERIFICADO
                ),

                source_ids=[
                    ENGINE_SOURCE_ID
                ],
            )
        )

        apsis = ae.NextLunarApsis(
            apsis
        )


def _append_seasons(
    events,
    start_utc,
    end_utc,
    timezone_name,
):
    for year in range(
        start_utc.year,
        end_utc.year + 1,
    ):
        seasons = ae.Seasons(
            year
        )

        for (
            attribute,
            event_type,
            label,
        ) in SEASON_EVENTS:
            event_time = getattr(
                seasons,
                attribute,
            )

            event_utc = _from_ae_time(
                event_time
            )

            if not (
                start_utc
                <= event_utc
                <= end_utc
            ):
                continue

            # Astronomy Engine documents
            # direct validation of Seasons
            # for 1800..2100.
            if 1800 <= year <= 2100:
                status = (
                    ScientificStatus
                    .HECHO_VERIFICADO
                )
            else:
                status = (
                    ScientificStatus
                    .APROXIMACION_DIVULGATIVA
                )

            events.append(
                AstronomyEvent(
                    event_type=event_type,

                    label_es=label,

                    time=_event_time(
                        event_time,
                        timezone_name,
                    ),

                    body=(
                        AstronomyBody.SUN
                    ),

                    details={
                        "calendar_year":
                            year,

                        "engine_validated_range":
                            "1800-2100",
                    },

                    scientific_status=(
                        status
                    ),

                    source_ids=[
                        ENGINE_SOURCE_ID
                    ],
                )
            )


def _solar_event_detail(
    event,
):
    if event is None:
        return None

    return {
        "utc":
            _from_ae_time(
                event.time
            ).isoformat(),

        "sun_altitude_deg":
            event.altitude,
    }


def _append_eclipses(
    events,
    observer_context,
    start_time,
    start_utc,
    end_utc,
):
    observer = _observer(
        observer_context
    )

    timezone_name = (
        observer_context.timezone
    )

    # -------------------------------------------------
    # Local solar eclipses
    # -------------------------------------------------

    local_solar = (
        ae.SearchLocalSolarEclipse(
            start_time,
            observer,
        )
    )

    for _ in range(5):
        peak_utc = _from_ae_time(
            local_solar.peak.time
        )

        if peak_utc > end_utc:
            break

        if peak_utc >= start_utc:
            events.append(
                AstronomyEvent(
                    event_type=(
                        AstronomyEventType
                        .LOCAL_SOLAR_ECLIPSE
                    ),

                    label_es=(
                        "Eclipse solar local"
                    ),

                    time=_event_time(
                        local_solar
                        .peak
                        .time,

                        timezone_name,
                    ),

                    body=(
                        AstronomyBody.SUN
                    ),

                    details={
                        "kind":
                            local_solar
                            .kind
                            .name
                            .lower(),

                        "obscuration":
                            local_solar
                            .obscuration,

                        "peak_sun_altitude_deg":
                            local_solar
                            .peak
                            .altitude,

                        "peak_visible_above_horizon":
                            (
                                local_solar
                                .peak
                                .altitude
                                > 0.0
                            ),

                        "partial_begin":
                            _solar_event_detail(
                                local_solar
                                .partial_begin
                            ),

                        "total_begin":
                            _solar_event_detail(
                                local_solar
                                .total_begin
                            ),

                        "total_end":
                            _solar_event_detail(
                                local_solar
                                .total_end
                            ),

                        "partial_end":
                            _solar_event_detail(
                                local_solar
                                .partial_end
                            ),
                    },

                    scientific_status=(
                        ScientificStatus
                        .HECHO_VERIFICADO
                    ),

                    source_ids=[
                        ENGINE_SOURCE_ID
                    ],
                )
            )

        local_solar = (
            ae.NextLocalSolarEclipse(
                local_solar.peak.time,
                observer,
            )
        )

    # -------------------------------------------------
    # Lunar eclipses
    # -------------------------------------------------

    lunar = ae.SearchLunarEclipse(
        start_time
    )

    for _ in range(10):
        peak_utc = _from_ae_time(
            lunar.peak
        )

        if peak_utc > end_utc:
            break

        if peak_utc >= start_utc:
            moon_eq = ae.Equator(
                ae.Body.Moon,
                lunar.peak,
                observer,
                True,
                True,
            )

            moon_horizon = ae.Horizon(
                lunar.peak,
                observer,
                moon_eq.ra,
                moon_eq.dec,
                ae.Refraction.Normal,
            )

            events.append(
                AstronomyEvent(
                    event_type=(
                        AstronomyEventType
                        .LUNAR_ECLIPSE
                    ),

                    label_es=(
                        "Eclipse lunar"
                    ),

                    time=_event_time(
                        lunar.peak,
                        timezone_name,
                    ),

                    body=(
                        AstronomyBody.MOON
                    ),

                    details={
                        "kind":
                            lunar
                            .kind
                            .name
                            .lower(),

                        "obscuration":
                            lunar.obscuration,

                        "moon_altitude_at_peak_deg":
                            moon_horizon.altitude,

                        "peak_visible_above_horizon":
                            (
                                moon_horizon.altitude
                                > 0.0
                            ),

                        "semi_duration_penumbral_min":
                            lunar.sd_penum,

                        "semi_duration_partial_min":
                            lunar.sd_partial,

                        "semi_duration_total_min":
                            lunar.sd_total,

                        "visibility_scope_note":
                            (
                                "This field evaluates "
                                "Moon altitude at eclipse "
                                "peak. Full local "
                                "visibility assessment "
                                "requires the complete "
                                "phase interval."
                            ),
                    },

                    scientific_status=(
                        ScientificStatus
                        .HECHO_VERIFICADO
                    ),

                    source_ids=[
                        ENGINE_SOURCE_ID
                    ],
                )
            )

        lunar = ae.NextLunarEclipse(
            lunar.peak
        )


def build_events(
    request,
    moment_utc,
):
    if request.event_window_days <= 0:
        return []

    end_utc = (
        moment_utc
        + timedelta(
            days=request.event_window_days
        )
    )

    start_time = _to_ae_time(
        moment_utc
    )

    events = []

    _append_moon_quarters(
        events,
        start_time,
        end_utc,
        request.observer.timezone,
    )

    _append_lunar_apsides(
        events,
        start_time,
        end_utc,
        request.observer.timezone,
    )

    _append_seasons(
        events,
        moment_utc,
        end_utc,
        request.observer.timezone,
    )

    if request.include_eclipses:
        _append_eclipses(
            events,
            request.observer,
            start_time,
            moment_utc,
            end_utc,
        )

    events.sort(
        key=lambda event:
            event.time.utc
    )

    return events


def _claims():
    return [
        ScientificClaim(
            statement=(
                "Celestial positions are "
                "deterministic topocentric "
                "calculations for the supplied "
                "observer and instant."
            ),

            scientific_status=(
                ScientificStatus
                .HECHO_VERIFICADO
            ),

            source_ids=[
                ENGINE_SOURCE_ID
            ],

            method=(
                "Astronomy Engine "
                "Equator + Horizon"
            ),

            precision_note=(
                "Astronomy Engine documents "
                "an approximately ±1 arcminute "
                "design target for supported "
                "position calculations."
            ),

            publication_primary_source_required=(
                True
            ),
        ),

        ScientificClaim(
            statement=(
                "Sunrise and sunset include "
                "Astronomy Engine's standard "
                "near-horizon refraction model."
            ),

            scientific_status=(
                ScientificStatus
                .HECHO_VERIFICADO
            ),

            source_ids=[
                ENGINE_SOURCE_ID
            ],

            method=(
                "Astronomy Engine "
                "SearchRiseSet"
            ),

            precision_note=(
                "Actual atmospheric refraction "
                "depends on local temperature, "
                "pressure, humidity and horizon."
            ),

            publication_primary_source_required=(
                True
            ),
        ),

        ScientificClaim(
            statement=(
                "The astronomy calculation core "
                "performs no network access "
                "at runtime."
            ),

            scientific_status=(
                ScientificStatus
                .HECHO_VERIFICADO
            ),

            source_ids=[
                ENGINE_SOURCE_ID
            ],

            method=(
                "Local astronomy-engine "
                "Python calculations"
            ),

            publication_primary_source_required=(
                False
            ),
        ),
    ]


def get_astronomy_health():
    return AstronomyHealth(
        status="ok",

        engine=ENGINE_NAME,

        engine_version=(
            ENGINE_VERSION
        ),

        license="MIT",

        classification=(
            "OPEN SOURCE + "
            "100 % GRATUITA"
        ),

        cpu_only=True,

        network_required_at_runtime=(
            False
        ),

        supported_bodies=list(
            BODY_MAP.keys()
        ),
    )


def build_astronomy_context(
    request,
):
    try:
        moment_utc = _to_utc(
            request.moment
        )

        local_zone = ZoneInfo(
            request.observer.timezone
        )

        body_positions = [
            build_body_position(
                body,
                request.observer,
                moment_utc,
            )
            for body in request.bodies
        ]

        return AstronomyContext(
            engine=ENGINE_NAME,

            engine_version=(
                ENGINE_VERSION
            ),

            generated_at_utc=(
                datetime.now(
                    timezone.utc
                )
            ),

            moment_utc=moment_utc,

            moment_local=(
                moment_utc.astimezone(
                    local_zone
                )
            ),

            observer=request.observer,

            bodies=body_positions,

            moon=build_moon_context(
                moment_utc
            ),

            twilight=(
                build_twilight_context(
                    request.observer,
                    moment_utc,
                )
            ),

            events=build_events(
                request,
                moment_utc,
            ),

            claims=_claims(),

            sources=[
                ENGINE_SOURCE
            ],

            scientific_status=(
                ScientificStatus
                .HECHO_VERIFICADO
            ),

            accuracy_note=(
                "Astronomy Engine is designed "
                "for approximately ±1 arcminute "
                "accuracy for supported position "
                "calculations. It is not a "
                "spacecraft-navigation ephemeris."
            ),

            refraction_note=(
                "Apparent horizon values use a "
                "standard atmospheric model. "
                "Real refraction depends on "
                "actual atmospheric conditions."
            ),

            scope_note=(
                "This module supplies local "
                "deterministic ephemerides. "
                "Publication claims about current "
                "ephemerides, eclipses, missions, "
                "discoveries or observing "
                "conditions must still be "
                "corroborated with appropriate "
                "current primary sources such as "
                "NASA, ESA, IGN, IAU or "
                "observatories."
            ),

            primary_source_verification_required_for_publication=(
                True
            ),
        )

    except ae.Error as exc:
        raise AstronomyCoreError(
            str(exc)
        ) from exc
