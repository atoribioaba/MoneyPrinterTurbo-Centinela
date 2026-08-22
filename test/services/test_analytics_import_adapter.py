from app.models.analytics_import_adapter import AnalyticsImportFormat, AnalyticsImportRequest, AnalyticsImportStatus
from app.models.analytics_brain import AnalyticsPlatform
from app.services.analytics_import_adapter import build_analytics_import
CSV="""content_id,native_metric_name,value,value_type,observed_at_utc\nabc,views,123,COUNT,2026-08-22T18:00:00+00:00\n"""
def test_csv_import_to_f31_contract():
    r=build_analytics_import(AnalyticsImportRequest(format=AnalyticsImportFormat.CSV,payload_text=CSV,default_platform=AnalyticsPlatform.YOUTUBE))
    assert r.status==AnalyticsImportStatus.IMPORT_READY
    assert r.observation_count==1
    assert r.analytics_request.observations[0].content_id=="abc"
def test_empty_import_waits_without_network():
    r=build_analytics_import(AnalyticsImportRequest())
    assert r.status==AnalyticsImportStatus.WAITING_FOR_IMPORT_DATA
    assert r.network_calls==0
