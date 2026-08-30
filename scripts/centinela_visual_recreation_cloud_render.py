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


def _ffprobe(ffprobe_binary: str, path: Path) -> dict:
    result = subprocess.run(
        [
            ffprobe_binary,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "ffprobe failed")
    return json.loads(result.stdout)


def _video_summary(probe: dict) -> dict:
    videos = [stream for stream in probe.get("streams", []) if stream.get("codec_type") == "video"]
    audios = [stream for stream in probe.get("streams", []) if stream.get("codec_type") == "audio"]
    if len(videos) != 1:
        raise AssertionError(f"expected one video stream, got {len(videos)}")
    video = videos[0]
    rate = str(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1")
    numerator, denominator = rate.split("/", 1)
    fps = float(numerator) / float(denominator)
    duration = float(video.get("duration") or probe.get("format", {}).get("duration") or 0.0)
    return {
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": fps,
        "codec": str(video.get("codec_name") or ""),
        "pixel_format": str(video.get("pix_fmt") or ""),
        "duration_seconds": duration,
        "audio_stream_count": len(audios),
    }


def _build_media(media_root: Path) -> None:
    from test.services.test_visual_recreation_cloud_replay import (
        _FIXTURES,
        _add_fixtures,
    )

    media_root.mkdir(parents=True, exist_ok=True)
    _add_fixtures(media_root, _FIXTURES)


def generate(output_dir: Path) -> dict:
    from app.models.astronomy import ScientificStatus
    from app.models.astromedia import HashMode, IndexRequest, Origin, Provider, Rights
    from app.models.material_selection import MaterialSelectionPlan, SelectionStatus
    from app.models.video_base import VideoBasePlanRequest, VideoBaseRenderMode
    from app.services.astromedia import AstroMediaCatalog
    from app.services.video_base_planner import VideoBasePlanner
    from app.services.video_base_renderer import FFmpegSceneRenderer
    from app.utils import utils
    from test.services.test_visual_recreation_cloud_replay import _plan, _resolve

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe are required")

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="centinela-visual-recreation-") as temporary:
        root = Path(temporary)
        media_root = root / "media"
        _build_media(media_root)

        catalog = AstroMediaCatalog(
            db_path=root / "catalog.sqlite3",
            json_path=root / "catalog.json",
            allowed_roots=[media_root],
            tasks_root=root / "tasks",
        )
        index = catalog.index_library(
            IndexRequest(
                root=str(media_root),
                recursive=True,
                hash_mode=HashMode.NONE,
                import_task_artifacts=False,
            )
        )
        if index.indexed_items != 5 or index.non_renderable_items != 0 or index.errors:
            raise AssertionError(index.model_dump(mode="json"))

        items = catalog.list_items(True)
        provenance_contract_pass = bool(items) and all(
            item.provider == Provider.AI_GENERATED
            and item.visual_origin == Origin.AI_GENERATED
            and item.scientific_status == ScientificStatus.RECREACION_VISUAL
            and item.rights_status == Rights.CONFIRMED_OWNED
            and item.publication_eligible is True
            and "NOT REAL OBSERVATION" in item.description
            for item in items
        )
        if not provenance_contract_pass:
            raise AssertionError("AI recreation provenance contract failed")

        story_plan = _plan()
        outcome = _resolve(catalog, media_root)
        if outcome.report.selected_count != 5 or outcome.report.unresolved_count != 0:
            raise AssertionError(outcome.report.model_dump(mode="json"))
        if outcome.report.publication_ready:
            raise AssertionError("AI recreation replay must remain non-publication-ready before review")

        selections = outcome.selection["selections"]
        if not all(
            row["status"] == SelectionStatus.SELECTED_AI_RECREATION.value
            and row["selected_provider"] == Provider.AI_GENERATED.value
            and row["selected_scientific_status"] == ScientificStatus.RECREACION_VISUAL.value
            and row["selected_rights_status"] == Rights.CONFIRMED_OWNED.value
            and row["selected_publication_eligible"] is True
            for row in selections
        ):
            raise AssertionError("selection lost explicit AI recreation labeling")

        materials = MaterialSelectionPlan.model_validate(outcome.selection)
        video_plan = VideoBasePlanner(catalog=catalog).build(
            VideoBasePlanRequest(
                plan=story_plan,
                materials=materials,
                render_mode=VideoBaseRenderMode.CLEAN_BASE,
                requested_codec="libx264",
            )
        )
        if not video_plan.clean_base_eligible:
            raise AssertionError("CLEAN_BASE unexpectedly ineligible after explicit recreation selection")
        if video_plan.placeholder_count != 0 or video_plan.unresolved_count != 0:
            raise AssertionError("CLEAN_BASE contains unresolved/placeholder scenes")

        render_root = root / "render-tasks"
        original_task_dir = utils.task_dir
        utils.task_dir = lambda sub_dir="": str(render_root / sub_dir)
        try:
            result = FFmpegSceneRenderer(ffmpeg, ffprobe).render(
                video_plan,
                task_id="visual-recreation-cloud-render",
                keep_segments=False,
            )
        finally:
            utils.task_dir = original_task_dir

        video_path = Path(result.video_path)
        manifest_path = Path(result.manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        probe = _ffprobe(ffprobe, video_path)
        summary = _video_summary(probe)
        video_sha256 = _sha256(video_path)

        assert result.scene_count == 5
        assert result.placeholder_count == 0
        assert result.requested_codec == "libx264"
        assert result.effective_codec == "libx264"
        assert result.codec_fallback is False
        assert manifest["render_mode"] == "CLEAN_BASE"
        assert manifest["scene_count"] == 5
        assert manifest["placeholder_count"] == 0
        assert manifest["final_video_sha256"] == video_sha256
        assert len({scene["selected_media_id"] for scene in manifest["scenes"]}) == 5
        assert all(scene["placeholder"] is False for scene in manifest["scenes"])
        assert summary["width"] == 1080
        assert summary["height"] == 1920
        assert abs(summary["fps"] - 30.0) <= 0.01
        assert summary["codec"] == "h264"
        assert summary["pixel_format"] == "yuv420p"
        assert summary["audio_stream_count"] == 0
        assert abs(summary["duration_seconds"] - 40.0) <= 0.30

        shutil.copy2(video_path, output_dir / "visual-recreation-preview.mp4")
        shutil.copy2(manifest_path, output_dir / "render-manifest.json")
        (output_dir / "ffprobe.json").write_text(
            json.dumps(probe, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        (output_dir / "media-selection.json").write_text(
            json.dumps(outcome.selection, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        (output_dir / "media-resolution-report.json").write_text(
            json.dumps(
                outcome.report.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        required_specificity = {
            "1": "crater",
            "2": "equatorial_bands",
            "3": "totality_corona",
            "4": "orion_belt",
            "5": "ring_nebula",
        }
        specificity_pass = all(
            any(
                reason.startswith("specificity_overlap:") and token in reason
                for reason in selections[int(scene) - 1]["reasons"]
            )
            for scene, token in required_specificity.items()
        )

        evidence = {
            "scenario": "VISUAL_RECREATION",
            "scope": "CLOUD_HERMETIC_RENDER_EVIDENCE",
            "media_selected": 5,
            "media_unresolved": 0,
            "ai_recreation_count": outcome.selection["ai_recreation_count"],
            "distinct_media": 5,
            "clean_base": True,
            "publication_ready": False,
            "review_required": True,
            "placeholder_count": 0,
            "render_pass": True,
            "visual_relevance_contract_pass": specificity_pass,
            "provenance_contract_pass": provenance_contract_pass,
            "recreation_label_pass": all(
                row["selected_scientific_status"] == ScientificStatus.RECREACION_VISUAL.value
                for row in selections
            ),
            "all_selected_ai_generated": all(
                row["selected_provider"] == Provider.AI_GENERATED.value for row in selections
            ),
            "scientific_scope": "SYNTHETIC_VISUAL_RECREATION_LABELING_CONTRACT_NO_REAL_OBSERVATION",
            "unsupported_scientific_claims": 0,
            "represents_real_observation": False,
            "represents_real_event": False,
            "production_astronomy_media": False,
            "recreation_label_required": True,
            "required_specificity": required_specificity,
            "requested_codec": "libx264",
            "effective_codec": "libx264",
            "nvenc_certified": False,
            "nvenc_reason": "LOCAL_RTX_2060_CERTIFICATION_REQUIRED",
            "width": summary["width"],
            "height": summary["height"],
            "fps": summary["fps"],
            "codec": summary["codec"],
            "pixel_format": summary["pixel_format"],
            "audio_stream_count": summary["audio_stream_count"],
            "duration_seconds": summary["duration_seconds"],
            "video_sha256": video_sha256,
            "material_selector_final_authority": True,
            "no_irrelevant_broll": True,
            "ai_generation": True,
            "auto_publication": False,
            "network_discovery": False,
            "human_review_required": True,
            "local_final_certification_required": True,
        }
        assert evidence["visual_relevance_contract_pass"] is True
        assert evidence["provenance_contract_pass"] is True
        assert evidence["recreation_label_pass"] is True
        assert evidence["all_selected_ai_generated"] is True
        (output_dir / "scenario-evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("cloud-visual-recreation-render"))
    args = parser.parse_args()
    evidence = generate(args.output)
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
