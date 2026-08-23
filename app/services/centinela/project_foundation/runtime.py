from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import RuntimeSnapshot, utc_now_iso


def _run(args: list[str], cwd: Path, timeout: int = 5) -> str:
    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip()


def _app_version(root: Path) -> str:
    try:
        with (root / "pyproject.toml").open("rb") as handle:
            value = tomllib.load(handle).get("project", {}).get("version")
    except (OSError, tomllib.TOMLDecodeError):
        return "unknown"
    return value.strip() if isinstance(value, str) and value.strip() else "unknown"


def _resolve_ffmpeg(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    configured = os.environ.get("IMAGEIO_FFMPEG_EXE")
    if configured:
        return configured
    return shutil.which("ffmpeg")


def capture_runtime_snapshot(
    repo_root: str | Path,
    *,
    encoder: str | None = None,
    llm: dict[str, Any] | None = None,
    tts: dict[str, Any] | None = None,
    media_providers: list[dict[str, Any]] | None = None,
    render: dict[str, Any] | None = None,
    environment: dict[str, Any] | None = None,
    ffmpeg_path: str | None = None,
) -> RuntimeSnapshot:
    """Capture effective runtime state without reading secrets from config.toml."""

    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise ValueError(f"repo_root is not a directory: {root}")

    resolved_ffmpeg = _resolve_ffmpeg(ffmpeg_path)
    ffmpeg_version = None
    if resolved_ffmpeg:
        output = _run([resolved_ffmpeg, "-version"], root)
        if output:
            ffmpeg_version = output.splitlines()[0].strip()

    return RuntimeSnapshot(
        snapshot_id=uuid4().hex,
        created_at=utc_now_iso(),
        git_commit=_run(["git", "rev-parse", "HEAD"], root) or "unknown",
        git_branch=_run(["git", "branch", "--show-current"], root) or "detached",
        app_version=_app_version(root),
        python_version=platform.python_version(),
        platform=platform.platform(),
        ffmpeg_path=resolved_ffmpeg,
        ffmpeg_version=ffmpeg_version,
        encoder=encoder,
        llm=llm or {},
        tts=tts or {},
        media_providers=media_providers or [],
        render=render or {},
        environment={
            "python_executable": sys.executable,
            **(environment or {}),
        },
    )
