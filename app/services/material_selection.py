from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

from app.models.astromedia import Provider, Rights
from app.models.material_selection import (
    MaterialCandidate,
    MaterialSelectionPlan,
    MaterialSelectionRequest,
    SceneMaterialSelection,
    SelectionStatus,
)
from app.services.astromedia import AstroMediaCatalog


SELECTOR_VERSION = "material-selection-v0.1-c2.11j"

PROVIDER_SCORE = {
    Provider.OWN_MEDIA: 8.0,
    Provider.NASA: 4.0,
    Provider.ESA: 4.0,
    Provider.WIKIMEDIA: 4.0,
    Provider.LOCAL_MEDIA: 2.0,
    Provider.PEXELS: 1.0,
    Provider.PIXABAY: 1.0,
    Provider.COVERR: 1.0,
    Provider.OTHER: 0.0,
    Provider.AI_GENERATED: -12.0,
}

RIGHTS_SCORE = {
    Rights.CONFIRMED_OWNED: 5.0,
    Rights.VERIFIED_LICENSE: 4.0,
    Rights.UNVERIFIED: -2.0,
    Rights.RESTRICTED: -1000.0,
}


# C2.11J body aliases are lexical evidence only. They deliberately do not
# canonicalize ScenePlan.astronomy_objects, so "Luna" never manufactures a
# strong object_overlap with catalog object "moon".
_BODY_ALIASES = {
    "luna": "moon",
    "lunar": "moon",
    "moon": "moon",
    "sol": "sun",
    "solar": "sun",
    "sun": "sun",
    "mercurio": "mercury",
    "mercury": "mercury",
    "venus": "venus",
    "marte": "mars",
    "mars": "mars",
    "jupiter": "jupiter",
    "saturno": "saturn",
    "saturn": "saturn",
    "urano": "uranus",
    "uranus": "uranus",
    "neptuno": "neptune",
    "neptune": "neptune",
    "pluton": "pluto",
    "pluto": "pluto",
}

# Scientific aliases are used only for lexical/specificity evidence. This lets
# Spanish Writer output match English scientific metadata without weakening the
# strong-object contract.
_SCIENTIFIC_ALIASES = {
    "fase": "phase",
    "fraccion": "fraction",
    "iluminada": "illuminated",
    "iluminado": "illuminated",
    "magnitud": "magnitude",
    "brillo": "brightness",
    "diametro": "diameter",
    "geometria": "geometry",
    "distancia": "distance",
    "constelacion": "constellation",
    "mapa": "map",
    "coordenada": "coordinate",
    "coordenadas": "coordinates",
    "posicion": "position",
    "eclipse": "eclipse",
    "ocultacion": "occultation",
    "transito": "transit",
    "conjuncion": "conjunction",
    "separacion": "separation",
    "altitud": "altitude",
    "azimut": "azimuth",
    "ascension": "ascension",
    "declinacion": "declination",
    "elongacion": "elongation",
    "perihelio": "perihelion",
    "afelio": "aphelion",
    "terminador": "terminator",
    "crater": "crater",
    "latitud": "latitude",
    "longitud": "longitude",
    "libracion": "libration",
    "orbita": "orbit",
    "orbital": "orbital",
    "inclinacion": "inclination",
}

_TOKEN_ALIASES = {**_BODY_ALIASES, **_SCIENTIFIC_ALIASES}

# Specificity is activated by a positive scientific vocabulary, not by every
# uncommon prose word. This prevents generic phrasing such as "de forma
# astronomicamente pertinente" from becoming a fake scientific requirement.
_SCIENTIFIC_SPECIFICITY_MARKERS = {
    "phase",
    "fraction",
    "illuminated",
    "magnitude",
    "brightness",
    "diameter",
    "angular",
    "geometry",
    "distance",
    "constellation",
    "map",
    "coordinate",
    "coordinates",
    "position",
    "eclipse",
    "occultation",
    "transit",
    "conjunction",
    "separation",
    "altitude",
    "azimuth",
    "ascension",
    "declination",
    "elongation",
    "perihelion",
    "aphelion",
    "terminator",
    "crater",
    "sunspot",
    "latitude",
    "longitude",
    "libration",
    "albedo",
    "velocity",
    "orbit",
    "orbital",
    "inclination",
}

