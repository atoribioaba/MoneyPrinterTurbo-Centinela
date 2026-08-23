from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.models.astronomy import AstronomyBody, AstronomyContextRequest
from app.services.astronomy_core import build_astronomy_context
from app.services.astronomy_director import build_grounding_packet
from app.services.centinela.orchestration import JobCancelled, ResourceClass
from app.services.centinela.production_spine import (
    StageArtifact,
    StageBinding,
    StageResult,
)

from .models import (
    FACT_LOCK_VERSION,
    WRITER_ROOM_VERSION,
    FactLock,
    WriterRoomRequest,
)
from .room import WriterRoom


class WriterRoomSpineError(RuntimeError):
    pass


_TIME_SENSITIVE_TOKENS = (
    "hoy",
    "esta noche",
    "mañana",
    "ahora",
    "visible",
    "visibilidad",
    "desde ",
    "conjunc",
    "eclipse",
    "ocultac",
    "salida",
    "puesta",
    "amanecer",
    "atardecer",
    "crepusculo",
    "crepúsculo",
    "horizonte",
    "esta semana",
    "este fin de semana",
    "proximo",
    "próximo",
    "proxima",
    "próxima",
)

_BODY_ALIASES = {
    AstronomyBody.SUN: ("sol", "sun"),
    AstronomyBody.MOON: ("luna", "moon"),
    AstronomyBody.MERCURY: ("mercurio", "mercury"),
    AstronomyBody.VENUS: ("venus",),
    AstronomyBody.MARS: ("marte", "mars"),
    AstronomyBody.JUPITER: ("jupiter", "júpiter"),
    AstronomyBody.SATURN: ("saturno", "saturn"),
    AstronomyBody.URANUS: ("urano", "uranus"),
    AstronomyBody.NEPTUNE: ("neptuno", "neptune"),
    AstronomyBody.PLUTO: ("pluton", "plutón", "pluto"),
}

_GENERIC_SUFFIXES = (
    ":geocentric_distance_km",
    ":visual_magnitude",
    ":illuminated_fraction",
    ":constellation",
)


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(
        ch for ch in normalized if not unicodedata.combining(ch)
    ).casefold()


