from __future__ import annotations
import csv,hashlib,io,json
from datetime import datetime,timezone
from typing import Any
from app.models.analytics_brain import AnalyticsBrainRequest, AnalyticsPlatform, AnalyticsSemanticConfidence, AnalyticsSourceType, MetricValueType, NativeMetricObservation
from app.models.analytics_import_adapter import *
class AnalyticsImportError(RuntimeError): pass
def _hash(v:Any)->str: return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest().upper()
def _bool(v):
    if isinstance(v,bool): return v
    return str(v or "").strip().casefold() in {"1","true","yes","y","si","sí"}
def _none(v):
    return None if v is None or str(v).strip()=="" else v
def _rows(request):
    text=request.payload_text.strip()
    if not text: return []
    if request.format==AnalyticsImportFormat.CSV:
        return list(csv.DictReader(io.StringIO(text)))
    try: raw=json.loads(text)
    except json.JSONDecodeError as exc: raise AnalyticsImportError(f"invalid JSON: {exc}") from exc
    if isinstance(raw,dict): raw=raw.get("observations",raw.get("rows"))
    if not isinstance(raw,list): raise AnalyticsImportError("JSON must be an array or contain observations/rows array")
    if not all(isinstance(x,dict) for x in raw): raise AnalyticsImportError("all import rows must be objects")
    return raw
def build_analytics_import(request:AnalyticsImportRequest)->AnalyticsImportPlan:
    rows=_rows(request); obs=[]
    for i,row in enumerate(rows,1):
        try:
            platform=row.get("platform") or (request.default_platform.value if request.default_platform else None)
            if not platform: raise ValueError("platform is required")
            source_type=row.get("source_type") or request.default_source_type.value
            confidence=row.get("semantic_confidence") or request.default_semantic_confidence.value
            obs.append(NativeMetricObservation(
                platform=AnalyticsPlatform(str(platform).upper()), content_id=str(row["content_id"]).strip(), native_metric_name=str(row["native_metric_name"]).strip(), value=float(row["value"]), value_type=MetricValueType(str(row["value_type"]).upper()), observed_at_utc=datetime.fromisoformat(str(row["observed_at_utc"]).replace("Z","+00:00")), source_type=AnalyticsSourceType(str(source_type).upper()), source_ref=_none(row.get("source_ref")), semantic_confidence=AnalyticsSemanticConfidence(str(confidence).upper()), position_ratio=float(row["position_ratio"]) if _none(row.get("position_ratio")) is not None else None, estimated=_bool(row.get("estimated",False)),
            ))
        except Exception as exc: raise AnalyticsImportError(f"row {i}: {exc}") from exc
    analytics=AnalyticsBrainRequest(observations=obs)
    status=AnalyticsImportStatus.IMPORT_READY if obs else AnalyticsImportStatus.WAITING_FOR_IMPORT_DATA
    stable={"version":ANALYTICS_IMPORT_ADAPTER_VERSION,"format":request.format.value,"observations":[x.model_dump(mode="json") for x in obs]}
    return AnalyticsImportPlan(status=status,row_count=len(rows),observation_count=len(obs),observations=obs,analytics_request=analytics,analytics_import_hash=_hash(stable),generated_at_utc=datetime.now(timezone.utc))
