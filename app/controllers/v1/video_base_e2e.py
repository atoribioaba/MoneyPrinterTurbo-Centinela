from app.controllers.v1.base import new_router
from app.models.video_base_e2e import VideoBaseE2ERequest
from app.services.video_base_e2e import build_video_base_e2e
from app.utils import utils
router=new_router()

@router.get("/video-base-e2e/health")
def health():
    return utils.get_response(200,{"status":"ok","version":"video-base-e2e-v0.1","verification_only":True,"clean_base_required":True,"renders_video":False})

@router.post("/video-base-e2e/verify")
def verify(body: VideoBaseE2ERequest):
    return utils.get_response(200,build_video_base_e2e(body).model_dump(mode="json"))
