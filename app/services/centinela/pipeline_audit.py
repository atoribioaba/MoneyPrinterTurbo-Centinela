from __future__ import annotations

from collections import Counter

from app.models.pipeline_audit import (
    OpenSourceClassification,
    PipelineAuditManifest,
    PipelineAuditResult,
)


REQUIRED_V1_FUNCTIONS = {
    "python_environment",
    "ephemeris",
    "video_encode",
    "gpu_encode",
    "llm_runtime",
    "tts",
    "stt_subtitles",
    "t2i",
    "i2v_t2v",
    "upscale",
    "weather",
    "seeing_transparency",
    "deep_sky_catalog",
}


def evaluate_pipeline_audit(
    manifest: PipelineAuditManifest,
    *,
    required_functions: set[str] | None = None,
) -> PipelineAuditResult:
    """Fail closed until the exact V1 pipeline is selected, licensed and evidenced."""
    required = set(required_functions or REQUIRED_V1_FUNCTIONS)
    blockers: list[str] = []
    warnings: list[str] = []

    selected = [item for item in manifest.components if item.selected_for_rc]
    selected_per_function = Counter(item.function_id for item in selected)

    for function_id in sorted(required):
        count = selected_per_function.get(function_id, 0)
        if count == 0:
            blockers.append(f"NO_RC_SELECTION:{function_id}")
        elif count > 1:
            blockers.append(f"MULTIPLE_RC_SELECTIONS:{function_id}:{count}")

    for item in selected:
        prefix = item.component_id
        if item.classification == OpenSourceClassification.LICENSE_UNVERIFIED:
            blockers.append(f"LICENSE_UNVERIFIED:{prefix}")

        if not item.version_or_commit:
            blockers.append(f"VERSION_NOT_PINNED:{prefix}")

        if item.weights_or_binary_artifact and not item.artifact_sha256:
            blockers.append(f"ARTIFACT_HASH_MISSING:{prefix}")

        if item.physical_validation_required and not item.physical_evidence_ids:
            blockers.append(f"PHYSICAL_EVIDENCE_MISSING:{prefix}")

        if not item.source_url.startswith(("https://", "http://")):
            blockers.append(f"SOURCE_URL_INVALID:{prefix}")

        if item.expected_vram_gb is not None and item.expected_vram_gb > 6.0:
            warnings.append(f"RTX2060_VRAM_RISK:{prefix}:{item.expected_vram_gb:.2f}GB")
        if item.expected_ram_gb is not None and item.expected_ram_gb > 12.0:
            warnings.append(f"SYSTEM_RAM_RISK:{prefix}:{item.expected_ram_gb:.2f}GB")

    audited_functions = {item.function_id for item in manifest.components}
    for function_id in sorted(required - audited_functions):
        blockers.append(f"FUNCTION_NOT_AUDITED:{function_id}")

    return PipelineAuditResult(
        pass_gate=not blockers,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        selected_components=len(selected),
        audited_components=len(manifest.components),
    )
