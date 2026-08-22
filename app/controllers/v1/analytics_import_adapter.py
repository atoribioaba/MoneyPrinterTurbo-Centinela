from fastapi import HTTPException
from app.controllers.v1.base import new_router
from app.models.analytics_import_adapter import AnalyticsImportRequest
from app.services.analytics_import_adapter import AnalyticsImportError, build_analytics_import
from app.utils import utils
router=new_router()
@router.get("/analytics-import-adapter/health")
def health(): return utils.get_response(200,{"status":"ok","version":"analytics-import-adapter-v0.1","formats":["CSV","JSON"],"network_calls":0,"database_writes":0})
@router.post("/analytics-import-adapter/parse")
def parse(body:AnalyticsImportRequest):
    try: result=build_analytics_import(body)
    except AnalyticsImportError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc
    return utils.get_response(200,result.model_dump(mode="json"))
