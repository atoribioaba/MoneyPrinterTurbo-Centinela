from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.models.astromedia import Provider, Rights
from app.models.final_render import FinalRenderResult
from app.models.finalization_e2e import (
    FinalizationE2EPlan,
    FinalizationE2EStatus,
    HumanFinalReviewDecision,
    HumanFinalReviewRecord,
)
from app.models.publication_package import (
    PublicationMetadata,
    PublicationPackagePlan,
    PublicationPackageRequest,
    PublicationPackageStatus,
    PublicationSupportAssetProbe,
    PublicationSupportManifest,
)
from app.models.video_base_e2e import VideoBaseE2ECheck, VideoBaseE2EPlan, VideoBaseE2EStatus
from app.services.centinela.av_runtime import VideoBaseManifest, build_finalization_request
from app.services.centinela.media_resolver import MediaResolutionReport
from app.services.centinela.orchestration import ResourceClass
from app.services.centinela.production_spine import (
    STRUCTURED_HUMAN_REVIEW_ARTIFACT_TYPE,
    StageArtifact,
    StageBinding,
    StageExecutionContext,
    StageResult,
)
from app.services.centinela.project_foundation import ArtifactNotFoundError, ArtifactRef, ArtifactStore
from app.services.finalization_e2e import build_finalization_e2e
from app.services.publication_package import build_publication_package

VERSION = "g006-publication-package-v0.1"
FINAL_RENDER = "final_render_manifest"
FINALIZATION = "finalization_e2e_evidence"
PLAN = "publication_package_plan"
THUMBNAIL = "publication_thumbnail"
PACKAGE_INPUT = "publication_package_input"
PACKAGE_MANIFEST = "publication_package_manifest"
TARGETS = {
    "master": "video/master_2160x3840.mp4",
    "social": "video/social_1080x1920.mp4",
    "thumbnail": "thumbnail/thumbnail.jpg",
    "subtitles_es": "subtitles/subtitles-es.srt",
    "provenance": "metadata/sources-licenses-provenance.json",
    "publication_checklist": "metadata/publication-checklist.json",
    "caption": "metadata/caption.txt",
    "metadata": "metadata/metadata.json",
}
PUBLISHABLE_RIGHTS = {Rights.CONFIRMED_OWNED, Rights.VERIFIED_LICENSE}

# Stable public names used by the frozen G-006 integration/tests.
FINALIZATION_EVIDENCE_ARTIFACT_TYPE = FINALIZATION
PUBLICATION_PLAN_ARTIFACT_TYPE = PLAN
PUBLICATION_THUMBNAIL_ARTIFACT_TYPE = THUMBNAIL
PUBLICATION_INPUT_ARTIFACT_TYPE = PACKAGE_INPUT
PUBLICATION_MANIFEST_ARTIFACT_TYPE = PACKAGE_MANIFEST


class PublicationPackageBlockedError(RuntimeError):
    pass


class PublicationPackageInputRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    version: str = VERSION
    project_id: str = Field(min_length=1, max_length=128)
    review_artifact_id: str = Field(min_length=1, max_length=128)
    thumbnail_artifact_id: str = Field(min_length=1, max_length=128)
    thumbnail_sha256: str = Field(min_length=64, max_length=64)
    metadata: PublicationMetadata
    created_at_utc: datetime


@dataclass(frozen=True, slots=True)
class PackageSource:
    logical_name: str
    sha256: str
    artifact_id: str | None = None
    path: Path | None = None
    data: bytes | None = None

    def __post_init__(self) -> None:
        if (self.path is None) == (self.data is None) or len(self.sha256) != 64:
            raise ValueError("invalid PackageSource")


@dataclass(frozen=True, slots=True)
class MaterializationResult:
    package_dir: Path
    manifest_path: Path
    reused: bool


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _json_bytes(value: Any, *, pretty: bool = False) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
            allow_nan=False,
        )
        + ("\n" if pretty else "")
    ).encode("utf-8")


# Compatibility helper names retained for the frozen G-006 test contract.
def _compact_json_bytes(value: Any) -> bytes:
    return _json_bytes(value)


def _sha256_bytes(data: bytes) -> str:
    return _sha(data)


