from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.models.astromedia import Provider, Rights
from app.models.material_selection import MaterialSelectionPlan, SelectionStatus
from app.services.centinela.av_runtime.models import AudioBundle, VideoBaseManifest
from app.services.centinela.media_resolver.models import MediaResolutionReport
from app.services.centinela.orchestration import ProjectState, ResourceClass
from app.services.centinela.production_spine import (
    ProductionSpine,
    StageArtifact,
    StageBinding,
    StageResult,
)
from app.services.centinela.writer_room import FinalScript
from app.utils import utils

from .models import (
    PUBLICATION_MANIFEST_FILENAME,
    REQUIRED_PUBLICATION_FILES,
    REQUIRED_REVIEW_CHECKS,
    REVIEW_PUBLICATION_VERSION,
    HumanReviewChecklist,
    PublicationCopyDraft,
    PublicationFile,
    PublicationPackageManifest,
    ReviewPacket,
)


FFMPEG_TIMEOUT_SECONDS = 300


class ReviewPublicationError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(_json_bytes(payload)).hexdigest().upper()


def _latest_ref(store: Any, project_id: str, artifact_type: str):
    refs = store.list_artifacts(project_id, artifact_type=artifact_type)
    if not refs:
        raise ReviewPublicationError(
            f"required artifact is missing: {artifact_type}"
        )
    return refs[-1]


def _load_model(store: Any, project_id: str, artifact_type: str, model_type):
    ref = _latest_ref(store, project_id, artifact_type)
    try:
        model = model_type.model_validate(store.read_json(project_id, ref.artifact_id))
    except (ValidationError, TypeError, ValueError) as exc:
        raise ReviewPublicationError(
            f"invalid {artifact_type} contract: {exc}"
        ) from exc
    return ref, model


def _ffmpeg() -> Path:
    value = Path(utils.get_ffmpeg_binary())
    if value.is_file():
        return value
    resolved = shutil.which(str(value)) or shutil.which("ffmpeg")
    if not resolved:
        raise ReviewPublicationError("FFmpeg is not available")
    return Path(resolved)


def _ffprobe(ffmpeg: Path) -> Path:
    sibling = ffmpeg.with_name("ffprobe.exe" if ffmpeg.suffix.lower() == ".exe" else "ffprobe")
    if sibling.is_file():
        return sibling
    resolved = shutil.which("ffprobe")
    if not resolved:
        raise ReviewPublicationError("ffprobe is not available")
    return Path(resolved)


