from __future__ import annotations

import math

from app.models.observation import (
    ObservationObjectClass,
    ObservabilityRequest,
    ObservabilityResult,
    ScoreComponent,
)


_WEIGHTS: dict[ObservationObjectClass, dict[str, float]] = {
    ObservationObjectClass.GENERAL: {
        "geometry": 1.4,
        "darkness": 1.0,
        "moon": 0.8,
        "clouds": 1.6,
        "precipitation": 0.8,
        "transparency": 1.0,
        "seeing": 0.8,
        "wind": 0.5,
        "dew": 0.4,
        "sky_quality": 0.8,
    },
    ObservationObjectClass.PLANETARY: {
        "geometry": 1.6,
        "darkness": 0.3,
        "moon": 0.1,
        "clouds": 1.6,
        "precipitation": 0.8,
        "transparency": 0.6,
        "seeing": 2.0,
        "wind": 0.5,
        "dew": 0.4,
        "sky_quality": 0.1,
    },
    ObservationObjectClass.LUNAR: {
        "geometry": 1.6,
        "darkness": 0.2,
        "clouds": 1.6,
        "precipitation": 0.8,
        "transparency": 0.6,
        "seeing": 1.8,
        "wind": 0.5,
        "dew": 0.4,
    },
    ObservationObjectClass.DEEP_SKY: {
        "geometry": 1.5,
        "darkness": 1.7,
        "moon": 1.5,
        "clouds": 1.8,
        "precipitation": 1.0,
        "transparency": 1.5,
        "seeing": 0.5,
        "wind": 0.4,
        "dew": 0.5,
        "sky_quality": 1.6,
    },
    ObservationObjectClass.MILKY_WAY: {
        "geometry": 1.2,
        "darkness": 1.9,
        "moon": 1.7,
        "clouds": 1.8,
        "precipitation": 1.0,
        "transparency": 1.6,
        "seeing": 0.1,
        "wind": 0.3,
        "dew": 0.4,
        "sky_quality": 1.7,
    },
    ObservationObjectClass.METEOR: {
        "geometry": 0.8,
        "darkness": 1.7,
        "moon": 1.4,
        "clouds": 1.9,
        "precipitation": 1.0,
        "transparency": 1.3,
        "seeing": 0.1,
        "wind": 0.3,
        "dew": 0.3,
        "sky_quality": 1.2,
    },
    ObservationObjectClass.COMET: {
        "geometry": 1.5,
        "darkness": 1.4,
        "moon": 1.2,
        "clouds": 1.8,
        "precipitation": 1.0,
        "transparency": 1.5,
        "seeing": 0.3,
        "wind": 0.4,
        "dew": 0.4,
        "sky_quality": 1.1,
    },
}


def airmass_from_altitude_deg(altitude_deg: float) -> float | None:
    """Return relative optical airmass using the Kasten-Young approximation.

    Below or at the geometric horizon the target is treated as not observable
    and no airmass value is returned.
    """
    if altitude_deg <= 0.0:
        return None
    altitude_deg = min(float(altitude_deg), 90.0)
    radians = math.radians(altitude_deg)
    denominator = math.sin(radians) + 0.50572 * (
        altitude_deg + 6.07995
    ) ** -1.6364
    return 1.0 / denominator


