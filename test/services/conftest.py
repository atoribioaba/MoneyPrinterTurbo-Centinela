from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PIL import Image

from app.models.astromedia import MediaType
from app.services import astromedia as astromedia_service
from app.services.centinela.orchestration.state_machine import (
    ProjectStateMachine as RawProjectStateMachine,
)


_MEDIA_RESOLVER_RAW_STATE_TESTS = {
    "test_r3_media_stage_integration_advances_only_when_resolved",
    "test_r3_media_stage_unresolved_goes_to_needs_input",
}


def _pillow_image_probe(path: Path) -> dict[str, object]:
    try:
        with Image.open(path) as image:
            width, height = image.size
            codec_name = (image.format or path.suffix.lstrip(".") or "image").casefold()
            image.verify()
    except (OSError, ValueError) as exc:
        raise astromedia_service.AstroMediaError(
            f"Image probe failed for {path}: {exc}"
        ) from exc

    return {
        "width": max(0, int(width)),
        "height": max(0, int(height)),
        "rotation_deg": 0,
        "fps": 0.0,
        "duration_seconds": 0.0,
        "codec_name": codec_name,
    }


@pytest.fixture(autouse=True)
def _general_ci_portability(monkeypatch, request):
    if request.node.name in _MEDIA_RESOLVER_RAW_STATE_TESTS:
        monkeypatch.setattr(
            request.node.module,
            "ProjectStateMachine",
            RawProjectStateMachine,
        )

    if shutil.which("ffprobe") is not None:
        return

    original_probe = astromedia_service._ffprobe

    def portable_probe(path, media_type):
        if media_type == MediaType.IMAGE:
            return _pillow_image_probe(Path(path))
        return original_probe(path, media_type)

    monkeypatch.setattr(astromedia_service, "_ffprobe", portable_probe)
