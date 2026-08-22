from app.controllers.v1.base import new_router
from app.models.operational_hardening import OperationalHardeningRequest
from app.services.operational_hardening import build_operational_hardening
from app.utils import utils
router=new_router()
@router.get("/operational-hardening/health")
def health(): return utils.get_response(200,{"status":"ok","version":"operational-hardening-v0.1","audit_only":True,"modifies_config":False,"resets_network":False})
@router.post("/operational-hardening/audit")
def audit(body:OperationalHardeningRequest): return utils.get_response(200,build_operational_hardening(body).model_dump(mode="json"))
