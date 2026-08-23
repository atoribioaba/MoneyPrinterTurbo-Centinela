from __future__ import annotations

from datetime import datetime, timezone

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import GroundingFact, NarrativeAct
from app.services.centinela.av_runtime.audio import (
    _align_script_tokens,
    _apply_pronunciations,
    _scene_ranges,
    _scene_timings,
)
from app.services.centinela.av_runtime.scenes import (
    _allocate_durations,
    build_scene_plan,
)
from app.services.centinela.av_runtime import (
    build_audio_stage_binding,
    build_scene_stage_binding,
    build_video_base_stage_binding,
)
from app.services.centinela.orchestration import ResourceClass
from app.services.centinela.writer_room import (
    WRITER_ROOM_LOGICAL_STAGES,
    FactLock,
    FinalScript,
    FinalScriptSegment,
    PronunciationEntry,
    ScriptClaim,
)


def _fact_lock() -> FactLock:
    return FactLock(
        subject="La Luna",
        research_mode="GENERIC_GEOCENTRIC",
        context_hash="A" * 64,
        facts=[
            GroundingFact(
                fact_id="body:moon:geocentric_distance_km",
                label_es="Distancia geocéntrica lunar",
                value=384400.0,
                unit="km",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
                source_ids=["astronomy-engine"],
            )
        ],
        sources=[],
        source_ids=["astronomy-engine"],
        scope_note="Prueba determinista.",
        location_assumed=False,
        moment_basis="test",
        primary_source_verification_required_for_publication=True,
        generated_at_utc=datetime.now(timezone.utc),
    )


def _final_script() -> FinalScript:
    claim = ScriptClaim(
        statement="La Luna está a una distancia geocéntrica calculada.",
        fact_ids=["body:moon:geocentric_distance_km"],
        scientific_status=ScientificStatus.HECHO_VERIFICADO,
    )
    narrations = [
        "La Luna aparece en el cielo y abre nuestra observación.",
        "Su presencia nos permite seguir el relato con calma y precisión.",
        "En el clímax contemplamos el disco lunar con todo su detalle.",
        "Después del máximo asombro recuperamos una mirada más serena.",
        "El cierre nos devuelve al cielo y a la escala del Universo.",
    ]
    visuals = [
        "Paisaje nocturno amplio con la Luna claramente visible.",
        "Plano medio del cielo con continuidad observacional realista.",
        "Detalle teleobjetivo del disco lunar sin recreaciones artificiales.",
        "Plano estable que preserve la lectura natural del cielo.",
        "Paisaje celeste amplio para un epílogo contemplativo y limpio.",
    ]
    segments = [
        FinalScriptSegment(
            act=act,
            narration=narration,
            visual_intent=visual,
            claim_indices=[0],
            estimated_seconds=12,
        )
        for act, narration, visual in zip(
            list(NarrativeAct),
            narrations,
            visuals,
            strict=True,
        )
    ]
    return FinalScript(
        subject="La Luna",
        language="es-ES",
        audience="divulgación astronómica general",
        target_duration_seconds=60,
        creative_thesis=(
            "Contemplar la Luna como una presencia física real y "
            "científicamente comprensible."
        ),
        hook="La Luna parece cercana, pero su escala cambia al medirla.",
        narration=" ".join(narrations),
        segments=segments,
        claims=[claim],
        pronunciation_map=[
            PronunciationEntry(
                written="Luna",
                spoken_es="Luna",
            )
        ],
        social_30s=(
            "La Luna domina el cielo, y medirla transforma una escena "
            "cotidiana en una experiencia astronómica."
        ),
        social_15s=(
            "Mira la Luna: contemplarla y medirla son dos formas de "
            "entender el mismo cielo."
        ),
        closing_line="Seguimos mirando el cielo.",
        fact_lock_hash="A" * 64,
        model_used="qwen3.5:4b-q4_K_M",
        logical_stages=list(WRITER_ROOM_LOGICAL_STAGES),
        inference_passes=3,
        llm_request_count=3,
        source_ids=["astronomy-engine"],
        scientifically_grounded=True,
        requires_human_review=True,
        approved_for_publication=False,
        primary_source_verification_required_for_publication=True,
        generated_at_utc=datetime.now(timezone.utc),
        content_hash="B" * 64,
    )


def test_duration_allocator_preserves_total_and_bounds():
    values = _allocate_durations([10, 20, 40, 20, 10], 60)
    assert sum(values) == 60
    assert all(2 <= value <= 45 for value in values)


def test_scene_plan_is_deterministic_five_act_bridge():
    plan = build_scene_plan(_final_script(), _fact_lock())
    assert plan.context_hash == "A" * 64
    assert len(plan.scenes) == 5
    assert [scene.act for scene in plan.scenes] == list(NarrativeAct)
    assert plan.total_duration_seconds == 60
    assert all(not scene.ai_recreation_allowed for scene in plan.scenes)
    assert plan.scenes[0].astronomy_objects == ["Luna"]


def test_pronunciation_only_applies_token_count_safe_entries():
    entries = [
        PronunciationEntry(written="Júpiter", spoken_es="Yúpiter"),
        PronunciationEntry(
            written="NGC 224",
            spoken_es="ene ge ce doscientos veinticuatro",
        ),
    ]
    transformed, applied, deferred = _apply_pronunciations(
        ["Júpiter y NGC 224 aparecen en el relato."],
        entries,
    )
    assert "Yúpiter" in transformed[0]
    assert "Júpiter" in applied
    assert "NGC 224" in deferred


def test_script_alignment_interpolates_a_single_mismatch():
    script = ["la", "luna", "esta", "muy", "lejos", "hoy"]
    words = [
        {"start": 0.1, "end": 0.3, "word": "la"},
        {"start": 0.3, "end": 0.6, "word": "luna"},
        {"start": 0.6, "end": 0.8, "word": "está"},
        {"start": 0.8, "end": 1.0, "word": "tan"},
        {"start": 1.0, "end": 1.3, "word": "lejos"},
        {"start": 1.3, "end": 1.5, "word": "hoy"},
    ]
    timings, ratio = _align_script_tokens(script, words, 1.7)
    assert ratio >= 5 / 6
    assert len(timings) == len(script)
    assert all(end > start for start, end in timings)


def test_scene_timing_covers_whole_audio():
    texts = [
        "uno dos tres",
        "cuatro cinco seis",
    ]
    ranges = _scene_ranges(texts)
    timings = [
        (0.1, 0.2),
        (0.2, 0.3),
        (0.3, 0.4),
        (0.6, 0.7),
        (0.7, 0.8),
        (0.8, 0.9),
    ]
    scenes = _scene_timings(ranges, timings, 1.0)
    assert scenes[0].start_s == 0.0
    assert scenes[-1].end_s == 1.0
    assert abs(sum(item.duration_s for item in scenes) - 1.0) < 0.02


def test_r7_bindings_preserve_resource_and_safety_contracts():
    scene = build_scene_stage_binding()
    audio = build_audio_stage_binding()
    video = build_video_base_stage_binding()

    assert scene.resource_class == ResourceClass.MEDIUM
    assert audio.resource_class == ResourceClass.HEAVY
    assert video.resource_class == ResourceClass.HEAVY

    for binding in (scene, audio, video):
        assert binding.invokes_network is False
        assert binding.auto_publication is False

    assert scene.invokes_llm is False
    assert audio.invokes_llm is False
    assert video.invokes_llm is False
    assert audio.invokes_render is True
    assert video.invokes_render is True
