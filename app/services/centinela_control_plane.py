"""Unified control-plane facade for EL CENTINELA DEL UNIVERSO.

The repository already contains many independently tested engineering services and
WebUI pages. This facade does not pretend that those pages are one executable
pipeline. It exposes the current integration truth and wraps the existing
``build_production_orchestrator`` service safely.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable

from app.models.production_orchestrator import (
    ProductionOrchestratorPlan,
    ProductionOrchestratorRequest,
)
from app.services.error_control import ErrorCategory, boundary_error
from app.services.production_orchestrator import build_production_orchestrator


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


# Core integration inventory. This is intentionally not a claim that it lists every
# Fxx engineering page in the repository; those remain individually accessible.
_ENGINEERING_INVENTORY = (
    EngineeringIntegration(
        key="astronomy",
        name="Astronomy Director",
        module="app.services.astronomy_director",
        role="Planificación astronómica con contexto temporal y evidencia.",
        status=IntegrationStatus.AVAILABLE,
        pipeline_stage="planning",
        note="Servicio y página propios; aún no es entrada directa del F51 orquestador.",
    ),
    EngineeringIntegration(
        key="story",
        name="Visual Story Graph",
        module="app.services.visual_story_graph",
        role="Estructura narrativa y secuenciación de escenas.",
        status=IntegrationStatus.AVAILABLE,
        pipeline_stage="story",
        note="Servicio y página propios; F51 recibe productos ya preparados.",
    ),
    EngineeringIntegration(
        key="material",
        name="Material Selection / Semantic Matching",
        module="app.services.material_selection",
        role="Selección y matching de material para escenas.",
        status=IntegrationStatus.AVAILABLE,
        pipeline_stage="material",
    ),
    EngineeringIntegration(
        key="cinematic",
        name="Cinematic / Reframing Toolchain",
        module="app.services.cinematic_director",
        role="Dirección cinematográfica, reframing, focal y movimiento visual.",
        status=IntegrationStatus.AVAILABLE,
        pipeline_stage="creative_video",
    ),
    EngineeringIntegration(
        key="quality",
        name="Quality Gates",
        module="app.services.quality_gates",
        role="Gate técnico/científico previo a entrega y orquestación.",
        status=IntegrationStatus.WIRED,
        pipeline_stage="quality",
        note="F51 consume QualityGatesPlan y bloquea si technical_ready no es verdadero.",
    ),
    EngineeringIntegration(
        key="delivery",
        name="Delivery Render",
        module="app.services.delivery_render",
        role="Prepara la entrega previa al render final.",
        status=IntegrationStatus.WIRED,
        pipeline_stage="delivery",
        note="F51 consume DeliveryRenderPlan y exige READY_FOR_EXPLICIT_RENDER_APPROVAL.",
    ),
    EngineeringIntegration(
        key="production_orchestrator",
        name="Production Orchestrator F51",
        module="app.services.production_orchestrator",
        role="Orquestación declarativa fail-closed previa a VideoBaseE2E/FinalizationE2E.",
        status=IntegrationStatus.WIRED,
        pipeline_stage="orchestration",
        note="No renderiza, no llama red, no autoriza publicación.",
    ),
    EngineeringIntegration(
        key="video_base",
        name="Video Base / Video Base E2E",
        module="app.services.video_base_e2e",
        role="Construcción y certificación del vídeo base.",
        status=IntegrationStatus.PARTIAL,
        pipeline_stage="video",
        note="Tiene flujo/página propios; F51 solo indica el siguiente paso, no lo ejecuta.",
    ),
    EngineeringIntegration(
        key="finalization",
        name="Finalization E2E",
        module="app.services.finalization_e2e",
        role="Finalización y autoridad de revisión humana.",
        status=IntegrationStatus.PARTIAL,
        pipeline_stage="human_review",
        note="Es downstream de F51 y conserva autoridad separada por diseño.",
    ),
    EngineeringIntegration(
        key="publication_package",
        name="Publication Package",
        module="app.services.publication_package",
        role="Materializa el paquete después de la aprobación humana válida.",
        status=IntegrationStatus.PARTIAL,
        pipeline_stage="publication_package",
        note="No equivale a publicar en una red social; esa acción permanece separada.",
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
    plan: dict[str, Any] | None
    error: dict[str, Any] | None = None


class CentinelaControlPlane:
    """Safe facade over the repository's real F51 builder function."""

    def __init__(
        self,
        builder: Callable[
            [ProductionOrchestratorRequest], ProductionOrchestratorPlan
        ] = build_production_orchestrator,
    ) -> None:
        self.builder = builder

    def build(self, request: ProductionOrchestratorRequest) -> ControlPlaneResult:
        try:
            plan = self.builder(request)
        except Exception as exc:
            error = boundary_error(
                code="control_plane_build_failed",
                category=ErrorCategory.VALIDATION,
                message=(
                    "El orquestador de producción rechazó la entrada o no pudo "
                    "construir un plan seguro."
                ),
                operation="control_plane.build",
                component="production_orchestrator",
                cause=exc,
            )
            return ControlPlaneResult(success=False, plan=None, error=error.as_dict())

        if hasattr(plan, "model_dump"):
            payload = plan.model_dump(mode="json")
        else:
            payload = {"result": str(plan)}
        return ControlPlaneResult(success=True, plan=payload)
