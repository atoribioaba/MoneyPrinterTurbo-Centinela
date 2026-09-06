from pathlib import Path

import pytest

from app.services.error_control import (
    CentinelaError,
    ErrorCategory,
    is_retryable_http_status,
    redact_secrets,
    validate_local_media_file,
)


def test_redact_secrets_hides_bearer_and_api_key():
    value = "Authorization: Bearer abc123 api_key=super-secret"
    safe = redact_secrets(value)
    assert "abc123" not in safe
    assert "super-secret" not in safe
    assert safe.count("***REDACTED***") == 2


def test_validate_local_media_file_accepts_non_empty_video(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"centinela")

    resolved = validate_local_media_file(
        video,
        operation="test.upload",
        allowed_extensions={".mp4"},
        max_size_bytes=1024,
    )

    assert resolved == video.resolve()


def test_validate_local_media_file_rejects_missing_file(tmp_path: Path):
    with pytest.raises(CentinelaError) as exc_info:
        validate_local_media_file(
            tmp_path / "missing.mp4",
            operation="test.upload",
            allowed_extensions={".mp4"},
        )

    error = exc_info.value
    assert error.category is ErrorCategory.FILESYSTEM
    assert error.code == "media_not_found"
    assert error.retryable is False


@pytest.mark.parametrize(
    ("status", "expected"),
    [(400, False), (401, False), (403, False), (404, False), (429, True), (500, True), (503, True)],
)
def test_retryable_http_status_is_fail_closed(status: int, expected: bool):
    assert is_retryable_http_status(status) is expected
