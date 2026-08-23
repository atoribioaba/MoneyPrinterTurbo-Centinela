from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import GroundingFact, NarrativeAct
from app.services.centinela.control_center import (
    CentinelaControlCenter,
    PipelineDisposition,
)
from app.services.centinela.orchestration import JobStatus, ProjectState
from app.services.centinela.production_spine import (
    SpineStage,
    StageArtifact,
    StageBinding,
    StageResult,
)
from app.services.centinela.project_foundation import ArtifactStore
from app.services.centinela.writer_room import (
    CritiqueBundle,
    DraftPacket,
    FactLock,
    FinalScriptCandidate,
    FinalScriptSegment,
    PronunciationEntry,
    ScriptClaim,
    StoryBeat,
    WriterRoom,
    WriterRoomRequest,
    build_writer_room_stage_binding,
)
from app.services.centinela.writer_room.runtime import GeneratedModel


class FakeCatalog:
    def list_items(self, active_only=True):
        return []


class FakePolicy:
    def decide(self):
        raise AssertionError("media policy must not run before MEDIA")


def fact(
    fact_id: str,
    value,
    *,
    status=ScientificStatus.HECHO_VERIFICADO,
):
    return GroundingFact(
        fact_id=fact_id,
        label_es=fact_id,
        value=value,
        unit=None,
        scientific_status=status,
        source_ids=[],
    )


def fact_lock(subject="Saturno"):
    return FactLock(
        subject=subject,
        research_mode="OBSERVATION_CONTEXT",
        context_hash="A" * 64,
        facts=[
            fact("context:moment_utc", "2026-08-23T20:00:00+00:00"),
            fact("observer:latitude_deg", 0.0),
            fact("observer:longitude_deg", 0.0),
            fact("body:saturn:altitude_apparent_deg", 25.0),
            fact("body:saturn:azimuth_deg", 120.0),
        ],
        sources=[],
        source_ids=[],
        scope_note="test",
        location_assumed=False,
        moment_basis="explicit_project_moment",
        generated_at_utc=datetime.now(timezone.utc),
    )


def claim():
    return ScriptClaim(
        statement="Saturno tiene una altitud aparente de 25 grados.",
        fact_ids=["body:saturn:altitude_apparent_deg"],
        scientific_status=ScientificStatus.HECHO_VERIFICADO,
    )


def story_arc():
    return [
        StoryBeat(
            act=act,
            intent=f"intent {act.value}",
            tension=f"tension {act.value}",
            visual_intent=f"visual {act.value}",
        )
        for act in NarrativeAct
    ]


def segments():
    return [
        FinalScriptSegment(
            act=act,
            narration=(
                "Contemplamos Saturno y mantenemos sólo la información "
                "respaldada por el Fact Lock."
            ),
            visual_intent=(
                "Saturno real o material astronómico directamente relacionado."
            ),
            claim_indices=[0] if act == NarrativeAct.DEVELOPMENT else [],
            estimated_seconds=8,
        )
        for act in NarrativeAct
    ]


class FakeRuntime:
    def resolve_model(self, requested):
        return requested or "fake-local-model"

    def generate(self, model_type, *, model, prompt, temperature):
        if model_type is DraftPacket:
            value = DraftPacket(
                creative_thesis=(
                    "Observar Saturno como una presencia real del cielo, "
                    "sin convertirlo en una ficha enciclopédica."
                ),
                story_arc=story_arc(),
                hook_candidates=[
                    "Saturno está ahí.",
                    "Busca este punto del cielo.",
                    "Un planeta, sin artificios.",
                ],
                selected_hook="Saturno está ahí.",
                draft_narration=(
                    "Saturno está ahí. Lo observamos con los datos "
                    "verificados del Fact Lock y sin añadir cifras externas."
                ),
                claims=[claim()],
                visual_beats=[
                    "cielo",
                    "Saturno",
                    "encuadre",
                    "clímax",
                    "cierre",
                ],
            )
        elif model_type is CritiqueBundle:
            value = CritiqueBundle(
                science_score=9.0,
                retention_score=8.0,
                visual_score=9.0,
                adversarial_score=9.0,
            )
        elif model_type is FinalScriptCandidate:
            value = FinalScriptCandidate(
                hook="Saturno está ahí.",
                narration=(
                    "Saturno está ahí. Lo seguimos con una narración "
                    "contenida, visual y respaldada por el Fact Lock."
                ),
                segments=segments(),
                claims=[claim()],
                pronunciation_map=[
                    PronunciationEntry(
                        written="Saturno",
                        spoken_es="Saturno",
                    )
                ],
                social_30s=(
                    "Saturno está ahí. Una observación breve y rigurosa, "
                    "con los datos verificados del Fact Lock."
                ),
                social_15s=(
                    "Saturno está ahí: observa el cielo con datos verificados."
                ),
                closing_line="Seguimos mirando.",
            )
        else:
            raise AssertionError(model_type)

        return GeneratedModel(
            value=value,
            request_count=1,
            repaired=False,
        )


def test_writer_room_builds_grounded_final_script():
    room = WriterRoom(runtime=FakeRuntime())
    final, report = room.generate(
        WriterRoomRequest(subject="Saturno"),
        fact_lock(),
    )
    assert final.version == "writer-room-v0.1"
    assert final.model_used == "fake-local-model"
    assert final.llm_request_count == 3
    assert final.requires_human_review is True
    assert final.approved_for_publication is False
    assert report.final_script_hash == final.content_hash
    assert [item.act for item in final.segments] == list(NarrativeAct)