_GENERIC_SPECIFICITY_TOKENS = {
    "astronomia",
    "astronomical",
    "astronomico",
    "astronomica",
    "astronomicamente",
    "pertinente",
    "forma",
    "cielo",
    "sky",
    "night",
    "noche",
    "nocturno",
    "imagen",
    "image",
    "video",
    "vista",
    "view",
    "plano",
    "scene",
    "escena",
    "centrada",
    "centrado",
    "centered",
    "cenital",
    "satelite",
    "satellite",
    "lunar",
    "solar",
    # "eclipse" activates specificity, but the generic event class is not
    # sufficient evidence for a requested subtype such as partial/total/diamond-ring.
    "eclipse",
    "mostrando",
    "mostrar",
    "showing",
    "show",
    "punto",
    "point",
    "referencia",
    "reference",
    "estelar",
    "stellar",
    "superficie",
    "surface",
    "disco",
    "disc",
    "representacion",
    "representation",
    "visual",
    "real",
    "sobre",
    "over",
    "dentro",
    "inside",
    "con",
    "with",
    "sin",
    "without",
    "para",
    "from",
    "desde",
    "hacia",
    "del",
    "de",
    "las",
    "los",
    "una",
    "uno",
    "the",
    "and",
    "que",
    "como",
    "por",
}
_GENERIC_SPECIFICITY_TOKENS.update(_BODY_ALIASES)
_GENERIC_SPECIFICITY_TOKENS.update(_BODY_ALIASES.values())


class MaterialSelectionError(RuntimeError):
    pass


def _fold(value):
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold()


def _tokens(value):
    raw = {
        token for token in re.findall(r"[a-z0-9_]+", _fold(value)) if len(token) >= 2
    }
    return raw | {_TOKEN_ALIASES[token] for token in raw if token in _TOKEN_ALIASES}


def _objects(values):
    return {_fold(value) for value in (values or []) if str(value).strip()}


def _scene_terms(scene):
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
    query = " ".join([*keywords, *objects]).strip() or visual
    return query, keywords, objects, visual


def _specificity_terms(keywords, objects, visual):
    """Return scene-specific evidence terms only for scientific requirements.

    Generic single-object scenes remain permissive. Once a recognized
    scientific discriminator is present, object identity alone is insufficient
    and the asset must carry secondary evidence for the requested semantics.
    """

    all_terms = _tokens(" ".join([*keywords, visual]))
    if not (all_terms & _SCIENTIFIC_SPECIFICITY_MARKERS):
        return set()

    object_tokens = _tokens(" ".join(objects))
    generic = _GENERIC_SPECIFICITY_TOKENS | object_tokens | {
        _BODY_ALIASES.get(token, token) for token in object_tokens
    }
    return {
        token
        for token in all_terms - generic
        if len(token) >= 4 or token.isdigit()
    }


def _item_evidence_tokens(item):
    return _tokens(
        " ".join(
            [
                str(item.title or ""),
                " ".join(item.tags or []),
                str(item.search_term or ""),
                str(item.description or ""),
                str(item.filename or ""),
                " ".join(item.astronomy_objects or []),
            ]
        )
    )


def _specificity_evidence(item, keywords, objects, visual):
    required = _specificity_terms(keywords, objects, visual)
    if not required:
        return True, set(), set()
    overlap = required & _item_evidence_tokens(item)
    return bool(overlap), required, overlap


def _plan_subject(plan):
    return str(
        getattr(plan, "subject", "") or getattr(plan, "topic", "") or "Astronomy video"
    ).strip()


def _scene_key(plan, scene_number):
    context_hash = str(
        getattr(plan, "context_hash", "")
        or getattr(plan, "astronomy_context_hash", "")
        or ""
    ).strip()
    if not context_hash:
        context_hash = _fold(_plan_subject(plan)).replace(" ", "_")
    return f"{context_hash}:scene:{scene_number}"


