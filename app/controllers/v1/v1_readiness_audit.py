from app.controllers.v1.base import new_router
from app.models.v1_readiness_audit import V1ReadinessRequest
from app.services.v1_readiness_audit import build_v1_readiness_audit
from app.utils import utils
router=new_router()
@router.get("/v1-readiness-audit/health")
def health(): return utils.get_response(200,{"status":"ok","version":"v1-readiness-audit-v0.1","audit_only":True,"can_authorize_freeze":True,"executes_freeze":False})
@router.post("/v1-readiness-audit/evaluate")
def evaluate(body:V1ReadinessRequest): return utils.get_response(200,build_v1_readiness_audit(body).model_dump(mode="json"))
