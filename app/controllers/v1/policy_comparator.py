from app.controllers.v1.base import new_router
from app.models.policy_comparator import PolicyComparatorRequest
from app.services.policy_comparator import build_policy_comparator
from app.utils import utils
router=new_router()
@router.get("/policy-comparator/health")
def health(): return utils.get_response(200,{"status":"ok","version":"policy-comparator-v0.1","planning_only":True,"quality_improvement_claims":False,"causal_claims":False,"activates_policy":False})
@router.post("/policy-comparator/plan")
def plan(body:PolicyComparatorRequest): return utils.get_response(200,build_policy_comparator(body).model_dump(mode="json"))
