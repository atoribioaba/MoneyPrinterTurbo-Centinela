from fastapi import HTTPException
from app.controllers.v1.base import new_router
from app.models.policy_simulator import PolicySimulatorRequest
from app.services.policy_simulator import build_policy_simulator
from app.utils import utils
router=new_router()
@router.get("/policy-simulator/health")
def health(): return utils.get_response(200,{"status":"ok","version":"policy-simulator-v0.1","planning_only":True,"uses_real_cinematic_director":True,"renders_video":False,"activates_policy":False})
@router.post("/policy-simulator/plan")
def plan(body:PolicySimulatorRequest):
    try:
        result=build_policy_simulator(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    return utils.get_response(200,result.model_dump(mode="json"))