def _hash_facts(facts, source_ids) -> str:
    payload = {
        "facts": [item.model_dump(mode="json") for item in facts],
        "source_ids": list(source_ids),
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def _subject_is_time_sensitive(subject: str) -> bool:
    folded = _fold(subject)
    return any(_fold(token) in folded for token in _TIME_SENSITIVE_TOKENS)


def _subject_bodies(subject: str) -> list[AstronomyBody]:
    folded = _fold(subject)
    result = []
    for body, aliases in _BODY_ALIASES.items():
        if any(_fold(alias) in folded for alias in aliases):
            result.append(body)
    return result or list(AstronomyBody)


def _generic_facts(grounding):
    result = []
    for fact in grounding.facts:
        fact_id = fact.fact_id
        if fact_id == "context:moment_utc":
            result.append(fact)
            continue
        if fact_id.startswith("body:") and fact_id.endswith(_GENERIC_SUFFIXES):
            result.append(fact)
            continue
        if fact_id.startswith("moon:") and any(
            token in fact_id
            for token in (
                "phase_name",
                "illuminated_fraction",
                "distance_km",
                "angular_diameter_deg",
            )
        ):
            result.append(fact)
    return result


def _previous_output_artifact(
    context: Any,
    artifact_type: str,
):
    receipt = context.previous_receipt
    if receipt is None:
        return None

    payload = context.store.read_json(
        context.project_id,
        receipt.artifact_id,
    )
    output_ids = (
        payload.get("output_artifact_ids")
        if isinstance(payload, dict)
        else None
    )
    if not isinstance(output_ids, list):
        return None

    matches = []
    for artifact_id in output_ids:
        ref = context.store.get_artifact(
            context.project_id,
            str(artifact_id),
        )
        if ref.artifact_type == artifact_type:
            matches.append(ref)

    if len(matches) > 1:
        raise WriterRoomSpineError(
            f"previous receipt contains multiple {artifact_type} artifacts"
        )
    return matches[0] if matches else None


class FactLockStageAdapter:
    """RESEARCH bridge backed only by deterministic Astronomy Core."""

    @staticmethod
    def _explicit_astronomy_payload(
        context: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        explicit = payload.get("astronomy")
        if explicit is not None:
            return explicit if isinstance(explicit, dict) else None

        manifest = context.store.load_project(context.project_id)
        observation = manifest.observation_context
        nested = observation.get("astronomy")
        if isinstance(nested, dict):
            return nested
        if isinstance(observation.get("observer"), dict):
            return dict(observation)
        return None

    def _generic_fact_lock(
        self,
        context: Any,
        subject: str,
    ) -> FactLock:
        request = AstronomyContextRequest(
            observer={
                "latitude_deg": 0.0,
                "longitude_deg": 0.0,
                "elevation_m": 0.0,
                "timezone": "UTC",
                "name": "internal geocentric-safe filter",
            },
            moment=datetime.now(timezone.utc),
            bodies=_subject_bodies(subject),
            event_window_days=0,
            include_eclipses=False,
        )
        astronomy = build_astronomy_context(request)
        grounding = build_grounding_packet(astronomy)
        facts = _generic_facts(grounding)
        if not facts:
            raise WriterRoomSpineError(
                "generic geocentric Fact Lock produced no safe facts"
            )
        source_ids = sorted(
            {
                source_id
                for fact in facts
                for source_id in fact.source_ids
            }
        )
        return FactLock(
            subject=subject,
            research_mode="GENERIC_GEOCENTRIC",
            context_hash=_hash_facts(facts, source_ids),
            facts=facts,
            sources=astronomy.sources,
            source_ids=source_ids,
            scope_note=(
                "Fact Lock genérico: sólo conserva hechos no dependientes de "
                "la ubicación del observador. Se excluyen altitud, azimut, "
                "salida/puesta, culminación, crepúsculos y eventos locales."
            ),
            location_assumed=False,
            moment_basis="runtime_current_utc",
            primary_source_verification_required_for_publication=(
                astronomy.primary_source_verification_required_for_publication
            ),
            generated_at_utc=datetime.now(timezone.utc),
        )

    def __call__(
        self,
        context: Any,
        payload: dict[str, Any],
    ) -> StageResult:
        manifest = context.store.load_project(context.project_id)
        raw = self._explicit_astronomy_payload(context, payload)

        if raw is None and _subject_is_time_sensitive(manifest.title):
            return StageResult.needs_input(
                "RESEARCH requires explicit location/time for this "
                "observation-dependent topic; R6 will not assume them",
                artifacts=(
                    StageArtifact(
                        artifact_type="research_requirements",
                        payload={
                            "version": FACT_LOCK_VERSION,
                            "subject": manifest.title,
                            "required": {
                                "observer.latitude_deg": True,
                                "observer.longitude_deg": True,
                                "observer.timezone": True,
                                "moment": (
                                    "timezone-aware ISO-8601 recommended for "
                                    "time-dependent publication"
                                ),
                            },
                            "location_assumed": False,
                            "date_assumed": False,
                            "auto_publication": False,
                        },
                        provenance={
                            "writer_room_version": WRITER_ROOM_VERSION,
                            "scientific_guardrail": "no_location_assumption",
                        },
                    ),
                ),
                details={
                    "required_input": "observation_context.astronomy",
                    "location_assumed": False,
                    "date_assumed": False,
                },
            )

        context.report_progress(20, "RESEARCH: Astronomy Core")
        try:
            if raw is None:
                fact_lock = self._generic_fact_lock(
                    context,
                    manifest.title,
                )
                engine = "Astronomy Engine via Astronomy Core"
                engine_version = "existing"
            else:
                if not isinstance(raw, dict):
                    return StageResult.blocked(
                        "astronomy research request must be an object"
                    )
                try:
                    request = AstronomyContextRequest.model_validate(raw)
                except ValidationError as exc:
                    return StageResult.needs_input(
                        "observation context is incomplete or invalid",
                        details={
                            "error_type": type(exc).__name__,
                            "error": str(exc)[:1400],
                            "location_assumed": False,
                            "date_assumed": False,
                        },
                    )
                astronomy = build_astronomy_context(request)
                grounding = build_grounding_packet(astronomy)
                fact_lock = FactLock(
                    subject=manifest.title,
                    research_mode="OBSERVATION_CONTEXT",
                    context_hash=grounding.context_hash,
                    facts=grounding.facts,
                    sources=astronomy.sources,
                    source_ids=grounding.source_ids,
                    scope_note=astronomy.scope_note,
                    location_assumed=False,
                    moment_basis=(
                        "explicit_project_moment"
                        if request.moment is not None
                        else "runtime_current_at_execution"
                    ),
                    primary_source_verification_required_for_publication=(
                        astronomy.primary_source_verification_required_for_publication
                    ),
                    generated_at_utc=datetime.now(timezone.utc),
                )
                engine = astronomy.engine
                engine_version = astronomy.engine_version
        except JobCancelled:
            raise
        except Exception as exc:
            return StageResult.blocked(
                "Astronomy Core failed while building Fact Lock",
                details={
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1400],
                },
            )

        context.report_progress(55, "RESEARCH: Fact Lock validado")
        return StageResult.complete(
            StageArtifact(
                artifact_type="fact_lock",
                payload=fact_lock.model_dump(mode="json"),
                provenance={
                    "fact_lock_version": FACT_LOCK_VERSION,
                    "astronomy_engine": engine,
                    "astronomy_engine_version": engine_version,
                    "context_hash": fact_lock.context_hash,
                    "research_mode": fact_lock.research_mode,
                    "location_assumed": False,
                },
                metadata={
                    "fact_count": len(fact_lock.facts),
                    "source_count": len(fact_lock.sources),
                    "research_mode": fact_lock.research_mode,
                    "primary_source_verification_required_for_publication": (
                        fact_lock.primary_source_verification_required_for_publication
                    ),
                },
            ),
            message="Astronomy Core Fact Lock created",
            details={
                "context_hash": fact_lock.context_hash,
                "fact_count": len(fact_lock.facts),
                "source_count": len(fact_lock.sources),
                "research_mode": fact_lock.research_mode,
                "auto_publication": False,
            },
        )


class WriterRoomStageAdapter:
    def __init__(
        self,
        writer_room: WriterRoom | None = None,
    ) -> None:
        self.writer_room = writer_room or WriterRoom()

    def __call__(
        self,
        context: Any,
        payload: dict[str, Any],
    ) -> StageResult:
        try:
            fact_ref = _previous_output_artifact(
                context,
                "fact_lock",
            )
        except Exception as exc:
            return StageResult.blocked(
                "RESEARCH receipt is invalid",
                details={
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1200],
                },
            )

        if fact_ref is None:
            return StageResult.needs_input(
                "fact_lock artifact is required before Writer Room",
                details={"required_artifact_type": "fact_lock"},
            )

        try:
            fact_payload = context.store.read_json(
                context.project_id,
                fact_ref.artifact_id,
            )
            fact_lock = FactLock.model_validate(fact_payload)
        except (ValidationError, TypeError, ValueError) as exc:
            return StageResult.blocked(
                "fact_lock is invalid",
                details={
                    "fact_lock_artifact_id": fact_ref.artifact_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1400],
                },
            )

        manifest = context.store.load_project(context.project_id)
        raw_request = payload.get("writer_room") or {}
        if not isinstance(raw_request, dict):
            return StageResult.blocked(
                "writer_room request must be an object"
            )

        request_payload = {
            "subject": manifest.title,
            **raw_request,
        }
        try:
            request = WriterRoomRequest.model_validate(
                request_payload
            )
        except ValidationError as exc:
            return StageResult.blocked(
                "Writer Room request is invalid",
                details={
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1400],
                },
            )

        context.report_progress(12, "SCRIPT: Writer Room iniciado")
        try:
            final_script, report = self.writer_room.generate(
                request,
                fact_lock,
                report_progress=context.report_progress,
                check_cancelled=context.check_cancelled,
            )
        except JobCancelled:
            raise
        except Exception as exc:
            return StageResult.blocked(
                "Writer Room execution failed",
                details={
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1600],
                    "ollama_scope": "loopback_only",
                    "model_download_triggered": False,
                },
            )

        artifacts = (
            StageArtifact(
                artifact_type="final_script",
                payload=final_script.model_dump(mode="json"),
                input_artifact_ids=(fact_ref.artifact_id,),
                provenance={
                    "writer_room_version": WRITER_ROOM_VERSION,
                    "fact_lock_hash": fact_lock.context_hash,
                    "model_used": final_script.model_used,
                    "ollama_scope": "loopback_only",
                    "structured_output": True,
                },
                metadata={
                    "requires_human_review": True,
                    "approved_for_publication": False,
                    "llm_request_count": final_script.llm_request_count,
                },
            ),
            StageArtifact(
                artifact_type="writer_room_report",
                payload=report.model_dump(mode="json"),
                input_artifact_ids=(fact_ref.artifact_id,),
                provenance={
                    "writer_room_version": WRITER_ROOM_VERSION,
                    "fact_lock_hash": fact_lock.context_hash,
                    "model_used": report.model_used,
                },
                metadata={
                    "inference_passes": report.inference_passes,
                    "llm_request_count": report.llm_request_count,
                },
            ),
        )

        return StageResult.complete(
            *artifacts,
            message="Writer Room produced a grounded FinalScript",
            details={
                "model_used": final_script.model_used,
                "logical_stages": final_script.logical_stages,
                "inference_passes": final_script.inference_passes,
                "llm_request_count": final_script.llm_request_count,
                "requires_human_review": True,
                "approved_for_publication": False,
                "auto_publication": False,
            },
        )


def build_fact_lock_stage_binding() -> StageBinding:
    return StageBinding(
        adapter_id="fact_lock_astronomy_core_v01",
        handler=FactLockStageAdapter(),
        resource_class=ResourceClass.LIGHT,
        producer_version=WRITER_ROOM_VERSION,
        invokes_network=False,
        invokes_llm=False,
        invokes_render=False,
        auto_publication=False,
    )


def build_writer_room_stage_binding(
    writer_room: WriterRoom | None = None,
) -> StageBinding:
    return StageBinding(
        adapter_id="writer_room_v01",
        handler=WriterRoomStageAdapter(writer_room),
        resource_class=ResourceClass.MEDIUM,
        producer_version=WRITER_ROOM_VERSION,
        invokes_network=False,
        invokes_llm=True,
        invokes_render=False,
        auto_publication=False,
    )
