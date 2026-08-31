from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from app.models.production_orchestrator import ProductionOrchestratorStatus
from app.models.video_base import VideoBaseRenderMode
from app.models.video_base_e2e import VIDEO_BASE_E2E_VERSION, VideoBaseE2ECheck, VideoBaseE2EPlan, VideoBaseE2ERequest, VideoBaseE2EStatus


def _hash(value: Any) -> str:
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str)
    return hashlib.sha256(raw.encode()).hexdigest().upper()


def build_video_base_e2e(request: VideoBaseE2ERequest) -> VideoBaseE2EPlan:
    if request.orchestrator.status == ProductionOrchestratorStatus.BLOCKED_BY_QUALITY_OR_DELIVERY:
        status=VideoBaseE2EStatus.WAITING_FOR_ORCHESTRATOR
        checks=[]
        present=False
    elif request.manifest is None:
        status=VideoBaseE2EStatus.WAITING_FOR_REAL_VIDEO_BASE
        checks=[]
        present=False
    elif request.manifest.render_mode != VideoBaseRenderMode.CLEAN_BASE or request.manifest.placeholder_count != 0:
        status=VideoBaseE2EStatus.WAITING_FOR_CLEAN_VIDEO_BASE
        checks=[]
        present=True
    else:
        m=request.manifest
        p=request.probe
        checks=[
            VideoBaseE2ECheck(check_id="file_exists",passed=p.exists,detail=p.file_path),
            VideoBaseE2ECheck(check_id="path_matches_manifest",passed=p.file_path==m.final_video_path,detail=f"probe={p.file_path}; manifest={m.final_video_path}"),
            VideoBaseE2ECheck(check_id="sha256_matches_manifest",passed=bool(p.sha256 and p.sha256.casefold()==m.final_video_sha256.casefold()),detail="probe SHA vs render manifest"),
            VideoBaseE2ECheck(check_id="resolution_1080x1920",passed=p.width==1080 and p.height==1920,detail=f"{p.width}x{p.height}"),
            VideoBaseE2ECheck(check_id="fps_30",passed=abs(p.fps-30.0)<=0.05,detail=str(p.fps)),
            VideoBaseE2ECheck(check_id="audio_absent",passed=p.audio_stream_count==0,detail=str(p.audio_stream_count)),
            VideoBaseE2ECheck(check_id="manifest_clean_base",passed=m.placeholder_count==0 and m.scene_count>0,detail=f"scenes={m.scene_count}; placeholders={m.placeholder_count}"),
        ]
        status=VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS if all(x.passed for x in checks) else VideoBaseE2EStatus.VIDEO_BASE_E2E_FAIL
        present=True
    stable={"version":VIDEO_BASE_E2E_VERSION,"orchestrator":request.orchestrator.production_orchestrator_hash,"manifest":request.manifest.model_dump(mode="json") if request.manifest else None,"probe":request.probe.model_dump(mode="json") if request.probe else None,"status":status.value,"checks":[x.model_dump(mode="json") for x in checks]}
    return VideoBaseE2EPlan(source_production_orchestrator_hash=request.orchestrator.production_orchestrator_hash,status=status,real_artifact_present=present,check_count=len(checks),passed_count=sum(x.passed for x in checks),failed_count=sum(not x.passed for x in checks),checks=checks,video_base_e2e_hash=_hash(stable),generated_at_utc=datetime.now(timezone.utc))
