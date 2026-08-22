from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from typing import Any
from app.models.finalization_e2e import *
from app.models.video_base_e2e import VideoBaseE2EStatus

def _hash(v:Any)->str:
    return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest().upper()

def build_finalization_e2e(request:FinalizationE2ERequest)->FinalizationE2EPlan:
    checks=[]
    if request.video_base.status != VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS:
        status=FinalizationE2EStatus.WAITING_FOR_VIDEO_BASE_E2E
    elif request.human_review is None:
        status=FinalizationE2EStatus.WAITING_FOR_HUMAN_REVIEW
    elif request.human_review.decision == HumanFinalReviewDecision.REJECT:
        status=FinalizationE2EStatus.HUMAN_REVIEW_REJECTED
    elif not request.artifacts:
        status=FinalizationE2EStatus.WAITING_FOR_FINAL_RENDERS
    else:
        profiles={a.profile_id:a for a in request.artifacts}
        master=profiles.get("MASTER_VERTICAL_2160X3840")
        social=profiles.get("SOCIAL_VERTICAL_1080X1920")
        def c(cid,ok,detail): checks.append(FinalizationCheck(check_id=cid,passed=ok,detail=detail))
        c("master_present",master is not None,"MASTER_VERTICAL_2160X3840")
        c("social_present",social is not None,"SOCIAL_VERTICAL_1080X1920")
        if master:
            c("master_file",master.exists,master.file_path); c("master_resolution",master.width==2160 and master.height==3840,f"{master.width}x{master.height}")
            c("master_fps",abs(master.fps-30)<=0.05,str(master.fps)); c("master_audio",master.audio_stream_count>=1,str(master.audio_stream_count)); c("master_subtitles",master.subtitles_ready,str(master.subtitles_ready)); c("master_rights",master.publication_rights_ready,str(master.publication_rights_ready))
        if social:
            c("social_file",social.exists,social.file_path); c("social_resolution",social.width==1080 and social.height==1920,f"{social.width}x{social.height}")
            c("social_fps",abs(social.fps-30)<=0.05,str(social.fps)); c("social_audio",social.audio_stream_count>=1,str(social.audio_stream_count)); c("social_subtitles",social.subtitles_ready,str(social.subtitles_ready)); c("social_rights",social.publication_rights_ready,str(social.publication_rights_ready))
        status=FinalizationE2EStatus.FINALIZATION_E2E_PASS if checks and all(x.passed for x in checks) else FinalizationE2EStatus.FINALIZATION_E2E_FAIL
    stable={"version":FINALIZATION_E2E_VERSION,"video_base":request.video_base.video_base_e2e_hash,"review":request.human_review.model_dump(mode="json") if request.human_review else None,"artifacts":[a.model_dump(mode="json") for a in request.artifacts],"status":status.value,"checks":[x.model_dump(mode="json") for x in checks]}
    return FinalizationE2EPlan(source_video_base_e2e_hash=request.video_base.video_base_e2e_hash,status=status,human_review_recorded=request.human_review is not None,artifact_count=len(request.artifacts),check_count=len(checks),passed_count=sum(x.passed for x in checks),failed_count=sum(not x.passed for x in checks),checks=checks,artifacts=request.artifacts,finalization_e2e_hash=_hash(stable),generated_at_utc=datetime.now(timezone.utc))
