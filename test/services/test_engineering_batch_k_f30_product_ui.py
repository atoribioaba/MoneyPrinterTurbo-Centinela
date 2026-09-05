from __future__ import annotations

import ast
from pathlib import Path

from app.models.delivery_render import (
    DeliveryRenderRequest,
    DeliveryRenderStatus,
    FFmpegCapabilityHint,
)
from app.models.quality_gates import QualityGatesPlan
from app.services.delivery_render import build_delivery_render


PAGE = Path("webui/pages/30_Delivery_Render.py")
SOURCE = PAGE.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _call_names():
    names = set()
    for node in ast.walk(TREE):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def _quality(ready: bool) -> QualityGatesPlan:
    return QualityGatesPlan.model_construct(
        subject="Fixture",
        source_plan_context_hash="ctx-f30",
        quality_gates_hash="f29-hash",
        technical_ready=ready,
    )


def _request(
    *,
    ready: bool = True,
    listed: bool = True,
    master_probe: bool | None = True,
    social_probe: bool | None = True,
    ffmpeg_present: bool = True,
    libx264_listed: bool = True,
) -> DeliveryRenderRequest:
    ffmpeg = FFmpegCapabilityHint(
        ffmpeg_present=ffmpeg_present,
        ffmpeg_version="fixture",
        h264_nvenc_listed=listed,
        libx264_listed=libx264_listed,
        nvenc_master_probe_success=master_probe,
        nvenc_social_probe_success=social_probe,
        capability_probe_invocations=2,
    )
    return DeliveryRenderRequest.model_construct(
        quality_gates=_quality(ready),
        ffmpeg=ffmpeg,
    )


def test_f30_page_uses_real_request_service_and_plan():
    calls = _call_names()
    assert "DeliveryRenderRequest" in SOURCE
    assert "DeliveryRenderPlan" in SOURCE
    assert "FFmpegCapabilityHint" in SOURCE
    assert "QualityGatesPlan" in SOURCE
    assert "build_delivery_render" in SOURCE
    assert "DeliveryRenderRequest" in calls
    assert "FFmpegCapabilityHint" in calls
    assert "build_delivery_render" in calls


def test_f30_page_is_planning_only_and_does_not_duplicate_codec_execution():
    calls = _call_names()
    forbidden_calls = {
        "Popen",
        "run",
        "system",
        "check_output",
        "check_call",
        "build_production_orchestrator",
    }
    assert not (forbidden_calls & calls)
    assert "subprocess" not in SOURCE
    assert "os.system" not in SOURCE
    assert "ffmpeg -encoders" not in SOURCE
    assert "Renderizar vídeo" not in SOURCE
    assert "Generar vídeo final" not in SOURCE
    assert "READY_FOR_EXPLICIT_RENDER_APPROVAL significa" in SOURCE
    assert "No se ha renderizado ningún archivo" in SOURCE
    assert "F30 termina en DeliveryRenderPlan" in SOURCE
    assert "no llama f51 automáticamente" in SOURCE.lower()
    assert "effective_codec_candidate =" not in SOURCE


def test_f30_product_ui_is_fail_closed_and_mobile_safe():
    assert 'st.button("Preparar plan de render", type="primary")' in SOURCE
    assert "No se ha podido preparar el plan F30" in SOURCE
    assert 'st.expander("Detalles técnicos", expanded=False)' in SOURCE
    assert "NO EJECUTADO" in SOURCE
    assert "PENDIENTE_PC" in SOURCE
    assert "st.table" not in SOURCE
    assert "st.dataframe" not in SOURCE
    assert "st.columns" not in SOURCE
    assert "server path" not in SOURCE.lower()


def test_f30_profiles_are_exact_and_rerender_from_original_sources():
    plan = build_delivery_render(_request())
    profiles = {item.profile_id: item for item in plan.profiles}
    master = profiles["MASTER_VERTICAL_2160X3840"]
    social = profiles["SOCIAL_VERTICAL_1080X1920"]
    assert (master.width, master.height, master.fps) == (2160, 3840, 30)
    assert (social.width, social.height, social.fps) == (1080, 1920, 30)
    assert master.source_strategy == "ORIGINAL_SOURCE_RERENDER"
    assert social.source_strategy == "ORIGINAL_SOURCE_RERENDER"
    assert plan.upscales_social_to_master is False
    assert all(item.execution_ready is False for item in plan.profiles)


def test_f30_nvenc_is_candidate_only_with_matching_probe_evidence():
    plan = build_delivery_render(_request(listed=True, master_probe=True, social_probe=True))
    assert all(item.effective_codec_candidate == "h264_nvenc" for item in plan.profiles)


def test_f30_incomplete_nvenc_evidence_preserves_libx264_fallback():
    plan = build_delivery_render(
        _request(listed=True, master_probe=False, social_probe=None)
    )
    profiles = {item.profile_id: item for item in plan.profiles}
    assert (
        profiles["MASTER_VERTICAL_2160X3840"].effective_codec_candidate
        == "libx264"
    )
    assert (
        profiles["SOCIAL_VERTICAL_1080X1920"].effective_codec_candidate
        == "libx264"
    )


def test_f30_nvenc_not_listed_preserves_libx264_fallback():
    plan = build_delivery_render(
        _request(listed=False, master_probe=True, social_probe=True)
    )
    assert all(item.effective_codec_candidate == "libx264" for item in plan.profiles)


def test_f30_ready_state_is_approval_gate_not_render_completion():
    plan = build_delivery_render(_request(ready=True))
    assert plan.status == DeliveryRenderStatus.READY_FOR_EXPLICIT_RENDER_APPROVAL
    assert plan.project_render_invocations == 0
    assert plan.renders_project_video is False
    assert plan.human_render_approval_required is True
    assert plan.auto_publication is False
    assert all(item.execution_ready is False for item in plan.profiles)


def test_f30_blocked_state_remains_fail_closed():
    plan = build_delivery_render(_request(ready=False))
    assert plan.status == DeliveryRenderStatus.BLOCKED_BY_QUALITY_GATES
    assert plan.project_render_invocations == 0
    assert plan.renders_project_video is False
    assert plan.auto_publication is False
