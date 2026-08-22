from app.controllers.v1.base import new_router
from app.models.publication_package import PublicationPackageRequest
from app.services.publication_package import build_publication_package
from app.utils import utils
router=new_router()
@router.get("/publication-package/health")
def health(): return utils.get_response(200,{"status":"ok","version":"publication-package-v0.1","manual_publication_only":True,"writes_files":False,"auto_publication":False})
@router.post("/publication-package/plan")
def plan(body:PublicationPackageRequest): return utils.get_response(200,build_publication_package(body).model_dump(mode="json"))