def _hex_sha(value: Any, label: str) -> str:
    value = str(value or "").lower()
    try:
        if len(value) != 64:
            raise ValueError
        int(value, 16)
    except ValueError as exc:
        raise PublicationPackageBlockedError(f"invalid {label} SHA256") from exc
    return value


def _read_model(store: ArtifactStore, project_id: str, ref: ArtifactRef, model, label: str):
    try:
        return model.model_validate(store.read_json(project_id, ref.artifact_id, verify_integrity=True))
    except (ValidationError, TypeError, ValueError) as exc:
        raise PublicationPackageBlockedError(f"invalid {label}") from exc


def _verified_ref(
    store: ArtifactStore, project_id: str, artifact_id: str, expected_sha: str, label: str
) -> tuple[ArtifactRef, Path]:
    try:
        ref = store.get_artifact(project_id, artifact_id)
        path = store.resolve_artifact_path(project_id, artifact_id)
    except ArtifactNotFoundError as exc:
        raise PublicationPackageBlockedError(f"missing {label}") from exc
    expected = _hex_sha(expected_sha, label)
    if ref.project_id != project_id or ref.sha256.lower() != expected or path.is_symlink() or not path.is_file():
        raise PublicationPackageBlockedError(f"invalid {label} identity/path")
    actual, _ = _file_sha(path)
    if actual != expected:
        raise PublicationPackageBlockedError(f"{label} SHA256 mismatch")
    return ref, path


def _review(context: StageExecutionContext) -> tuple[ArtifactRef, HumanFinalReviewRecord]:
    ref = context.previous_receipt
    if ref is None or ref.artifact_type != STRUCTURED_HUMAN_REVIEW_ARTIFACT_TYPE:
        raise PublicationPackageBlockedError("authoritative Review receipt missing")
    record = _read_model(context.store, context.project_id, ref, HumanFinalReviewRecord, "Review")
    if ref.project_id != context.project_id or record.decision != HumanFinalReviewDecision.APPROVE or not record.all_required_gates_passed:
        raise PublicationPackageBlockedError("Review 7/7 required")
    return ref, record


def _latest_for_review(store: ArtifactStore, project_id: str, artifact_type: str, review_id: str) -> ArtifactRef:
    refs = [
        ref
        for ref in store.list_artifacts(project_id, artifact_type=artifact_type)
        if ref.metadata.get("human_review_artifact_id") == review_id
        or ref.provenance.get("human_review_artifact_id") == review_id
    ]
    if not refs:
        raise PublicationPackageBlockedError(f"{artifact_type} missing for current Review")
    return refs[-1]