def angular_separation_deg(
    ra1_hours: float,
    dec1_deg: float,
    ra2_hours: float,
    dec2_deg: float,
) -> float:
    """Great-circle angular separation for two equatorial coordinates."""
    ra1 = math.radians((ra1_hours % 24.0) * 15.0)
    ra2 = math.radians((ra2_hours % 24.0) * 15.0)
    dec1 = math.radians(dec1_deg)
    dec2 = math.radians(dec2_deg)
    cosine = (
        math.sin(dec1) * math.sin(dec2)
        + math.cos(dec1) * math.cos(dec2) * math.cos(ra1 - ra2)
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _geometry_score(altitude: float) -> float:
    if altitude <= 0:
        return 0.0
    if altitude >= 60:
        return 100.0
    return altitude / 60.0 * 100.0


def _darkness_score(sun_altitude: float) -> float:
    if sun_altitude <= -18:
        return 100.0
    if sun_altitude <= -12:
        return 80.0 + (-12.0 - sun_altitude) / 6.0 * 20.0
    if sun_altitude <= -6:
        return 50.0 + (-6.0 - sun_altitude) / 6.0 * 30.0
    if sun_altitude < 0:
        return (-sun_altitude) / 6.0 * 50.0
    return 0.0


def _moon_score(
    moon_altitude: float,
    separation: float,
    illumination: float,
) -> float:
    if moon_altitude <= 0:
        return 100.0
    proximity = max(0.0, (120.0 - separation) / 120.0)
    penalty = 100.0 * illumination * proximity
    return max(0.0, 100.0 - penalty)


def _seeing_score(seeing_arcsec: float) -> float:
    if seeing_arcsec <= 1.0:
        return 100.0
    if seeing_arcsec >= 4.0:
        return 0.0
    return (4.0 - seeing_arcsec) / 3.0 * 100.0


def _wind_score(wind_kph: float) -> float:
    if wind_kph <= 10.0:
        return 100.0
    if wind_kph >= 50.0:
        return 0.0
    return (50.0 - wind_kph) / 40.0 * 100.0


def _precipitation_score(probability_percent: float) -> float:
    return max(0.0, min(100.0, 100.0 - probability_percent))


def _dew_score(temperature_c: float, dew_point_c: float) -> float:
    spread = temperature_c - dew_point_c
    if spread >= 5.0:
        return 100.0
    if spread <= 0.5:
        return 10.0
    return 10.0 + (spread - 0.5) / 4.5 * 90.0


def _sky_quality_score(bortle: int | None, sqm: float | None) -> float:
    if sqm is not None:
        return max(0.0, min(100.0, (sqm - 18.0) / 4.0 * 100.0))
    assert bortle is not None
    return (9.0 - bortle) / 8.0 * 100.0


def _grade(score: float | None, completeness: float) -> str:
    if score is None or completeness < 50.0:
        return "INSUFFICIENT_DATA"
    if score >= 85:
        return "EXCELLENT"
    if score >= 70:
        return "GOOD"
    if score >= 50:
        return "MARGINAL"
    return "POOR"


def evaluate_observability(request: ObservabilityRequest) -> ObservabilityResult:
    """Build an interpretable observing score without hiding missing data.

    The score is a deterministic weighted summary of only the inputs that are
    actually present. `completeness_percent` is computed against the complete
    object-specific weight set, so absent forecast/sky data can never masquerade
    as excellent conditions.
    """
    weights = _WEIGHTS[request.object_class]
    components: list[ScoreComponent] = []
    missing: list[str] = []

    def add(name: str, score: float, rationale: str) -> None:
        weight = weights.get(name)
        if weight:
            components.append(
                ScoreComponent(
                    name=name,
                    score=score,
                    weight=weight,
                    rationale=rationale,
                )
            )

    add(
        "geometry",
        _geometry_score(request.target_altitude_deg),
        f"target altitude={request.target_altitude_deg:.1f} deg",
    )
    add(
        "darkness",
        _darkness_score(request.sun_altitude_deg),
        f"Sun altitude={request.sun_altitude_deg:.1f} deg",
    )

    if "moon" in weights:
        moon_values = (
            request.moon_altitude_deg,
            request.moon_target_separation_deg,
            request.moon_illumination_fraction,
        )
        if all(value is not None for value in moon_values):
            add(
                "moon",
                _moon_score(
                    float(request.moon_altitude_deg),
                    float(request.moon_target_separation_deg),
                    float(request.moon_illumination_fraction),
                ),
                "Moon interference from altitude, angular separation and illumination",
            )
        else:
            missing.append("moon_context")

    weather = request.weather
    if weather is None:
        for key in (
            "clouds",
            "precipitation",
            "transparency",
            "seeing",
            "wind",
            "dew",
        ):
            if key in weights:
                missing.append(key)
    else:
        if weather.cloud_cover_percent is not None:
            add(
                "clouds",
                100.0 - weather.cloud_cover_percent,
                f"total cloud cover={weather.cloud_cover_percent:.0f}%",
            )
        elif "clouds" in weights:
            missing.append("clouds")

        if weather.precipitation_probability_percent is not None:
            add(
                "precipitation",
                _precipitation_score(weather.precipitation_probability_percent),
                "precipitation probability="
                f"{weather.precipitation_probability_percent:.0f}%",
            )
        elif "precipitation" in weights:
            missing.append("precipitation")

        if weather.transparency_percent is not None:
            add(
                "transparency",
                weather.transparency_percent,
                f"transparency={weather.transparency_percent:.0f}%",
            )
        elif "transparency" in weights:
            missing.append("transparency")

        if weather.seeing_arcsec is not None:
            add(
                "seeing",
                _seeing_score(weather.seeing_arcsec),
                f"seeing={weather.seeing_arcsec:.2f} arcsec",
            )
        elif "seeing" in weights:
            missing.append("seeing")

        wind_values = [
            value
            for value in (weather.wind_speed_kph, weather.wind_gust_kph)
            if value is not None
        ]
        if wind_values:
            effective_wind = max(wind_values)
            add(
                "wind",
                _wind_score(effective_wind),
                f"worst reported wind/gust={effective_wind:.1f} km/h",
            )
        elif "wind" in weights:
            missing.append("wind")

        if weather.temperature_c is not None and weather.dew_point_c is not None:
            add(
                "dew",
                _dew_score(weather.temperature_c, weather.dew_point_c),
                "dew risk from temperature-dew-point spread",
            )
        elif "dew" in weights:
            missing.append("dew")

    if "sky_quality" in weights:
        if request.sky_quality is None:
            missing.append("sky_quality")
        else:
            add(
                "sky_quality",
                _sky_quality_score(
                    request.sky_quality.bortle_class,
                    request.sky_quality.sqm_mag_arcsec2,
                ),
                f"sky quality evidence={request.sky_quality.evidence_kind.value}",
            )

    expected_weight = sum(weights.values())
    available_weight = sum(component.weight for component in components)
    completeness = (
        100.0 * available_weight / expected_weight if expected_weight else 0.0
    )

    score = None
    if available_weight:
        score = sum(
            component.score * component.weight for component in components
        ) / available_weight
        score = round(score, 2)

    return ObservabilityResult(
        score=score,
        grade=_grade(score, completeness),
        completeness_percent=round(completeness, 2),
        airmass=airmass_from_altitude_deg(request.target_altitude_deg),
        components=components,
        missing_inputs=sorted(set(missing)),
    )
