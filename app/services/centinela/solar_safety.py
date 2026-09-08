from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


NASA_SOLAR_SAFETY_URL = "https://science.nasa.gov/eclipses/safety/"
AAS_OPTICS_SAFETY_URL = "https://eclipse.aas.org/eye-safety/optics-filters"


class SolarViewingMethod(str, Enum):
    NAKED_EYE = "naked_eye"
    HANDHELD_VIEWER = "handheld_viewer"
    MAGNIFIED_OPTICS = "magnified_optics"
    PINHOLE_PROJECTION = "pinhole_projection"


class SolarSafetyDecision(str, Enum):
    BLOCK = "BLOCK"
    FILTERED_METHOD_REQUIRED = "FILTERED_METHOD_REQUIRED"
    FILTERED_METHOD_ACCEPTABLE = "FILTERED_METHOD_ACCEPTABLE"
    PINHOLE_INDIRECT_ACCEPTABLE = "PINHOLE_INDIRECT_ACCEPTABLE"
    HUMAN_TOTALITY_CONFIRMATION_REQUIRED = "HUMAN_TOTALITY_CONFIRMATION_REQUIRED"


class SolarSafetyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    method: SolarViewingMethod
    bright_solar_surface_visible: bool
    authoritative_totality_context: bool = False
    handheld_viewer_iso12312_2_evidence: bool = False
    front_aperture_solar_filter_confirmed: bool = False
    manufacturer_use_instructions_confirmed: bool = False
    eyepiece_solar_filter: bool = False
    regular_sunglasses: bool = False


class SolarSafetyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    decision: SolarSafetyDecision
    reasons: list[str]
    authoritative_sources: list[str]
    software_authorizes_filter_removal: bool = False


def assess_solar_viewing_safety(request: SolarSafetyInput) -> SolarSafetyResult:
    """Fail-closed solar-viewing gate based on NASA/AAS safety principles.

    This function intentionally never authorizes removing protection for
    totality. Exact totality transitions are time/location critical and remain
    a human/authoritative-event responsibility.
    """
    sources = [NASA_SOLAR_SAFETY_URL, AAS_OPTICS_SAFETY_URL]

    if request.regular_sunglasses:
        return SolarSafetyResult(
            decision=SolarSafetyDecision.BLOCK,
            reasons=["Regular sunglasses are not solar viewing protection."],
            authoritative_sources=sources,
        )

    if request.eyepiece_solar_filter:
        return SolarSafetyResult(
            decision=SolarSafetyDecision.BLOCK,
            reasons=[
                "Eyepiece-end solar filters are rejected; concentrated sunlight reaches them after the objective."
            ],
            authoritative_sources=sources,
        )

    if request.method == SolarViewingMethod.PINHOLE_PROJECTION:
        return SolarSafetyResult(
            decision=SolarSafetyDecision.PINHOLE_INDIRECT_ACCEPTABLE,
            reasons=["Pinhole projection is indirect viewing; do not look through the pinhole."],
            authoritative_sources=sources,
        )

    if request.method == SolarViewingMethod.MAGNIFIED_OPTICS:
        if (
            request.front_aperture_solar_filter_confirmed
            and request.manufacturer_use_instructions_confirmed
        ):
            return SolarSafetyResult(
                decision=SolarSafetyDecision.FILTERED_METHOD_ACCEPTABLE,
                reasons=[
                    "Magnified optics require a purpose-built solar filter secured over the front aperture and used to its instructions."
                ],
                authoritative_sources=sources,
            )
        return SolarSafetyResult(
            decision=SolarSafetyDecision.BLOCK,
            reasons=[
                "Camera lenses, binoculars and telescopes are blocked without confirmed front-aperture solar filtration."
            ],
            authoritative_sources=sources,
        )

    if request.method == SolarViewingMethod.HANDHELD_VIEWER:
        if request.handheld_viewer_iso12312_2_evidence:
            return SolarSafetyResult(
                decision=SolarSafetyDecision.FILTERED_METHOD_ACCEPTABLE,
                reasons=[
                    "Direct unmagnified viewing uses a solar viewer with ISO 12312-2 conformity evidence."
                ],
                authoritative_sources=sources,
            )
        return SolarSafetyResult(
            decision=SolarSafetyDecision.FILTERED_METHOD_REQUIRED,
            reasons=["Safe direct solar viewing evidence is missing."],
            authoritative_sources=sources,
        )

    if request.method == SolarViewingMethod.NAKED_EYE:
        if request.bright_solar_surface_visible:
            return SolarSafetyResult(
                decision=SolarSafetyDecision.BLOCK,
                reasons=[
                    "Unfiltered direct viewing is blocked whenever any bright solar surface is visible."
                ],
                authoritative_sources=sources,
            )
        if request.authoritative_totality_context:
            return SolarSafetyResult(
                decision=SolarSafetyDecision.HUMAN_TOTALITY_CONFIRMATION_REQUIRED,
                reasons=[
                    "Software does not authorize filter removal; totality must be confirmed from the live authoritative observing context."
                ],
                authoritative_sources=sources,
            )

    return SolarSafetyResult(
        decision=SolarSafetyDecision.BLOCK,
        reasons=["Solar viewing state is not sufficiently proven for direct unfiltered viewing."],
        authoritative_sources=sources,
    )
