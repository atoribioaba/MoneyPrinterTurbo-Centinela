from datetime import datetime,timezone
from app.models.finalization_e2e import FinalizationE2EPlan, FinalizationE2EStatus
from app.models.publication_package import PublicationPackageRequest, PublicationPackageStatus
from app.services.publication_package import build_publication_package
NOW=datetime(2026,8,22,tzinfo=timezone.utc)
def fin(status=FinalizationE2EStatus.WAITING_FOR_VIDEO_BASE_E2E):
    return FinalizationE2EPlan(source_video_base_e2e_hash="b",status=status,human_review_recorded=False,artifact_count=0,check_count=0,passed_count=0,failed_count=0,checks=[],artifacts=[],finalization_e2e_hash="f",generated_at_utc=NOW)
def test_waits_for_finalization():
    r=build_publication_package(PublicationPackageRequest(finalization=fin()))
    assert r.status==PublicationPackageStatus.WAITING_FOR_FINALIZATION
    assert r.auto_publication is False
