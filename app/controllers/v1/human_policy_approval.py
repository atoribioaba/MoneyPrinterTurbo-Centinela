from fastapi import HTTPException
from app.controllers.v1.base import new_router
from app.models.human_policy_approval import HumanPolicyApprovalRequest
from app.services.human_policy_approval import build_human_policy_approval
from app.utils import utils
router=new_router()
@router.get("/human-policy-approval/health")
def health(): return utils.get_response(200,{"status":"ok","version":"human-policy-approval-v0.1","planning_only":True,"auto_approval":False,"activates_policy":False,"auto_publication":False})
@router.post("/human-policy-approval/plan")
def plan(body:HumanPolicyApprovalRequest):
    try:
        result=build_human_policy_approval(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    return utils.get_response(200,result.model_dump(mode="json"))
