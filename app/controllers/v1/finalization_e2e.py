from app.controllers.v1.base import new_router
from app.models.finalization_e2e import (
    FINALIZATION_E2E_VERSION,
    FinalizationE2ERequest,
)
from app.services.finalization_e2e import build_finalization_e2e
from app.utils import utils

router = new_router()


@router.get("/finalization-e2e/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": FINALIZATION_E2E_VERSION,
            "human_review_required": True,
            "seven_review_gates_required": True,
            "canonical_final_render_evidence_required": True,
            "verification_only": True,
            "network_calls": 0,
            "auto_publication": False,
            "authorization_to_publish": False,
            "marks_published": False,
        },
    )


@router.post("/finalization-e2e/verify")
def verify(body: FinalizationE2ERequest):
    return utils.get_response(
        200,
        build_finalization_e2e(body).model_dump(mode="json"),
    )