def test_writer_room_rejects_unknown_fact_id():
    bad = claim().model_copy(update={"fact_ids": ["body:saturn:invented"]})

    class BadRuntime(FakeRuntime):
        def generate(self, model_type, *, model, prompt, temperature):
            result = super().generate(
                model_type,
                model=model,
                prompt=prompt,
                temperature=temperature,
            )
            if model_type is DraftPacket:
                result = GeneratedModel(
                    value=result.value.model_copy(update={"claims": [bad]}),
                    request_count=1,
                    repaired=False,
                )
            return result

    with pytest.raises(Exception, match="unknown fact_ids"):
        WriterRoom(runtime=BadRuntime()).generate(
            WriterRoomRequest(subject="Saturno"),
            fact_lock(),
        )


def fake_script_binding():
    def handler(context, payload):
        return StageResult.complete(
            StageArtifact(
                artifact_type="final_script",
                payload={"test": True},
            ),
            message="fake script",
        )

    return StageBinding(
        adapter_id="fake_script_r6_test",
        handler=handler,
        resource_class="MEDIUM",
    )


def service(tmp_path, *, bindings=None):
    return CentinelaControlCenter(
        store=ArtifactStore(tmp_path / "centinela"),
        catalog=FakeCatalog(),
        media_policy=FakePolicy(),
        stage_bindings=bindings or {},
        register_default_writer_room=True,
        register_default_media=False,
        max_workers=2,
    )


def test_control_center_registers_r6_research_and_script(tmp_path):
    app = service(tmp_path)
    try:
        by_stage = {
            item.stage: item
            for item in app.capabilities()
        }
        assert by_stage[SpineStage.RESEARCH].connected is True
        assert by_stage[SpineStage.SCRIPT].connected is True
        assert by_stage[SpineStage.SCENES].connected is False
    finally:
        app.shutdown()


def test_generic_subject_builds_geocentric_fact_lock_automatically(tmp_path):
    app = service(
        tmp_path,
        bindings={SpineStage.SCRIPT: fake_script_binding()},
    )
    try:
        project, start = app.create_project(
            "Saturno",
            auto_start=True,
        )
        record = app.jobs.wait(start.job_id, timeout=30)
        assert record.status == JobStatus.SUCCEEDED
        assert record.result["stage"] == SpineStage.SCENES.value
        assert app.project(project.project_id).state == ProjectState.SCRIPT_READY

        refs = app.store.list_artifacts(
            project.project_id,
            artifact_type="fact_lock",
        )
        payload = app.store.read_json(
            project.project_id,
            refs[-1].artifact_id,
        )
        assert payload["research_mode"] == "GENERIC_GEOCENTRIC"
        assert payload["location_assumed"] is False
        assert not any(
            item["fact_id"].startswith("observer:")
            for item in payload["facts"]
        )
        assert not any(
            "altitude_apparent_deg" in item["fact_id"]
            for item in payload["facts"]
        )
    finally:
        app.shutdown()


def test_time_sensitive_subject_without_observer_needs_input(tmp_path):
    app = service(
        tmp_path,
        bindings={SpineStage.SCRIPT: fake_script_binding()},
    )
    try:
        project, start = app.create_project(
            "Saturno esta noche",
            auto_start=True,
        )
        record = app.jobs.wait(start.job_id, timeout=15)
        assert record.status == JobStatus.SUCCEEDED
        assert record.result["disposition"] == PipelineDisposition.NEEDS_INPUT.value
        assert app.project(project.project_id).state == ProjectState.NEEDS_INPUT

        requirements = app.store.list_artifacts(
            project.project_id,
            artifact_type="research_requirements",
        )
        assert requirements
        payload = app.store.read_json(
            project.project_id,
            requirements[-1].artifact_id,
        )
        assert payload["location_assumed"] is False
        assert payload["date_assumed"] is False
    finally:
        app.shutdown()


def test_explicit_observer_runs_fact_lock_and_script_then_stops_scenes(tmp_path):
    app = service(
        tmp_path,
        bindings={SpineStage.SCRIPT: fake_script_binding()},
    )
    try:
        project, start = app.create_project(
            "Saturno esta noche",
            observation_context={
                "astronomy": {
                    "observer": {
                        "latitude_deg": 0.0,
                        "longitude_deg": 0.0,
                        "elevation_m": 0.0,
                        "timezone": "UTC",
                        "name": "R6 test observer",
                    },
                    "moment": "2026-08-23T20:00:00+00:00",
                    "bodies": ["saturn"],
                    "event_window_days": 1,
                    "include_eclipses": False,
                }
            },
            auto_start=True,
        )
        record = app.jobs.wait(start.job_id, timeout=30)
        assert record.status == JobStatus.SUCCEEDED
        assert record.result["disposition"] == PipelineDisposition.CAPABILITY_PENDING.value
        assert record.result["stage"] == SpineStage.SCENES.value
        assert record.result["completed_stages"] == [
            SpineStage.RESEARCH.value,
            SpineStage.SCRIPT.value,
        ]
        assert app.project(project.project_id).state == ProjectState.SCRIPT_READY

        fact_refs = app.store.list_artifacts(
            project.project_id,
            artifact_type="fact_lock",
        )
        fact_payload = app.store.read_json(
            project.project_id,
            fact_refs[-1].artifact_id,
        )
        assert fact_payload["research_mode"] == "OBSERVATION_CONTEXT"
        assert fact_payload["subject"] == "Saturno esta noche"
    finally:
        app.shutdown()


def test_writer_room_binding_is_local_medium_and_no_autopublish():
    binding = build_writer_room_stage_binding(
        WriterRoom(runtime=FakeRuntime())
    )
    assert binding.resource_class.value == "MEDIUM"
    assert binding.invokes_llm is True
    assert binding.invokes_network is False
    assert binding.invokes_render is False
    assert binding.auto_publication is False
