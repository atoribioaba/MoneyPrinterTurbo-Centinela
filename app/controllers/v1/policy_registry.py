from fastapi import HTTPException
from app.controllers.v1.base import new_router
from app.models.policy_registry import PolicyRegistryRequest
from app.services.policy_registry import build_policy_registry
from app.utils import utils
router=new_router()
@router.get("/policy-registry/health")
def health(): return utils.get_response(200,{"status":"ok","version":"policy-registry-v0.1","planning_only":True,"immutable_registry":True,"writes_runtime_config":False,"activates_policy":False,"active_policy_changed":False})
@router.post("/policy-registry/plan")
def plan(body:PolicyRegistryRequest):
    try: result=build_policy_registry(body)
    except RuntimeError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc
    return utils.get_response(200,result.model_dump(mode="json"))
