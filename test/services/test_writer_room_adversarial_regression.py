from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import (
    AstronomyDirectorError,
    GroundingFact,
    NarrativeAct,
)
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
from app.services.centinela.writer_room.room import WriterRoomError
from app.services.centinela.writer_room.runtime import (
    GeneratedModel,
    WriterRoomOllamaRuntime,
    WriterRoomRuntimeError,
)


FACT_ID = "body:saturn:constellation"


def _fact_lock(
    *,
    status: ScientificStatus = ScientificStatus.HECHO_VERIFICADO,
) -> FactLock:
    return FactLock(
        subject="Saturno",
        research_mode="GENERIC_GEOCENTRIC",
        context_hash="B" * 64,
        facts=[
            GroundingFact(
                fact_id=FACT_ID,
                label_es="Constelación de Saturno",
                value="Pisces",
                unit=None,
                scientific_status=status,
                source_ids=["source:test"],
            )
        ],
        sources=[],
        source_ids=["source:test"],
        scope_note="Fixture adversarial Writer Room C3.",
        location_assumed=False,
        moment_basis="fixture",
        primary_source_verification_required_for_publication=True,
        generated_at_utc=datetime.now(timezone.utc),
    )


def _claim(
    *,
    fact_id: str = FACT_ID,
    status: ScientificStatus = ScientificStatus.HECHO_VERIFICADO,
) -> ScriptClaim:
    return ScriptClaim(
        statement="Saturno aparece en la constelación indicada por Fact Lock.",
        fact_ids=[fact_id],
        scientific_status=status,
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


def _segments(claim_indices: list[int] | None = None) -> list[FinalScriptSegment]:
    return [
        FinalScriptSegment(
            act=act,
            narration=(
                "Saturno permanece ligado al mismo hecho astronómico "
                "controlado por Fact Lock."
            ),
            visual_intent=(
                "Material real de Saturno o del campo celeste pertinente."
            ),
            claim_indices=(claim_indices or [])
            if act == NarrativeAct.DEVELOPMENT
            else [],
            estimated_seconds=8,
        )
        for act in NarrativeAct
    ]


def _draft(claim: ScriptClaim | None = None) -> DraftPacket:
    return DraftPacket(
        creative_thesis=(
            "Construir una observación de Saturno sin permitir que el guion "
            "escape de los hechos estructurados del Fact Lock."
        ),
        story_arc=_story_arc(),
        hook_candidates=[
            "Saturno está ahí.",
            "Mira el campo de Saturno.",
            "Seguimos a Saturno.",
        ],
        selected_hook="Saturno está ahí.",
        draft_narration=(
            "Saturno está ahí. La narración mantiene el hecho estructurado "
            "sin añadir certeza ni datos ajenos al Fact Lock disponible."
        ),
        claims=[claim or _claim()],
        visual_beats=[
            "cielo",
            "Saturno",
            "campo estelar",
            "clímax",
            "cierre",
        ],
    )


def _candidate(claim: ScriptClaim | None = None) -> FinalScriptCandidate:
    return FinalScriptCandidate(
        hook="Saturno está ahí.",
        narration=(
            "Saturno está ahí. Lo contemplamos sin añadir datos externos y "
            "mantenemos el guion ligado al Fact Lock durante todo el relato."
        ),
        segments=_segments([0]),
        claims=[claim or _claim()],
        pronunciation_map=[],
        social_30s=(
            "Saturno está ahí. Una observación breve, ligada al Fact Lock y "
            "sin incorporar información astronómica externa."
        ),
        social_15s=(
            "Saturno, observado con un guion limitado a sus hechos trazables."
        ),
        closing_line="Seguimos mirando.",
    )


class _Runtime:
    def __init__(
        self,
        *,
        draft_claim: ScriptClaim | None = None,
        final_claim: ScriptClaim | None = None,
    ) -> None:
        self.draft_claim = draft_claim
        self.final_claim = final_claim
        self.resolve_calls = 0
        self.generate_calls = 0

    def resolve_model(self, requested):
        self.resolve_calls += 1
        return requested or "writer-room-adversarial-fixture"

    def generate(self, model_type, *, model, prompt, temperature):
        self.generate_calls += 1
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
            value = _candidate(self.final_claim)
        else:
            raise AssertionError(model_type)
        return GeneratedModel(
            value=value,
            request_count=1,
            repaired=False,
        )


def test_subject_mismatch_fails_before_any_model_call():
    runtime = _Runtime()

    with pytest.raises(WriterRoomError, match="subject does not match"):
        WriterRoom(runtime=runtime).generate(
            WriterRoomRequest(subject="Júpiter"),
            _fact_lock(),
        )

    assert runtime.resolve_calls == 0
    assert runtime.generate_calls == 0


def test_verified_draft_claim_cannot_launder_non_verified_fact():
    runtime = _Runtime(
        draft_claim=_claim(status=ScientificStatus.HECHO_VERIFICADO),
    )

    with pytest.raises(WriterRoomError, match="not HECHO_VERIFICADO"):
        WriterRoom(runtime=runtime).generate(
            WriterRoomRequest(subject="Saturno"),
            _fact_lock(status=ScientificStatus.NO_VERIFICADO),
        )


def test_final_claim_is_revalidated_and_cannot_introduce_unknown_fact_id():
    runtime = _Runtime(
        final_claim=_claim(fact_id="body:saturn:invented"),
    )

    with pytest.raises(WriterRoomError, match="unknown fact_ids"):
        WriterRoom(runtime=runtime).generate(
            WriterRoomRequest(subject="Saturno"),
            _fact_lock(),
        )

    assert runtime.generate_calls == 3


def test_successful_writer_room_output_remains_manual_review_only():
    final, report = WriterRoom(runtime=_Runtime()).generate(
        WriterRoomRequest(subject="Saturno"),
        _fact_lock(),
    )

    assert final.requires_human_review is True
    assert final.approved_for_publication is False
    assert final.primary_source_verification_required_for_publication is True
    assert final.llm_request_count == 3
    assert report.llm_request_count == 3


class _StructuredAdapter:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.calls = 0

    def resolve_model(self, requested):
        return requested or "structured-fixture"

    def generate_json(self, *, model, prompt, temperature, schema):
        self.calls += 1
        if not self.outputs:
            raise AssertionError("unexpected extra structured-output retry")
        return self.outputs.pop(0)


def test_structured_runtime_repairs_once_then_returns_valid_model():
    adapter = _StructuredAdapter(
        [
            "not-json",
            (
                '{"statement":"Saturno permanece ligado al Fact Lock.",'
                f'"fact_ids":["{FACT_ID}"],'
                '"scientific_status":"HECHO_VERIFICADO"}'
            ),
        ]
    )
    runtime = WriterRoomOllamaRuntime(adapter=adapter)

    generated = runtime.generate(
        ScriptClaim,
        model="structured-fixture",
        prompt="fixture",
        temperature=0.2,
    )

    assert generated.repaired is True
    assert generated.request_count == 2
    assert generated.value.fact_ids == [FACT_ID]
    assert adapter.calls == 2


def test_structured_runtime_fails_closed_after_second_invalid_output():
    adapter = _StructuredAdapter(["not-json", "still-not-json"])
    runtime = WriterRoomOllamaRuntime(adapter=adapter)

    with pytest.raises(
        WriterRoomRuntimeError,
        match="failed structured validation twice",
    ):
        runtime.generate(
            ScriptClaim,
            model="structured-fixture",
            prompt="fixture",
            temperature=0.2,
        )

    assert adapter.calls == 2


def test_runtime_wraps_model_resolution_failure_without_generation():
    class MissingModelAdapter(_StructuredAdapter):
        def resolve_model(self, requested):
            raise AstronomyDirectorError("model is not installed")

    adapter = MissingModelAdapter([])
    runtime = WriterRoomOllamaRuntime(adapter=adapter)

    with pytest.raises(WriterRoomRuntimeError, match="not installed"):
        runtime.resolve_model("missing-model")

    assert adapter.calls == 0
