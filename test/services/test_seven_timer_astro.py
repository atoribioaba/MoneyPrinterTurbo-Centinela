from datetime import UTC, datetime

import pytest

from app.models.observation import (
    ObservationObjectClass,
    ObservabilityRequest,
)
from app.services.centinela.observation_intelligence import evaluate_observability
from app.services.centinela.seven_timer_astro import (
    SEVEN_TIMER_TERMS_CLASSIFICATION,
    build_7timer_astro_url,
    parse_7timer_astro_payload,
)


def _payload(*, seeing=2, transparency=3):
    return {
        "product": "astro",
        "init": "2026090818",
        "dataseries": [
            {
                "timepoint": 3,
                "seeing": seeing,
                "transparency": transparency,
            }
        ],
    }


def test_7timer_url_is_machine_readable_and_contains_no_secret_material():
    url = build_7timer_astro_url(latitude=41.652, longitude=-4.729)
    assert url.startswith("https://www.7timer.info/bin/api.pl?")
    assert "product=astro" in url
    assert "output=json" in url
    assert "lat=41.652" in url
    assert "lon=-4.729" in url
    assert "key=" not in url.lower()
    assert "token=" not in url.lower()
    assert SEVEN_TIMER_TERMS_CLASSIFICATION == "FREE_TO_USE_TERMS_NON_SPDX"


def test_7timer_preserves_interior_forecast_bins_without_midpoint_fabrication():
    retrieved = datetime(2026, 9, 8, 18, 10, tzinfo=UTC)
    snapshots = parse_7timer_astro_payload(_payload(), retrieved_at=retrieved)
    assert len(snapshots) == 1
    item = snapshots[0]
    assert item.valid_at == datetime(2026, 9, 8, 21, 0, tzinfo=UTC)
    assert item.model_run_at == datetime(2026, 9, 8, 18, 0, tzinfo=UTC)
    assert item.seeing_arcsec is None
    assert item.seeing_arcsec_min == 0.5
    assert item.seeing_arcsec_max == 0.75
    assert item.transparency_percent is None
    assert item.transparency_extinction_mag_per_airmass_min == 0.4
    assert item.transparency_extinction_mag_per_airmass_max == 0.5
    assert item.provider_seeing_category == 2
    assert item.provider_transparency_category == 3
    assert item.source_id.startswith("7timer:astro:")


def test_7timer_preserves_open_ended_best_and_worst_bins():
    best = parse_7timer_astro_payload(
        _payload(seeing=1, transparency=1),
        retrieved_at=datetime(2026, 9, 8, 18, 10, tzinfo=UTC),
    )[0]
    assert best.seeing_arcsec_min is None
    assert best.seeing_arcsec_max == 0.5
    assert best.transparency_extinction_mag_per_airmass_min is None
    assert best.transparency_extinction_mag_per_airmass_max == 0.3

    worst = parse_7timer_astro_payload(
        _payload(seeing=8, transparency=8),
        retrieved_at=datetime(2026, 9, 8, 18, 10, tzinfo=UTC),
    )[0]
    assert worst.seeing_arcsec_min == 2.5
    assert worst.seeing_arcsec_max is None
    assert worst.transparency_extinction_mag_per_airmass_min == 1.0
    assert worst.transparency_extinction_mag_per_airmass_max is None


def test_observability_uses_conservative_bounds_and_preserves_source():
    conditions = parse_7timer_astro_payload(
        _payload(seeing=2, transparency=3),
        retrieved_at=datetime(2026, 9, 8, 18, 10, tzinfo=UTC),
    )[0]
    request = ObservabilityRequest(
        object_class=ObservationObjectClass.PLANETARY,
        target_altitude_deg=60,
        sun_altitude_deg=-18,
        moon_altitude_deg=-5,
        moon_target_separation_deg=120,
        moon_illumination_fraction=0.5,
        astronomy_conditions=conditions,
    )
    result = evaluate_observability(request)
    by_name = {component.name: component for component in result.components}
    assert by_name["seeing"].score == 100.0
    assert "upper-bound" in by_name["seeing"].rationale
    assert 63.0 < by_name["transparency"].score < 64.0
    assert "one-airmass transmission" in by_name["transparency"].rationale
    assert by_name["seeing"].source_ids == [conditions.source_id]
    assert conditions.source_id in result.input_source_ids


def test_open_ended_bad_bins_fail_closed_instead_of_guessing():
    conditions = parse_7timer_astro_payload(
        _payload(seeing=8, transparency=8),
        retrieved_at=datetime(2026, 9, 8, 18, 10, tzinfo=UTC),
    )[0]
    request = ObservabilityRequest(
        object_class=ObservationObjectClass.DEEP_SKY,
        target_altitude_deg=60,
        sun_altitude_deg=-20,
        moon_altitude_deg=-5,
        moon_target_separation_deg=120,
        moon_illumination_fraction=0.1,
        astronomy_conditions=conditions,
    )
    result = evaluate_observability(request)
    by_name = {component.name: component for component in result.components}
    assert by_name["seeing"].score == 0.0
    assert by_name["transparency"].score == 0.0
    assert "fail-closed" in by_name["seeing"].rationale
    assert "fail-closed" in by_name["transparency"].rationale


def test_7timer_rejects_ambiguous_or_wrong_payload_metadata():
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_7timer_astro_payload(
            _payload(),
            retrieved_at=datetime(2026, 9, 8, 18, 10),
        )

    wrong = _payload()
    wrong["product"] = "civil"
    with pytest.raises(ValueError, match="product must be astro"):
        parse_7timer_astro_payload(
            wrong,
            retrieved_at=datetime(2026, 9, 8, 18, 10, tzinfo=UTC),
        )


def test_invalid_provider_sentinel_rows_do_not_become_false_conditions():
    payload = {
        "product": "astro",
        "init": "2026090818",
        "dataseries": [
            {"timepoint": 3, "seeing": -9999, "transparency": -9999},
            {"timepoint": 6, "seeing": 4, "transparency": -9999},
        ],
    }
    snapshots = parse_7timer_astro_payload(
        payload,
        retrieved_at=datetime(2026, 9, 8, 18, 10, tzinfo=UTC),
    )
    assert len(snapshots) == 1
    assert snapshots[0].provider_seeing_category == 4
    assert snapshots[0].provider_transparency_category is None