def validate_rights_provenance(
    store: ArtifactStore,
    project_id: str,
    final_render: FinalRenderResult,
    video_manifest: VideoBaseManifest,
    review: HumanFinalReviewRecord,
) -> tuple[ArtifactRef, MediaResolutionReport]:
    if final_render.project_id != project_id or not review.rights_passed:
        raise PublicationPackageBlockedError("rights project/Review mismatch")
    p = final_render.rights_provenance
    if not isinstance(p, dict) or not p:
        raise PublicationPackageBlockedError("rights_provenance missing")
    if p.get("upstream_publication_ready") is not True or p.get("human_review_rights_passed") is not True:
        raise PublicationPackageBlockedError("publication readiness/Review rights false")
    media_id = str(p.get("media_resolution_artifact_id") or "")
    if not media_id or media_id != final_render.media_resolution_artifact_id or media_id != video_manifest.source_media_resolution_artifact_id:
        raise PublicationPackageBlockedError("media rights lineage mismatch")
    expected_sha = _hex_sha(p.get("media_resolution_sha256"), "media_resolution")
    try:
        ref = store.get_artifact(project_id, media_id)
    except ArtifactNotFoundError as exc:
        raise PublicationPackageBlockedError("media_resolution missing") from exc
    if ref.sha256.lower() != expected_sha:
        raise PublicationPackageBlockedError("media_resolution SHA mismatch")
    media = _read_model(store, project_id, ref, MediaResolutionReport, "MediaResolutionReport")
    if not media.publication_ready or media.unresolved_count != 0 or media.source_plan_context_hash != video_manifest.source_plan_context_hash:
        raise PublicationPackageBlockedError("media rights/scientific lineage invalid")

    rows = p.get("selected_media")
    selected = [scene for scene in media.scenes if scene.selected_media_id]
    if not isinstance(rows, list) or not rows or len(rows) != len(selected):
        raise PublicationPackageBlockedError("selected-media provenance missing")
    by_scene = {row.get("scene_number"): row for row in rows if isinstance(row, dict)}
    if len(by_scene) != len(rows):
        raise PublicationPackageBlockedError("selected-media provenance identity invalid")
    for scene in selected:
        row = by_scene.get(scene.scene_number)
        if row is None or row.get("media_id") != scene.selected_media_id:
            raise PublicationPackageBlockedError("selected media id mismatch")
        provider = scene.selected_provider.value if scene.selected_provider else None
        if row.get("provider") != provider:
            raise PublicationPackageBlockedError("selected media provider mismatch")
        try:
            rights = Rights(str(row.get("rights_status") or ""))
        except ValueError as exc:
            raise PublicationPackageBlockedError("invalid rights status") from exc
        if rights not in PUBLISHABLE_RIGHTS or rights != scene.selected_rights_status:
            raise PublicationPackageBlockedError("non-publishable rights status")
        if row.get("publication_eligible") is not True or scene.selected_publication_eligible is not True:
            raise PublicationPackageBlockedError("selected media ineligible")
        candidate = next((item for item in scene.candidates if item.media_id == scene.selected_media_id), None)
        if candidate is not None:
            for key in ("source_url", "license_name", "license_url", "attribution", "attribution_required"):
                if row.get(key) != getattr(candidate, key):
                    raise PublicationPackageBlockedError(f"selected media {key} mismatch")
        if rights == Rights.CONFIRMED_OWNED and provider != Provider.OWN_MEDIA.value:
            raise PublicationPackageBlockedError("owned media provenance invalid")
        if rights == Rights.VERIFIED_LICENSE and not str(row.get("license_name") or "").strip():
            raise PublicationPackageBlockedError("verified license evidence missing")
        if row.get("attribution_required") is True and not str(row.get("attribution") or "").strip():
            raise PublicationPackageBlockedError("required attribution missing")
    return ref, media


def _video_e2e(store: ArtifactStore, project_id: str, result: FinalRenderResult):
    try:
        ref = store.get_artifact(project_id, result.video_base_manifest_artifact_id)
    except ArtifactNotFoundError as exc:
        raise PublicationPackageBlockedError("video_base_manifest missing") from exc
    manifest = _read_model(store, project_id, ref, VideoBaseManifest, "VideoBaseManifest")
    if manifest.source_media_resolution_artifact_id != result.media_resolution_artifact_id or manifest.subtitle_artifact_id != result.subtitle_artifact_id:
        raise PublicationPackageBlockedError("FinalRender/VIDEO_BASE lineage mismatch")
    master, _ = _verified_ref(store, project_id, manifest.master_video_artifact_id, manifest.master_sha256, "VIDEO_BASE master")
    social, _ = _verified_ref(store, project_id, manifest.social_video_artifact_id, manifest.social_sha256, "VIDEO_BASE social")
    checks = [
        VideoBaseE2ECheck(check_id="manifest", passed=True, detail=ref.artifact_id),
        VideoBaseE2ECheck(check_id="hashes", passed=master.sha256 == manifest.master_sha256 and social.sha256 == manifest.social_sha256, detail="master/social"),
        VideoBaseE2ECheck(check_id="profiles", passed=manifest.master_width == 2160 and manifest.master_height == 3840 and manifest.social_width == 1080 and manifest.social_height == 1920, detail="canonical"),
        VideoBaseE2ECheck(check_id="fps", passed=manifest.fps == 30, detail=str(manifest.fps)),
        VideoBaseE2ECheck(check_id="clean", passed=manifest.clean_base_audio_streams == 0 and manifest.master_direct_from_selected_sources and not manifest.master_derived_from_social and not manifest.auto_publication, detail="R7"),
    ]
    stable = {"manifest": (ref.artifact_id, ref.sha256), "checks": [c.model_dump(mode="json") for c in checks]}
    plan = VideoBaseE2EPlan(
        source_production_orchestrator_hash=ref.sha256,
        status=VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS if all(c.passed for c in checks) else VideoBaseE2EStatus.VIDEO_BASE_E2E_FAIL,
        real_artifact_present=True,
        check_count=len(checks),
        passed_count=sum(c.passed for c in checks),
        failed_count=sum(not c.passed for c in checks),
        checks=checks,
        video_base_e2e_hash=hashlib.sha256(_json_bytes(stable)).hexdigest().upper(),
        generated_at_utc=datetime.now(timezone.utc),
    )
    if plan.status != VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS:
        raise PublicationPackageBlockedError("R7 VIDEO_BASE revalidation failed")
    return ref, manifest, plan


