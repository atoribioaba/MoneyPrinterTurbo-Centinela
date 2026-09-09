from __future__ import annotations

import re

from app.models.astronomy import ScientificStatus
from app.models.horizon import HorizonPoint, HorizonProfile


_HORIZON_TOKEN_SPLIT = re.compile(r"[,;\n]+")


def parse_horizon_profile_text(
    text: str,
    *,
    profile_id: str,
    source_id: str,
    scientific_status: ScientificStatus = ScientificStatus.NO_VERIFICADO,
) -> HorizonProfile:
    """Parse explicit `azimuth:altitude` evidence into a local-horizon profile.

    Example: `0:5, 90:12, 180:4, 270:8`.
    This parser never creates terrain data. The caller must identify the source and
    choose the appropriate scientific-status label for the supplied profile.
    """
    tokens = [item.strip() for item in _HORIZON_TOKEN_SPLIT.split(str(text)) if item.strip()]
    if len(tokens) < 2:
        raise ValueError("horizon profile requires at least two azimuth:altitude points")

    points: list[HorizonPoint] = []
    for token in tokens:
        if token.count(":") != 1:
            raise ValueError(f"invalid horizon point: {token!r}")
        azimuth_text, altitude_text = (part.strip() for part in token.split(":", 1))
        try:
            points.append(
                HorizonPoint(
                    azimuth_deg=float(azimuth_text),
                    altitude_deg=float(altitude_text),
                )
            )
        except ValueError as exc:
            raise ValueError(f"invalid horizon point: {token!r}") from exc

    return HorizonProfile(
        profile_id=profile_id,
        points=points,
        source_ids=[source_id],
        scientific_status=scientific_status,
    )


def horizon_altitude_deg(profile: HorizonProfile, azimuth_deg: float) -> float:
    """Return the circularly interpolated local-horizon altitude at an azimuth.

    The profile is treated as periodic over 360 degrees. No terrain model or DEM is
    invented: the returned value is only an interpolation of the supplied evidence.
    """
    azimuth = float(azimuth_deg) % 360.0
    points = sorted(profile.points, key=lambda item: item.azimuth_deg)

    for point in points:
        if abs(point.azimuth_deg - azimuth) <= 1e-12:
            return point.altitude_deg

    left = points[-1]
    right = points[0]
    left_az = left.azimuth_deg - 360.0
    right_az = right.azimuth_deg
    target_az = azimuth

    for index in range(len(points) - 1):
        candidate_left = points[index]
        candidate_right = points[index + 1]
        if candidate_left.azimuth_deg < azimuth < candidate_right.azimuth_deg:
            left = candidate_left
            right = candidate_right
            left_az = left.azimuth_deg
            right_az = right.azimuth_deg
            break
    else:
        if azimuth > points[-1].azimuth_deg:
            left = points[-1]
            right = points[0]
            left_az = left.azimuth_deg
            right_az = right.azimuth_deg + 360.0
        else:
            left = points[-1]
            right = points[0]
            left_az = left.azimuth_deg - 360.0
            right_az = right.azimuth_deg

    span = right_az - left_az
    if span <= 0.0:
        raise ValueError("horizon profile interpolation span must be positive")
    fraction = (target_az - left_az) / span
    return left.altitude_deg + fraction * (right.altitude_deg - left.altitude_deg)
