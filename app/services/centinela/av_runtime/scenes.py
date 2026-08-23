from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import (
    AstronomyVideoPlan,
    GenerationOrigin,
    NarrativeAct,
    PlanScientificClaim,
    ScenePlan,
    ShotType,
)
from app.services.centinela.orchestration import ResourceClass
from app.services.centinela.production_spine import (
    StageArtifact,
    StageBinding,
    StageResult,
)
from app.services.centinela.writer_room import FactLock, FinalScript

from .models import R7_AV_RUNTIME_VERSION


_SOURCE_PRIORITY = [
    "OWN_MEDIA",
    "ASTRONOMY_SPECIFIC_FREE",
    "NASA",
    "ESA",
    "WIKIMEDIA",
    "PEXELS",
    "PIXABAY",
    "COVERR",
    "AI_GENERATED_LAST_RESORT",
]

_STOPWORDS = {
    "para", "como", "desde", "hacia", "sobre", "entre", "cuando", "donde",
    "esta", "este", "estos", "estas", "unos", "unas", "del", "las", "los",
    "una", "uno", "con", "sin", "por", "que", "se", "su", "sus", "más",
    "pero", "muy", "escena", "plano", "imagen", "video", "vídeo",
}

_BODY_LABELS = {
    "sun": "Sol",
    "moon": "Luna",
    "mercury": "Mercurio",
    "venus": "Venus",
    "mars": "Marte",
    "jupiter": "Júpiter",
    "saturn": "Saturno",
    "uranus": "Urano",
    "neptune": "Neptuno",
    "pluto": "Plutón",
}

_STATUS_RANK = {
    ScientificStatus.HECHO_VERIFICADO: 0,
    ScientificStatus.APROXIMACION_DIVULGATIVA: 1,
    ScientificStatus.RECREACION_VISUAL: 2,
    ScientificStatus.INFERENCIA: 3,
    ScientificStatus.HIPOTESIS: 4,
    ScientificStatus.NO_VERIFICADO: 5,
}


class SceneAdapterError(RuntimeError):
    pass


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(
        ch for ch in normalized if not unicodedata.combining(ch)
    ).casefold()


def _word_tokens(value: str) -> list[str]:
    return re.findall(r"\w+", str(value or ""), flags=re.UNICODE)


def _allocate_durations(weights: list[int], total: int) -> list[int]:
    if not weights:
        raise ValueError("duration allocation requires at least one scene")
    if total < len(weights) * 2 or total > len(weights) * 45:
        raise ValueError("target duration cannot satisfy scene duration bounds")

    weights = [max(1, int(value)) for value in weights]
    weight_sum = sum(weights)
    raw = [total * value / weight_sum for value in weights]
    values = [min(45, max(2, int(value))) for value in raw]

    while sum(values) < total:
        candidates = [
            index
            for index, value in enumerate(values)
            if value < 45
        ]
        if not candidates:
            raise ValueError("cannot distribute remaining duration")
        index = max(
            candidates,
            key=lambda item: (raw[item] - values[item], weights[item], -item),
        )
        values[index] += 1

    while sum(values) > total:
        candidates = [
            index
            for index, value in enumerate(values)
            if value > 2
        ]
        if not candidates:
            raise ValueError("cannot reduce allocated duration")
        index = min(
            candidates,
            key=lambda item: (raw[item] - values[item], weights[item], item),
        )
        values[index] -= 1

    return values


def _status_for_claims(claims) -> ScientificStatus:
    if not claims:
        return ScientificStatus.APROXIMACION_DIVULGATIVA
    return max(
        (claim.scientific_status for claim in claims),
        key=lambda status: _STATUS_RANK[status],
    )


def _objects_for_claims(claims) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for claim in claims:
        for fact_id in claim.fact_ids:
            parts = fact_id.split(":")
            candidate = None
            if len(parts) >= 2 and parts[0] == "body":
                candidate = _BODY_LABELS.get(parts[1], parts[1].title())
            elif parts and parts[0] == "moon":
                candidate = "Luna"
            elif parts and parts[0] == "twilight":
                candidate = "Sol"
            if candidate and candidate.casefold() not in seen:
                seen.add(candidate.casefold())
                result.append(candidate)
    return result


