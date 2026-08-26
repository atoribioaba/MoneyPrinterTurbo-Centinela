from __future__ import annotations

from datetime import datetime, timezone

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import GroundingFact, NarrativeAct
from app.services.centinela.av_runtime.scenes import build_scene_plan
from app.services.centinela.writer_room import (
    WRITER_ROOM_LOGICAL_STAGES,
    FactLock,
    FinalScript,
    FinalScriptSegment,
    ScriptClaim,
)


def _fact_lock() -> FactLock:
    return FactLock(
        subject="La Luna",
        research_mode="GENERIC_GEOCENTRIC",
        context_hash="D" * 64,
        facts=[
            GroundingFact(
                fact_id="body:moon:geocentric_distance_km",
                label_es="Distancia geocentrica lunar",
                value=384400.0,
                unit="km",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
                source_ids=["source:fixture"],
            ),
            GroundingFact(
                fact_id="context:moment_utc",
                label_es="Momento UTC",
                value="2026-08-25T23:00:00Z",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
                source_ids=["source:fixture"],
            ),
        ],
        sources=[],
        source_ids=["source:fixture"],
        scope_note="Contrato hermetico V31 scene-5 grounding.",
        location_assumed=False,
        moment_basis="fixture UTC",
        primary_source_verification_required_for_publication=True,
        generated_at_utc=datetime.now(timezone.utc),
    )


def _final_script() -> FinalScript:
    moon_claim = ScriptClaim(
        statement="La Luna tiene una distancia geocentrica calculada.",
        fact_ids=["body:moon:geocentric_distance_km"],
        scientific_status=ScientificStatus.HECHO_VERIFICADO,
    )
    moment_claim = ScriptClaim(
        statement="La observacion corresponde al instante fijado por FactLock.",
        fact_ids=["context:moment_utc"],
        scientific_status=ScientificStatus.HECHO_VERIFICADO,
    )

    narrations = [
        "La Luna abre nuestra observacion.",
        "Su escala fisica conduce el desarrollo.",
        "El disco lunar concentra el climax.",
        "La medida devuelve contexto a la escena.",
        "La Luna queda como referencia luminosa para cerrar la observacion.",
    ]
    visuals = [
        "Vista realista de la Luna sobre el cielo nocturno.",
        "Plano lunar estable con lectura observacional.",
        "Detalle del disco lunar sin recreacion artificial.",
        "Plano lunar que mantenga continuidad cientifica.",
        "Vista cenital centrada en el satelite lunar como punto de referencia estelar.",
    ]

    segments = []
    for index, (act, narration, visual) in enumerate(
        zip(list(NarrativeAct), narrations, visuals, strict=True)
    ):
        segments.append(
            FinalScriptSegment(
                act=act,
                narration=narration,
                visual_intent=visual,
                claim_indices=[0 if index < 4 else 1],
                estimated_seconds=12,
            )
        )

    return FinalScript(
        subject="La Luna",
        language="es-ES",
        audience="divulgacion astronomica general",
        target_duration_seconds=60,
        creative_thesis="Observar la Luna con trazabilidad cientifica.",
        hook="La Luna transforma el cielo cuando la medimos.",
        narration=" ".join(narrations),
        segments=segments,
        claims=[moon_claim, moment_claim],
        pronunciation_map=[],
        social_30s="La Luna como referencia observacional y cientifica.",
        social_15s="Mirar la Luna tambien es medirla.",
        closing_line="Seguimos mirando el cielo.",
        fact_lock_hash="D" * 64,
        model_used="cloud-cert-fixture",
        logical_stages=list(WRITER_ROOM_LOGICAL_STAGES),
        inference_passes=3,
        llm_request_count=3,
        source_ids=["source:fixture"],
        scientifically_grounded=True,
        requires_human_review=True,
        approved_for_publication=False,
        primary_source_verification_required_for_publication=True,
        generated_at_utc=datetime.now(timezone.utc),
        content_hash="E" * 64,
    )


def test_scene5_keeps_weak_lexical_lunar_hint_without_inventing_strong_object():
    plan = build_scene_plan(_final_script(), _fact_lock())
    scene5 = plan.scenes[4]

    # The only scene-5 claim is context:moment_utc, so SCENES must not invent a
    # strong astronomy object merely because the visual says Moon/Luna.
    assert scene5.astronomy_objects == []

    # The subject/visual is still allowed to provide a weak lexical hint. This is
    # exactly the safe bridge needed by the V31 epilogue class: MaterialSelector
    # can use lexical evidence for a genuinely generic lunar visual while C2.11J
    # still rejects generic Moon for specific scientific requirements.
    assert any(value.casefold() == "luna" for value in scene5.material_keywords)
    assert "lunar" in scene5.visual_requirement.casefold()
    assert scene5.ai_recreation_allowed is False
