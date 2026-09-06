"""Unified control-plane facade for EL CENTINELA DEL UNIVERSO.

MoneyPrinterTurbo remains the rendering/generation engine. This module gives the
Centinela-specific engineering services one truthful inventory and one orchestration
surface instead of exposing unrelated modules as if they were all fully wired.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from app.services.error_control import ErrorCategory, boundary_error
from app.services.production_orchestrator import ProductionOrchestrator, ProductionPlan


class IntegrationStatus(StrEnum):
    WIRED = "wired"
    PARTIAL = "partial"
    AVAILABLE = "available_not_wired"
    PLACEHOLDER = "placeholder"


@dataclass(frozen=True, slots=True)
class EngineeringIntegration:
    key: str
    name: str
    module: str
    role: str
    status: IntegrationStatus
    pipeline_stage: str | None = None
    note: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "name": self.name,
            "module": self.module,
            "role": self.role,
            "status": self.status.value,
            "pipeline_stage": self.pipeline_stage or "—",
            "note": self.note,
        }


# This registry deliberately distinguishes "module exists" from "executed by the
# production orchestrator". It is the source used by the WebUI status page and docs.
_ENGINEERING_INVENTORY = (
    EngineeringIntegration(
        key="astronomy",
        name="Astronomy Director",
        module="app.services.astronomy_director",
        role="Planificación astronómica con contexto temporal y evidencia.",
        status=IntegrationStatus.WIRED,
        pipeline_stage="astronomy",
    ),
    EngineeringIntegration(
        key="story",
        name="Visual Story Graph",
        module="app.services.visual_story_graph",
        role="Estructura narrativa y secuenciación de escenas.",
        status=IntegrationStatus.WIRED,
        pipeline_stage="script",
    ),
    EngineeringIntegration(
        key="material",
        name="Semantic Matcher",
        module="app.services.semantic_matcher",
        role="Matching semántico guion → material.",
        status=IntegrationStatus.AVAILABLE,
        pipeline_stage="material",
        note="El handler por defecto de material del orquestador aún es passthrough.",
    ),
    EngineeringIntegration(
        key="cinematic",
        name="Cinematic Director",
        module="app.services.cinematic_director",
        role="Dirección cinematográfica y continuidad visual.",
        status=IntegrationStatus.AVAILABLE,
        note="Servicio disponible; todavía no es una etapa propia del orquestador.",
    ),
    EngineeringIntegration(
        key="smart_reframing",
        name="Smart Reframing / Focal / Ken Burns",
        module="app.services.smart_reframing",
        role="Composición 9:16 y movimiento visual inteligente.",
        status=IntegrationStatus.AVAILABLE,
        pipeline_stage="video",
        note="La etapa video del orquestador sigue siendo un placeholder.",
    ),
    EngineeringIntegration(
        key="video",
        name="Video Base Renderer",
        module="app.services.video_base_renderer",
        role="Renderizado del vídeo base.",
        status=IntegrationStatus.PLACEHOLDER,
        pipeline_stage="video",
        note="Existe renderer, pero el handler por defecto aún devuelve pending_video_render.",
    ),
    EngineeringIntegration(
        key="subtitles",
        name="Subtitles",
        module="app.services.subtitle",
        role="Generación/render de subtítulos.",
        status=IntegrationStatus.PLACEHOLDER,
        pipeline_stage="subtitles",
        note="La etapa del orquestador todavía devuelve pending_subtitle_render.",
    ),
    EngineeringIntegration(
        key="audio",
        name="Voice / TTS",
        module="app.services.voice",
        role="Narración y audio.",
        status=IntegrationStatus.PLACEHOLDER,
        pipeline_stage="audio",
        note="La etapa del orquestador todavía devuelve pending_audio_render.",
    ),
    EngineeringIntegration(
        key="quality",
        name="Quality Gates",
        module="app.services.quality_gates",
        role="Preflight de autenticidad, calidad y compliance.",
        status=IntegrationStatus.AVAILABLE,
        note="Disponible como servicio; se debe integrar como gate visible antes de revisión.",
    ),
    EngineeringIntegration(
        key="finalization",
        name="Finalization E2E",
        module="app.services.finalization_e2e",
        role="Finalización y revisión humana.",
        status=IntegrationStatus.WIRED,
        pipeline_stage="finalization",
    ),
    EngineeringIntegration(
        key="publication_package",
        name="Publication Package",
        module="app.services.publication_package",
        role="Preparación del paquete de publicación después de la revisión.",
        status=IntegrationStatus.WIRED,
        pipeline_stage="publication",
        note="Fail-closed: requiere ready_for_manual_publication.",
    ),
)


def get_engineering_inventory() -> tuple[EngineeringIntegration, ...]:
    return _ENGINEERING_INVENTORY


def inventory_summary() -> dict[str, int]:
    counts = {status.value: 0 for status in IntegrationStatus}
    for item in _ENGINEERING_INVENTORY:
        counts[item.status.value] += 1
    return counts


@dataclass(slots=True)
class ControlPlaneResult:
    success: bool
    run: dict[str, Any] | None
    error: dict[str, Any] | None = None


class CentinelaControlPlane:
    """Small facade over the production orchestrator with safe boundary errors."""

    def __init__(self, orchestrator: ProductionOrchestrator | None = None) -> None:
        self.orchestrator = orchestrator or ProductionOrchestrator()

    def execute(
        self,
        plan: ProductionPlan,
        *,
        handlers: Mapping[Any, Any] | None = None,
    ) -> ControlPlaneResult:
        try:
            run = self.orchestrator.execute(plan, handlers=handlers)
        except Exception as exc:
            error = boundary_error(
                code="control_plane_execution_failed",
                category=ErrorCategory.UNKNOWN,
                message="La ejecución del pipeline falló antes de producir un estado recuperable.",
                operation="control_plane.execute",
                component="production_orchestrator",
                cause=exc,
            )
            return ControlPlaneResult(success=False, run=None, error=error.as_dict())

        run_payload = run.as_dict() if hasattr(run, "as_dict") else {"result": str(run)}
        success = bool(getattr(run, "succeeded", False))
        return ControlPlaneResult(success=success, run=run_payload)
