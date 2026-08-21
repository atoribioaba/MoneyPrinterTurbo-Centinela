from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.delivery_render import (
    DELIVERY_RENDER_VERSION,
    DeliveryProfile,
    DeliveryRenderPlan,
    DeliveryRenderRequest,
    DeliveryRenderStatus,
)


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_delivery_render(request: DeliveryRenderRequest) -> DeliveryRenderPlan:
    gates = request.quality_gates
    ffmpeg = request.ffmpeg

    social_codec = (
        "h264_nvenc"
        if ffmpeg.h264_nvenc_listed and ffmpeg.nvenc_social_probe_success is True
        else "libx264"
    )
    master_codec = (
        "h264_nvenc"
        if ffmpeg.h264_nvenc_listed and ffmpeg.nvenc_master_probe_success is True
        else "libx264"
    )

    profiles = [
        DeliveryProfile(
            profile_id="MASTER_VERTICAL_2160X3840",
            width=2160,
            height=3840,
            fps=30,
            requested_codec="h264_nvenc",
            effective_codec_candidate=master_codec,
        ),
        DeliveryProfile(
            profile_id="SOCIAL_VERTICAL_1080X1920",
            width=1080,
            height=1920,
            fps=30,
            requested_codec="h264_nvenc",
            effective_codec_candidate=social_codec,
        ),
    ]

    status = (
        DeliveryRenderStatus.READY_FOR_EXPLICIT_RENDER_APPROVAL
        if gates.technical_ready and ffmpeg.ffmpeg_present and ffmpeg.libx264_listed
        else DeliveryRenderStatus.BLOCKED_BY_QUALITY_GATES
    )

    stable = {
        "version": DELIVERY_RENDER_VERSION,
        "quality_gates_hash": gates.quality_gates_hash,
        "ffmpeg": ffmpeg.model_dump(mode="json"),
        "profiles": [profile.model_dump(mode="json") for profile in profiles],
        "status": status.value,
    }

    return DeliveryRenderPlan(
        subject=gates.subject,
        source_plan_context_hash=gates.source_plan_context_hash,
        source_quality_gates_hash=gates.quality_gates_hash,
        status=status,
        ffmpeg_present=ffmpeg.ffmpeg_present,
        ffmpeg_version=ffmpeg.ffmpeg_version,
        h264_nvenc_listed=ffmpeg.h264_nvenc_listed,
        libx264_listed=ffmpeg.libx264_listed,
        nvenc_social_probe_success=ffmpeg.nvenc_social_probe_success,
        nvenc_master_probe_success=ffmpeg.nvenc_master_probe_success,
        capability_probe_invocations=ffmpeg.capability_probe_invocations,
        profile_count=len(profiles),
        profiles=profiles,
        delivery_render_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
