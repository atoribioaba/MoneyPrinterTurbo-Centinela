from datetime import datetime,timezone
import pytest
from app.models.analytics_brain import AnalyticsPlatform
from app.models.evidence_recommendation_gate import CandidateRecommendation,EvidenceRecommendationGatePlan,EvidenceRecommendationStatus
from app.models.policy_candidate import PolicyBinding,PolicyCandidateRequest,PolicyCandidateStatus
from app.services.policy_candidate import build_policy_candidate
NOW=datetime(2026,8,22,tzinfo=timezone.utc)
def gate():
    rec=CandidateRecommendation(recommendation_id="rec-1",experiment_id="exp-1",hypothesis_id="hyp-1",platform=AnalyticsPlatform.YOUTUBE,variable="cinematic_intensity_bias",recommended_definition="0.05",success_metric="AUDIENCE_WATCH_RATIO",observed_delta=.05)
    return EvidenceRecommendationGatePlan(source_experiment_evidence_ledger_hash="ledger",status=EvidenceRecommendationStatus.CANDIDATE_RECOMMENDATIONS_READY,recommendation_count=1,recommendations=[rec],evidence_recommendation_gate_hash="gate",generated_at_utc=NOW)
def bind(**kw):
    d=dict(recommendation_id="rec-1",parameter="intensity_bias",baseline_value=0.0,candidate_value=0.05,human_mapping_confirmed=True); d.update(kw); return PolicyBinding(**d)
def test_no_binding_waits(): assert build_policy_candidate(PolicyCandidateRequest(recommendations=gate())).status==PolicyCandidateStatus.WAITING_FOR_EXPLICIT_POLICY_BINDINGS
def test_confirmed_binding_creates_candidate(): assert build_policy_candidate(PolicyCandidateRequest(recommendations=gate(),bindings=[bind()])).candidate_count==1
def test_unconfirmed_binding_not_inferred(): assert build_policy_candidate(PolicyCandidateRequest(recommendations=gate(),bindings=[bind(human_mapping_confirmed=False)])).candidate_count==0
def test_unsupported_rejected():
    with pytest.raises(RuntimeError): build_policy_candidate(PolicyCandidateRequest(recommendations=gate(),bindings=[bind(parameter="invented")]))
def test_range_enforced():
    with pytest.raises(RuntimeError): build_policy_candidate(PolicyCandidateRequest(recommendations=gate(),bindings=[bind(candidate_value=.5)]))
