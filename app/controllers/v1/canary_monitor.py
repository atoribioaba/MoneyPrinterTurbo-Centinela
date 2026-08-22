from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.canary_monitor import CanaryMonitorRequest
from app.services.canary_monitor import build_canary_monitor
from app.utils import utils

router = new_router()


@router.get("/canary-monitor/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "canary-monitor-v0.1",
            "descriptive_only": True,
            "launches_canary": False,
            "executes_rollback": False,
            "activates_policy": False,
        },
    )


@router.post("/canary-monitor/plan")
def plan(body: CanaryMonitorRequest):
    try:
        result = build_canary_monitor(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
