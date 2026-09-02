from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.models.astromedia import Rights
from app.models.final_render import (
    FINAL_RENDER_VERSION,
    MASTER_PROFILE_ID,
    SOCIAL_PROFILE_ID,
    FinalRenderArtifact,
    FinalRenderResult,
)
from app.models.finalization_e2e import (
    FinalizationE2ERequest,
    HumanFinalReviewDecision,
    HumanFinalReviewRecord,
)
from app.models.video_base_e2e import VideoBaseE2EPlan
from app.services.centinela.av_runtime.models import AudioBundle, VideoBaseManifest
from app.services.centinela.media_resolver import MediaResolutionReport
from app.services.centinela.orchestration import ProjectState, ProjectStateMachine
from app.services.centinela.production_spine import STRUCTURED_HUMAN_REVIEW_ARTIFACT_TYPE
from app.services.centinela.project_foundation import (
    ArtifactNotFoundError,
    ArtifactRef,
    ArtifactStore,
)
from app.utils import utils


class FinalRenderError(RuntimeError):
    pass


class FinalRenderBlockedError(FinalRenderError):
    pass


CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]
ProbeRunner = Callable[[Path], dict[str, Any]]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fraction(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        if "/" in value:
            left, right = value.split("/", 1)
            denominator = float(right)
            return float(left) / denominator if denominator else 0.0
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _resolve_ffprobe_binary(ffmpeg_binary: str) -> str:
    resolved = shutil.which("ffprobe")
    if resolved:
        return resolved
    ffmpeg = Path(ffmpeg_binary)
    if ffmpeg.is_absolute():
        sibling = ffmpeg.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if sibling.is_file():
            return str(sibling)
    return "ffprobe"


def _default_run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FinalRenderError(f"failed to execute {command[0]}: {exc}") from exc


def _error_text(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout or "").strip()[:2400]


class FinalRenderService:
    """Mux approved audio onto frozen VIDEO_BASE master/social artifacts.

    This post-approval stage never reselects media, rebuilds scenes, changes script,
    or re-encodes the approved video stream. The approved SRT remains an immutable
    sidecar referenced by artifact ID and SHA256.
    """

    def __init__(
        self,
        store: ArtifactStore,
        *,
        state_machine: ProjectStateMachine | None = None,
        ffmpeg_binary: str | None = None,
        ffprobe_binary: str | None = None,
        command_runner: CommandRunner | None = None,
        probe_runner: ProbeRunner | None = None,
    ) -> None:
        self.store = store
        self.state_machine = state_machine or ProjectStateMachine(store)
        self.ffmpeg_binary = ffmpeg_binary or str(utils.get_ffmpeg_binary())
        self.ffprobe_binary = ffprobe_binary or _resolve_ffprobe_binary(self.ffmpeg_binary)
        self._command_runner = command_runner or _default_run
        self._probe_runner = probe_runner

    def _probe(self, path: Path) -> dict[str, Any]:
        if self._probe_runner is not None:
            return dict(self._probe_runner(path))
        result = self._command_runner(
            [
                self.ffprobe_binary,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ]
        )
        if result.returncode != 0:
            raise FinalRenderError(f"ffprobe failed for {path}: {_error_text(result)}")
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise FinalRenderError(f"invalid ffprobe JSON for {path}") from exc
        streams = payload.get("streams") or []
        videos = [item for item in streams if item.get("codec_type") == "video"]
        audios = [item for item in streams if item.get("codec_type") == "audio"]
        subtitles = [item for item in streams if item.get("codec_type") == "subtitle"]
        if len(videos) != 1:
            raise FinalRenderError(
                f"expected one video stream in {path}, found {len(videos)}"
            )
        video = videos[0]
        try:
            duration = float(
                video.get("duration")
                or (payload.get("format") or {}).get("duration")
                or 0.0
            )
        except (TypeError, ValueError):
            duration = 0.0
        return {
            "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0),
            "fps": _fraction(video.get("avg_frame_rate") or video.get("r_frame_rate")),
            "codec": str(video.get("codec_name") or ""),
            "pix_fmt": str(video.get("pix_fmt") or ""),
            "duration": duration,
            "video_streams": len(videos),
            "audio_streams": len(audios),
            "subtitle_streams": len(subtitles),
        }

    def _require_final_approved(self, project_id: str) -> None:
        state = self.state_machine.current_state(project_id)
        if state != ProjectState.FINAL_APPROVED:
            raise FinalRenderBlockedError(
                f"final render requires FINAL_APPROVED; project is {state.value}"
            )

    def _validated_review(self, project_id: str) -> tuple[ArtifactRef, HumanFinalReviewRecord]:
        refs = self.store.list_artifacts(
            project_id,
            artifact_type=STRUCTURED_HUMAN_REVIEW_ARTIFACT_TYPE,
        )
        if not refs:
            raise FinalRenderBlockedError(
                "FINAL_APPROVED lacks a HumanFinalReviewRecord artifact"
            )
        ref = refs[-1]
        try:
            record = HumanFinalReviewRecord.model_validate(
                self.store.read_json(project_id, ref.artifact_id, verify_integrity=True)
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise FinalRenderBlockedError("invalid HumanFinalReviewRecord") from exc
        if record.decision != HumanFinalReviewDecision.APPROVE:
            raise FinalRenderBlockedError("final render requires APPROVE review decision")
        if not record.all_required_gates_passed:
            raise FinalRenderBlockedError(
                "final render requires all seven canonical human review gates"
            )

        authorized = False
        for transition in reversed(self.state_machine.history(project_id)):
            metadata = transition.metadata if isinstance(transition.metadata, dict) else {}
            if not (
                metadata.get("human_review") is True
                and metadata.get("structured_review") is True
            ):
                continue
            authorized = (
                transition.to_state == ProjectState.FINAL_APPROVED
                and metadata.get("decision_artifact_id") == ref.artifact_id
                and metadata.get("decision") == HumanFinalReviewDecision.APPROVE.value
                and metadata.get("approved") is True
            )
            break
        if not authorized:
            raise FinalRenderBlockedError(
                "structured review artifact does not authorize current FINAL_APPROVED state"
            )
        return ref, record

    @staticmethod
    def _verify_file_hash(path: Path, expected: str, label: str) -> str:
        if not path.is_file() or path.stat().st_size <= 0:
            raise FinalRenderBlockedError(f"missing approved {label} artifact")
        actual = _sha256(path)
        if actual.casefold() != expected.casefold():
            raise FinalRenderBlockedError(f"{label} SHA256 mismatch")
        return actual

    def _validated_inputs(
        self,
        project_id: str,
        review_ref: ArtifactRef,
        review: HumanFinalReviewRecord,
    ) -> dict[str, Any]:
        try:
            video_manifest_ref = self.store.get_latest_artifact(
                project_id, "video_base_manifest"
            )
            video_manifest = VideoBaseManifest.model_validate(
                self.store.read_json(
                    project_id,
                    video_manifest_ref.artifact_id,
                    verify_integrity=True,
                )
            )
            audio_ref = self.store.get_artifact(
                project_id,
                video_manifest.source_audio_bundle_artifact_id,
            )
            audio = AudioBundle.model_validate(
                self.store.read_json(project_id, audio_ref.artifact_id, verify_integrity=True)
            )
            media_ref = self.store.get_artifact(
                project_id,
                video_manifest.source_media_resolution_artifact_id,
            )
            media = MediaResolutionReport.model_validate(
                self.store.read_json(project_id, media_ref.artifact_id, verify_integrity=True)
            )
            master_ref = self.store.get_artifact(
                project_id, video_manifest.master_video_artifact_id
            )
            social_ref = self.store.get_artifact(
                project_id, video_manifest.social_video_artifact_id
            )
            audio_master_ref = self.store.get_artifact(
                project_id, audio.voice_master_artifact_id
            )
            subtitle_ref = self.store.get_artifact(
                project_id, audio.subtitle_artifact_id
            )
        except (ArtifactNotFoundError, ValidationError, TypeError, ValueError) as exc:
            raise FinalRenderBlockedError(
                "approved final-render input artifact is missing or invalid"
            ) from exc

        if not (
            video_manifest.source_plan_context_hash
            == audio.source_plan_context_hash
            == media.source_plan_context_hash
        ):
            raise FinalRenderBlockedError(
                "VIDEO_BASE/audio/media scientific lineage mismatch"
            )
        if video_manifest.subtitle_artifact_id != audio.subtitle_artifact_id:
            raise FinalRenderBlockedError("VIDEO_BASE/audio subtitle lineage mismatch")
        if audio_ref.artifact_id != video_manifest.source_audio_bundle_artifact_id:
            raise FinalRenderBlockedError("VIDEO_BASE/audio bundle lineage mismatch")
        if audio.auto_publication or video_manifest.auto_publication:
            raise FinalRenderBlockedError("AUTO_PUBLICATION invariant violation")
        if audio.sample_rate_hz != 48000 or audio.channels < 1:
            raise FinalRenderBlockedError("approved audio master contract is invalid")

        if media.unresolved_count != 0 or not review.rights_passed:
            raise FinalRenderBlockedError("publication rights are not fully approved")
        accepted_rights = {Rights.CONFIRMED_OWNED, Rights.VERIFIED_LICENSE}
        for scene in media.scenes:
            if not scene.selected_media_id:
                raise FinalRenderBlockedError(
                    f"scene {scene.scene_number} lacks approved selected media"
                )
            if (
                scene.selected_publication_eligible is not True
                or scene.selected_rights_status not in accepted_rights
            ):
                raise FinalRenderBlockedError(
                    f"scene {scene.scene_number} lacks publication-eligible rights"
                )

        master_path = self.store.resolve_artifact_path(project_id, master_ref.artifact_id)
        social_path = self.store.resolve_artifact_path(project_id, social_ref.artifact_id)
        audio_path = self.store.resolve_artifact_path(project_id, audio_master_ref.artifact_id)
        subtitle_path = self.store.resolve_artifact_path(project_id, subtitle_ref.artifact_id)

        master_sha = self._verify_file_hash(master_path, master_ref.sha256, "master base")
        social_sha = self._verify_file_hash(social_path, social_ref.sha256, "social base")
        audio_sha = self._verify_file_hash(audio_path, audio_master_ref.sha256, "audio master")
        subtitle_sha = self._verify_file_hash(subtitle_path, subtitle_ref.sha256, "subtitle")

        if master_sha.casefold() != video_manifest.master_sha256.casefold():
            raise FinalRenderBlockedError("master base manifest hash mismatch")
        if social_sha.casefold() != video_manifest.social_sha256.casefold():
            raise FinalRenderBlockedError("social base manifest hash mismatch")
        if audio_sha.casefold() != audio.voice_master_sha256.casefold():
            raise FinalRenderBlockedError("audio bundle master hash mismatch")
        if subtitle_sha.casefold() != audio.subtitle_sha256.casefold():
            raise FinalRenderBlockedError("audio bundle subtitle hash mismatch")

        master_probe = self._validate_base_probe(master_path, 2160, 3840, "master")
        social_probe = self._validate_base_probe(social_path, 1080, 1920, "social")
        for label, probe in (("master", master_probe), ("social", social_probe)):
            if abs(float(probe["duration"]) - audio.duration_seconds) > 0.75:
                raise FinalRenderBlockedError(
                    f"approved {label} VIDEO_BASE duration does not match approved audio"
                )

        rights_rows: list[dict[str, Any]] = []
        for scene in media.scenes:
            selected = next(
                (
                    item
                    for item in scene.candidates
                    if item.media_id == scene.selected_media_id
                ),
                None,
            )
            rights_rows.append(
                {
                    "scene_number": scene.scene_number,
                    "media_id": scene.selected_media_id,
                    "provider": (
                        scene.selected_provider.value if scene.selected_provider else None
                    ),
                    "rights_status": (
                        scene.selected_rights_status.value
                        if scene.selected_rights_status
                        else None
                    ),
                    "publication_eligible": scene.selected_publication_eligible,
                    "source_url": selected.source_url if selected else None,
                    "license_name": selected.license_name if selected else None,
                    "license_url": selected.license_url if selected else None,
                    "attribution": selected.attribution if selected else None,
                    "attribution_required": (
                        selected.attribution_required if selected else None
                    ),
                }
            )

        return {
            "review_ref": review_ref,
            "video_manifest_ref": video_manifest_ref,
            "video_manifest": video_manifest,
            "audio_ref": audio_ref,
            "audio": audio,
            "media_ref": media_ref,
            "media": media,
            "master_ref": master_ref,
            "master_path": master_path,
            "master_probe": master_probe,
            "social_ref": social_ref,
            "social_path": social_path,
            "social_probe": social_probe,
            "audio_master_ref": audio_master_ref,
            "audio_path": audio_path,
            "subtitle_ref": subtitle_ref,
            "subtitle_path": subtitle_path,
            "subtitle_sha": subtitle_sha,
            "rights_rows": rights_rows,
        }

    def _validate_base_probe(
        self,
        path: Path,
        width: int,
        height: int,
        label: str,
    ) -> dict[str, Any]:
        probe = self._probe(path)
        if (
            probe.get("video_streams", 1) != 1
            or probe.get("width") != width
            or probe.get("height") != height
            or abs(float(probe.get("fps") or 0.0) - 30.0) > 0.05
            or int(probe.get("audio_streams") or 0) != 0
            or float(probe.get("duration") or 0.0) <= 0.0
        ):
            raise FinalRenderBlockedError(
                f"approved {label} VIDEO_BASE artifact failed ffprobe contract"
            )
        return probe

    @staticmethod
    def _fingerprint(inputs: dict[str, Any]) -> str:
        stable = {
            "version": FINAL_RENDER_VERSION,
            "review": (
                inputs["review_ref"].artifact_id,
                inputs["review_ref"].sha256,
            ),
            "video_manifest": (
                inputs["video_manifest_ref"].artifact_id,
                inputs["video_manifest_ref"].sha256,
            ),
            "audio": (inputs["audio_ref"].artifact_id, inputs["audio_ref"].sha256),
            "media": (inputs["media_ref"].artifact_id, inputs["media_ref"].sha256),
            "master": (inputs["master_ref"].artifact_id, inputs["master_ref"].sha256),
            "social": (inputs["social_ref"].artifact_id, inputs["social_ref"].sha256),
            "audio_master": (
                inputs["audio_master_ref"].artifact_id,
                inputs["audio_master_ref"].sha256,
            ),
            "subtitle": (
                inputs["subtitle_ref"].artifact_id,
                inputs["subtitle_ref"].sha256,
            ),
        }
        raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _load_reusable(self, project_id: str, fingerprint: str) -> FinalRenderResult | None:
        for ref in reversed(
            self.store.list_artifacts(project_id, artifact_type="final_render_manifest")
        ):
            if ref.metadata.get("input_fingerprint") != fingerprint:
                continue
            try:
                result = FinalRenderResult.model_validate(
                    self.store.read_json(project_id, ref.artifact_id, verify_integrity=True)
                )
                if result.manifest_artifact_id != ref.artifact_id:
                    continue
                for artifact in (result.master, result.social):
                    stored = self.store.get_artifact(project_id, artifact.artifact_id)
                    path = self.store.resolve_artifact_path(project_id, stored.artifact_id)
                    actual = self._verify_file_hash(path, stored.sha256, artifact.profile_id)
                    if actual.casefold() != artifact.sha256.casefold():
                        raise FinalRenderBlockedError("reusable final render hash mismatch")
                return result.model_copy(update={"reused": True})
            except Exception:
                continue
        return None

    def _mux(self, base_video: Path, audio: Path, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.ffmpeg_binary,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(base_video),
            "-i",
            str(audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-map_metadata",
            "-1",
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
        result = self._command_runner(command)
        if result.returncode != 0:
            raise FinalRenderError(
                f"final FFmpeg mux failed for {output.name}: {_error_text(result)}"
            )
        if not output.is_file() or output.stat().st_size <= 0:
            raise FinalRenderError(f"final FFmpeg mux produced no file: {output}")

    def _validate_final_probe(
        self,
        path: Path,
        width: int,
        height: int,
        label: str,
        expected_duration: float,
        expected_video_codec: str,
    ) -> dict[str, Any]:
        probe = self._probe(path)
        if (
            probe.get("video_streams", 1) != 1
            or probe.get("width") != width
            or probe.get("height") != height
            or abs(float(probe.get("fps") or 0.0) - 30.0) > 0.05
            or int(probe.get("audio_streams") or 0) != 1
            or float(probe.get("duration") or 0.0) <= 0.0
            or abs(float(probe.get("duration") or 0.0) - expected_duration) > 0.75
            or str(probe.get("codec") or "") != expected_video_codec
        ):
            raise FinalRenderError(
                f"final {label} ffprobe validation failed: "
                + json.dumps(probe, ensure_ascii=False, sort_keys=True)
            )
        return probe

    def _ingest_or_verify(
        self,
        project_id: str,
        *,
        artifact_id: str,
        artifact_type: str,
        source_path: Path,
        input_artifact_ids: tuple[str, ...],
        provenance: dict[str, Any],
        metadata: dict[str, Any],
    ) -> ArtifactRef:
        try:
            existing = self.store.get_artifact(project_id, artifact_id)
        except ArtifactNotFoundError:
            return self.store.ingest_file(
                project_id,
                artifact_type,
                source_path,
                producer="centinela.final_renderer",
                artifact_id=artifact_id,
                producer_version=FINAL_RENDER_VERSION,
                input_artifact_ids=input_artifact_ids,
                provenance=provenance,
                metadata=metadata,
            )
        if existing.artifact_type != artifact_type:
            raise FinalRenderBlockedError("deterministic final artifact ID type mismatch")
        existing_path = self.store.resolve_artifact_path(project_id, existing.artifact_id)
        existing_sha = self._verify_file_hash(
            existing_path,
            existing.sha256,
            artifact_type,
        )
        rendered_sha = self._verify_file_hash(
            source_path,
            _sha256(source_path),
            f"candidate {artifact_type}",
        )
        if rendered_sha.casefold() != existing_sha.casefold():
            raise FinalRenderBlockedError(
                "deterministic final render changed for identical approved inputs"
            )
        return existing

    def render(
        self,
        project_id: str,
        *,
        work_dir: str | Path | None = None,
    ) -> FinalRenderResult:
        self._require_final_approved(project_id)
        review_ref, review = self._validated_review(project_id)
        inputs = self._validated_inputs(project_id, review_ref, review)
        fingerprint = self._fingerprint(inputs)

        reusable = self._load_reusable(project_id, fingerprint)
        if reusable is not None:
            return reusable

        work = (
            Path(work_dir)
            if work_dir is not None
            else Path(utils.task_dir(f"final-render-{project_id}")) / fingerprint[:16]
        )
        work.mkdir(parents=True, exist_ok=True)
        master_output = work / "final-master-2160x3840.mp4"
        social_output = work / "final-social-1080x1920.mp4"

        self._mux(inputs["master_path"], inputs["audio_path"], master_output)
        master_probe = self._validate_final_probe(
            master_output,
            2160,
            3840,
            "master",
            inputs["audio"].duration_seconds,
            str(inputs["master_probe"]["codec"]),
        )
        self._mux(inputs["social_path"], inputs["audio_path"], social_output)
        social_probe = self._validate_final_probe(
            social_output,
            1080,
            1920,
            "social",
            inputs["audio"].duration_seconds,
            str(inputs["social_probe"]["codec"]),
        )

        token = fingerprint[:24].lower()
        master_id = f"g002-final-master-{token}"
        social_id = f"g002-final-social-{token}"
        manifest_id = f"g002-final-render-{token}"
        common_inputs = (
            inputs["video_manifest_ref"].artifact_id,
            inputs["audio_ref"].artifact_id,
            inputs["media_ref"].artifact_id,
            inputs["audio_master_ref"].artifact_id,
            inputs["subtitle_ref"].artifact_id,
            inputs["review_ref"].artifact_id,
        )

        master_ref = self._ingest_or_verify(
            project_id,
            artifact_id=master_id,
            artifact_type="final_master_video",
            source_path=master_output,
            input_artifact_ids=(inputs["master_ref"].artifact_id, *common_inputs),
            provenance={
                "final_render_version": FINAL_RENDER_VERSION,
                "source_video_base_artifact_id": inputs["master_ref"].artifact_id,
                "source_video_base_sha256": inputs["master_ref"].sha256,
                "human_review_artifact_id": review_ref.artifact_id,
                "subtitle_artifact_id": inputs["subtitle_ref"].artifact_id,
                "subtitle_mode": "SIDECAR_PRESERVED",
                "post_review_content_mutation": False,
            },
            metadata={
                "profile_id": MASTER_PROFILE_ID,
                "width": 2160,
                "height": 3840,
                "fps": 30,
                "audio_streams": int(master_probe["audio_streams"]),
                "publication_rights_ready": True,
                "auto_publication": False,
            },
        )
        social_ref = self._ingest_or_verify(
            project_id,
            artifact_id=social_id,
            artifact_type="final_social_video",
            source_path=social_output,
            input_artifact_ids=(inputs["social_ref"].artifact_id, *common_inputs),
            provenance={
                "final_render_version": FINAL_RENDER_VERSION,
                "source_video_base_artifact_id": inputs["social_ref"].artifact_id,
                "source_video_base_sha256": inputs["social_ref"].sha256,
                "human_review_artifact_id": review_ref.artifact_id,
                "subtitle_artifact_id": inputs["subtitle_ref"].artifact_id,
                "subtitle_mode": "SIDECAR_PRESERVED",
                "post_review_content_mutation": False,
            },
            metadata={
                "profile_id": SOCIAL_PROFILE_ID,
                "width": 1080,
                "height": 1920,
                "fps": 30,
                "audio_streams": int(social_probe["audio_streams"]),
                "publication_rights_ready": True,
                "auto_publication": False,
            },
        )

        master_path = self.store.resolve_artifact_path(project_id, master_ref.artifact_id)
        social_path = self.store.resolve_artifact_path(project_id, social_ref.artifact_id)
        master_sha = self._verify_file_hash(master_path, master_ref.sha256, "final master")
        social_sha = self._verify_file_hash(social_path, social_ref.sha256, "final social")

        result = FinalRenderResult(
            project_id=project_id,
            input_fingerprint=fingerprint,
            manifest_artifact_id=manifest_id,
            human_review_artifact_id=review_ref.artifact_id,
            human_review=review,
            video_base_manifest_artifact_id=inputs["video_manifest_ref"].artifact_id,
            audio_bundle_artifact_id=inputs["audio_ref"].artifact_id,
            media_resolution_artifact_id=inputs["media_ref"].artifact_id,
            subtitle_artifact_id=inputs["subtitle_ref"].artifact_id,
            subtitle_sha256=inputs["subtitle_sha"],
            master=FinalRenderArtifact(
                profile_id=MASTER_PROFILE_ID,
                artifact_id=master_ref.artifact_id,
                file_path=str(master_path),
                sha256=master_sha,
                width=int(master_probe["width"]),
                height=int(master_probe["height"]),
                fps=float(master_probe["fps"]),
                codec=str(master_probe["codec"]),
                pixel_format=str(master_probe.get("pix_fmt") or "") or None,
                duration_seconds=float(master_probe["duration"]),
                audio_stream_count=int(master_probe["audio_streams"]),
                source_video_base_artifact_id=inputs["master_ref"].artifact_id,
                source_video_base_sha256=inputs["master_ref"].sha256,
                source_audio_artifact_id=inputs["audio_master_ref"].artifact_id,
                source_subtitle_artifact_id=inputs["subtitle_ref"].artifact_id,
                audio_codec="aac",
                ffprobe=master_probe,
            ),
            social=FinalRenderArtifact(
                profile_id=SOCIAL_PROFILE_ID,
                artifact_id=social_ref.artifact_id,
                file_path=str(social_path),
                sha256=social_sha,
                width=int(social_probe["width"]),
                height=int(social_probe["height"]),
                fps=float(social_probe["fps"]),
                codec=str(social_probe["codec"]),
                pixel_format=str(social_probe.get("pix_fmt") or "") or None,
                duration_seconds=float(social_probe["duration"]),
                audio_stream_count=int(social_probe["audio_streams"]),
                source_video_base_artifact_id=inputs["social_ref"].artifact_id,
                source_video_base_sha256=inputs["social_ref"].sha256,
                source_audio_artifact_id=inputs["audio_master_ref"].artifact_id,
                source_subtitle_artifact_id=inputs["subtitle_ref"].artifact_id,
                audio_codec="aac",
                ffprobe=social_probe,
            ),
            rights_provenance={
                "media_resolution_artifact_id": inputs["media_ref"].artifact_id,
                "media_resolution_sha256": inputs["media_ref"].sha256,
                "upstream_publication_ready": inputs["media"].publication_ready,
                "human_review_rights_passed": review.rights_passed,
                "selected_media": inputs["rights_rows"],
            },
            generated_at_utc=datetime.now(timezone.utc),
        )

        try:
            existing_manifest = self.store.get_artifact(project_id, manifest_id)
        except ArtifactNotFoundError:
            manifest_ref = self.store.put_json(
                project_id,
                "final_render_manifest",
                result.model_dump(mode="json"),
                producer="centinela.final_renderer",
                artifact_id=manifest_id,
                producer_version=FINAL_RENDER_VERSION,
                input_artifact_ids=(
                    master_ref.artifact_id,
                    social_ref.artifact_id,
                    *common_inputs,
                ),
                provenance={
                    "final_render_version": FINAL_RENDER_VERSION,
                    "human_review_artifact_id": review_ref.artifact_id,
                    "video_base_manifest_artifact_id": inputs["video_manifest_ref"].artifact_id,
                    "post_review_content_mutation": False,
                    "verification_target": "FinalizationE2E",
                },
                metadata={
                    "input_fingerprint": fingerprint,
                    "master_artifact_id": master_ref.artifact_id,
                    "social_artifact_id": social_ref.artifact_id,
                    "auto_publication": False,
                },
            )
            if manifest_ref.artifact_id != manifest_id:
                raise FinalRenderError("final render manifest ID mismatch")
        else:
            if existing_manifest.artifact_type != "final_render_manifest":
                raise FinalRenderBlockedError("deterministic final manifest ID collision")

        return result


def build_finalization_request(
    video_base: VideoBaseE2EPlan,
    final_render: FinalRenderResult,
) -> FinalizationE2ERequest:
    if not isinstance(video_base, VideoBaseE2EPlan):
        raise TypeError("video_base must be VideoBaseE2EPlan")
    if not isinstance(final_render, FinalRenderResult):
        raise TypeError("final_render must be FinalRenderResult")
    return FinalizationE2ERequest(
        video_base=video_base,
        human_review=final_render.human_review,
        artifacts=final_render.finalization_artifacts(),
    )
