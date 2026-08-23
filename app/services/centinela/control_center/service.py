from __future__ import annotations

import time
from collections import Counter
from typing import Any

from app.services.astromedia import AstroMediaCatalog
from app.services.centinela.av_runtime import (
    build_audio_stage_binding,
    build_scene_stage_binding,
    build_video_base_stage_binding,
)
from app.services.centinela.media_resolver import MediaResolver, build_media_stage_binding
from app.services.centinela.orchestration import (
    JobManager,
    JobStatus,
    ProjectState,
    ProjectStateMachine,
    ResourceClass,
)
from app.services.centinela.production_spine import (
    STAGE_DESCRIPTORS,
    ProductionSpine,
    ScheduleDisposition,
    SpineStage,
    StageBinding,
)
from app.services.centinela.project_foundation import ArtifactStore
from app.services.centinela.writer_room import (
    build_fact_lock_stage_binding,
    build_writer_room_stage_binding,
)

from .media_policy import DEFAULT_MEDIA_ROOT, MediaAutomationPolicy
from .models import (
    AUTO_PIPELINE_JOB_TYPE,
    CapabilityView,
    JobView,
    LibraryView,
    MediaRefreshDecision,
    PipelineDisposition,
    PipelineStart,
    ProjectView,
)

_STAGE_LABELS = {
    SpineStage.RESEARCH: "Investigación y Fact Lock",
    SpineStage.SCRIPT: "Guion",
    SpineStage.SCENES: "Dirección de escenas",
    SpineStage.MEDIA: "Resolución de medios",
    SpineStage.AUDIO: "Voz, audio y subtítulos",
    SpineStage.VIDEO_BASE: "Vídeo base",
    SpineStage.REVIEW_PREP: "Preparación de revisión",
    SpineStage.PUBLICATION_PACKAGE: "Paquete de publicación",
}

_STATE_LABELS = {
    ProjectState.DRAFT: "Borrador",
    ProjectState.RESEARCH_READY: "Investigación lista",
    ProjectState.SCRIPT_READY: "Guion listo",
    ProjectState.SCENES_READY: "Escenas listas",
    ProjectState.MEDIA_READY: "Medios listos",
    ProjectState.AUDIO_READY: "Audio listo",
    ProjectState.VIDEO_BASE_READY: "Vídeo base listo",
    ProjectState.READY_FOR_HUMAN_REVIEW: "Listo para revisión humana",
    ProjectState.FINAL_APPROVED: "Aprobado",
    ProjectState.PUBLICATION_PACKAGE_READY: "Paquete de publicación listo",
    ProjectState.BLOCKED: "Bloqueado",
    ProjectState.NEEDS_INPUT: "Necesita decisión",
    ProjectState.FAILED: "Fallido",
    ProjectState.CANCELLED: "Cancelado",
}

_BACKEND_STATUS = {
    SpineStage.RESEARCH: "R6 Fact Lock local conectado",
    SpineStage.SCRIPT: "R6 Writer Room local conectado",
    SpineStage.SCENES: "R7 puente FinalScript → scene_plan conectado",
    SpineStage.MEDIA: "R4 Media Resolver conectado",
    SpineStage.AUDIO: "R7 Qwen3-TTS + Whisper + mastering conectado",
    SpineStage.VIDEO_BASE: "R7 social/master + preview conectado",
    SpineStage.REVIEW_PREP: "Review Studio pendiente (R8)",
    SpineStage.PUBLICATION_PACKAGE: "materialización pendiente (R8)",
}

_ACTIVE_JOB_STATUSES = {
    JobStatus.QUEUED,
    JobStatus.RUNNING,
    JobStatus.CANCEL_REQUESTED,
}


class ControlCenterError(RuntimeError):
    pass


