from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import AstronomyVideoPlan
from app.models.astronomy_motion_graphics import AstronomyMotionGraphicsPlan
from app.models.cinematic_infographics import (
    CINEMATIC_INFOGRAPHICS_VERSION,
    CinematicInfographicsPlan,
    InfographicCard,
    InfographicCardType,
    InfographicLayout,
    InfographicScene,
    InfographicStructuralChecks,
)


class CinematicInfographicsError(RuntimeError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash_json(value: Any) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest().upper()


def _card_type(status: ScientificStatus) -> InfographicCardType:
    return {
        ScientificStatus.HECHO_VERIFICADO:
            InfographicCardType.VERIFIED_FACT,
        ScientificStatus.APROXIMACION_DIVULGATIVA:
            InfographicCardType.APPROXIMATION,
        ScientificStatus.HIPOTESIS:
            InfographicCardType.HYPOTHESIS,
        ScientificStatus.RECREACION_VISUAL:
            InfographicCardType.VISUAL_RECREATION,
        ScientificStatus.INFERENCIA:
            InfographicCardType.INFERENCE,
        ScientificStatus.NO_VERIFICADO:
            InfographicCardType.UNVERIFIED,
    }[status]


def _validate(
    plan: AstronomyVideoPlan,
    graphics: AstronomyMotionGraphicsPlan,
) -> None:
    if plan.context_hash != graphics.source_plan_context_hash:
        raise CinematicInfographicsError(
            "F3/F16 context hash mismatch"
        )
    if len(plan.scenes) != graphics.scene_count:
        raise CinematicInfographicsError(
            "F3/F16 scene count mismatch"
        )


def build_cinematic_infographics(
    plan: AstronomyVideoPlan,
    graphics: AstronomyMotionGraphicsPlan,
) -> CinematicInfographicsPlan:
    _validate(plan, graphics)

    scenes: list[InfographicScene] = []

    for scene in plan.scenes:
        cards: list[InfographicCard] = []

        for index, claim in enumerate(scene.claims, start=1):
            grounding_ready = (
                claim.scientific_status
                == ScientificStatus.HECHO_VERIFICADO
                and bool(claim.fact_ids)
            )

            cards.append(
                InfographicCard(
                    card_id=f"scene:{scene.scene_number}:card:{index}",
                    scene_number=scene.scene_number,
                    card_type=_card_type(claim.scientific_status),
                    layout=(
                        InfographicLayout.MINIMAL_FACT_CARD
                        if grounding_ready
                        else InfographicLayout.CINEMATIC_SIDE_CARD
                    ),
                    statement=claim.statement,
                    scientific_status=claim.scientific_status,
                    fact_ids=list(claim.fact_ids),
                    grounding_ready=grounding_ready,
                    human_review_required=True,
                )
            )

        scenes.append(
            InfographicScene(
                scene_number=scene.scene_number,
                card_count=len(cards),
                cards=cards,
                human_review_required=True,
            )
        )

    all_cards = [
        card
        for scene in scenes
        for card in scene.cards
    ]

    stable = {
        "version": CINEMATIC_INFOGRAPHICS_VERSION,
        "subject": plan.subject,
        "source_plan_context_hash": plan.context_hash,
        "source_motion_graphics_hash": graphics.motion_graphics_hash,
        "scenes": [
            scene.model_dump(mode="json")
            for scene in scenes
        ],
    }

    return CinematicInfographicsPlan(
        subject=plan.subject,
        source_plan_context_hash=plan.context_hash,
        source_motion_graphics_version=graphics.version,
        source_motion_graphics_hash=graphics.motion_graphics_hash,
        scene_count=len(scenes),
        card_count=len(all_cards),
        verified_card_count=sum(
            card.card_type == InfographicCardType.VERIFIED_FACT
            for card in all_cards
        ),
        grounding_ready_count=sum(
            card.grounding_ready for card in all_cards
        ),
        human_review_required_count=sum(
            card.human_review_required for card in all_cards
        ),
        scenes=scenes,
        structural_checks=InfographicStructuralChecks(
            source_plan_alignment=True,
            motion_graphics_hash_preserved=True,
            plan_claims_only=True,
            fact_ids_preserved=True,
            scientific_status_preserved=True,
            no_external_data_added=True,
            no_invented_numbers=True,
            no_invented_charts=True,
        ),
        infographics_hash=_hash_json(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
