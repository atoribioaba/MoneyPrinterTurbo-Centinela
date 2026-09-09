import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.pipeline_audit import (
    OpenSourceClassification,
    PipelineAuditManifest,
    PipelineComponentAudit,
    PipelineDecision,
)
from app.services.centinela.pipeline_audit import (
    REQUIRED_PHYSICAL_VALIDATION_FUNCTIONS,
    REQUIRED_V1_FUNCTIONS,
    evaluate_pipeline_audit,
)


SEED = Path("docs/centinela/PIPELINE_OSS_AUDIT_PRE_PC.json")


def _component(
    *,
    component_id="engine",
    function_id="ephemeris",
    selected=True,
    classification=OpenSourceClassification.OPEN_SOURCE_FREE,
    version="1.0.0",
    artifact_sha256=None,
    weights=False,
    physical=False,
    physical_evidence=None,
):
    return PipelineComponentAudit(
        component_id=component_id,
        function_id=function_id,
        component=component_id,
        classification=classification,
        decision=PipelineDecision.KEEP,
        license_id_or_status="MIT",
        source_url="https://example.test/project",
        selected_for_rc=selected,
        version_or_commit=version,
        artifact_sha256=artifact_sha256,
        weights_or_binary_artifact=weights,
        physical_validation_required=physical,
        physical_evidence_ids=physical_evidence or [],
    )


def _manifest(components):
    return PipelineAuditManifest(
        project_sha="a" * 40,
        created_at=datetime(2026, 9, 9, 12, 0, tzinfo=UTC),
        components=components,
    )


def test_pre_pc_seed_is_machine_readable_and_audits_every_required_function():
    manifest = PipelineAuditManifest.model_validate(json.loads(SEED.read_text("utf-8")))
    audited = {item.function_id for item in manifest.components}
    assert REQUIRED_V1_FUNCTIONS <= audited
    assert manifest.auto_publication is False

    result = evaluate_pipeline_audit(manifest)
    assert result.pass_gate is False
    assert result.selected_components == 0
    assert all(
        f"NO_RC_SELECTION:{function_id}" in result.blockers
        for function_id in REQUIRED_V1_FUNCTIONS
    )


def test_physical_policy_covers_every_target_runtime_function():
    assert REQUIRED_PHYSICAL_VALIDATION_FUNCTIONS == {
        "python_environment",
        "video_encode",
        "gpu_encode",
        "llm_runtime",
        "tts",
        "stt_subtitles",
        "t2i",
        "i2v_t2v",
        "upscale",
    }
    assert REQUIRED_PHYSICAL_VALIDATION_FUNCTIONS <= REQUIRED_V1_FUNCTIONS


def test_a_function_cannot_select_multiple_rc_candidates():
    manifest = _manifest(
        [
            _component(component_id="runtime-a", function_id="llm_runtime"),
            _component(component_id="runtime-b", function_id="llm_runtime"),
        ]
    )
    result = evaluate_pipeline_audit(manifest, required_functions={"llm_runtime"})
    assert result.pass_gate is False
    assert "MULTIPLE_RC_SELECTIONS:llm_runtime:2" in result.blockers


def test_selected_unverified_or_unpinned_component_fails_closed():
    component = _component(
        classification=OpenSourceClassification.LICENSE_UNVERIFIED,
        version=None,
    )
    result = evaluate_pipeline_audit(
        _manifest([component]), required_functions={"ephemeris"}
    )
    assert "LICENSE_UNVERIFIED:engine" in result.blockers
    assert "VERSION_NOT_PINNED:engine" in result.blockers


def test_selected_model_requires_exact_artifact_hash():
    component = _component(weights=True, artifact_sha256=None)
    result = evaluate_pipeline_audit(
        _manifest([component]), required_functions={"ephemeris"}
    )
    assert "ARTIFACT_HASH_MISSING:engine" in result.blockers


def test_selected_physical_component_requires_physical_evidence():
    component = _component(physical=True)
    result = evaluate_pipeline_audit(
        _manifest([component]), required_functions={"ephemeris"}
    )
    assert "PHYSICAL_EVIDENCE_MISSING:engine" in result.blockers


def test_target_runtime_cannot_opt_out_of_physical_validation_policy():
    component = _component(
        component_id="runtime",
        function_id="llm_runtime",
        physical=False,
        physical_evidence=None,
    )
    result = evaluate_pipeline_audit(
        _manifest([component]), required_functions={"llm_runtime"}
    )
    assert result.pass_gate is False
    assert "PHYSICAL_POLICY_MISMATCH:runtime:llm_runtime" in result.blockers
    assert "PHYSICAL_EVIDENCE_MISSING:runtime" in result.blockers


def test_target_runtime_false_flag_still_fails_even_if_evidence_id_is_supplied():
    component = _component(
        component_id="runtime",
        function_id="llm_runtime",
        physical=False,
        physical_evidence=["pc-report:sha256:abc"],
    )
    result = evaluate_pipeline_audit(
        _manifest([component]), required_functions={"llm_runtime"}
    )
    assert result.pass_gate is False
    assert "PHYSICAL_POLICY_MISMATCH:runtime:llm_runtime" in result.blockers
    assert "PHYSICAL_EVIDENCE_MISSING:runtime" not in result.blockers


def test_non_runtime_ephemeris_can_remain_cloud_validated():
    component = _component(
        component_id="ephemeris",
        function_id="ephemeris",
        physical=False,
    )
    result = evaluate_pipeline_audit(
        _manifest([component]), required_functions={"ephemeris"}
    )
    assert result.pass_gate is True
    assert result.blockers == []


def test_a_fully_pinned_scoped_component_can_pass_its_gate():
    component = _component(
        weights=True,
        artifact_sha256="b" * 64,
        physical=True,
        physical_evidence=["pc-report:sha256:abc"],
    )
    result = evaluate_pipeline_audit(
        _manifest([component]), required_functions={"ephemeris"}
    )
    assert result.pass_gate is True
    assert result.blockers == []


def test_auto_publication_true_is_structurally_rejected():
    with pytest.raises(ValidationError, match="AUTO_PUBLICATION"):
        PipelineAuditManifest(
            project_sha="a" * 40,
            created_at=datetime(2026, 9, 9, 12, 0, tzinfo=UTC),
            components=[],
            auto_publication=True,
        )


def test_component_ids_are_unique_but_alternatives_may_share_function():
    manifest = _manifest(
        [
            _component(component_id="a", function_id="tts", selected=False),
            _component(component_id="b", function_id="tts", selected=False),
        ]
    )
    assert len(manifest.components) == 2

    with pytest.raises(ValidationError, match="duplicate component_id"):
        _manifest(
            [
                _component(component_id="same", function_id="tts", selected=False),
                _component(component_id="same", function_id="llm_runtime", selected=False),
            ]
        )
