from app.controllers.v1.base import new_router
from app.models.finalization_e2e import FinalizationE2ERequest
from app.services.finalization_e2e import build_finalization_e2e
from app.utils import utils
router=new_router()
@router.get("/finalization-e2e/health")
def health(): return utils.get_response(200,{"status":"ok","version":"finalization-e2e-v0.1","human_review_required":True,"verification_only":True,"auto_publication":False})
@router.post("/finalization-e2e/verify")
def verify(body:FinalizationE2ERequest): return utils.get_response(200,build_finalization_e2e(body).model_dump(mode="json"))
