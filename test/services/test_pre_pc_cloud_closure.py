from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/centinela/PRE_PC_CLOUD_CLOSURE.json"
C20_SHA = "2c6267c8d9ad3d144ebe6db73189a34c63656ce0"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_pre_pc_manifest_is_machine_readable_and_keeps_safety_invariants() -> None:
    data = _manifest()
    assert data["schema_version"] == "centinela-pre-pc-cloud-closure-v1"
    assert data["auto_publication"] is False
    assert data["merge_authorized"] is False
    assert data["architecture_freeze_authorized"] is False
    assert data["default_branch_change_authorized"] is False
    assert data["physical_gates_certified_in_cloud"] is False
    assert data["reconciliation_state"] == "PENDING_PHYSICAL_PC"


def test_c20_remains_first_physical_return_target_and_pr69_does_not_replace_it() -> None:
    data = _manifest()
    target = data["physical_return_target"]
    cloud = data["cloud_improvement_line"]
    assert target["branch"] == (
        "centinela-engineering/c05-c20-windows-path-contract-adversarial-v0.1"
    )
    assert target["sha"] == C20_SHA
    assert cloud["pull_request"] == 69
    assert cloud["draft_required"] is True
    assert cloud["merge_required_before_pc"] is False
    assert cloud["head_sha_embedded_in_manifest"] is False


def test_first_physical_action_is_read_only_preflight_before_git_sync() -> None:
    data = _manifest()
    first = data["physical_pc_first_action"]
    assert first["script"] == "scripts/centinela_pc_return_readonly_preflight.ps1"
    assert first["repo_path"] == r"E:\Github\MoneyPrinterTurbo"
    assert first["read_only_required"] is True
    assert first["must_run_before_git_sync"] is True

    forbidden = set(data["forbidden_before_preflight_review"])
    for command in (
        "git fetch",
        "git pull",
        "git switch",
        "git checkout",
        "git merge",
        "git rebase",
        "git reset",
        "git clean",
        "git stash pop",
        "git stash apply",
    ):
        assert command in forbidden


def test_expected_local_state_is_only_expectation_not_asserted_physical_fact() -> None:
    data = _manifest()
    local = data["expected_pre_trip_local_state"]
    assert local["head"] == "186104539a7116ad48b96beac90eccd3c4c37801"
    assert local["stash_sha"] == "22ee99b0703be803e63beaed2370485c84604c9a"
    assert local["interpretation"] == (
        "EXPECTED_ONLY_NOT_ASSERTED; physical preflight evidence is authoritative."
    )
    assert len(local["known_untracked"]) == 3


def test_cloud_closure_explicitly_lists_core_physical_only_gates() -> None:
    gates = set(_manifest()["physical_only_gates"])
    expected = {
        "real_astromedia_catalog",
        "f57_local_8_of_8",
        "rtx2060_detection",
        "cuda_dependency_runtime",
        "nvenc_real_encode",
        "llm_local_benchmark",
        "tts_es_es_ab_listening",
        "ai_visual_t2i_i2v_t2v_upscale_runtime",
        "golden_real_e2e",
        "human_review_7_of_7",
        "backup_recovery_physical_drill",
        "f58_final_release_candidate",
        "explicit_human_v1_freeze_approval",
    }
    assert expected <= gates


def test_cloud_head_identity_is_resolved_from_git_not_self_referential_json() -> None:
    cloud = _manifest()["cloud_improvement_line"]
    assert cloud["exact_head_resolution"] == (
        "READ_PR_69_HEAD_AND_REQUIRE_ALL_EXPECTED_CHECKS_SUCCESS"
    )
    assert cloud["head_sha_embedded_in_manifest"] is False
