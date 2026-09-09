from app.services.centinela.solar_safety import (
    SolarSafetyDecision,
    SolarSafetyInput,
    SolarViewingMethod,
    assess_solar_viewing_safety,
)


def test_regular_sunglasses_never_count_as_solar_protection():
    result = assess_solar_viewing_safety(
        SolarSafetyInput(
            method=SolarViewingMethod.NAKED_EYE,
            bright_solar_surface_visible=True,
            regular_sunglasses=True,
        )
    )
    assert result.decision == SolarSafetyDecision.BLOCK


def test_magnified_optics_require_front_aperture_filter():
    blocked = assess_solar_viewing_safety(
        SolarSafetyInput(
            method=SolarViewingMethod.MAGNIFIED_OPTICS,
            bright_solar_surface_visible=True,
            handheld_viewer_iso12312_2_evidence=True,
        )
    )
    assert blocked.decision == SolarSafetyDecision.BLOCK

    filtered = assess_solar_viewing_safety(
        SolarSafetyInput(
            method=SolarViewingMethod.MAGNIFIED_OPTICS,
            bright_solar_surface_visible=True,
            front_aperture_solar_filter_confirmed=True,
            manufacturer_use_instructions_confirmed=True,
        )
    )
    assert filtered.decision == SolarSafetyDecision.FILTERED_METHOD_ACCEPTABLE


def test_eyepiece_filter_is_fail_closed():
    result = assess_solar_viewing_safety(
        SolarSafetyInput(
            method=SolarViewingMethod.MAGNIFIED_OPTICS,
            bright_solar_surface_visible=True,
            front_aperture_solar_filter_confirmed=True,
            manufacturer_use_instructions_confirmed=True,
            eyepiece_solar_filter=True,
        )
    )
    assert result.decision == SolarSafetyDecision.BLOCK


def test_totality_context_never_auto_authorizes_filter_removal():
    result = assess_solar_viewing_safety(
        SolarSafetyInput(
            method=SolarViewingMethod.NAKED_EYE,
            bright_solar_surface_visible=False,
            authoritative_totality_context=True,
        )
    )
    assert result.decision == SolarSafetyDecision.HUMAN_TOTALITY_CONFIRMATION_REQUIRED
    assert result.software_authorizes_filter_removal is False


def test_pinhole_projection_is_indirect():
    result = assess_solar_viewing_safety(
        SolarSafetyInput(
            method=SolarViewingMethod.PINHOLE_PROJECTION,
            bright_solar_surface_visible=True,
        )
    )
    assert result.decision == SolarSafetyDecision.PINHOLE_INDIRECT_ACCEPTABLE
