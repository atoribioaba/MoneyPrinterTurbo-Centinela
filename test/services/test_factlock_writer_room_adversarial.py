from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import GroundingFact, NarrativeAct
from app.services.centinela.writer_room import (
    CritiqueBundle,
    DraftPacket,
    FactLock,
    FinalScriptCandidate,
    FinalScriptSegment,
    ScriptClaim,
    StoryBeat,
    WriterRoom,
    WriterRoomRequest,
)
from app.services.centinela.writer_room.fact_guard import (
    FactLockQuantitativeError,
    validate_quantitative_claims,
)
from app.services.centinela.writer_room.runtime import GeneratedModel


DISTANCE_FACT_ID = "moon:distance_km"
ILLUMINATION_FACT_ID = "moon:illuminated_fraction"


def _fact_lock() -> FactLock:
    return FactLock(
        subject="La Luna",
        research_mode="GENERIC_GEOCENTRIC",
        context_hash="A" * 64,
        facts=[
            GroundingFact(
                fact_id=DISTANCE_FACT_ID,
                label_es="Distancia geocéntrica lunar",
                value=398145.0,
                unit="km",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
                source_ids=["source:test"],
            ),
            GroundingFact(
                fact_id=ILLUMINATION_FACT_ID,
                label_es="Fracción iluminada lunar",
                value=0.507,
                unit="fraction",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
                source_ids=["source:test"],
            ),
        ],
        sources=[],
        source_ids=["source:test"],
        scope_note="Fixture cuantitativo adversarial C3.",
        location_assumed=False,
        moment_basis="fixture",
        primary_source_verification_required_for_publication=True,
        generated_at_utc=datetime.now(timezone.utc),
    )


def _claim(
    statement: str = "La Luna está a 398145 km de distancia geocéntrica.",
) -> ScriptClaim:
    return ScriptClaim(
        statement=statement,
        fact_ids=[DISTANCE_FACT_ID],
        scientific_status=ScientificStatus.HECHO_VERIFICADO,
    )


def _story_arc() -> list[StoryBeat]:
    return [
        StoryBeat(
            act=act,
            intent=f"intent {act.value}",
            tension=f"tension {act.value}",
            visual_intent=f"visual {act.value}",
        )
        for act in NarrativeAct
    ]


def _segments(
    *,
    development_narration: str = (
        "La distancia geocéntrica indicada por el Fact Lock es 398145 km."
    ),
) -> list[FinalScriptSegment]:
    result = []
    for act in NarrativeAct:
        narration = (
            development_narration
            if act == NarrativeAct.DEVELOPMENT
            else "Contemplamos la Luna sin añadir cifras nuevas al Fact Lock."
        )
        result.append(
            FinalScriptSegment(
                act=act,
                narration=narration,
                visual_intent=(
                    "Material lunar directamente relacionado con la narración."
                ),
                claim_indices=[0] if act == NarrativeAct.DEVELOPMENT else [],
                estimated_seconds=8,
            )
        )
    return result


def _draft(claim: ScriptClaim | None = None) -> DraftPacket:
    return DraftPacket(
        creative_thesis=(
            "Contemplar la Luna con un único dato cuantitativo trazable, "
            "sin deformarlo durante la escritura."
        ),
        story_arc=_story_arc(),
        hook_candidates=[
            "Mira la Luna de otra forma.",
            "Una cifra cambia la escala.",
            "La distancia importa.",
        ],
        selected_hook="La distancia importa.",
        draft_narration=(
            "La Luna aparece en el cielo y el guion conserva la distancia "
            "geocéntrica exactamente dentro del margen autorizado por Fact Lock."
        ),
        claims=[claim or _claim()],
        visual_beats=[
            "Luna",
            "encuadre lunar",
            "escala",
            "clímax",
            "cierre",
        ],
    )


