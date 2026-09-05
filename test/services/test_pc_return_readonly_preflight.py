from __future__ import annotations

import concurrent.futures
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "centinela_pc_return_readonly_preflight.ps1"
IS_WINDOWS = platform.system() == "Windows"
WINDOWS_ONLY = pytest.mark.skipif(
    not IS_WINDOWS,
    reason="PC return preflight runtime tests require Windows PowerShell 5.1.",
)


def _powershell() -> str:
    executable = shutil.which("powershell.exe") or shutil.which("powershell")
    if not executable:
        pytest.skip("Windows PowerShell is not available.")
    return executable


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return result.stdout.strip()


def _make_repo(tmp_path: Path, critical_file: bool = False) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", str(repo)],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(repo, "config", "user.email", "centinela-ci@example.invalid")
    _git(repo, "config", "user.name", "Centinela CI")
    (repo / "README.txt").write_text("fixture\n", encoding="utf-8")

    if critical_file:
        path = repo / "app" / "services" / "centinela" / "quality"
        path.mkdir(parents=True)
        (path / "f57_real_runner.py").write_text(
            "VALUE = 'fixture'\n",
            encoding="utf-8",
        )

    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "fixture")
    return repo


def _parse_markers(stdout: str) -> dict[str, str]:
    markers: dict[str, str] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if re.fullmatch(r"[A-Z0-9_]+", key):
            markers[key] = value
    return markers


def _invoke(
    script: Path,
    repo: Path,
    output_root: Path,
    *,
    env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    output_root.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-RepoPath",
            str(repo),
            "-OutputRoot",
            str(output_root),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=90,
    )
    return result, _parse_markers(result.stdout)


def _report(markers: dict[str, str]) -> str:
    path = Path(markers["PREFLIGHT_REPORT"])
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _patched_script(
    tmp_path: Path,
    *,
    old: str,
    new: str,
) -> Path:
    content = SCRIPT.read_text(encoding="utf-8")
    assert content.count(old) == 1
    target = tmp_path / "preflight-injected.ps1"
    target.write_text(content.replace(old, new), encoding="utf-8")
    return target


