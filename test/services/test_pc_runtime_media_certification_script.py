from pathlib import Path


SCRIPT = Path("scripts/centinela_pc_runtime_media_certification.ps1")


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_runtime_certification_is_temp_scoped_and_non_destructive():
    text = _text().lower()
    assert "$env:temp" in text
    assert "temp_synthetic_artifacts_only" in text
    assert "auto_publication=false" in text

    forbidden = (
        "git pull",
        "git fetch",
        "git reset",
        "git clean",
        "git merge",
        "git rebase",
        "git switch",
        "git checkout",
        "git restore",
        "git commit",
        "git push",
        "git tag",
        "git cherry-pick",
        "pip install",
        "uv add",
        "uv sync",
        "winget install",
        "choco install",
        "docker pull",
        "ollama pull",
        "remove-item",
    )
    for token in forbidden:
        assert token not in text


def test_runtime_certification_requires_real_nvenc_and_x264_encodes():
    text = _text()
    assert "h264_nvenc" in text
    assert "libx264" in text
    assert "testsrc2=size=1080x1920:rate=30" in text
    assert "ffprobe" in text.lower()
    assert "PHYSICAL_NVENC_PROVEN" in text
    assert "LIBX264_FALLBACK_PROVEN" in text
    assert "CUDA_DEPENDENCY_RUNTIME_PROVEN=FALSE" in text


def test_runtime_certification_hashes_report_and_artifacts():
    text = _text()
    assert "Get-FileHash" in text
    assert "-Algorithm SHA256" in text
    assert "RUNTIME_MEDIA_SHA256" in text


def test_runtime_certification_uses_powershell_syntax_not_shell_backslash_continuation():
    text = _text()
    assert "Invoke-EncodeProbe \\\" not in text