def _candidate(
    *,
    claim: ScriptClaim | None = None,
    narration: str | None = None,
    social_30s: str | None = None,
    development_narration: str | None = None,
) -> FinalScriptCandidate:
    return FinalScriptCandidate(
        hook="La distancia importa.",
        narration=narration
        or (
            "La Luna está ante nosotros. El Fact Lock conserva una distancia "
            "geocéntrica verificable y el guion evita introducir cifras ajenas."
        ),
        segments=_segments(
            development_narration=development_narration
            or "La distancia geocéntrica indicada por el Fact Lock es 398145 km."
        ),
        claims=[claim or _claim()],
        pronunciation_map=[],
        social_30s=social_30s
        or (
            "La Luna conserva su escala real: el guion usa sólo la distancia "
            "respaldada por el Fact Lock y no añade cifras nuevas."
        ),
        social_15s=(
            "La Luna, contada con una distancia trazable y sin cifras inventadas."
        ),
        closing_line="Seguimos mirando con rigor.",
    )


class _Runtime:
    def __init__(
        self,
        *,
        draft_claim: ScriptClaim | None = None,
        final_candidate: FinalScriptCandidate | None = None,
    ) -> None:
        self.draft_claim = draft_claim
        self.final_candidate = final_candidate

    def resolve_model(self, requested):
        return requested or "factlock-adversarial-fixture"

    def generate(self, model_type, *, model, prompt, temperature):
        if model_type is DraftPacket:
            value = _draft(self.draft_claim)
        elif model_type is CritiqueBundle:
            value = CritiqueBundle(
                science_score=9.0,
                retention_score=8.0,
                visual_score=9.0,
                adversarial_score=9.0,
            )
        elif model_type is FinalScriptCandidate:
            value = self.final_candidate or _candidate()
        else:
            raise AssertionError(model_type)
        return GeneratedModel(
            value=value,
            request_count=1,
            repaired=False,
        )


def test_writer_room_rejects_398145_km_collapsed_to_less_than_400_km():
    runtime = _Runtime(
        draft_claim=_claim("La Luna está a menos de 400 km."),
    )

    with pytest.raises(FactLockQuantitativeError, match="unsupported quantitative"):
        WriterRoom(runtime=runtime).generate(
            WriterRoomRequest(subject="La Luna"),
            _fact_lock(),
        )


def test_writer_room_rejects_same_number_with_wrong_unit():
    runtime = _Runtime(
        draft_claim=_claim("La Luna está a 398145 m de distancia geocéntrica."),
    )

    with pytest.raises(FactLockQuantitativeError, match="unsupported quantitative"):
        WriterRoom(runtime=runtime).generate(
            WriterRoomRequest(subject="La Luna"),
            _fact_lock(),
        )


def test_writer_room_rejects_numeric_tampering_outside_claims():
    candidate = _candidate(
        narration=(
            "La Luna parece próxima, pero aquí se introduce una distancia falsa "
            "de 400 km aunque el claim estructurado permanezca correcto."
        ),
    )

    with pytest.raises(FactLockQuantitativeError, match="final narration"):
        WriterRoom(runtime=_Runtime(final_candidate=candidate)).generate(
            WriterRoomRequest(subject="La Luna"),
            _fact_lock(),
        )


def test_writer_room_rejects_numeric_tampering_in_social_compression():
    candidate = _candidate(
        social_30s=(
            "La compresión social no puede convertir la distancia lunar en "
            "400 km aunque el claim estructurado original siga siendo correcto."
        ),
    )

    with pytest.raises(FactLockQuantitativeError, match="social_30s"):
        WriterRoom(runtime=_Runtime(final_candidate=candidate)).generate(
            WriterRoomRequest(subject="La Luna"),
            _fact_lock(),
        )


def test_legitimate_distance_rounding_is_not_exact_string_brittle():
    rounded = _claim("La Luna está aproximadamente a 400.000 km.")

    validate_quantitative_claims([rounded], _fact_lock())


def test_fraction_to_percentage_conversion_is_allowed_with_small_rounding():
    percentage = ScriptClaim(
        statement="La fracción iluminada es aproximadamente del 51%.",
        fact_ids=[ILLUMINATION_FACT_ID],
        scientific_status=ScientificStatus.HECHO_VERIFICADO,
    )

    validate_quantitative_claims([percentage], _fact_lock())
