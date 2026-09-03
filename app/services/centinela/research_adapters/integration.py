from __future__ import annotations

from typing import Any

from app.models.publication_package import PublicationMetadata
from app.services.astromedia import AstroMediaCatalog
from app.services.centinela.control_center import CentinelaControlCenter
from app.services.centinela.orchestration import ProjectState
from app.services.centinela.production_spine import (
    ProductionSpine,
    SpineStage,
    StageStateError,
)
from app.services.centinela.project_foundation import ArtifactRef, ArtifactStore
from app.services.centinela.publication_package import (
    build_publication_package_stage_binding,
    persist_publication_package_input,
)
from app.services.centinela.writer_room import build_writer_room_stage_binding

from .conflict_gate import build_c3_external_research_binding
from .router import C3AstronomyResearchRouter


class C3ResearchControlCenter(CentinelaControlCenter):
    """Opt-in Control Center with external astronomy network access at RESEARCH only."""

    def __init__(
        self,
        *,
        store: ArtifactStore | None = None,
        catalog: AstroMediaCatalog | None = None,
        router: C3AstronomyResearchRouter | None = None,
        register_default_media: bool = True,
        register_default_av: bool = False,
        max_workers: int = 2,
        **kwargs: Any,
    ) -> None:
        if "spine" in kwargs or "stage_bindings" in kwargs:
            raise ValueError(
                "C3ResearchControlCenter owns its ProductionSpine and RESEARCH binding"
            )
        artifact_store = store or ArtifactStore()
        spine = ProductionSpine(
            artifact_store,
            max_workers=max_workers,
            allow_network_adapters=True,
            allow_exclusive_adapters=False,
        )
        research_router = router or C3AstronomyResearchRouter()
        super().__init__(
            store=artifact_store,
            spine=spine,
            catalog=catalog,
            register_default_writer_room=False,
            register_default_media=register_default_media,
            register_default_av=register_default_av,
            stage_bindings={
                SpineStage.RESEARCH: build_c3_external_research_binding(research_router),
                SpineStage.SCRIPT: build_writer_room_stage_binding(),
                SpineStage.PUBLICATION_PACKAGE: build_publication_package_stage_binding(),
            },
            max_workers=max_workers,
            **kwargs,
        )
        self.research_router = research_router
        self._c3_owned_spine = spine

    def prepare_publication_package_input(
        self,
        project_id: str,
        *,
        thumbnail_bytes: bytes,
        thumbnail_filename: str,
        title: str,
        caption: str,
        hashtags: list[str] | None = None,
        youtube_description: str | None = None,
    ) -> tuple[ArtifactRef, ArtifactRef]:
        if self.spine.state_machine.current_state(project_id) != ProjectState.FINAL_APPROVED:
            raise StageStateError("publication package input requires FINAL_APPROVED")
        review_ref = self.spine._previous_receipt(
            project_id,
            SpineStage.PUBLICATION_PACKAGE,
        )
        if review_ref is None:
            raise StageStateError(
                "publication package input requires authoritative structured Review 7/7"
            )
        metadata = PublicationMetadata(
            title=title.strip(),
            caption=caption.strip(),
            hashtags=list(hashtags or []),
            youtube_description=(
                youtube_description.strip() if youtube_description and youtube_description.strip() else None
            ),
        )
        return persist_publication_package_input(
            self.store,
            project_id=project_id,
            review_ref=review_ref,
            thumbnail_bytes=thumbnail_bytes,
            thumbnail_filename=thumbnail_filename,
            metadata=metadata,
        )

    def schedule_publication_package(self, project_id: str):
        return self.spine.schedule_stage(
            project_id,
            SpineStage.PUBLICATION_PACKAGE,
            request={},
            auto_start=True,
        )

    def shutdown(self, *, wait: bool = True) -> None:
        self._c3_owned_spine.shutdown(wait=wait)
