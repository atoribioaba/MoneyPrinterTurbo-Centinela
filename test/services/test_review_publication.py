from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models.astromedia import Provider, Rights
from app.models.material_selection import SelectionStatus
from app.services.centinela.review_publication import (
    REQUIRED_PUBLICATION_FILES,
    REQUIRED_REVIEW_CHECKS,
    HumanReviewChecklist,
    PublicationFile,
    PublicationPackageManifest,
    ReviewPacket,
    build_publication_package_stage_binding,
    build_review_prep_stage_binding,
)
from app.services.centinela.review_publication.service import (
    _build_copy_draft,
    _rights_records,
)


NOW = datetime.now(timezone.utc)


def _packet(**overrides):
    payload = {
        "project_id": "project-r8-test",
        "subject": "La Luna y Júpiter",
        "final_script_artifact_id": "final-script",
        "final_script_sha256": "A" * 64,
        "material_selection_artifact_id": "selection",
        "material_selection_sha256": "B" * 64,
        "media_resolution_artifact_id": "media-report",
        "media_resolution_sha256": "C" * 64,
        "audio_bundle_artifact_id": "audio",
        "audio_bundle_sha256": "D" * 64,
        "video_base_manifest_artifact_id": "video",
        "video_base_manifest_sha256": "E" * 64,
        "review_preview_artifact_id": "preview",
        "review_preview_sha256": "F" * 64,
        "subtitle_artifact_id": "subtitle",
        "subtitle_sha256": "1" * 64,
        "thumbnail_candidate_artifact_id": "thumb",
        "thumbnail_candidate_sha256": "2" * 64,
        "review_copy_draft_artifact_id": "copy",
        "review_copy_draft_sha256": "3" * 64,
        "publication_copy": {
            "instagram_caption": "Texto para Instagram suficientemente claro.",
            "tiktok_caption": "Texto para TikTok suficientemente claro.",
            "youtube_title": "La Luna y Júpiter",
            "youtube_description": "Descripción de YouTube suficientemente clara.",
            "hashtags": ["#Astronomía"],
        },
        "rights_scene_count": 5,
        "publication_eligible_scene_count": 5,
        "license_gate_passed": True,
        "approval_available": True,
        "primary_source_verification_required": True,
        "required_checks": list(REQUIRED_REVIEW_CHECKS),
        "generated_at_utc": NOW,
    }
    payload.update(overrides)
    return ReviewPacket(**payload)


def test_review_packet_blocks_approval_when_rights_incomplete():
    with pytest.raises(ValidationError):
        _packet(license_gate_passed=False, approval_available=True)

    packet = _packet(
        license_gate_passed=False,
        approval_available=False,
        publication_eligible_scene_count=4,
    )
    assert packet.approval_available is False


def test_structured_approval_requires_all_checks():
    checks = {name: True for name in REQUIRED_REVIEW_CHECKS}
    checks["subtitle_text_verified"] = False
    with pytest.raises(ValidationError):
        HumanReviewChecklist(
            project_id="project-r8-test",
            review_packet_artifact_id="packet",
            review_packet_sha256="A" * 64,
            reviewer="Humano",
            notes="Revisión técnica completa.",
            approved=True,
            **checks,
            reviewed_at_utc=NOW,
        )

    approved = HumanReviewChecklist(
        project_id="project-r8-test",
        review_packet_artifact_id="packet",
        review_packet_sha256="A" * 64,
        reviewer="Humano",
        notes="Revisión técnica completa.",
        approved=True,
        **{name: True for name in REQUIRED_REVIEW_CHECKS},
        reviewed_at_utc=NOW,
    )
    assert approved.all_checks_passed is True
    assert approved.publication_authorized is False