def _run(command: list[str], *, timeout: int = FFMPEG_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReviewPublicationError(
            f"process failed to execute: {command[0]}: {exc}"
        ) from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise ReviewPublicationError(
            f"process exit={result.returncode}: {message[:1800]}"
        )
    return result


def _probe_media(path: Path) -> dict[str, Any]:
    ffmpeg = _ffmpeg()
    result = _run(
        [
            str(_ffprobe(ffmpeg)),
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        timeout=60,
    )
    payload = json.loads(result.stdout or "{}")
    videos = [
        row for row in payload.get("streams", [])
        if row.get("codec_type") == "video"
    ]
    audios = [
        row for row in payload.get("streams", [])
        if row.get("codec_type") == "audio"
    ]
    duration = float((payload.get("format") or {}).get("duration") or 0.0)
    if videos:
        duration = float(videos[0].get("duration") or duration or 0.0)
    return {
        "video_streams": len(videos),
        "audio_streams": len(audios),
        "audio_channels": int(audios[0].get("channels") or 0) if audios else 0,
        "width": int(videos[0].get("width") or 0) if videos else 0,
        "height": int(videos[0].get("height") or 0) if videos else 0,
        "duration": duration,
    }


def _assert_sha(ref: Any, expected: str, label: str) -> None:
    if ref.sha256.casefold() != str(expected).casefold():
        raise ReviewPublicationError(
            f"{label} SHA mismatch: artifact={ref.sha256} contract={expected}"
        )


def _extract_thumbnail(preview: Path, output: Path, duration: float) -> None:
    if not preview.is_file():
        raise ReviewPublicationError("review preview file is missing")
    seek = min(max(duration * 0.33, 0.1), max(0.1, duration - 0.1))
    _run(
        [
            str(_ffmpeg()),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{seek:.3f}",
            "-i",
            str(preview),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output),
        ],
        timeout=120,
    )
    if not output.is_file() or output.stat().st_size <= 0:
        raise ReviewPublicationError("thumbnail extraction produced no image")


def _mux_final_video(
    clean_video: Path,
    mastered_voice: Path,
    output: Path,
    *,
    width: int,
    height: int,
    expected_duration: float,
) -> dict[str, Any]:
    if not clean_video.is_file() or not mastered_voice.is_file():
        raise ReviewPublicationError("finalization input file is missing")
    _run(
        [
            str(_ffmpeg()),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(clean_video),
            "-i",
            str(mastered_voice),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    probe = _probe_media(output)
    if probe["video_streams"] != 1 or probe["audio_streams"] != 1:
        raise ReviewPublicationError(
            f"final video stream contract failed: {probe}"
        )
    if probe["width"] != width or probe["height"] != height:
        raise ReviewPublicationError(
            f"final video resolution contract failed: {probe}"
        )
    if not math.isfinite(probe["duration"]) or probe["duration"] <= 0:
        raise ReviewPublicationError("final video duration is invalid")
    if abs(probe["duration"] - expected_duration) > 0.8:
        raise ReviewPublicationError(
            "final video duration diverges from mastered voice: "
            f"video={probe['duration']:.3f} audio={expected_duration:.3f}"
        )
    return probe


def _hashtags(subject: str) -> list[str]:
    tags = [
        "#Astronomía",
        "#Astrofotografía",
        "#Universo",
        "#Cielo",
        "#ElCentinelaDelUniverso",
    ]
    folded = subject.casefold()
    known = {
        "luna": "#Luna",
        "sol": "#Sol",
        "júpiter": "#Júpiter",
        "jupiter": "#Júpiter",
        "saturno": "#Saturno",
        "marte": "#Marte",
        "venus": "#Venus",
        "mercurio": "#Mercurio",
        "eclipse": "#Eclipse",
        "cometa": "#Cometa",
        "galaxia": "#Galaxias",
        "constel": "#Constelaciones",
    }
    for needle, tag in known.items():
        if needle in folded and tag not in tags:
            tags.append(tag)
    return tags[:12]


def _build_copy_draft(script: FinalScript) -> PublicationCopyDraft:
    instagram = f"{script.social_30s.strip()}\n\n{script.closing_line.strip()}"
    tiktok = f"{script.social_15s.strip()}\n\n{script.closing_line.strip()}"
    title = re.sub(r"\s+", " ", script.subject).strip()[:100]
    description = (
        f"{script.hook.strip()}\n\n"
        f"{script.narration.strip()}\n\n"
        "EL CENTINELA DEL UNIVERSO · astronomía, astrofotografía y observación del cielo."
    )[:5000]
    return PublicationCopyDraft(
        instagram_caption=instagram[:2200],
        tiktok_caption=tiktok[:2200],
        youtube_title=title,
        youtube_description=description,
        hashtags=_hashtags(script.subject),
    )


def _rights_records(
    selection: MaterialSelectionPlan,
    report: MediaResolutionReport,
) -> tuple[list[dict[str, Any]], bool]:
    evidence_by_scene = {item.scene_number: item for item in report.scenes}
    records: list[dict[str, Any]] = []
    gate = True

    for scene in selection.selections:
        evidence = evidence_by_scene.get(scene.scene_number)
        candidate = None
        if evidence is not None and scene.selected_media_id:
            candidate = next(
                (
                    item for item in evidence.candidates
                    if item.media_id == scene.selected_media_id
                ),
                None,
            )

        rights = scene.selected_rights_status
        provider = scene.selected_provider
        eligible = scene.selected_publication_eligible is True
        status_ok = scene.status in {
            SelectionStatus.SELECTED,
            SelectionStatus.MANUAL_OVERRIDE,
        }
        rights_ok = rights in {
            Rights.CONFIRMED_OWNED,
            Rights.VERIFIED_LICENSE,
        }
        ai_forbidden = provider == Provider.AI_GENERATED or (
            scene.status == SelectionStatus.SELECTED_AI_RECREATION
        )

        license_name = candidate.license_name if candidate is not None else None
        license_url = candidate.license_url if candidate is not None else None
        attribution = (
            candidate.attribution if candidate is not None
            else scene.selected_attribution
        )
        attribution_required = bool(
            candidate.attribution_required if candidate is not None else False
        )
        source_url = (
            candidate.source_url if candidate is not None
            else scene.selected_source_url
        )

        license_complete = True
        if rights == Rights.VERIFIED_LICENSE and not license_name:
            license_complete = False
        if attribution_required and not attribution:
            license_complete = False

        row_ok = (
            eligible
            and status_ok
            and rights_ok
            and not ai_forbidden
            and license_complete
        )
        gate = gate and row_ok
        records.append(
            {
                "scene_number": scene.scene_number,
                "media_id": scene.selected_media_id,
                "provider": None if provider is None else provider.value,
                "rights_status": None if rights is None else rights.value,
                "publication_eligible": eligible,
                "license_name": license_name,
                "license_url": license_url,
                "attribution": attribution,
                "attribution_required": attribution_required,
                "source_url": source_url,
                "license_record_complete": license_complete,
                "package_rights_gate": row_ok,
            }
        )

    return records, gate


def _load_review_sources(store: Any, project_id: str) -> dict[str, Any]:
    final_ref, final_script = _load_model(store, project_id, "final_script", FinalScript)
    selection_ref, selection = _load_model(
        store, project_id, "material_selection", MaterialSelectionPlan
    )
    media_ref, media = _load_model(
        store, project_id, "media_resolution", MediaResolutionReport
    )
    audio_ref, audio = _load_model(store, project_id, "audio_bundle", AudioBundle)
    video_ref, video = _load_model(
        store, project_id, "video_base_manifest", VideoBaseManifest
    )

    social_ref = store.get_artifact(project_id, video.social_video_artifact_id)
    master_ref = store.get_artifact(project_id, video.master_video_artifact_id)
    preview_ref = store.get_artifact(project_id, video.review_preview_artifact_id)
    subtitle_ref = store.get_artifact(project_id, video.subtitle_artifact_id)
    voice_ref = store.get_artifact(project_id, audio.voice_master_artifact_id)

    _assert_sha(social_ref, video.social_sha256, "social video")
    _assert_sha(master_ref, video.master_sha256, "master video")
    _assert_sha(preview_ref, video.review_preview_sha256, "review preview")
    _assert_sha(subtitle_ref, audio.subtitle_sha256, "subtitle")
    _assert_sha(voice_ref, audio.voice_master_sha256, "mastered voice")

    if video.master_derived_from_social or not video.master_direct_from_selected_sources:
        raise ReviewPublicationError("R7 master provenance contract is invalid")
    if video.clean_base_audio_streams != 0 or video.review_preview_audio_streams != 1:
        raise ReviewPublicationError("R7 video audio-stream contract is invalid")
    if audio.auto_publication or video.auto_publication or video.wangp_triggered:
        raise ReviewPublicationError("R7 guardrail violation detected")

    return {
        "final_ref": final_ref,
        "final_script": final_script,
        "selection_ref": selection_ref,
        "selection": selection,
        "media_ref": media_ref,
        "media": media,
        "audio_ref": audio_ref,
        "audio": audio,
        "video_ref": video_ref,
        "video": video,
        "social_ref": social_ref,
        "master_ref": master_ref,
        "preview_ref": preview_ref,
        "subtitle_ref": subtitle_ref,
        "voice_ref": voice_ref,
    }


class ReviewPrepStageAdapter:
    def __call__(self, context: Any, request: dict[str, Any]) -> StageResult:
        del request
        context.check_cancelled()
        source = _load_review_sources(context.store, context.project_id)
        script: FinalScript = source["final_script"]
        video: VideoBaseManifest = source["video"]
        selection: MaterialSelectionPlan = source["selection"]
        media: MediaResolutionReport = source["media"]

        rights_records, license_gate = _rights_records(selection, media)
        eligible_count = sum(
            bool(item["package_rights_gate"]) for item in rights_records
        )
        copy_draft = _build_copy_draft(script)
        copy_payload = copy_draft.model_dump(mode="json")

        work = Path(tempfile.mkdtemp(prefix="centinela-r8-review-"))
        thumbnail = work / "thumbnail-candidate.jpg"
        preview_path = context.store.resolve_artifact_path(
            context.project_id, source["preview_ref"].artifact_id
        )
        _extract_thumbnail(
            preview_path,
            thumbnail,
            video.review_preview_duration_seconds,
        )

        thumb_id = "r8thumb-" + uuid4().hex
        copy_id = "r8copy-" + uuid4().hex
        packet_id = "r8review-" + uuid4().hex

        packet = ReviewPacket(
            project_id=context.project_id,
            subject=script.subject,
            final_script_artifact_id=source["final_ref"].artifact_id,
            final_script_sha256=source["final_ref"].sha256.upper(),
            material_selection_artifact_id=source["selection_ref"].artifact_id,
            material_selection_sha256=source["selection_ref"].sha256.upper(),
            media_resolution_artifact_id=source["media_ref"].artifact_id,
            media_resolution_sha256=source["media_ref"].sha256.upper(),
            audio_bundle_artifact_id=source["audio_ref"].artifact_id,
            audio_bundle_sha256=source["audio_ref"].sha256.upper(),
            video_base_manifest_artifact_id=source["video_ref"].artifact_id,
            video_base_manifest_sha256=source["video_ref"].sha256.upper(),
            review_preview_artifact_id=source["preview_ref"].artifact_id,
            review_preview_sha256=source["preview_ref"].sha256.upper(),
            subtitle_artifact_id=source["subtitle_ref"].artifact_id,
            subtitle_sha256=source["subtitle_ref"].sha256.upper(),
            thumbnail_candidate_artifact_id=thumb_id,
            thumbnail_candidate_sha256=_sha256(thumbnail),
            review_copy_draft_artifact_id=copy_id,
            review_copy_draft_sha256=_json_sha256(copy_payload),
            publication_copy=copy_draft,
            rights_scene_count=len(rights_records),
            publication_eligible_scene_count=eligible_count,
            license_gate_passed=license_gate,
            approval_available=license_gate,
            primary_source_verification_required=(
                script.primary_source_verification_required_for_publication
            ),
            required_checks=list(REQUIRED_REVIEW_CHECKS),
            generated_at_utc=datetime.now(timezone.utc),
        )

        common = (
            source["final_ref"].artifact_id,
            source["selection_ref"].artifact_id,
            source["media_ref"].artifact_id,
            source["audio_ref"].artifact_id,
            source["video_ref"].artifact_id,
            source["preview_ref"].artifact_id,
            source["subtitle_ref"].artifact_id,
        )

        return StageResult.complete(
            StageArtifact(
                artifact_type="review_thumbnail_candidate",
                source_path=str(thumbnail),
                suffix=".jpg",
                artifact_id=thumb_id,
                input_artifact_ids=common,
                provenance={
                    "review_publication_version": REVIEW_PUBLICATION_VERSION,
                    "source": "R7_REVIEW_PREVIEW_FRAME",
                    "ai_generated": False,
                },
                metadata={"purpose": "HUMAN_REVIEW_THUMBNAIL"},
            ),
            StageArtifact(
                artifact_type="review_copy_draft",
                payload=copy_payload,
                artifact_id=copy_id,
                input_artifact_ids=common,
                provenance={
                    "review_publication_version": REVIEW_PUBLICATION_VERSION,
                    "source": "FINAL_SCRIPT_DETERMINISTIC_COMPRESSION",
                    "llm_rerun": False,
                },
                metadata={"human_review_required": True},
            ),
            StageArtifact(
                artifact_type="review_packet",
                payload=packet.model_dump(mode="json"),
                artifact_id=packet_id,
                input_artifact_ids=(thumb_id, copy_id, *common),
                provenance={
                    "review_publication_version": REVIEW_PUBLICATION_VERSION,
                    "explicit_human_approval_required": True,
                    "auto_publication": False,
                },
                metadata={
                    "approval_available": packet.approval_available,
                    "license_gate_passed": packet.license_gate_passed,
                    "auto_publication": False,
                },
            ),
            message="R8 prepared review preview, thumbnail, publication copy and evidence packet",
            details={
                "approval_available": packet.approval_available,
                "rights_scene_count": packet.rights_scene_count,
                "publication_eligible_scene_count": packet.publication_eligible_scene_count,
                "auto_publication": False,
                "wangp": False,
            },
        )


def build_review_prep_stage_binding() -> StageBinding:
    return StageBinding(
        adapter_id="r8_review_prep_v01",
        handler=ReviewPrepStageAdapter(),
        resource_class=ResourceClass.LIGHT,
        producer_version=REVIEW_PUBLICATION_VERSION,
        invokes_network=False,
        invokes_llm=False,
        invokes_render=True,
        auto_publication=False,
    )


def record_structured_review(
    spine: ProductionSpine,
    project_id: str,
    *,
    approved: bool,
    reviewer: str,
    notes: str,
    checks: dict[str, bool],
):
    if spine.state_machine.current_state(project_id) != ProjectState.READY_FOR_HUMAN_REVIEW:
        raise ReviewPublicationError(
            "structured review requires READY_FOR_HUMAN_REVIEW"
        )

    packet_ref, packet = _load_model(
        spine.store, project_id, "review_packet", ReviewPacket
    )
    if set(checks) != set(REQUIRED_REVIEW_CHECKS):
        raise ReviewPublicationError(
            "structured review checks must match the canonical R8 contract"
        )
    normalized = {
        name: bool(checks[name])
        for name in REQUIRED_REVIEW_CHECKS
    }
    if approved and not packet.approval_available:
        raise ReviewPublicationError(
            "approval is blocked until media rights/license evidence is complete"
        )

    checklist = HumanReviewChecklist(
        project_id=project_id,
        review_packet_artifact_id=packet_ref.artifact_id,
        review_packet_sha256=packet_ref.sha256.upper(),
        reviewer=reviewer,
        notes=notes,
        approved=approved,
        **normalized,
        reviewed_at_utc=datetime.now(timezone.utc),
    )
    checklist_ref = spine.store.put_json(
        project_id,
        "review_checklist",
        checklist.model_dump(mode="json"),
        producer="centinela.review_publication.human_review",
        producer_version=REVIEW_PUBLICATION_VERSION,
        input_artifact_ids=(
            packet_ref.artifact_id,
            packet.thumbnail_candidate_artifact_id,
            packet.review_copy_draft_artifact_id,
        ),
        provenance={
            "explicit_human_decision": True,
            "review_publication_version": REVIEW_PUBLICATION_VERSION,
        },
        metadata={
            "approved": approved,
            "all_checks_passed": checklist.all_checks_passed,
            "publication_authorized": False,
        },
    )
    decision_ref = spine.record_human_review(
        project_id,
        approved=approved,
        reviewer=reviewer,
        notes=notes,
    )
    return checklist_ref, decision_ref


def review_snapshot(store: Any, project_id: str) -> dict[str, Any]:
    packet_ref, packet = _load_model(store, project_id, "review_packet", ReviewPacket)
    preview_path = store.resolve_artifact_path(
        project_id, packet.review_preview_artifact_id
    )
    thumbnail_path = store.resolve_artifact_path(
        project_id, packet.thumbnail_candidate_artifact_id
    )
    source = _load_review_sources(store, project_id)
    rights_records, current_license_gate = _rights_records(
        source["selection"],
        source["media"],
    )
    if current_license_gate != packet.license_gate_passed:
        raise ReviewPublicationError(
            "rights/license evidence changed after review packet creation"
        )
    return {
        "packet_artifact_id": packet_ref.artifact_id,
        "packet": packet.model_dump(mode="json"),
        "preview_path": str(preview_path),
        "thumbnail_path": str(thumbnail_path),
        "copy": packet.publication_copy.model_dump(mode="json"),
        "rights_records": rights_records,
        "approval_available": packet.approval_available,
        "license_gate_passed": packet.license_gate_passed,
        "primary_source_verification_required": (
            packet.primary_source_verification_required
        ),
        "required_checks": list(packet.required_checks),
    }


def _write_text(path: Path, value: str) -> None:
    path.write_text(value.rstrip() + "\n", encoding="utf-8", newline="\n")


def _write_json(path: Path, payload: Any) -> None:
    path.write_bytes(_json_bytes(payload))


def _file_record(path: Path) -> PublicationFile:
    return PublicationFile(
        name=path.name,
        sha256=_sha256(path),
        size_bytes=path.stat().st_size,
    )


def _publication_metadata(
    *,
    script: FinalScript,
    video: VideoBaseManifest,
    audio: AudioBundle,
    checklist: HumanReviewChecklist,
) -> dict[str, Any]:
    return {
        "schema": "centinela-publication-metadata-v0.1",
        "subject": script.subject,
        "language": script.language,
        "audience": script.audience,
        "social": {"width": 1080, "height": 1920, "fps": 30},
        "master": {"width": 2160, "height": 3840, "fps": 30},
        "duration_seconds": audio.duration_seconds,
        "reviewer": checklist.reviewer,
        "reviewed_at_utc": checklist.reviewed_at_utc.isoformat(),
        "master_direct_from_selected_sources": video.master_direct_from_selected_sources,
        "master_derived_from_social": video.master_derived_from_social,
        "subtitle_burned_in": video.subtitle_burned_in,
        "publication_authorized": False,
        "auto_publication": False,
    }


def _provenance_payload(
    source: dict[str, Any],
    packet: ReviewPacket,
    packet_artifact_id: str,
) -> dict[str, Any]:
    video: VideoBaseManifest = source["video"]
    return {
        "schema": "centinela-provenance-v0.1",
        "review_packet_artifact_id": packet_artifact_id,
        "final_script": {
            "artifact_id": source["final_ref"].artifact_id,
            "sha256": source["final_ref"].sha256.upper(),
        },
        "material_selection": {
            "artifact_id": source["selection_ref"].artifact_id,
            "sha256": source["selection_ref"].sha256.upper(),
        },
        "media_resolution": {
            "artifact_id": source["media_ref"].artifact_id,
            "sha256": source["media_ref"].sha256.upper(),
        },
        "audio_bundle": {
            "artifact_id": source["audio_ref"].artifact_id,
            "sha256": source["audio_ref"].sha256.upper(),
        },
        "video_base_manifest": {
            "artifact_id": source["video_ref"].artifact_id,
            "sha256": source["video_ref"].sha256.upper(),
            "master_direct_from_selected_sources": video.master_direct_from_selected_sources,
            "master_derived_from_social": video.master_derived_from_social,
        },
        "guardrails": {
            "external_network_used": False,
            "llm_rerun": False,
            "model_downloads": False,
            "wangp": False,
            "auto_publication": False,
        },
    }


class PublicationPackageStageAdapter:
    def __call__(self, context: Any, request: dict[str, Any]) -> StageResult:
        del request
        context.check_cancelled()

        source = _load_review_sources(context.store, context.project_id)
        packet_ref, packet = _load_model(
            context.store, context.project_id, "review_packet", ReviewPacket
        )
        checklist_ref, checklist = _load_model(
            context.store, context.project_id, "review_checklist", HumanReviewChecklist
        )
        decision_ref = _latest_ref(
            context.store, context.project_id, "human_review_decision"
        )
        decision = context.store.read_json(context.project_id, decision_ref.artifact_id)

        if decision.get("approved") is not True or not checklist.approved:
            return StageResult.needs_input(
                "explicit approved human review is required",
                details={"human_review_required": True},
            )
        if not checklist.all_checks_passed:
            return StageResult.needs_input(
                "all structured review checks must pass",
                details={"review_checklist_complete": False},
            )
        if not packet.license_gate_passed:
            return StageResult.blocked(
                "publication package blocked by incomplete rights/license evidence",
                details={"license_gate_passed": False},
            )

        script: FinalScript = source["final_script"]
        selection: MaterialSelectionPlan = source["selection"]
        media: MediaResolutionReport = source["media"]
        audio: AudioBundle = source["audio"]
        video: VideoBaseManifest = source["video"]
        if checklist.review_packet_artifact_id != packet_ref.artifact_id:
            return StageResult.blocked(
                "latest structured checklist does not belong to latest review packet",
                details={"review_packet_consistent": False},
            )
        if (
            str(decision.get("reviewer") or "") != checklist.reviewer
            or str(decision.get("notes") or "") != checklist.notes
        ):
            return StageResult.blocked(
                "human review decision and structured checklist disagree",
                details={"human_review_consistent": False},
            )

        copy_ref, copy_draft = _load_model(
            context.store, context.project_id, "review_copy_draft", PublicationCopyDraft
        )
        _assert_sha(
            copy_ref,
            packet.review_copy_draft_sha256,
            "review publication copy",
        )
        thumbnail_ref = context.store.get_artifact(
            context.project_id,
            packet.thumbnail_candidate_artifact_id,
        )
        _assert_sha(
            thumbnail_ref,
            packet.thumbnail_candidate_sha256,
            "review thumbnail candidate",
        )

        rights_records, license_gate = _rights_records(selection, media)
        if not license_gate:
            return StageResult.blocked(
                "rights/license evidence changed after review",
                details={"license_gate_passed": False},
            )

        work = Path(tempfile.mkdtemp(prefix="centinela-r8-package-"))
        package_dir = work / "publication"
        package_dir.mkdir(parents=True, exist_ok=False)

        social_clean = context.store.resolve_artifact_path(
            context.project_id, source["social_ref"].artifact_id
        )
        master_clean = context.store.resolve_artifact_path(
            context.project_id, source["master_ref"].artifact_id
        )
        voice_master = context.store.resolve_artifact_path(
            context.project_id, source["voice_ref"].artifact_id
        )
        subtitle = context.store.resolve_artifact_path(
            context.project_id, source["subtitle_ref"].artifact_id
        )
        thumbnail = context.store.resolve_artifact_path(
            context.project_id, packet.thumbnail_candidate_artifact_id
        )

        social_final = package_dir / "social_1080x1920.mp4"
        master_final = package_dir / "master_2160x3840.mp4"
        _mux_final_video(
            social_clean,
            voice_master,
            social_final,
            width=1080,
            height=1920,
            expected_duration=audio.duration_seconds,
        )
        context.check_cancelled()
        _mux_final_video(
            master_clean,
            voice_master,
            master_final,
            width=2160,
            height=3840,
            expected_duration=audio.duration_seconds,
        )
        context.check_cancelled()

        shutil.copy2(thumbnail, package_dir / "thumbnail.jpg")
        shutil.copy2(subtitle, package_dir / "subtitles-es.srt")
        _write_text(package_dir / "caption-instagram.txt", copy_draft.instagram_caption)
        _write_text(package_dir / "caption-tiktok.txt", copy_draft.tiktok_caption)
        _write_text(package_dir / "title-youtube.txt", copy_draft.youtube_title)
        _write_text(package_dir / "description-youtube.txt", copy_draft.youtube_description)
        _write_text(package_dir / "hashtags.txt", " ".join(copy_draft.hashtags))

        metadata = _publication_metadata(
            script=script,
            video=video,
            audio=audio,
            checklist=checklist,
        )
        provenance = _provenance_payload(source, packet, packet_ref.artifact_id)
        licenses = {
            "schema": "centinela-licenses-v0.1",
            "complete": True,
            "items": rights_records,
        }
        _write_json(package_dir / "metadata.json", metadata)
        _write_json(package_dir / "provenance.json", provenance)
        _write_json(package_dir / "licenses.json", licenses)
        _write_json(
            package_dir / "review-checklist.json",
            checklist.model_dump(mode="json"),
        )

        files = [
            _file_record(package_dir / name)
            for name in REQUIRED_PUBLICATION_FILES
        ]

        zip_id = "r8package-" + uuid4().hex
        social_id = "r8social-" + uuid4().hex
        master_id = "r8master-" + uuid4().hex
        thumb_id = "r8thumbfinal-" + uuid4().hex
        subtitles_id = "r8subtitles-" + uuid4().hex
        manifest_id = "r8manifest-" + uuid4().hex

        # A ZIP cannot contain its own SHA256 without a recursion paradox.
        # The archive copy therefore records package_zip_sha256 as null and
        # points to the persisted publication_package_manifest artifact as
        # the authoritative location of the final ZIP hash.
        manifest_without_zip = {
            "version": REVIEW_PUBLICATION_VERSION,
            "project_id": context.project_id,
            "subject": script.subject,
            "approval_artifact_id": decision_ref.artifact_id,
            "review_checklist_artifact_id": checklist_ref.artifact_id,
            "review_packet_artifact_id": packet_ref.artifact_id,
            "package_zip_artifact_id": zip_id,
            "source_final_script_sha256": source["final_ref"].sha256.upper(),
            "source_audio_bundle_sha256": source["audio_ref"].sha256.upper(),
            "source_video_base_manifest_sha256": source["video_ref"].sha256.upper(),
            "source_material_selection_sha256": source["selection_ref"].sha256.upper(),
            "source_media_resolution_sha256": source["media_ref"].sha256.upper(),
            "files": [item.model_dump(mode="json") for item in files],
            "manifest_filename": PUBLICATION_MANIFEST_FILENAME,
            "provenance_complete": True,
            "license_review_complete": True,
            "publication_authorized": False,
            "auto_publication": False,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        _write_json(
            package_dir / PUBLICATION_MANIFEST_FILENAME,
            {
                **manifest_without_zip,
                "package_zip_sha256": None,
                "package_zip_sha256_location": (
                    "persisted publication_package_manifest artifact"
                ),
            },
        )

        zip_path = work / "publication-package.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(package_dir.iterdir(), key=lambda item: item.name):
                archive.write(path, arcname=f"publication/{path.name}")

        zip_sha = _sha256(zip_path)
        manifest = PublicationPackageManifest(
            **manifest_without_zip,
            package_zip_sha256=zip_sha,
        )

        common_inputs = (
            decision_ref.artifact_id,
            checklist_ref.artifact_id,
            packet_ref.artifact_id,
            copy_ref.artifact_id,
            source["video_ref"].artifact_id,
            source["audio_ref"].artifact_id,
            source["selection_ref"].artifact_id,
            source["media_ref"].artifact_id,
        )

        return StageResult.complete(
            StageArtifact(
                artifact_type="publication_social_video",
                source_path=str(social_final),
                suffix=".mp4",
                artifact_id=social_id,
                input_artifact_ids=common_inputs,
                provenance={
                    "review_publication_version": REVIEW_PUBLICATION_VERSION,
                    "source_video_artifact_id": source["social_ref"].artifact_id,
                    "video_reencoded": False,
                    "mastered_voice_muxed": True,
                },
                metadata={"width": 1080, "height": 1920, "audio_streams": 1},
            ),
            StageArtifact(
                artifact_type="publication_master_video",
                source_path=str(master_final),
                suffix=".mp4",
                artifact_id=master_id,
                input_artifact_ids=common_inputs,
                provenance={
                    "review_publication_version": REVIEW_PUBLICATION_VERSION,
                    "source_video_artifact_id": source["master_ref"].artifact_id,
                    "source_mode": "DIRECT_R7_MASTER_PLUS_MASTERED_VOICE",
                    "derived_from_social": False,
                    "video_reencoded": False,
                    "mastered_voice_muxed": True,
                },
                metadata={"width": 2160, "height": 3840, "audio_streams": 1},
            ),
            StageArtifact(
                artifact_type="publication_thumbnail",
                source_path=str(package_dir / "thumbnail.jpg"),
                suffix=".jpg",
                artifact_id=thumb_id,
                input_artifact_ids=(packet.thumbnail_candidate_artifact_id, *common_inputs),
                provenance={
                    "review_publication_version": REVIEW_PUBLICATION_VERSION,
                    "human_reviewed_candidate": True,
                    "ai_generated": False,
                },
            ),
            StageArtifact(
                artifact_type="publication_subtitles",
                source_path=str(package_dir / "subtitles-es.srt"),
                suffix=".srt",
                artifact_id=subtitles_id,
                input_artifact_ids=(source["subtitle_ref"].artifact_id, *common_inputs),
                provenance={
                    "review_publication_version": REVIEW_PUBLICATION_VERSION,
                    "script_authority": True,
                },
            ),
            StageArtifact(
                artifact_type="publication_package_zip",
                source_path=str(zip_path),
                suffix=".zip",
                artifact_id=zip_id,
                input_artifact_ids=(social_id, master_id, thumb_id, subtitles_id, *common_inputs),
                provenance={
                    "review_publication_version": REVIEW_PUBLICATION_VERSION,
                    "canonical_root": "publication/",
                    "publication_authorized": False,
                },
                metadata={
                    "file_count": len(REQUIRED_PUBLICATION_FILES) + 1,
                    "auto_publication": False,
                },
            ),
            StageArtifact(
                artifact_type="publication_package_manifest",
                payload=manifest.model_dump(mode="json"),
                artifact_id=manifest_id,
                input_artifact_ids=(zip_id, social_id, master_id, thumb_id, subtitles_id, *common_inputs),
                provenance={
                    "review_publication_version": REVIEW_PUBLICATION_VERSION,
                    "explicit_human_approval": True,
                    "publication_authorized": False,
                    "auto_publication": False,
                },
                metadata={
                    "package_zip_artifact_id": zip_id,
                    "publication_authorized": False,
                    "auto_publication": False,
                },
            ),
            message="R8 materialized the approved manual Publication Package",
            details={
                "canonical_file_count": len(REQUIRED_PUBLICATION_FILES) + 1,
                "master_direct_r7_source": True,
                "master_derived_from_social": False,
                "publication_authorized": False,
                "auto_publication": False,
            },
        )


def build_publication_package_stage_binding() -> StageBinding:
    return StageBinding(
        adapter_id="r8_publication_package_v01",
        handler=PublicationPackageStageAdapter(),
        resource_class=ResourceClass.MEDIUM,
        producer_version=REVIEW_PUBLICATION_VERSION,
        invokes_network=False,
        invokes_llm=False,
        invokes_render=True,
        auto_publication=False,
    )


def publication_snapshot(store: Any, project_id: str) -> dict[str, Any]:
    manifest_ref, manifest = _load_model(
        store, project_id, "publication_package_manifest", PublicationPackageManifest
    )
    zip_ref = store.get_artifact(project_id, manifest.package_zip_artifact_id)
    zip_path = store.resolve_artifact_path(project_id, zip_ref.artifact_id)
    _assert_sha(zip_ref, manifest.package_zip_sha256, "publication package ZIP")
    return {
        "manifest_artifact_id": manifest_ref.artifact_id,
        "manifest": manifest.model_dump(mode="json"),
        "zip_path": str(zip_path),
        "zip_size_bytes": zip_ref.size_bytes,
        "publication_authorized": False,
        "auto_publication": False,
    }