class CentinelaControlCenter:
    """Product application service for Streamlit/API/CLI consumers."""

    def __init__(
        self,
        *,
        store: ArtifactStore | None = None,
        jobs: JobManager | None = None,
        spine: ProductionSpine | None = None,
        catalog: AstroMediaCatalog | None = None,
        media_policy: MediaAutomationPolicy | None = None,
        stage_bindings: dict[SpineStage | str, StageBinding] | None = None,
        register_default_writer_room: bool = False,
        register_default_media: bool = True,
        register_default_av: bool = False,
        max_workers: int = 2,
    ) -> None:
        if max_workers < 2:
            raise ValueError("Control Center requires max_workers >= 2 for coordinator + stage job")

        self.store = spine.store if spine is not None and store is None else (store or ArtifactStore())
        self._owns_jobs = jobs is None and spine is None

        if spine is not None:
            if spine.store is not self.store:
                raise ValueError("spine and control center must share ArtifactStore")
            self.spine = spine
            self.jobs = spine.jobs
        else:
            self.jobs = jobs or JobManager(
                self.store,
                max_workers=max_workers,
                thread_name_prefix="centinela-product",
            )
            state_machine = ProjectStateMachine(self.store)
            self.spine = ProductionSpine(
                self.store,
                state_machine=state_machine,
                jobs=self.jobs,
                max_workers=max_workers,
            )

        self.catalog = catalog or AstroMediaCatalog()
        self.media_policy = media_policy or MediaAutomationPolicy(
            self.catalog,
            media_root=DEFAULT_MEDIA_ROOT,
        )
        self._registered_stages: set[SpineStage] = set()

        if register_default_writer_room:
            self.register_stage(
                SpineStage.RESEARCH,
                build_fact_lock_stage_binding(),
            )
            self.register_stage(
                SpineStage.SCRIPT,
                build_writer_room_stage_binding(),
            )

        if register_default_media:
            self.register_stage(
                SpineStage.MEDIA,
                build_media_stage_binding(
                    MediaResolver(catalog=self.catalog),
                ),
            )

        if register_default_av:
            self.register_stage(
                SpineStage.SCENES,
                build_scene_stage_binding(),
            )
            self.register_stage(
                SpineStage.AUDIO,
                build_audio_stage_binding(),
            )
            self.register_stage(
                SpineStage.VIDEO_BASE,
                build_video_base_stage_binding(catalog=self.catalog),
            )

        for stage, binding in (stage_bindings or {}).items():
            self.register_stage(stage, binding, replace=True)

        self.jobs.register_handler(
            AUTO_PIPELINE_JOB_TYPE,
            self._pipeline_handler,
        )

    def register_stage(
        self,
        stage: SpineStage | str,
        binding: StageBinding,
        *,
        replace: bool = False,
    ) -> None:
        normalized = SpineStage(stage)
        if normalized in self._registered_stages and not replace:
            raise ValueError(f"stage already registered: {normalized.value}")
        if normalized in self._registered_stages:
            self.spine.unregister_adapter(normalized)
        self.spine.register_adapter(normalized, binding)
        self._registered_stages.add(normalized)

    def recover_runtime(self) -> dict[str, Any]:
        return self.spine.recover()

    def shutdown(self, *, wait: bool = True) -> None:
        if self._owns_jobs:
            self.jobs.shutdown(wait=wait)

    @staticmethod
    def _job_view(record: Any) -> JobView:
        return JobView(
            job_id=record.job_id,
            job_type=record.job_type,
            status=record.status,
            progress=record.progress,
            message=record.message,
            resource_class=record.resource_class,
            created_at=record.created_at,
            updated_at=record.updated_at,
            error_type=record.error_type,
            error_message=record.error_message,
        )

    def _next_action_text(
        self,
        state: ProjectState,
        next_stage: SpineStage | None,
        connected: bool,
    ) -> str:
        if state == ProjectState.READY_FOR_HUMAN_REVIEW:
            return "Revisión humana explícita requerida."
        if state == ProjectState.PUBLICATION_PACKAGE_READY:
            return "Paquete listo; la publicación continúa siendo manual."
        if state == ProjectState.FINAL_APPROVED:
            return "Preparar paquete de publicación cuando R8 esté conectado."
        if state == ProjectState.NEEDS_INPUT:
            return "Hay una decisión o entrada pendiente; revisa el proyecto."
        if state == ProjectState.BLOCKED:
            return "La producción está bloqueada; revisa el motivo antes de continuar."
        if state in {ProjectState.FAILED, ProjectState.CANCELLED}:
            return "El proyecto está en un estado terminal."
        if next_stage is None:
            return "No hay una acción automática disponible."
        label = _STAGE_LABELS[next_stage]
        if connected:
            return f"Automatización preparada para: {label}."
        return f"Capacidad pendiente de conexión: {label}."

    def project(self, project_id: str) -> ProjectView:
        manifest = self.store.load_project(project_id)
        state = self.spine.state_machine.current_state(project_id)
        status = self.spine.project_status(project_id)
        jobs = self.jobs.list_jobs(project_id=project_id)
        latest_jobs = tuple(self._job_view(item) for item in jobs[-8:])
        counts = Counter(ref.artifact_type for ref in manifest.artifacts.values())
        connected = status.next_stage in self._registered_stages if status.next_stage else False
        return ProjectView(
            project_id=manifest.project_id,
            title=manifest.title,
            state=state,
            state_label=_STATE_LABELS[state],
            next_stage=status.next_stage,
            next_action=self._next_action_text(state, status.next_stage, connected),
            capability_pending=bool(status.next_stage and not connected),
            active_job_id=status.active_job_id,
            artifact_count=len(manifest.artifacts),
            artifact_type_counts=dict(sorted(counts.items())),
            created_at=manifest.created_at,
            updated_at=manifest.updated_at,
            observation_context=dict(manifest.observation_context),
            latest_jobs=latest_jobs,
            architecture_freeze=False,
            auto_publication=False,
        )

    def projects(self) -> list[ProjectView]:
        return [self.project(row["project_id"]) for row in self.store.list_projects()]

    def create_project(
        self,
        title: str,
        *,
        observation_context: dict[str, Any] | None = None,
        auto_start: bool = True,
    ) -> tuple[ProjectView, PipelineStart | None]:
        title = str(title or "").strip()
        if not title:
            raise ValueError("El tema o título del vídeo es obligatorio.")
        manifest = self.store.create_project(
            title,
            observation_context=observation_context or {},
            metadata={
                "product": "EL CENTINELA DEL UNIVERSO",
                "created_via": "control_center",
                "auto_publication": False,
            },
        )
        view = self.project(manifest.project_id)
        started = self.start_pipeline(manifest.project_id) if auto_start else None
        return view, started

    def _active_pipeline_job(self, project_id: str):
        matches = [
            item
            for item in self.jobs.list_jobs(project_id=project_id)
            if item.job_type == AUTO_PIPELINE_JOB_TYPE
            and item.status in _ACTIVE_JOB_STATUSES
        ]
        return matches[-1] if matches else None

    def start_pipeline(self, project_id: str) -> PipelineStart:
        self.store.load_project(project_id)
        existing = self._active_pipeline_job(project_id)
        if existing is not None:
            return PipelineStart(
                project_id=project_id,
                job_id=existing.job_id,
                existing=True,
                status=existing.status,
            )
        record = self.jobs.enqueue(
            project_id,
            AUTO_PIPELINE_JOB_TYPE,
            resource_class=ResourceClass.LIGHT,
            message="Producción automática iniciada",
            auto_start=True,
        )
        return PipelineStart(
            project_id=project_id,
            job_id=record.job_id,
            existing=False,
            status=record.status,
        )

    def _media_request(self) -> tuple[dict[str, Any], MediaRefreshDecision]:
        decision = self.media_policy.decide()
        return (
            {
                "resolver": {
                    "refresh_catalog": decision.refresh_catalog,
                    "catalog_root": decision.root,
                    "import_task_artifacts": True,
                    "semantic_evidence": False,
                    "analyze_selected_focal": True,
                    "publication_eligible_only": False,
                }
            },
            decision,
        )

    def _wait_stage(
        self,
        coordinator_context: Any,
        stage_job_id: str,
        stage: SpineStage,
        ordinal: int,
    ):
        while True:
            if coordinator_context.cancel_requested:
                try:
                    self.jobs.request_cancel(
                        stage_job_id,
                        reason="cancelled from product coordinator",
                    )
                finally:
                    coordinator_context.check_cancelled()

            record = self.jobs.get_job(stage_job_id)
            if record.status not in _ACTIVE_JOB_STATUSES:
                return record

            base = min(85, 5 + ordinal * 10)
            scaled = min(9, round(record.progress * 0.09))
            coordinator_context.report_progress(
                min(95, base + scaled),
                f"{_STAGE_LABELS[stage]} · {record.progress}%",
            )
            time.sleep(0.1)

    def _pipeline_handler(self, context: Any, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        project_id = self.jobs.get_job(context.job_id).project_id
        context.report_progress(2, "Analizando estado del proyecto")

        completed_stages: list[str] = []
        media_refresh: dict[str, Any] | None = None

        for ordinal in range(12):
            context.check_cancelled()
            status = self.spine.project_status(project_id)
            state = status.state

            if state == ProjectState.READY_FOR_HUMAN_REVIEW:
                return {
                    "disposition": PipelineDisposition.WAITING_HUMAN_REVIEW.value,
                    "state": state.value,
                    "completed_stages": completed_stages,
                    "auto_publication": False,
                }
            if state == ProjectState.FINAL_APPROVED:
                if SpineStage.PUBLICATION_PACKAGE not in self._registered_stages:
                    return {
                        "disposition": PipelineDisposition.CAPABILITY_PENDING.value,
                        "state": state.value,
                        "stage": SpineStage.PUBLICATION_PACKAGE.value,
                        "completed_stages": completed_stages,
                        "auto_publication": False,
                    }
            if state == ProjectState.PUBLICATION_PACKAGE_READY:
                return {
                    "disposition": PipelineDisposition.PUBLICATION_PACKAGE_READY.value,
                    "state": state.value,
                    "completed_stages": completed_stages,
                    "auto_publication": False,
                }
            if state == ProjectState.NEEDS_INPUT:
                return {
                    "disposition": PipelineDisposition.NEEDS_INPUT.value,
                    "state": state.value,
                    "completed_stages": completed_stages,
                    "auto_publication": False,
                }
            if state == ProjectState.BLOCKED:
                return {
                    "disposition": PipelineDisposition.BLOCKED.value,
                    "state": state.value,
                    "completed_stages": completed_stages,
                    "auto_publication": False,
                }
            if state in {ProjectState.FAILED, ProjectState.CANCELLED}:
                return {
                    "disposition": PipelineDisposition.TERMINAL.value,
                    "state": state.value,
                    "completed_stages": completed_stages,
                    "auto_publication": False,
                }

            stage = status.next_stage
            if stage is None:
                return {
                    "disposition": PipelineDisposition.NO_NEXT_ACTION.value,
                    "state": state.value,
                    "completed_stages": completed_stages,
                    "auto_publication": False,
                }

            if stage not in self._registered_stages:
                context.report_progress(
                    min(95, 5 + ordinal * 10),
                    f"Capacidad pendiente: {_STAGE_LABELS[stage]}",
                )
                return {
                    "disposition": PipelineDisposition.CAPABILITY_PENDING.value,
                    "state": state.value,
                    "stage": stage.value,
                    "stage_label": _STAGE_LABELS[stage],
                    "roadmap_owner": STAGE_DESCRIPTORS[stage].future_owner,
                    "completed_stages": completed_stages,
                    "auto_publication": False,
                }

            request: dict[str, Any] = {}
            if stage == SpineStage.MEDIA:
                request, decision = self._media_request()
                media_refresh = decision.to_dict()

            schedule = self.spine.schedule_stage(
                project_id,
                stage,
                request=request,
                auto_start=True,
            )
            if schedule.disposition == ScheduleDisposition.NEEDS_INPUT or not schedule.job_id:
                return {
                    "disposition": PipelineDisposition.NEEDS_INPUT.value,
                    "state": self.spine.state_machine.current_state(project_id).value,
                    "stage": stage.value,
                    "completed_stages": completed_stages,
                    "media_refresh": media_refresh,
                    "auto_publication": False,
                }

            stage_job = self._wait_stage(context, schedule.job_id, stage, ordinal)
            if stage_job.status != JobStatus.SUCCEEDED:
                return {
                    "disposition": PipelineDisposition.STAGE_JOB_FAILED.value,
                    "state": self.spine.state_machine.current_state(project_id).value,
                    "stage": stage.value,
                    "stage_job_status": stage_job.status.value,
                    "error_type": stage_job.error_type,
                    "error_message": stage_job.error_message,
                    "completed_stages": completed_stages,
                    "media_refresh": media_refresh,
                    "auto_publication": False,
                }

            completed_stages.append(stage.value)
            context.report_progress(
                min(95, 5 + len(completed_stages) * 10),
                f"{_STAGE_LABELS[stage]} completado",
            )

        raise ControlCenterError("automatic pipeline exceeded the bounded stage loop")

    def review(
        self,
        project_id: str,
        *,
        approved: bool,
        reviewer: str,
        notes: str,
    ):
        return self.spine.record_human_review(
            project_id,
            approved=approved,
            reviewer=reviewer,
            notes=notes,
        )

    def cancel_job(self, job_id: str) -> bool:
        return self.jobs.request_cancel(job_id, reason="cancelled from Control Center")

    def capabilities(self) -> tuple[CapabilityView, ...]:
        rows = []
        for stage, descriptor in STAGE_DESCRIPTORS.items():
            rows.append(
                CapabilityView(
                    stage=stage,
                    label=_STAGE_LABELS[stage],
                    resource_class=descriptor.minimum_resource_class,
                    connected=stage in self._registered_stages,
                    backend_status=_BACKEND_STATUS[stage],
                    roadmap_owner=descriptor.future_owner,
                )
            )
        return tuple(rows)

    def library(self) -> LibraryView:
        items = list(self.catalog.list_items(True))
        providers = Counter(item.provider.value for item in items)
        rights = Counter(item.rights_status.value for item in items)
        return LibraryView(
            active_items=len(items),
            publication_eligible_items=sum(bool(item.publication_eligible) for item in items),
            provider_counts=dict(sorted(providers.items())),
            rights_counts=dict(sorted(rights.items())),
            refresh=self.media_policy.decide(),
        )

    def storage_integrity(self) -> str:
        return self.store.database_integrity_check()