def test_rights_gate_rejects_unverified_or_ai_media():
    good_scene = SimpleNamespace(
        scene_number=1,
        selected_media_id="owned-1",
        selected_rights_status=Rights.CONFIRMED_OWNED,
        selected_provider=Provider.OWN_MEDIA,
        selected_publication_eligible=True,
        status=SelectionStatus.SELECTED,
        selected_attribution=None,
        selected_source_url=None,
    )
    bad_scene = SimpleNamespace(
        scene_number=2,
        selected_media_id="bad-2",
        selected_rights_status=Rights.UNVERIFIED,
        selected_provider=Provider.LOCAL_MEDIA,
        selected_publication_eligible=False,
        status=SelectionStatus.SELECTED,
        selected_attribution=None,
        selected_source_url=None,
    )
    selection = SimpleNamespace(selections=[good_scene, bad_scene])
    report = SimpleNamespace(
        scenes=[
            SimpleNamespace(scene_number=1, candidates=[]),
            SimpleNamespace(scene_number=2, candidates=[]),
        ]
    )
    records, gate = _rights_records(selection, report)
    assert gate is False
    assert records[0]["package_rights_gate"] is True
    assert records[1]["package_rights_gate"] is False


def test_publication_package_requires_canonical_files_and_manual_publication():
    files = [
        PublicationFile(name=name, sha256="A" * 64, size_bytes=1)
        for name in REQUIRED_PUBLICATION_FILES
    ]
    manifest = PublicationPackageManifest(
        project_id="project-r8-test",
        subject="Prueba R8",
        approval_artifact_id="approval",
        review_checklist_artifact_id="checklist",
        review_packet_artifact_id="packet",
        package_zip_artifact_id="zip",
        package_zip_sha256="B" * 64,
        source_final_script_sha256="C" * 64,
        source_audio_bundle_sha256="D" * 64,
        source_video_base_manifest_sha256="E" * 64,
        source_material_selection_sha256="F" * 64,
        source_media_resolution_sha256="1" * 64,
        files=files,
        provenance_complete=True,
        license_review_complete=True,
        generated_at_utc=NOW,
    )
    assert manifest.publication_authorized is False
    assert manifest.auto_publication is False
    assert {item.name for item in manifest.files} == set(REQUIRED_PUBLICATION_FILES)


def test_r8_stage_bindings_have_no_network_llm_or_autopublish():
    review = build_review_prep_stage_binding()
    package = build_publication_package_stage_binding()
    assert review.invokes_network is False
    assert review.invokes_llm is False
    assert review.auto_publication is False
    assert package.invokes_network is False
    assert package.invokes_llm is False
    assert package.auto_publication is False


def test_publication_copy_is_deterministic_and_uses_final_script_only():
    script = SimpleNamespace(
        social_30s="La Luna y Júpiter comparten el cielo.",
        social_15s="Mira la Luna junto a Júpiter.",
        closing_line="Sigue mirando arriba.",
        subject="La Luna y Júpiter",
        hook="Dos mundos brillantes en una misma mirada.",
        narration="Narración final aprobada para la prueba técnica de R8.",
    )
    draft = _build_copy_draft(script)
    assert "#Luna" in draft.hashtags
    assert "#Júpiter" in draft.hashtags
    assert draft.youtube_title == "La Luna y Júpiter"
    assert "Narración final aprobada" in draft.youtube_description


def _repo_root():
    from pathlib import Path

    return Path(__file__).resolve().parents[2]


def test_r8_product_ui_connects_review_and_publication():
    text = (_repo_root() / "webui" / "product" / "pages.py").read_text(
        encoding="utf-8"
    )
    assert "register_default_review_publication=True" in text
    assert "st.video(" in text
    assert "st.image(" in text
    assert "review_with_checklist(" in text
    assert "st.download_button(" in text
    assert "Publicación automática" in text


def test_r8_finalization_source_contract_is_explicit():
    text = (
        _repo_root()
        / "app"
        / "services"
        / "centinela"
        / "review_publication"
        / "service.py"
    ).read_text(encoding="utf-8")
    assert '"-c:v",\n            "copy"' in text
    assert 'source["master_ref"].artifact_id' in text
    assert '"derived_from_social": False' in text
    assert '"publication_authorized": False' in text
