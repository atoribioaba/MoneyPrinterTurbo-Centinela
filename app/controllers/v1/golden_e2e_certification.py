from app.controllers.v1.base import new_router
from app.models.golden_e2e_certification import GoldenE2ECertificationRequest
from app.services.golden_e2e_certification import build_golden_e2e_certification
from app.utils import utils
router=new_router()
@router.get("/golden-e2e-certification/health")
def health(): return utils.get_response(200,{"status":"ok","version":"golden-e2e-certification-v0.1","required_scenarios":8,"real_video_required":True,"synthetic_only_not_accepted":True})
@router.post("/golden-e2e-certification/evaluate")
def evaluate(body:GoldenE2ECertificationRequest): return utils.get_response(200,build_golden_e2e_certification(body).model_dump(mode="json"))
