from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.astromedia import SearchRequest
from app.services.astromedia import AstroMediaCatalog

from .models import MediaResolverRequest, NormalizedMediaCandidate


def scene_query(scene: Any) -> str:
    keywords = [
        str(value).strip()
        for value in (getattr(scene, "material_keywords", None) or [])
        if str(value).strip()
    ]
    objects = [
        str(value).strip()
        for value in (getattr(scene, "astronomy_objects", None) or [])
        if str(value).strip()
    ]
    visual = str(getattr(scene, "visual_requirement", "") or "").strip()
    ordered = [*keywords, *objects]
    if visual:
        ordered.append(visual)
    return " ".join(dict.fromkeys(ordered)).strip()


@dataclass(slots=True)
class AstroMediaCatalogSource:
    catalog: AstroMediaCatalog
    source_id: str = "astromedia_catalog"
    invokes_network: bool = False

    def search_scene(
        self,
        scene: Any,
        request: MediaResolverRequest,
    ) -> list[NormalizedMediaCandidate]:
        results = self.catalog.search(
            SearchRequest(
                query=scene_query(scene),
                publication_eligible_only=request.publication_eligible_only,
                renderable_only=True,
                include_duplicates=False,
                limit=request.max_candidates_per_scene,
            )
        )

        return [
            NormalizedMediaCandidate(
                source_id=self.source_id,
                media_id=result.item.media_id,
                local_path=result.item.local_path,
                media_type=result.item.media_type,
                provider=result.item.provider,
                rights_status=result.item.rights_status,
                publication_eligible=result.item.publication_eligible,
                renderable=result.item.renderable,
                title=result.item.title,
                width=result.item.width,
                height=result.item.height,
                duration_seconds=result.item.duration_seconds,
                astronomy_objects=list(result.item.astronomy_objects),
                source_url=result.item.source_url,
                license_name=result.item.license_name,
                license_url=result.item.license_url,
                attribution=result.item.attribution,
                attribution_required=result.item.attribution_required,
                scientific_status=result.item.scientific_status.value,
                content_sha256=result.item.content_sha256,
                lexical_score=float(result.score),
                lexical_reasons=list(result.reasons),
            )
            for result in results
        ]
