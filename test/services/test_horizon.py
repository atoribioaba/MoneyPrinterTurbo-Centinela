import pytest
from pydantic import ValidationError

from app.models.astronomy import ScientificStatus
from app.models.horizon import HorizonPoint, HorizonProfile
from app.services.centinela.horizon import (
    horizon_altitude_deg,
    parse_horizon_profile_text,
)


def test_horizon_text_parser_preserves_explicit_source_and_unverified_status():
    profile = parse_horizon_profile_text(
        "0:5, 90:12; 180:4\n270:8",
        profile_id="field-horizon",
        source_id="user-horizon-2026-09-09",
    )

    assert len(profile.points) == 4
    assert profile.source_ids == ["user-horizon-2026-09-09"]
    assert profile.scientific_status == ScientificStatus.NO_VERIFICADO
    assert profile.points[1].azimuth_deg == 90.0
    assert profile.points[1].altitude_deg == 12.0


def test_horizon_interpolation_returns_exact_nodes_and_linear_interior():
    profile = parse_horizon_profile_text(
        "0:0, 90:18, 180:0, 270:0",
        profile_id="fixture",
        source_id="fixture-source",
    )

    assert horizon_altitude_deg(profile, 90.0) == 18.0
    assert horizon_altitude_deg(profile, 45.0) == pytest.approx(9.0)


def test_horizon_interpolation_wraps_across_zero_azimuth():
    profile = HorizonProfile(
        profile_id="wrap",
        points=[
            HorizonPoint(azimuth_deg=10.0, altitude_deg=10.0),
            HorizonPoint(azimuth_deg=350.0, altitude_deg=30.0),
        ],
        source_ids=["fixture-source"],
    )

    assert horizon_altitude_deg(profile, 0.0) == pytest.approx(20.0)
    assert horizon_altitude_deg(profile, 360.0) == pytest.approx(20.0)


def test_horizon_profile_rejects_duplicate_azimuths():
    with pytest.raises(ValidationError, match="azimuths must be unique"):
        HorizonProfile(
            profile_id="duplicate",
            points=[
                HorizonPoint(azimuth_deg=90.0, altitude_deg=5.0),
                HorizonPoint(azimuth_deg=90.0, altitude_deg=10.0),
            ],
            source_ids=["fixture-source"],
        )


def test_horizon_text_parser_rejects_malformed_or_incomplete_evidence():
    with pytest.raises(ValueError, match="at least two"):
        parse_horizon_profile_text(
            "90:5",
            profile_id="too-small",
            source_id="fixture-source",
        )
    with pytest.raises(ValueError, match="invalid horizon point"):
        parse_horizon_profile_text(
            "0:5, not-a-point",
            profile_id="bad",
            source_id="fixture-source",
        )
