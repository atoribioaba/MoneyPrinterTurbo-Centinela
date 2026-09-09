from __future__ import annotations

import hashlib
from pathlib import Path

from app.models.recovery import (
    RecoveryManifest,
    RecoveryVerificationItem,
    RecoveryVerificationResult,
)


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_recovery_manifest(
    manifest: RecoveryManifest,
    *,
    restored_root: str | Path,
) -> RecoveryVerificationResult:
    """Read-only verification of a restored tree against a signed-by-hash manifest."""
    root = Path(restored_root).resolve()
    items: list[RecoveryVerificationItem] = []
    blockers: list[str] = []
    required_total = 0
    required_passed = 0

    for artifact in manifest.artifacts:
        if artifact.required:
            required_total += 1
        path = (root / artifact.relative_path).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            blockers.append(f"PATH_ESCAPE:{artifact.artifact_id}")
            items.append(
                RecoveryVerificationItem(
                    artifact_id=artifact.artifact_id,
                    relative_path=artifact.relative_path,
                    exists=False,
                    hash_matches=False,
                )
            )
            continue

        exists = path.is_file()
        actual_hash = _sha256_file(path) if exists else None
        matches = bool(actual_hash) and actual_hash.casefold() == artifact.sha256.casefold()
        if artifact.required and exists and matches:
            required_passed += 1
        elif artifact.required:
            blockers.append(
                f"{'HASH_MISMATCH' if exists else 'MISSING_REQUIRED'}:{artifact.artifact_id}"
            )

        items.append(
            RecoveryVerificationItem(
                artifact_id=artifact.artifact_id,
                relative_path=artifact.relative_path,
                exists=exists,
                hash_matches=matches,
                actual_sha256=actual_hash,
            )
        )

    verified = required_total > 0 and required_passed == required_total and not blockers
    return RecoveryVerificationResult(
        release_candidate_sha=manifest.release_candidate_sha,
        verified=verified,
        required_total=required_total,
        required_passed=required_passed,
        items=items,
        blockers=sorted(set(blockers)),
    )
