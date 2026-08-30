from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe(ffprobe: str, path: Path) -> dict:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "ffprobe failed")
    return json.loads(result.stdout)


def _summary(probe: dict) -> dict:
    videos = [stream for stream in probe.get("streams", []) if stream.get("codec_type") == "video"]
    audios = [stream for stream in probe.get("streams", []) if stream.get("codec_type") == "audio"]
    assert len(videos) == 1
    video = videos[0]
    rate = str(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1")
    numerator, denominator = rate.split("/", 1)
    return {
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": float(numerator) / float(denominator),
        "codec": str(video.get("codec_name") or ""),
        "pixel_format": str(video.get("pix_fmt") or ""),
        "duration_seconds": float(video.get("duration") or probe.get("format", {}).get("duration") or 0.0),
        "audio_stream_count": len(audios),
    }


def generate(output_dir: Path) -> dict:
    from app.models.astromedia import HashMode, IndexRequest
    from app.models.material_selection import MaterialSelectionPlan, SelectionStatus
    from app.models.video_base import VideoBasePlanRequest, VideoBaseRenderMode
    from app.services.astromedia import AstroMediaCatalog
    from app.services.video_base_planner import VideoBasePlanBlockedError, VideoBasePlanner
    from app.services.video_base_renderer import FFmpegSceneRenderer
    from app.utils import utils
    from test.services.test_deep_sky_media_cloud_replay import (
        _FIXTURES,
        _fixture_image,
        _plan,
        _resolve,
        _write_sidecar,
    )

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe are required")

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="centinela-insufficient-media-") as temporary:
        root = Path(temporary)
        media_root = root / "media"
        media_root.mkdir()

        initial_fixtures = _FIXTURES[:-1]
        recovery_fixture = _FIXTURES[-1]
        for filename, marker, title, tags, objects in initial_fixtures:
            path = media_root / filename
            _fixture_image(path, marker)
            _write_sidecar(path, title=title, tags=tags, objects=objects)

        catalog = AstroMediaCatalog(
            db_path=root / "catalog.sqlite3",
            json_path=root / "catalog.json",
            allowed_roots=[media_root],
            tasks_root=root / "tasks",
        )

        initial_index = catalog.index_library(
            IndexRequest(
                root=str(media_root),
                recursive=True,
                hash_mode=HashMode.NONE,
                import_task_artifacts=False,
            )
        )
        assert initial_index.indexed_items == 4
        assert initial_index.non_renderable_items == 0
        assert initial_index.errors == []

        initial = _resolve(catalog, media_root)
        assert initial.report.scene_count == 5
        assert initial.report.selected_count == 4
        assert initial.report.unresolved_count == 1
        assert initial.report.publication_ready is False
        assert initial.report.guardrails.material_selector_is_final_authority is True
        assert initial.report.guardrails.irrelevant_broll_fallback is False
        assert initial.report.guardrails.ai_generation_triggered is False
        assert initial.report.guardrails.auto_publication is False
        assert initial.report.guardrails.network_discovery_default is False

        scene5 = initial.selection["selections"][4]
        assert scene5["status"] == SelectionStatus.NO_ADEQUATE_MEDIA.value
        assert scene5["selected_media_id"] is None
        assert scene5["selected_local_path"] is None

        planner = VideoBasePlanner(catalog=catalog)
        initial_materials = MaterialSelectionPlan.model_validate(initial.selection)
        blockers: list[str] = []
        try:
            planner.build(
                VideoBasePlanRequest(
                    plan=_plan(),
                    materials=initial_materials,
                    render_mode=VideoBaseRenderMode.CLEAN_BASE,
                    requested_codec="libx264",
                )
            )
        except VideoBasePlanBlockedError as exc:
            blockers = list(exc.blockers)
        else:
            raise AssertionError("CLEAN_BASE must fail closed when required media is missing")
        assert blockers == ["scene 5: NO_ADEQUATE_MEDIA"]

        (initial_filename, initial_marker, initial_title, initial_tags, initial_objects) = recovery_fixture
        recovery_path = media_root / initial_filename
        _fixture_image(recovery_path, initial_marker)
        _write_sidecar(
            recovery_path,
            title=initial_title,
            tags=initial_tags,
            objects=initial_objects,
        )
        recovery_index = catalog.index_library(
            IndexRequest(
                root=str(media_root),
                recursive=True,
                hash_mode=HashMode.NONE,
                import_task_artifacts=False,
            )
        )
        assert recovery_index.indexed_items == 5
        assert recovery_index.non_renderable_items == 0
        assert recovery_index.errors == []

        recovered = _resolve(catalog, media_root)
        assert recovered.report.selected_count == 5
        assert recovered.report.unresolved_count == 0
        assert recovered.report.publication_ready is True
        recovered_scene5 = recovered.selection["selections"][4]
        specificity_pass = any(
            reason.startswith("specificity_overlap:") and "ring_nebula" in reason
            for reason in recovered_scene5["reasons"]
        )
        assert specificity_pass is True

        recovered_materials = MaterialSelectionPlan.model_validate(recovered.selection)
        recovered_plan = planner.build(
            VideoBasePlanRequest(
                plan=_plan(),
                materials=recovered_materials,
                render_mode=VideoBaseRenderMode.CLEAN_BASE,
                requested_codec="libx264",
            )
        )
        assert recovered_plan.clean_base_eligible is True
        assert recovered_plan.unresolved_count == 0
        assert recovered_plan.placeholder_count == 0

        render_root = root / "render-tasks"
        original_task_dir = utils.task_dir
        utils.task_dir = lambda sub_dir="": str(render_root / sub_dir)
        try:
            result = FFmpegSceneRenderer(ffmpeg, ffprobe).render(
                recovered_plan,
                task_id="insufficient-media-recovery-render",
                keep_segments=False,
            )
        finally:
            utils.task_dir = original_task_dir

        video = Path(result.video_path)
        manifest_path = Path(result.manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        probe = _probe(ffprobe, video)
        summary = _summary(probe)
        digest = _sha256(video)

        assert result.scene_count == 5
        assert result.placeholder_count == 0
        assert result.requested_codec == "libx264"
        assert result.effective_codec == "libx264"
        assert result.codec_fallback is False
        assert manifest["render_mode"] == "CLEAN_BASE"
        assert manifest["final_video_sha256"] == digest
        assert summary["width"] == 1080
        assert summary["height"] == 1920
        assert abs(summary["fps"] - 30.0) <= 0.01
        assert summary["codec"] == "h264"
        assert summary["pixel_format"] == "yuv420p"
        assert summary["audio_stream_count"] == 0
        assert abs(summary["duration_seconds"] - 40.0) <= 0.30

        shutil.copy2(video, output_dir / "insufficient-media-recovery-preview.mp4")
        shutil.copy2(manifest_path, output_dir / "render-manifest.json")
        (output_dir / "ffprobe.json").write_text(
            json.dumps(probe, indent=2, sort_keys=True), encoding="utf-8"
        )
        (output_dir / "initial-media-selection.json").write_text(
            json.dumps(initial.selection, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (output_dir / "recovered-media-selection.json").write_text(
            json.dumps(recovered.selection, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (output_dir / "initial-media-resolution-report.json").write_text(
            json.dumps(initial.report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (output_dir / "recovered-media-resolution-report.json").write_text(
            json.dumps(recovered.report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        evidence = {
            "scenario": "INSUFFICIENT_MEDIA",
            "scope": "CLOUD_HERMETIC_FAIL_CLOSED_AND_RECOVERY_EVIDENCE",
            "initial_media_selected": 4,
            "initial_media_unresolved": 1,
            "initial_publication_ready": False,
            "initial_scene5_status": SelectionStatus.NO_ADEQUATE_MEDIA.value,
            "initial_scene5_selected_media_id": None,
            "clean_base_blocked": True,
            "clean_base_blockers": blockers,
            "recovery_media_selected": 5,
            "recovery_media_unresolved": 0,
            "recovery_publication_ready": True,
            "recovery_specificity_pass": specificity_pass,
            "recovery_clean_base": True,
            "render_pass": True,
            "visual_relevance_contract_pass": True,
            "provenance_contract_pass": all(
                row["selected_publication_eligible"] is True
                for row in recovered.selection["selections"]
            ),
            "scientific_scope": "STATIC_DEEP_SKY_OBJECT_LABELS_NO_COORDINATES_OR_EPHEMERIS",
            "unsupported_scientific_claims": 0,
            "requested_codec": "libx264",
            "effective_codec": "libx264",
            "nvenc_certified": False,
            "nvenc_reason": "LOCAL_RTX_2060_CERTIFICATION_REQUIRED",
            **summary,
            "video_sha256": digest,
            "material_selector_final_authority": True,
            "no_irrelevant_broll": True,
            "ai_generation": False,
            "auto_publication": False,
            "network_discovery": False,
            "human_review_required": True,
            "local_final_certification_required": True,
        }
        assert evidence["provenance_contract_pass"] is True
        (output_dir / "scenario-evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("cloud-insufficient-media-render"),
    )
    args = parser.parse_args()
    print(json.dumps(generate(args.output), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