def _score(item, keywords, objects, visual, reuse_count):
    object_overlap = sorted(_objects(objects) & _objects(item.astronomy_objects))
    wanted = _tokens(" ".join([*keywords, visual]))
    title = wanted & _tokens(item.title)
    tags = wanted & _tokens(" ".join(item.tags))
    search = wanted & _tokens(item.search_term)
    description = wanted & _tokens(item.description)
    filename = wanted & _tokens(item.filename)
    keyword_overlap = sorted(title | tags | search | description | filename)

    relevance = (
        12.0 * len(object_overlap)
        + 6.0 * len(title)
        + 5.0 * len(tags)
        + 4.0 * len(search)
        + 2.0 * len(description)
        + 1.0 * len(filename)
    )
    reuse_penalty = -12.0 * reuse_count
    total = (
        relevance
        + PROVIDER_SCORE.get(item.provider, 0.0)
        + RIGHTS_SCORE.get(item.rights_status, -2.0)
        + reuse_penalty
    )

    reasons = []
    if object_overlap:
        reasons.append("object_overlap:" + ",".join(object_overlap))
    if title:
        reasons.append("title_overlap:" + ",".join(sorted(title)))
    if tags:
        reasons.append("tag_overlap:" + ",".join(sorted(tags)))
    if search:
        reasons.append("search_overlap:" + ",".join(sorted(search)))
    if description:
        reasons.append("description_overlap:" + ",".join(sorted(description)))
    if filename:
        reasons.append("filename_overlap:" + ",".join(sorted(filename)))
    reasons += [
        "provider:" + item.provider.value,
        "rights:" + item.rights_status.value,
    ]
    if reuse_count:
        reasons.append("reuse_penalty:" + str(reuse_count))

    return (
        MaterialCandidate(
            media_id=item.media_id,
            local_path=item.local_path,
            provider=item.provider,
            rights_status=item.rights_status,
            publication_eligible=item.publication_eligible,
            relevance_score=round(relevance, 4),
            total_score=round(total, 4),
            reuse_penalty=round(reuse_penalty, 4),
            object_overlap=object_overlap,
            keyword_overlap=keyword_overlap,
            reasons=reasons,
        ),
        bool(object_overlap or title or tags or search),
    )


def _selected_fields(item):
    return {
        "selected_media_id": item.media_id,
        "selected_local_path": item.local_path,
        "selected_provider": item.provider,
        "selected_rights_status": item.rights_status,
        "selected_publication_eligible": item.publication_eligible,
        "selected_source_url": item.source_url,
        "selected_attribution": item.attribution,
        "selected_scientific_status": item.scientific_status.value,
    }