def _physical_sources(store: ArtifactStore, project_id: str, result: FinalRenderResult):
    master_ref, master_path = _verified_ref(store, project_id, result.master.artifact_id, result.master.sha256, "final master")
    social_ref, social_path = _verified_ref(store, project_id, result.social.artifact_id, result.social.sha256, "final social")
    subtitle_ref, subtitle_path = _verified_ref(store, project_id, result.subtitle_artifact_id, result.subtitle_sha256, "subtitles")
    canonical = result.model_copy(update={
        "master": result.master.model_copy(update={"file_path": str(master_path)}),
        "social": result.social.model_copy(update={"file_path": str(social_path)}),
    })
    return canonical, master_ref, master_path, social_ref, social_path, subtitle_ref, subtitle_path


def _support_bytes(result: FinalRenderResult, finalization: FinalizationE2EPlan, review_ref: ArtifactRef, review: HumanFinalReviewRecord):
    provenance = _json_bytes({
        "version": VERSION,
        "project_id": result.project_id,
        "final_render_manifest_artifact_id": result.manifest_artifact_id,
        "human_review_artifact_id": review_ref.artifact_id,
        "rights_provenance": result.rights_provenance,
    }, pretty=True)
    checklist = _json_bytes({
        "version": VERSION,
        "project_id": result.project_id,
        "human_review_artifact_id": review_ref.artifact_id,
        "review": review.model_dump(mode="json"),
        "review_7_of_7": review.all_required_gates_passed,
        "finalization_e2e_hash": finalization.finalization_e2e_hash,
        "finalization_status": finalization.status.value,
        "checks": [c.model_dump(mode="json") for c in finalization.checks],
        "auto_publication": False,
    }, pretty=True)
    return provenance, checklist


def _sources(plan, metadata, result, master_ref, master_path, social_ref, social_path, thumbnail_ref, thumbnail_path, subtitle_ref, subtitle_path, provenance, checklist):
    meta = _json_bytes(metadata.model_dump(mode="json"))
    caption = metadata.caption.encode()
    values = {
        "master": PackageSource("master", result.master.sha256, master_ref.artifact_id, master_path),
        "social": PackageSource("social", result.social.sha256, social_ref.artifact_id, social_path),
        "thumbnail": PackageSource("thumbnail", thumbnail_ref.sha256, thumbnail_ref.artifact_id, thumbnail_path),
        "subtitles_es": PackageSource("subtitles_es", subtitle_ref.sha256, subtitle_ref.artifact_id, subtitle_path),
        "provenance": PackageSource("provenance", _sha(provenance), data=provenance),
        "publication_checklist": PackageSource("publication_checklist", _sha(checklist), data=checklist),
        "caption": PackageSource("caption", _sha(caption), data=caption),
        "metadata": PackageSource("metadata", _sha(meta), data=meta),
    }
    hashes = {a.asset_id: (a.sha256 or "").lower() for a in plan.assets}
    if any(hashes.get(name) != source.sha256.lower() for name, source in values.items()):
        raise PublicationPackageBlockedError("planner/source SHA mismatch")
    return values



def _package_support_bytes(*args, **kwargs):
    return _support_bytes(*args, **kwargs)


def _make_sources(*args, **kwargs):
    return _sources(*args, **kwargs)


