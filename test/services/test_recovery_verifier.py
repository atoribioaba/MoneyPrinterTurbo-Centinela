import hashlib

import pytest

from app.models.recovery import RecoveryArtifact, RecoveryArtifactKind, RecoveryManifest
from app.services.centinela.recovery_verifier import verify_recovery_manifest


SHA40 = "a" * 40


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_recovery_verifier_requires_exact_hashes(tmp_path):
    lock = tmp_path / "uv.lock"
    lock.write_bytes(b"locked")
    manifest = RecoveryManifest(
        release_candidate_sha=SHA40,
        artifacts=[
            RecoveryArtifact(
                artifact_id="lock",
                kind=RecoveryArtifactKind.LOCKFILE,
                relative_path="uv.lock",
                sha256=_sha(b"locked"),
            )
        ],
    )
    result = verify_recovery_manifest(manifest, restored_root=tmp_path)
    assert result.verified is True
    assert result.required_passed == 1

    lock.write_bytes(b"modified")
    result = verify_recovery_manifest(manifest, restored_root=tmp_path)
    assert result.verified is False
    assert "HASH_MISMATCH:lock" in result.blockers


def test_recovery_verifier_reports_missing_required_file(tmp_path):
    manifest = RecoveryManifest(
        release_candidate_sha=SHA40,
        artifacts=[
            RecoveryArtifact(
                artifact_id="golden",
                kind=RecoveryArtifactKind.GOLDEN,
                relative_path="golden/final.mp4",
                sha256="b" * 64,
            )
        ],
    )
    result = verify_recovery_manifest(manifest, restored_root=tmp_path)
    assert result.verified is False
    assert "MISSING_REQUIRED:golden" in result.blockers


def test_recovery_manifest_rejects_unsafe_or_duplicate_paths():
    with pytest.raises(ValueError, match="relative"):
        RecoveryArtifact(
            artifact_id="x",
            kind=RecoveryArtifactKind.CONFIG,
            relative_path="C:/secret/config.toml",
            sha256="b" * 64,
        )
    with pytest.raises(ValueError, match="unsafe"):
        RecoveryArtifact(
            artifact_id="x",
            kind=RecoveryArtifactKind.CONFIG,
            relative_path="../config.toml",
            sha256="b" * 64,
        )

    item_a = RecoveryArtifact(
        artifact_id="a",
        kind=RecoveryArtifactKind.CONFIG,
        relative_path="config/a.toml",
        sha256="b" * 64,
    )
    item_b = RecoveryArtifact(
        artifact_id="b",
        kind=RecoveryArtifactKind.CONFIG,
        relative_path="CONFIG/A.TOML",
        sha256="c" * 64,
    )
    with pytest.raises(ValueError, match="paths must be unique"):
        RecoveryManifest(
            release_candidate_sha=SHA40,
            artifacts=[item_a, item_b],
        )


def test_recovery_manifest_never_allows_auto_publication():
    artifact = RecoveryArtifact(
        artifact_id="lock",
        kind=RecoveryArtifactKind.LOCKFILE,
        relative_path="uv.lock",
        sha256="b" * 64,
    )
    with pytest.raises(ValueError, match="AUTO_PUBLICATION"):
        RecoveryManifest(
            release_candidate_sha=SHA40,
            artifacts=[artifact],
            auto_publication=True,
        )