class MaterialSelector:
    def __init__(self, catalog=None):
        self.catalog = catalog or AstroMediaCatalog()

    def _manual_override(self, scene_key):
        media_id = self.catalog.get_override(scene_key)
        if not media_id:
            return None
        item = self.catalog.get(media_id)
        if item is None:
            raise MaterialSelectionError(
                "Manual override references unknown media_id: " + media_id
            )
        if not item.active:
            raise MaterialSelectionError(
                "Manual override references inactive media: " + media_id
            )
        if not item.renderable:
            raise MaterialSelectionError(
                "Manual override references non-renderable media: " + media_id
            )
        return item

    def _rank_candidates(
        self,
        *,
        keywords,
        objects,
        visual,
        used_counts,
        request,
    ):
        ranked = []
        for item in self.catalog.list_items(True):
            if not item.active or not item.renderable or item.duplicate_of_media_id:
                continue
            if item.rights_status == Rights.RESTRICTED:
                continue
            if request.publication_eligible_only and not item.publication_eligible:
                continue

            reuse_count = (
                used_counts.get(item.media_id, 0) if request.avoid_reuse else 0
            )
            candidate, anchor = _score(
                item,
                keywords,
                objects,
                visual,
                reuse_count,
            )
            specificity_ok, required_specificity, specificity_overlap = (
                _specificity_evidence(item, keywords, objects, visual)
            )

            # C2.11J: generic object match is allowed only for a genuinely
            # generic scene. Scientific requirements need secondary evidence.
            if anchor and specificity_ok:
                if required_specificity:
                    candidate.reasons.append(
                        "specificity_overlap:" + ",".join(sorted(specificity_overlap))
                    )
                ranked.append((candidate, item))

        ranked.sort(
            key=lambda pair: (
                -pair[0].total_score,
                -pair[0].relevance_score,
                pair[1].local_path.casefold(),
            )
        )
        return ranked

    def select_scene(self, plan, scene, request, used_counts):
        number = int(getattr(scene, "scene_number", 0))
        if number <= 0:
            raise MaterialSelectionError("scene_number must be positive")

        query, keywords, objects, visual = _scene_terms(scene)
        scene_key = _scene_key(plan, number)
        manual = self._manual_override(scene_key)

        if manual is not None:
            candidate, _ = _score(manual, keywords, objects, visual, 0)
            used_counts[manual.media_id] = used_counts.get(manual.media_id, 0) + 1
            return SceneMaterialSelection(
                scene_number=number,
                scene_key=scene_key,
                visual_requirement=visual,
                query=query,
                status=SelectionStatus.MANUAL_OVERRIDE,
                selected_score=candidate.total_score,
                relevance_score=candidate.relevance_score,
                manual_override=True,
                review_required=(
                    not manual.publication_eligible
                    or manual.rights_status == Rights.RESTRICTED
                ),
                reasons=["manual_override_hard_priority", *candidate.reasons],
                alternatives=[],
                **_selected_fields(manual),
            )

        ranked = self._rank_candidates(
            keywords=keywords,
            objects=objects,
            visual=visual,
            used_counts=used_counts,
            request=request,
        )
        real = [
            pair
            for pair in ranked
            if pair[0].relevance_score >= request.min_relevance_score
            and pair[1].provider != Provider.AI_GENERATED
        ]
        ai = [
            pair
            for pair in ranked
            if pair[0].relevance_score >= request.min_relevance_score
            and pair[1].provider == Provider.AI_GENERATED
        ]
        ai_allowed = bool(getattr(scene, "ai_recreation_allowed", False))

        selected = None
        status = None
        if real:
            selected = real[0]
            status = SelectionStatus.SELECTED
        elif request.allow_ai_last_resort and ai_allowed and ai:
            selected = ai[0]
            status = SelectionStatus.SELECTED_AI_RECREATION

        if selected is not None:
            candidate, item = selected
            used_counts[item.media_id] = used_counts.get(item.media_id, 0) + 1
            alternatives = [
                pair[0] for pair in ranked if pair[1].media_id != item.media_id
            ][: request.max_alternatives]
            return SceneMaterialSelection(
                scene_number=number,
                scene_key=scene_key,
                visual_requirement=visual,
                query=query,
                status=status,
                selected_score=candidate.total_score,
                relevance_score=candidate.relevance_score,
                manual_override=False,
                review_required=(
                    not item.publication_eligible
                    or status == SelectionStatus.SELECTED_AI_RECREATION
                ),
                reasons=["deterministic_material_selection", *candidate.reasons],
                alternatives=alternatives,
                **_selected_fields(item),
            )

        unresolved = (
            SelectionStatus.AI_RECREATION_REQUIRED
            if request.allow_ai_last_resort and ai_allowed
            else SelectionStatus.NO_ADEQUATE_MEDIA
        )
        reasons = [
            "no_candidate_reached_min_relevance",
            "min_relevance_score:" + str(request.min_relevance_score),
            (
                "scene_allows_ai_recreation"
                if unresolved == SelectionStatus.AI_RECREATION_REQUIRED
                else "ai_recreation_not_selected"
            ),
        ]
        return SceneMaterialSelection(
            scene_number=number,
            scene_key=scene_key,
            visual_requirement=visual,
            query=query,
            status=unresolved,
            review_required=True,
            reasons=reasons,
            alternatives=[pair[0] for pair in ranked][: request.max_alternatives],
        )

    def select_plan(self, request: MaterialSelectionRequest):
        scenes = list(request.plan.scenes)
        if not scenes:
            raise MaterialSelectionError("AstronomyVideoPlan has no scenes")

        used_counts = {}
        selections = [
            self.select_scene(request.plan, scene, request, used_counts)
            for scene in scenes
        ]
        selected_statuses = {
            SelectionStatus.SELECTED,
            SelectionStatus.MANUAL_OVERRIDE,
            SelectionStatus.SELECTED_AI_RECREATION,
        }
        unresolved_statuses = {
            SelectionStatus.NO_ADEQUATE_MEDIA,
            SelectionStatus.AI_RECREATION_REQUIRED,
        }
        selected_count = sum(
            selection.status in selected_statuses for selection in selections
        )
        manual_count = sum(
            selection.status == SelectionStatus.MANUAL_OVERRIDE
            for selection in selections
        )
        unresolved_count = sum(
            selection.status in unresolved_statuses for selection in selections
        )
        ai_count = sum(
            selection.status
            in {
                SelectionStatus.SELECTED_AI_RECREATION,
                SelectionStatus.AI_RECREATION_REQUIRED,
            }
            for selection in selections
        )
        review_required = any(selection.review_required for selection in selections)
        publication_ready = (
            selected_count == len(scenes)
            and not review_required
            and all(
                selection.selected_publication_eligible is True
                for selection in selections
            )
        )
        context_hash = str(
            getattr(request.plan, "context_hash", "")
            or getattr(request.plan, "astronomy_context_hash", "")
            or ""
        )
        return MaterialSelectionPlan(
            subject=_plan_subject(request.plan),
            source_plan_context_hash=context_hash,
            selector_version=SELECTOR_VERSION,
            scene_count=len(scenes),
            selected_count=selected_count,
            manual_override_count=manual_count,
            unresolved_count=unresolved_count,
            ai_recreation_count=ai_count,
            selections=selections,
            review_required=review_required,
            publication_ready=publication_ready,
            generated_at_utc=datetime.now(timezone.utc),
        )