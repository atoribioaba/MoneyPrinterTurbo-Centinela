from fastapi import HTTPException
from app.controllers.v1.base import new_router
from app.models.policy_candidate import PolicyCandidateRequest
from app.services.policy_candidate import build_policy_candidate
from app.utils import utils
router=new_router()
@router.get("/policy-candidate/health")
def health(): return utils.get_response(200,{"status":"ok","version":"policy-candidate-v0.1","planning_only":True,"inferred_bindings":False,"updates_director_policy":False,"activates_policy":False})
@router.post("/policy-candidate/plan")
def plan(body:PolicyCandidateRequest):
    try:
        result=build_policy_candidate(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    return utils.get_response(200,result.model_dump(mode="json"))