def _keywords(
    subject: str,
    visual_intent: str,
    astronomy_objects: list[str],
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        value = str(value).strip()
        key = _fold(value)
        if value and key and key not in seen:
            seen.add(key)
            result.append(value)

    for value in astronomy_objects:
        add(value)

    corpus = f"{subject} {visual_intent}"
    for token in _word_tokens(corpus):
        folded = _fold(token)
        if len(folded) < 4 or folded in _STOPWORDS:
            continue
        add(token)
        if len(result) >= 8:
            break

    return result[:8]


def _shot_type(visual_intent: str, act: NarrativeAct) -> ShotType:
    folded = _fold(visual_intent)
    if "timelapse" in folded or "time lapse" in folded:
        return ShotType.TIMELAPSE
    if any(token in folded for token in ("detalle", "crater", "mancha solar")):
        return ShotType.DETAIL
    if any(token in folded for token in ("teleobjetivo", "telescopio", "disco lunar")):
        return ShotType.TELEPHOTO
    if any(token in folded for token in ("seguimiento", "tracking")):
        return ShotType.TRACKING
    if any(token in folded for token in ("horizonte", "paisaje", "panoram")):
        return ShotType.WIDE
    if act == NarrativeAct.CLIMAX:
        return ShotType.CLOSE_UP
    if act in {NarrativeAct.INTRODUCTION, NarrativeAct.EPILOGUE}:
        return ShotType.WIDE
    return ShotType.MEDIUM


def _transition(act: NarrativeAct) -> str:
    return {
        NarrativeAct.INTRODUCTION: "Corte motivado hacia el desarrollo.",
        NarrativeAct.DEVELOPMENT: "Continuidad observacional; evitar transición gratuita.",
        NarrativeAct.CLIMAX: "Corte de énfasis al punto de máximo asombro.",
        NarrativeAct.RESOLUTION: "Corte respirado tras el clímax.",
        NarrativeAct.EPILOGUE: "Fundido final sólo si favorece el cierre contemplativo.",
    }[act]


def build_scene_plan(
    final_script: FinalScript,
    fact_lock: FactLock,
) -> AstronomyVideoPlan:
    if final_script.fact_lock_hash != fact_lock.context_hash:
        raise SceneAdapterError("FinalScript and FactLock hashes do not match")
    if len(final_script.segments) != 5:
        raise SceneAdapterError("R7 requires the canonical five-act FinalScript")

    durations = _allocate_durations(
        [len(_word_tokens(segment.narration)) for segment in final_script.segments],
        final_script.target_duration_seconds,
    )

    scenes: list[ScenePlan] = []
    for index, (segment, duration) in enumerate(
        zip(final_script.segments, durations, strict=True),
        start=1,
    ):
        claims = [
            final_script.claims[item]
            for item in segment.claim_indices
        ]
        plan_claims = [
            PlanScientificClaim(
                statement=claim.statement,
                fact_ids=claim.fact_ids,
                scientific_status=claim.scientific_status,
            )
            for claim in claims
        ]
        objects = _objects_for_claims(claims)

        scenes.append(
            ScenePlan(
                scene_number=index,
                act=segment.act,
                duration_seconds=duration,
                narration=segment.narration,
                visual_requirement=segment.visual_intent,
                astronomy_objects=objects,
                shot_type=_shot_type(segment.visual_intent, segment.act),
                material_keywords=_keywords(
                    final_script.subject,
                    segment.visual_intent,
                    objects,
                ),
                source_priority=list(_SOURCE_PRIORITY),
                transition=_transition(segment.act),
                claims=plan_claims,
                ai_recreation_allowed=False,
                scientific_status=_status_for_claims(claims),
            )
        )

    return AstronomyVideoPlan(
        subject=final_script.subject,
        language=final_script.language,
        audience=final_script.audience,
        hook=final_script.hook,
        scientific_context_summary=final_script.creative_thesis,
        narrative_arc=list(NarrativeAct),
        scenes=scenes,
        epilogue=final_script.closing_line,
        external_research_required=False,
        research_questions=[],
        context_hash=fact_lock.context_hash,
        generation_origin=GenerationOrigin.LLM_VALIDATED,
        model_used=final_script.model_used,
        repair_attempted=False,
        total_duration_seconds=sum(durations),
        requires_human_review=True,
        approved_for_publication=False,
        generated_at_utc=datetime.now(timezone.utc),
    )


def _latest_ref(context: Any, artifact_type: str):
    refs = context.store.list_artifacts(
        context.project_id,
        artifact_type=artifact_type,
    )
    return refs[-1] if refs else None


class SceneStageAdapter:
    def __call__(
        self,
        context: Any,
        payload: dict[str, Any],
    ) -> StageResult:
        del payload
        final_ref = _latest_ref(context, "final_script")
        fact_ref = _latest_ref(context, "fact_lock")
        if final_ref is None or fact_ref is None:
            return StageResult.needs_input(
                "FinalScript and FactLock are required before SCENES",
                details={
                    "final_script_present": final_ref is not None,
                    "fact_lock_present": fact_ref is not None,
                },
            )

        try:
            final_script = FinalScript.model_validate(
                context.store.read_json(
                    context.project_id,
                    final_ref.artifact_id,
                )
            )
            fact_lock = FactLock.model_validate(
                context.store.read_json(
                    context.project_id,
                    fact_ref.artifact_id,
                )
            )
            plan = build_scene_plan(final_script, fact_lock)
        except (ValidationError, TypeError, ValueError, SceneAdapterError) as exc:
            return StageResult.blocked(
                "R7 scene plan could not be built from the approved Writer Room output",
                details={
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1600],
                },
            )

        context.report_progress(55, "SCENES: cinco actos materializados")

        report = {
            "version": R7_AV_RUNTIME_VERSION,
            "subject": plan.subject,
            "source_final_script_hash": final_script.content_hash,
            "source_fact_lock_hash": fact_lock.context_hash,
            "scene_count": len(plan.scenes),
            "total_duration_seconds": plan.total_duration_seconds,
            "one_scene_per_canonical_act": True,
            "reran_llm": False,
            "ai_generation_triggered": False,
            "wangp_triggered": False,
            "auto_publication": False,
        }

        return StageResult.complete(
            StageArtifact(
                artifact_type="scene_plan",
                payload=plan.model_dump(mode="json"),
                input_artifact_ids=(
                    final_ref.artifact_id,
                    fact_ref.artifact_id,
                ),
                provenance={
                    "av_runtime_version": R7_AV_RUNTIME_VERSION,
                    "source_final_script_hash": final_script.content_hash,
                    "fact_lock_hash": fact_lock.context_hash,
                    "deterministic_bridge": True,
                },
                metadata={
                    "scene_count": len(plan.scenes),
                    "total_duration_seconds": plan.total_duration_seconds,
                    "requires_human_review": True,
                },
            ),
            StageArtifact(
                artifact_type="scene_plan_report",
                payload=report,
                input_artifact_ids=(
                    final_ref.artifact_id,
                    fact_ref.artifact_id,
                ),
                provenance={
                    "av_runtime_version": R7_AV_RUNTIME_VERSION,
                    "deterministic_bridge": True,
                },
            ),
            message="R7 converted FinalScript into the canonical scene plan",
            details={
                "scene_count": len(plan.scenes),
                "reran_llm": False,
                "auto_publication": False,
            },
        )


def build_scene_stage_binding() -> StageBinding:
    return StageBinding(
        adapter_id="r7_scene_adapter_v01",
        handler=SceneStageAdapter(),
        resource_class=ResourceClass.MEDIUM,
        producer_version=R7_AV_RUNTIME_VERSION,
        invokes_network=False,
        invokes_llm=False,
        invokes_render=False,
        auto_publication=False,
    )
