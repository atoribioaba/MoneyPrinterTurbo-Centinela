from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


class CertificationError(RuntimeError):
    pass


def _run(
    args: list[str],
    *,
    cwd: Path,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
    )
    if check and result.returncode != 0:
        if capture:
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="")
        raise CertificationError(
            f"command failed ({result.returncode}): {' '.join(args)}"
        )
    return result


def _lines(args: list[str], *, cwd: Path) -> list[str]:
    result = _run(args, cwd=cwd, capture=True)
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]


def _one(args: list[str], *, cwd: Path) -> str:
    values = _lines(args, cwd=cwd)
    if len(values) != 1:
        raise CertificationError(
            f"expected one line from {' '.join(args)}, got {len(values)}"
        )
    return values[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CertificationError(f"JSON file not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise CertificationError(f"JSON root must be object: {path}")
    return value


def _changed_paths(repo: Path) -> list[str]:
    values = set()
    commands = (
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    )
    for command in commands:
        values.update(_lines(command, cwd=repo))
    return sorted(values)


def _commit_paths(repo: Path, parent: str, head: str) -> list[str]:
    return sorted(
        _lines(
            ["git", "diff", "--name-only", f"{parent}..{head}"],
            cwd=repo,
        )
    )


def _require_exact(actual: list[str], expected: list[str], label: str) -> None:
    actual_set = set(actual)
    expected_set = set(expected)

    unexpected = sorted(actual_set - expected_set)
    missing = sorted(expected_set - actual_set)

    print(f"{label}_COUNT={len(actual)}")
    for path in actual:
        print(path)

    if unexpected:
        print("UNEXPECTED:")
        for path in unexpected:
            print(path)
    if missing:
        print("MISSING:")
        for path in missing:
            print(path)

    if actual_set != expected_set or len(actual) != len(expected):
        raise CertificationError(f"{label} does not match phase manifest")


def _verify_evidence(config: dict[str, Any], expected_parent: str) -> tuple[Path, dict, Path, dict]:
    validation_path = Path(config["validation_manifest"])
    validation = _load_json(validation_path)

    if validation.get("phase") != config["phase"]:
        raise CertificationError("validation manifest phase mismatch")
    if validation.get("status") != "PASS":
        raise CertificationError("validation manifest is not PASS")
    if validation.get("validated_head") != expected_parent:
        raise CertificationError("validation manifest HEAD mismatch")

    run_pointer_path = Path(config["run_pointer"])
    run_pointer = _load_json(run_pointer_path)

    if run_pointer.get("phase") != config["phase"]:
        raise CertificationError("run pointer phase mismatch")

    run_manifest_path = Path(str(run_pointer.get("run_manifest") or ""))
    run_manifest = _load_json(run_manifest_path)

    for key, expected in config.get("run_expectations", {}).items():
        actual = run_manifest.get(key)
        if actual != expected:
            raise CertificationError(
                f"real-run expectation failed: {key} "
                f"expected={expected!r} actual={actual!r}"
            )

    output_path = Path(str(run_manifest.get("output") or ""))
    if not output_path.is_file():
        raise CertificationError(f"real output not found: {output_path}")

    expected_output_sha = str(run_manifest.get("output_sha256") or "").upper()
    actual_output_sha = _sha256(output_path)
    if not expected_output_sha or actual_output_sha != expected_output_sha:
        raise CertificationError("real output SHA256 mismatch")

    print(f"VALIDATION_MANIFEST={validation_path}")
    print(f"RUN_MANIFEST={run_manifest_path}")
    print(f"REAL_OUTPUT={output_path}")
    print(f"REAL_OUTPUT_SHA256={actual_output_sha}")
    print("EVIDENCE_GATE=PASS")

    return validation_path, validation, run_manifest_path, run_manifest


def _gitleaks_staged(repo: Path, report: Path) -> None:
    report.parent.mkdir(parents=True, exist_ok=True)
    _run(["gitleaks", "version"], cwd=repo)
    result = _run(
        [
            "gitleaks",
            "git",
            "--staged",
            "--redact",
            "--no-banner",
            "--report-format",
            "json",
            "--report-path",
            str(report),
            str(repo),
        ],
        cwd=repo,
        check=False,
    )
    if result.returncode != 0:
        raise CertificationError(
            "Gitleaks staged failed; commit was not created"
        )
    print("GITLEAKS_STAGED=PASS")


def _gitleaks_commit(repo: Path, parent: str, head: str, report: Path) -> None:
    report.parent.mkdir(parents=True, exist_ok=True)
    result = _run(
        [
            "gitleaks",
            "git",
            f"--log-opts={parent}..{head}",
            "--redact",
            "--no-banner",
            "--report-format",
            "json",
            "--report-path",
            str(report),
            str(repo),
        ],
        cwd=repo,
        check=False,
    )
    if result.returncode != 0:
        raise CertificationError(
            "Gitleaks commit-range failed; push will not run"
        )
    print("GITLEAKS_COMMIT=PASS")


def certify(repo: Path, manifest_path: Path) -> None:
    config = _load_json(manifest_path)

    required = {
        "phase",
        "name",
        "version",
        "branch",
        "expected_parent",
        "checkpoint_number",
        "commit_message",
        "bundle_slug",
        "expected_paths",
        "validation_manifest",
        "run_pointer",
        "run_expectations",
        "private_origin_repository",
        "backup_root",
        "final_evidence_name",
    }
    missing = sorted(required - set(config))
    if missing:
        raise CertificationError(
            "phase manifest missing keys: " + ", ".join(missing)
        )

    expected_paths = sorted(str(path) for path in config["expected_paths"])
    if len(expected_paths) != len(set(expected_paths)):
        raise CertificationError("expected_paths contains duplicates")

    phase = str(config["phase"])
    branch = str(config["branch"])
    expected_parent = str(config["expected_parent"])
    commit_message = str(config["commit_message"])

    print("=" * 60)
    print(" CENTINELA PHASE CERTIFICATION")
    print("=" * 60)
    print(f"PHASE={phase}")
    print(f"MANIFEST={manifest_path}")

    current_branch = _one(["git", "branch", "--show-current"], cwd=repo)
    current_head = _one(["git", "rev-parse", "HEAD"], cwd=repo)

    print(f"BRANCH={current_branch}")
    print(f"HEAD={current_head}")

    if current_branch != branch:
        raise CertificationError(
            f"branch mismatch: expected {branch}, got {current_branch}"
        )

    validation_path, validation, run_manifest_path, run_manifest = (
        _verify_evidence(config, expected_parent)
    )

    backup_root = Path(config["backup_root"])
    backup_root.mkdir(parents=True, exist_ok=True)

    run_dir = run_manifest_path.parent
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    staged_report = backup_root / f"gitleaks-{phase.lower()}-staged-{stamp}.json"
    commit_report = backup_root / f"gitleaks-{phase.lower()}-commit-{stamp}.json"

    if current_head == expected_parent:
        actual_changes = _changed_paths(repo)
        _require_exact(actual_changes, expected_paths, "CHANGESET")
        print("EXACT_CHANGESET=PASS")

        _run(["git", "add", "--", *expected_paths], cwd=repo)

        staged = sorted(
            _lines(["git", "diff", "--cached", "--name-only"], cwd=repo)
        )
        _require_exact(staged, expected_paths, "STAGED")
        print("EXACT_STAGE=PASS")

        unstaged = _lines(["git", "diff", "--name-only"], cwd=repo)
        untracked = _lines(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=repo,
        )
        if unstaged or untracked:
            raise CertificationError(
                "changes remain outside the exact stage"
            )

        _run(["git", "diff", "--cached", "--check"], cwd=repo)
        print("DIFF_CHECK=PASS")

        _gitleaks_staged(repo, staged_report)

        _run(["git", "commit", "-m", commit_message], cwd=repo)
        current_head = _one(["git", "rev-parse", "HEAD"], cwd=repo)
        parent = _one(["git", "rev-parse", "HEAD^"], cwd=repo)
        if parent != expected_parent:
            raise CertificationError("new commit parent mismatch")

        print(f"{phase}_COMMIT={current_head}")
        print(f"{phase}_PARENT={parent}")

    else:
        parent = _one(["git", "rev-parse", "HEAD^"], cwd=repo)
        actual_message = _one(
            ["git", "log", "-1", "--pretty=%s"],
            cwd=repo,
        )
        if parent != expected_parent or actual_message != commit_message:
            raise CertificationError(
                "HEAD is neither expected parent nor resumable phase commit"
            )
        commit_files = _commit_paths(repo, expected_parent, current_head)
        _require_exact(commit_files, expected_paths, "COMMIT_CHANGESET")
        if _changed_paths(repo):
            raise CertificationError(
                "resume mode requires clean worktree"
            )
        print("RESUME_AFTER_COMMIT=TRUE")

    _gitleaks_commit(
        repo,
        expected_parent,
        current_head,
        commit_report,
    )

    checkpoint_number = int(config["checkpoint_number"])
    bundle = backup_root / (
        f"centinela-checkpoint-{checkpoint_number}-"
        f"{config['bundle_slug']}-{stamp}.bundle"
    )
    _run(
        ["git", "bundle", "create", str(bundle), branch],
        cwd=repo,
    )
    _run(["git", "bundle", "verify", str(bundle)], cwd=repo)
    bundle_sha = _sha256(bundle)

    print(f"CHECKPOINT{checkpoint_number}={bundle}")
    print(f"CHECKPOINT{checkpoint_number}_SHA256={bundle_sha}")
    print(f"CHECKPOINT{checkpoint_number}_VERIFY=PASS")

    origin = _one(["git", "remote", "get-url", "origin"], cwd=repo)
    expected_repo = str(config["private_origin_repository"])
    if expected_repo not in origin:
        raise CertificationError(
            f"origin is not the private Centinela repository: {origin}"
        )
    print(f"ORIGIN={origin}")

    remote_ref = f"refs/heads/{branch}"
    remote_lines = _lines(
        ["git", "ls-remote", "--heads", "origin", remote_ref],
        cwd=repo,
    )

    if remote_lines:
        if len(remote_lines) != 1:
            raise CertificationError("remote branch resolution is ambiguous")
        remote_sha = remote_lines[0].split()[0]
        if remote_sha != current_head:
            raise CertificationError(
                "remote branch exists at different SHA; refusing force push"
            )
        print("PUSH_ALREADY_PRESENT=TRUE")
    else:
        _run(
            ["git", "push", "--set-upstream", "origin", branch],
            cwd=repo,
        )

    remote_lines = _lines(
        ["git", "ls-remote", "--heads", "origin", remote_ref],
        cwd=repo,
    )
    if len(remote_lines) != 1:
        raise CertificationError("cannot verify one remote phase branch")
    remote_sha = remote_lines[0].split()[0]
    if remote_sha != current_head:
        raise CertificationError("remote SHA does not match local commit")

    print(f"LOCAL_SHA={current_head}")
    print(f"REMOTE_SHA={remote_sha}")
    print("REMOTE_SHA_MATCH=TRUE")

    evidence_dir = run_manifest_path.parent
    evidence_dir.mkdir(parents=True, exist_ok=True)

    staged_copy = evidence_dir / "gitleaks-staged.json"
    commit_copy = evidence_dir / "gitleaks-commit.json"

    if staged_report.is_file():
        shutil.copy2(staged_report, staged_copy)
    if commit_report.is_file():
        shutil.copy2(commit_report, commit_copy)

    final_manifest_path = evidence_dir / str(config["final_evidence_name"])
    final = {
        "schema": "centinela-phase-certification-v0.1",
        "phase": phase,
        "name": config["name"],
        "version": config["version"],
        "status": "COMPLETE",
        "phase_certified": True,
        "generated_at_local": datetime.now().astimezone().isoformat(),
        "repository": expected_repo,
        "branch": branch,
        "parent_commit": expected_parent,
        "phase_commit": current_head,
        "remote_commit": remote_sha,
        "validation_manifest": str(validation_path),
        "validation_manifest_sha256": _sha256(validation_path),
        "real_run_manifest": str(run_manifest_path),
        "real_run_manifest_sha256": _sha256(run_manifest_path),
        "real_output": run_manifest.get("output"),
        "real_output_sha256": run_manifest.get("output_sha256"),
        "checkpoint": {
            "number": checkpoint_number,
            "bundle_path": str(bundle),
            "sha256": bundle_sha,
            "verify": "PASS",
        },
        "security": {
            "gitleaks_staged": (
                "PASS" if staged_copy.is_file() else "COMMIT_RANGE_EQUIVALENT_RESUME"
            ),
            "gitleaks_commit_range": "PASS",
            "leaked_secrets": 0,
            "staged_report": str(staged_copy) if staged_copy.is_file() else None,
            "commit_report": str(commit_copy),
        },
        "run_summary": run_manifest,
    }
    final_manifest_path.write_text(
        json.dumps(final, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    final_sha = _sha256(final_manifest_path)

    if _changed_paths(repo):
        print("WORKTREE:")
        _run(["git", "status", "--short"], cwd=repo)
        raise CertificationError("final worktree is not clean")

    print(f"FINAL_EVIDENCE={final_manifest_path}")
    print(f"FINAL_EVIDENCE_SHA256={final_sha}")
    print("WORKTREE_CLEAN=TRUE")
    print("")
    print("=" * 60)
    print(f" {phase} CHECKPOINT {checkpoint_number}: COMPLETE")
    print(" REMOTE_SHA_MATCH=TRUE")
    print(" WORKTREE_CLEAN=TRUE")
    print(" PHASE_CERTIFIED=TRUE")
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Certify one EL CENTINELA MoneyPrinterTurbo phase."
    )
    parser.add_argument("--repo", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    try:
        certify(
            Path(args.repo).resolve(),
            Path(args.manifest).resolve(),
        )
    except CertificationError as exc:
        print("")
        print("PHASE_CERTIFIED=FALSE")
        print("ERROR=" + str(exc))
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