class PublicationPackageMaterializer:
    def __init__(self, store: ArtifactStore) -> None:
        self.store = store

    def _parent(self, project_id: str) -> Path:
        self.store.load_project(project_id)
        root = self.store.root.resolve()
        parent = self.store.root / "publication-packages" / project_id
        cursor = self.store.root
        for part in (Path("publication-packages") / project_id).parts:
            cursor /= part
            if cursor.exists() and cursor.is_symlink():
                raise PublicationPackageBlockedError("package path symlink blocked")
        resolved = parent.resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise PublicationPackageBlockedError("package root escape blocked") from exc
        parent.mkdir(parents=True, exist_ok=True)
        return resolved

    def _verify_source(self, project_id: str, source: PackageSource) -> None:
        expected = _hex_sha(source.sha256, source.logical_name)
        if source.path is None:
            assert source.data is not None
            if _sha(source.data) != expected:
                raise PublicationPackageBlockedError("generated source SHA mismatch")
            return
        if source.artifact_id is None:
            raise PublicationPackageBlockedError("physical source lacks artifact identity")
        ref, canonical = _verified_ref(store=self.store, project_id=project_id, artifact_id=source.artifact_id, expected_sha=expected, label=source.logical_name)
        if ref.project_id != project_id or source.path.resolve() != canonical.resolve():
            raise PublicationPackageBlockedError("source traversal/absolute path blocked")

    @staticmethod
    def _write_source(source: PackageSource, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.parent / f".{destination.name}.{uuid4().hex}.tmp"
        try:
            with temp.open("xb") as dst:
                if source.path is not None:
                    with source.path.open("rb") as src:
                        shutil.copyfileobj(src, dst, length=1024 * 1024)
                else:
                    assert source.data is not None
                    dst.write(source.data)
                dst.flush()
                os.fsync(dst.fileno())
            os.replace(temp, destination)
        finally:
            temp.unlink(missing_ok=True)

    @staticmethod
    def _verify_package(package: Path, plan_hash: str, sources: dict[str, PackageSource], review_id: str, render_id: str) -> None:
        manifest_path = package / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise PublicationPackageBlockedError("invalid package manifest") from exc
        safe = (
            manifest.get("publication_package_hash") == plan_hash
            and manifest.get("asset_count") == 8
            and manifest.get("human_review_artifact_id") == review_id
            and manifest.get("final_render_artifact_id") == render_id
            and manifest.get("source_artifacts_preserved") is True
            and manifest.get("post_review_content_mutation") is False
            and manifest.get("manual_publication_only") is True
            and manifest.get("auto_publication") is False
            and manifest.get("authorization_to_publish") is False
            and manifest.get("marks_published") is False
            and manifest.get("uploads_files") is False
            and manifest.get("webhook_calls") == 0
            and manifest.get("package_network_calls") == 0
        )
        if not safe:
            raise PublicationPackageBlockedError("package identity/safety mismatch")
        rows = manifest.get("assets")
        if not isinstance(rows, list) or len(rows) != 8:
            raise PublicationPackageBlockedError("package asset count mismatch")
        seen = set()
        for row in rows:
            name, rel = row.get("logical_name"), str(row.get("relative_path") or "")
            if name in seen or TARGETS.get(name) != rel:
                raise PublicationPackageBlockedError("package asset mapping mismatch")
            seen.add(name)
            source = sources.get(name)
            if source is None or row.get("source_artifact_id") != source.artifact_id or row.get("source_sha256") != source.sha256.lower():
                raise PublicationPackageBlockedError("package source identity mismatch")
            path = (package / rel).resolve()
            try:
                path.relative_to(package.resolve())
            except ValueError as exc:
                raise PublicationPackageBlockedError("package traversal blocked") from exc
            if path.is_symlink() or not path.is_file():
                raise PublicationPackageBlockedError("package asset missing/symlinked")
            sha, size = _file_sha(path)
            if sha != row.get("sha256") or size != row.get("size_bytes"):
                raise PublicationPackageBlockedError("package asset integrity mismatch")
        if seen != set(TARGETS):
            raise PublicationPackageBlockedError("package asset set mismatch")

    def materialize(self, project_id: str, plan: PublicationPackagePlan, finalization: FinalizationE2EPlan, review: HumanFinalReviewRecord, sources: dict[str, PackageSource], *, human_review_artifact_id: str, final_render_artifact_id: str) -> MaterializationResult:
        if not isinstance(plan, PublicationPackagePlan) or not isinstance(finalization, FinalizationE2EPlan) or not isinstance(review, HumanFinalReviewRecord):
            raise PublicationPackageBlockedError("certified evidence missing")
        if plan.status != PublicationPackageStatus.READY_FOR_MANUAL_PACKAGE or finalization.status != FinalizationE2EStatus.FINALIZATION_E2E_PASS or plan.source_finalization_e2e_hash != finalization.finalization_e2e_hash:
            raise PublicationPackageBlockedError("Finalization/plan not READY")
        if review.decision != HumanFinalReviewDecision.APPROVE or not review.all_required_gates_passed or not review.rights_passed:
            raise PublicationPackageBlockedError("Review 7/7 required")
        if not (plan.planning_only and plan.manual_publication_only and not plan.writes_files and not plan.uploads_files and plan.network_calls == 0 and plan.webhook_calls == 0 and not plan.auto_publication and not plan.authorization_to_publish and not plan.marks_published and plan.rights_ready and plan.finalization_evidence_valid):
            raise PublicationPackageBlockedError("planner safety contract failed")
        by_id = {a.asset_id: a for a in plan.assets}
        if set(by_id) != set(TARGETS) or set(sources) != set(TARGETS):
            raise PublicationPackageBlockedError("eight-source contract failed")
        for name, rel in TARGETS.items():
            asset, source = by_id[name], sources[name]
            if asset.target_filename != Path(rel).name or not asset.present or asset.sha256 is None or asset.sha256.lower() != source.sha256.lower():
                raise PublicationPackageBlockedError(f"asset contract failed: {name}")
            self._verify_source(project_id, source)

        parent = self._parent(project_id)
        stable = plan.publication_package_hash.lower()[:24]
        package = parent / f"publication-package-{stable}"
        if package.exists():
            self._verify_package(package, plan.publication_package_hash, sources, human_review_artifact_id, final_render_artifact_id)
            return MaterializationResult(package, package / "manifest.json", True)

        staging = parent / f".publication-package-{stable}.{uuid4().hex}.staging"
        staging.mkdir(exist_ok=False)
        try:
            rows = []
            for asset in plan.assets:
                source, rel = sources[asset.asset_id], Path(TARGETS[asset.asset_id])
                self._write_source(source, staging / rel)
                sha, size = _file_sha(staging / rel)
                if sha != source.sha256.lower():
                    raise PublicationPackageBlockedError("post-copy SHA mismatch")
                rows.append({"logical_name": asset.asset_id, "relative_path": rel.as_posix(), "size_bytes": size, "sha256": sha, "source_artifact_id": source.artifact_id, "source_sha256": source.sha256.lower()})
            manifest = {
                "version": VERSION,
                "project_id": project_id,
                "package_id": f"publication-package-{stable}",
                "publication_package_hash": plan.publication_package_hash,
                "source_finalization_e2e_hash": finalization.finalization_e2e_hash,
                "human_review_artifact_id": human_review_artifact_id,
                "final_render_artifact_id": final_render_artifact_id,
                "asset_count": 8,
                "assets": rows,
                "source_artifacts_preserved": True,
                "post_review_content_mutation": False,
                "manual_publication_only": True,
                "auto_publication": False,
                "authorization_to_publish": False,
                "marks_published": False,
                "uploads_files": False,
                "webhook_calls": 0,
                "package_network_calls": 0,
            }
            (staging / "manifest.json").write_bytes(_json_bytes(manifest, pretty=True))
            self._verify_package(staging, plan.publication_package_hash, sources, human_review_artifact_id, final_render_artifact_id)
            if package.exists():
                raise PublicationPackageBlockedError("package collision")
            os.replace(staging, package)
            self._verify_package(package, plan.publication_package_hash, sources, human_review_artifact_id, final_render_artifact_id)
            return MaterializationResult(package, package / "manifest.json", False)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise


class PublicationPackageStageAdapter:
    def __call__(self, context: StageExecutionContext, payload: dict[str, Any]) -> StageResult:
        if payload:
            return StageResult.blocked("PUBLICATION_PACKAGE request must be empty")
        try:
            review_ref, review = _review(context)
            input_ref = _latest_for_review(context.store, context.project_id, PACKAGE_INPUT, review_ref.artifact_id)
            package_input = _read_model(context.store, context.project_id, input_ref, PublicationPackageInputRecord, "publication input")
            if package_input.project_id != context.project_id or package_input.review_artifact_id != review_ref.artifact_id or review_ref.artifact_id not in input_ref.input_artifact_ids:
                raise PublicationPackageBlockedError("publication input lineage mismatch")
            thumbnail_ref, thumbnail_path = _verified_ref(context.store, context.project_id, package_input.thumbnail_artifact_id, package_input.thumbnail_sha256, "thumbnail")
            if review_ref.artifact_id not in thumbnail_ref.input_artifact_ids or thumbnail_ref.artifact_id not in input_ref.input_artifact_ids:
                raise PublicationPackageBlockedError("thumbnail/Review lineage mismatch")

            final_ref = _latest_for_review(context.store, context.project_id, FINAL_RENDER, review_ref.artifact_id)
            result = _read_model(context.store, context.project_id, final_ref, FinalRenderResult, "FinalRenderResult")
            if result.project_id != context.project_id or result.manifest_artifact_id != final_ref.artifact_id or result.human_review_artifact_id != review_ref.artifact_id:
                raise PublicationPackageBlockedError("FinalRender project/Review mismatch")
            required = {review_ref.artifact_id, result.video_base_manifest_artifact_id, result.media_resolution_artifact_id, result.subtitle_artifact_id, result.master.artifact_id, result.social.artifact_id}
            if not required.issubset(set(final_ref.input_artifact_ids)):
                raise PublicationPackageBlockedError("FinalRender lineage incomplete")

            video_ref, video_manifest, video_e2e = _video_e2e(context.store, context.project_id, result)
            media_ref, _ = validate_rights_provenance(context.store, context.project_id, result, video_manifest, review)
            canonical, master_ref, master_path, social_ref, social_path, subtitle_ref, subtitle_path = _physical_sources(context.store, context.project_id, result)
            finalization = build_finalization_e2e(build_finalization_request(video_e2e, canonical))
            if finalization.status != FinalizationE2EStatus.FINALIZATION_E2E_PASS:
                raise PublicationPackageBlockedError("FinalizationE2E did not PASS")
            provenance, checklist = _support_bytes(canonical, finalization, review_ref, review)
            support = PublicationSupportManifest(
                thumbnail=PublicationSupportAssetProbe(source_path=str(thumbnail_path), present=True, sha256=thumbnail_ref.sha256),
                subtitles_es=PublicationSupportAssetProbe(source_path=str(subtitle_path), present=True, sha256=subtitle_ref.sha256),
                provenance=PublicationSupportAssetProbe(present=True, sha256=_sha(provenance)),
                review_checklist=PublicationSupportAssetProbe(present=True, sha256=_sha(checklist)),
            )
            plan = build_publication_package(PublicationPackageRequest(finalization=finalization, metadata=package_input.metadata, support=support))
            if plan.status != PublicationPackageStatus.READY_FOR_MANUAL_PACKAGE:
                raise PublicationPackageBlockedError("PublicationPackagePlan not READY")
            sources = _sources(plan, package_input.metadata, canonical, master_ref, master_path, social_ref, social_path, thumbnail_ref, thumbnail_path, subtitle_ref, subtitle_path, provenance, checklist)
            materialized = PublicationPackageMaterializer(context.store).materialize(
                context.project_id, plan, finalization, review, sources,
                human_review_artifact_id=review_ref.artifact_id,
                final_render_artifact_id=final_ref.artifact_id,
            )
        except Exception as exc:
            return StageResult.blocked("G-006 publication package blocked", details={"error_type": type(exc).__name__, "error": str(exc)[:1800]})

        inputs = tuple(dict.fromkeys((review_ref.artifact_id, input_ref.artifact_id, thumbnail_ref.artifact_id, final_ref.artifact_id, video_ref.artifact_id, media_ref.artifact_id, master_ref.artifact_id, social_ref.artifact_id, subtitle_ref.artifact_id)))
        return StageResult.complete(
            StageArtifact(artifact_type=FINALIZATION, payload=finalization.model_dump(mode="json"), input_artifact_ids=inputs, provenance={"human_review_artifact_id": review_ref.artifact_id, "final_render_artifact_id": final_ref.artifact_id}),
            StageArtifact(artifact_type=PLAN, payload=plan.model_dump(mode="json"), input_artifact_ids=inputs, provenance={"human_review_artifact_id": review_ref.artifact_id, "source_finalization_e2e_hash": finalization.finalization_e2e_hash}),
            StageArtifact(
                artifact_type=PACKAGE_MANIFEST,
                source_path=str(materialized.manifest_path),
                suffix=".json",
                input_artifact_ids=inputs,
                provenance={"package_dir": str(materialized.package_dir), "human_review_artifact_id": review_ref.artifact_id, "final_render_artifact_id": final_ref.artifact_id, "source_artifacts_preserved": True, "post_review_content_mutation": False},
                metadata={"asset_count": 8, "manual_publication_only": True, "auto_publication": False, "authorization_to_publish": False, "marks_published": False, "uploads_files": False, "webhook_calls": 0, "package_network_calls": 0, "reused": materialized.reused},
            ),
            message="G-006 manual publication package materialized",
            details={"package_dir": str(materialized.package_dir), "asset_count": 8, "manual_publication_only": True, "auto_publication": False},
        )


def build_publication_package_stage_binding() -> StageBinding:
    return StageBinding(
        adapter_id="g006_publication_package",
        handler=PublicationPackageStageAdapter(),
        resource_class=ResourceClass.LIGHT,
        producer_version=VERSION,
        invokes_network=False,
        invokes_llm=False,
        invokes_render=False,
        auto_publication=False,
    )


def persist_publication_package_input(
    store: ArtifactStore,
    *,
    project_id: str,
    review_ref: ArtifactRef,
    thumbnail_bytes: bytes,
    thumbnail_filename: str,
    metadata: PublicationMetadata,
) -> tuple[ArtifactRef, ArtifactRef]:
    if not thumbnail_bytes or Path(thumbnail_filename).suffix.lower() not in {".jpg", ".jpeg"} or review_ref.project_id != project_id:
        raise ValueError("valid project-scoped JPEG thumbnail is required")
    thumb_sha = _sha(thumbnail_bytes)
    stable = _json_bytes({"version": VERSION, "project_id": project_id, "review": (review_ref.artifact_id, review_ref.sha256), "thumbnail_sha256": thumb_sha, "metadata": metadata.model_dump(mode="json")})
    token = hashlib.sha256(stable).hexdigest()[:24]
    thumb_id, input_id = f"g006-thumbnail-{token}", f"g006-publication-input-{token}"
    try:
        thumb = store.get_artifact(project_id, thumb_id)
    except ArtifactNotFoundError:
        thumb = store.put_bytes(project_id, THUMBNAIL, thumbnail_bytes, producer="centinela.g006.publication_input", suffix=".jpg", artifact_id=thumb_id, producer_version=VERSION, input_artifact_ids=(review_ref.artifact_id,), provenance={"human_review_artifact_id": review_ref.artifact_id}, metadata={"human_review_artifact_id": review_ref.artifact_id})
    else:
        if thumb.artifact_type != THUMBNAIL or thumb.sha256 != thumb_sha or review_ref.artifact_id not in thumb.input_artifact_ids:
            raise PublicationPackageBlockedError("thumbnail identity collision")
    record = PublicationPackageInputRecord(project_id=project_id, review_artifact_id=review_ref.artifact_id, thumbnail_artifact_id=thumb.artifact_id, thumbnail_sha256=thumb.sha256, metadata=metadata, created_at_utc=datetime.now(timezone.utc))
    try:
        input_ref = store.get_artifact(project_id, input_id)
    except ArtifactNotFoundError:
        input_ref = store.put_json(project_id, PACKAGE_INPUT, record.model_dump(mode="json"), producer="centinela.g006.publication_input", artifact_id=input_id, producer_version=VERSION, input_artifact_ids=(review_ref.artifact_id, thumb.artifact_id), provenance={"human_review_artifact_id": review_ref.artifact_id}, metadata={"human_review_artifact_id": review_ref.artifact_id})
    else:
        persisted = _read_model(store, project_id, input_ref, PublicationPackageInputRecord, "publication input")
        if input_ref.artifact_type != PACKAGE_INPUT or persisted.project_id != project_id or persisted.review_artifact_id != review_ref.artifact_id or persisted.thumbnail_artifact_id != thumb.artifact_id or persisted.metadata != metadata:
            raise PublicationPackageBlockedError("publication input identity collision")
    return input_ref, thumb