@WINDOWS_ONLY
def test_t01_happy_path_gate_valid(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result, markers = _invoke(SCRIPT, repo, tmp_path / "out")

    assert result.returncode == 0, result.stdout + result.stderr
    assert markers["PREFLIGHT_COLLECTOR_STATUS"] == "VALID"
    assert markers["PREFLIGHT_GATE_COMPLETE"] == "TRUE"
    assert markers["PREFLIGHT_COMPLETE"] == "TRUE"
    assert markers["GIT_EVIDENCE_COMPLETE"] == "TRUE"
    assert markers["PREFLIGHT_REPORT_WRITTEN"] == "TRUE"
    assert markers["PREFLIGHT_REPORT_HASHED"] == "TRUE"
    assert markers["PREFLIGHT_HASH_FILE_WRITTEN"] == "TRUE"
    assert Path(markers["PREFLIGHT_REPORT"]).is_file()
    assert Path(markers["PREFLIGHT_HASH_FILE"]).is_file()


@WINDOWS_ONLY
def test_t02_missing_repo_is_blocked_not_failed(tmp_path: Path) -> None:
    repo = tmp_path / "missing-repo"
    result, markers = _invoke(SCRIPT, repo, tmp_path / "out")

    assert result.returncode == 2
    assert markers["PREFLIGHT_COLLECTOR_STATUS"] == "BLOCKED"
    assert markers["PREFLIGHT_GATE_COMPLETE"] == "FALSE"
    assert "B_REPO_PATH_MISSING" in markers["PREFLIGHT_BLOCKERS"]
    assert markers["PREFLIGHT_REPORT_WRITTEN"] == "TRUE"
    assert markers["PREFLIGHT_REPORT_HASHED"] == "TRUE"


@WINDOWS_ONLY
def test_t03_existing_non_git_directory_is_blocked(tmp_path: Path) -> None:
    repo = tmp_path / "not-git"
    repo.mkdir()
    result, markers = _invoke(SCRIPT, repo, tmp_path / "out")

    assert result.returncode == 2
    assert markers["PREFLIGHT_COLLECTOR_STATUS"] == "BLOCKED"
    assert markers["PREFLIGHT_GATE_COMPLETE"] == "FALSE"
    assert "B_NOT_GIT_WORKTREE" in markers["PREFLIGHT_BLOCKERS"]


@WINDOWS_ONLY
def test_t04_git_unavailable_is_blocked(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    env = os.environ.copy()
    system_root = Path(env["SystemRoot"])
    env["PATH"] = str(system_root / "System32")

    result, markers = _invoke(
        SCRIPT,
        repo,
        tmp_path / "out",
        env=env,
    )

    assert result.returncode == 2
    assert markers["PREFLIGHT_GATE_COMPLETE"] == "FALSE"
    assert "B_GIT_UNAVAILABLE" in markers["PREFLIGHT_BLOCKERS"]


@WINDOWS_ONLY
def test_t05_missing_optional_critical_files_are_valid_evidence(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path)
    result, markers = _invoke(SCRIPT, repo, tmp_path / "out")
    report = _report(markers)

    assert result.returncode == 0
    assert markers["PREFLIGHT_GATE_COMPLETE"] == "TRUE"
    assert report.count("CRITICAL_FILE | PATH=") == 3
    assert report.count("EXISTS=FALSE") >= 3
    assert "CRITICAL_FILE_SHA256" not in report


@WINDOWS_ONLY
def test_t06_present_critical_file_has_hash_and_metadata(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path, critical_file=True)
    critical = (
        repo
        / "app"
        / "services"
        / "centinela"
        / "quality"
        / "f57_real_runner.py"
    )
    expected_hash = hashlib.sha256(critical.read_bytes()).hexdigest().upper()

    result, markers = _invoke(SCRIPT, repo, tmp_path / "out")
    report = _report(markers)

    assert result.returncode == 0
    assert expected_hash in report
    assert "SIZE_BYTES=" in report
    assert "LAST_WRITE_TIME_UTC=" in report
    assert "TRACKING_STATE=TRACKED" in report


@WINDOWS_ONLY
def test_t07_report_write_failure_is_collector_failure(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path)
    old = (
        "$script:ReportLines | Set-Content -LiteralPath $ReportPath "
        "-Encoding UTF8 -ErrorAction Stop"
    )
    injected = _patched_script(
        tmp_path,
        old=old,
        new="throw 'INJECTED_REPORT_WRITE_FAILURE'",
    )

    result, markers = _invoke(injected, repo, tmp_path / "out")

    assert result.returncode == 3
    assert markers["PREFLIGHT_COLLECTOR_STATUS"] == "FAILED"
    assert markers["PREFLIGHT_REPORT_WRITTEN"] == "FALSE"
    assert markers["PREFLIGHT_GATE_COMPLETE"] == "FALSE"
    assert "B_REPORT_WRITE_FAILED" in markers["PREFLIGHT_BLOCKERS"]


@WINDOWS_ONLY
def test_t08_report_hash_failure_is_collector_failure(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path)
    old = (
        "$ReportHash = (Get-FileHash -LiteralPath $ReportPath "
        "-Algorithm SHA256 -ErrorAction Stop).Hash"
    )
    injected = _patched_script(
        tmp_path,
        old=old,
        new="throw 'INJECTED_REPORT_HASH_FAILURE'",
    )

    result, markers = _invoke(injected, repo, tmp_path / "out")

    assert result.returncode == 3
    assert markers["PREFLIGHT_COLLECTOR_STATUS"] == "FAILED"
    assert markers["PREFLIGHT_REPORT_WRITTEN"] == "TRUE"
    assert markers["PREFLIGHT_REPORT_HASHED"] == "FALSE"
    assert markers["PREFLIGHT_GATE_COMPLETE"] == "FALSE"
    assert "B_REPORT_HASH_FAILED" in markers["PREFLIGHT_BLOCKERS"]


def test_t09_static_safety_forbids_mutating_git_and_repo_context() -> None:
    content = SCRIPT.read_text(encoding="utf-8")

    assert "Push-Location" not in content
    assert "Pop-Location" not in content
    assert "@('--no-optional-locks', '-C', $RepoPath)" in content
    assert "Remove-Item" not in content

    prohibited = (
        "pull",
        "fetch",
        "reset",
        "clean",
        "merge",
        "rebase",
        "switch",
        "checkout",
        "restore",
        "commit",
        "push",
        "tag",
        "cherry-pick",
    )
    for command in prohibited:
        literal = re.compile(rf"['\"]{re.escape(command)}['\"]")
        assert literal.search(content) is None, command


@WINDOWS_ONLY
def test_t10_report_completion_and_gate_are_independent(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "missing-repo"
    result, markers = _invoke(SCRIPT, repo, tmp_path / "out")

    assert result.returncode == 2
    assert markers["PREFLIGHT_EXECUTION_FINISHED"] == "TRUE"
    assert markers["PREFLIGHT_REPORT_WRITTEN"] == "TRUE"
    assert markers["PREFLIGHT_REPORT_HASHED"] == "TRUE"
    assert markers["PREFLIGHT_HASH_FILE_WRITTEN"] == "TRUE"
    assert markers["PREFLIGHT_GATE_COMPLETE"] == "FALSE"
    assert markers["PREFLIGHT_COMPLETE"] == "FALSE"


@WINDOWS_ONLY
def test_t11_detached_head_is_warning_not_blocker(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _git(repo, "checkout", "--detach", "-q", "HEAD")

    result, markers = _invoke(SCRIPT, repo, tmp_path / "out")
    report = _report(markers)

    assert result.returncode == 0
    assert markers["PREFLIGHT_GATE_COMPLETE"] == "TRUE"
    assert "W_DETACHED_HEAD_OBSERVED" in markers["PREFLIGHT_WARNINGS"]
    assert "HEAD_MODE=DETACHED" in report


@WINDOWS_ONLY
def test_t12_core_git_native_failure_blocks_gate(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    bad_index = tmp_path / "bad-index"
    bad_index.mkdir()
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = str(bad_index)

    result, markers = _invoke(
        SCRIPT,
        repo,
        tmp_path / "out",
        env=env,
    )

    assert result.returncode == 2
    assert markers["PREFLIGHT_GATE_COMPLETE"] == "FALSE"
    blockers = markers["PREFLIGHT_BLOCKERS"]
    assert (
        "B_STATUS_UNREADABLE" in blockers
        or "B_CRITICAL_FILE_INVENTORY_FAILED" in blockers
    )


@WINDOWS_ONLY
def test_t13_concurrent_runs_never_share_evidence_directory(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path)
    output_root = tmp_path / "out"

    def run_once() -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
        return _invoke(SCRIPT, repo, output_root)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: run_once(), range(2)))

    assert all(result.returncode == 0 for result, _ in results)
    report_dirs = {
        Path(markers["PREFLIGHT_REPORT"]).parent
        for _, markers in results
    }
    assert len(report_dirs) == 2


def test_t14_optional_tool_absence_is_warning_not_blocker() -> None:
    content = SCRIPT.read_text(encoding="utf-8")

    warning_codes = (
        "W_NVIDIA_SMI_NOT_AVAILABLE",
        "W_FFMPEG_NOT_AVAILABLE",
        "W_FFPROBE_NOT_AVAILABLE",
        "W_NVCC_NOT_AVAILABLE",
        "W_OLLAMA_NOT_AVAILABLE",
    )
    for code in warning_codes:
        assert f"Add-Warning '{code}'" in content
        assert f"Add-Blocker '{code}'" not in content

    assert (
        "COLLECTION_FAILURE_IS_NOT_COLLECTED_NEGATIVE_EVIDENCE=TRUE"
        in content
    )
