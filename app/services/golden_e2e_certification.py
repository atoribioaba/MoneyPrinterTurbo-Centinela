from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from app.models.finalization_e2e import FinalizationE2EStatus
from app.models.golden_e2e_certification import (
    GOLDEN_E2E_CERTIFICATION_VERSION,
    GoldenCertificationStatus,
    GoldenE2ECertificationPlan,
    GoldenE2ECertificationRequest,
    GoldenScenarioId,
)
from app.models.operational_hardening import OperationalHardeningStatus
from app.models.video_base_e2e import VideoBaseE2EStatus
def _hash(v:Any)->str:
    return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest().upper()
def build_golden_e2e_certification(request:GoldenE2ECertificationRequest)->GoldenE2ECertificationPlan:
    required=set(GoldenScenarioId)
    provided={x.scenario_id for x in request.scenarios}
    missing=sorted(required-provided,key=lambda x:x.value)
    passed=sum(all([x.scientific_pass,x.visual_relevance_pass,x.provenance_pass,x.render_pass,x.no_irrelevant_broll,x.recovery_pass]) for x in request.scenarios)
    if request.video_base.status!=VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS or request.finalization.status!=FinalizationE2EStatus.FINALIZATION_E2E_PASS:
        status=GoldenCertificationStatus.WAITING_FOR_REAL_E2E
    elif missing or request.performance is None:
        status=GoldenCertificationStatus.WAITING_FOR_GOLDEN_EVIDENCE
    else:
        perf=request.performance
        ok=passed==len(request.scenarios)==len(required) and perf.oom_events==0 and perf.unrecovered_failures==0 and perf.nvenc_path_tested and perf.libx264_fallback_tested and request.hardening.status!=OperationalHardeningStatus.HARDENING_BLOCKED
        status=GoldenCertificationStatus.CERTIFICATION_PASS if ok else GoldenCertificationStatus.CERTIFICATION_FAIL
    stable={"version":GOLDEN_E2E_CERTIFICATION_VERSION,"video_base":request.video_base.video_base_e2e_hash,"finalization":request.finalization.finalization_e2e_hash,"hardening":request.hardening.operational_hardening_hash,"scenarios":[x.model_dump(mode="json") for x in request.scenarios],"performance":request.performance.model_dump(mode="json") if request.performance else None,"status":status.value}
    return GoldenE2ECertificationPlan(status=status,scenario_count=len(request.scenarios),passed_scenario_count=passed,missing_scenarios=missing,performance_present=request.performance is not None,golden_e2e_hash=_hash(stable),generated_at_utc=datetime.now(timezone.utc))
