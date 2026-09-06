import json
from pathlib import Path

import pytest

from app.services.error_control import CentinelaError
from app.services.social_publication import (
    AUTO_PUBLICATION,
    InstagramAdapter,
    TikTokAdapter,
    YouTubeAdapter,
)


class _Response:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.content = json.dumps(self._payload).encode() if payload is not None else b""

    def json(self):
        return self._payload


class _Session:
    def __init__(self):
        self.requests = []
        self.puts = []
        self.request_responses = []
        self.put_responses = []

    def request(self, method, url, timeout=None, **kwargs):
        self.requests.append((method, url, timeout, kwargs))
        return self.request_responses.pop(0)

    def put(self, url, headers=None, data=None, timeout=None):
        body = data.read() if hasattr(data, "read") else data
        self.puts.append((url, headers or {}, body, timeout))
        return self.put_responses.pop(0)


def _video(tmp_path: Path, size: int = 1024) -> Path:
    path = tmp_path / "video.mp4"
    path.write_bytes(b"x" * size)
    return path


def test_auto_publication_invariant_is_false():
    assert AUTO_PUBLICATION is False


@pytest.mark.parametrize("adapter_method", ["youtube", "tiktok", "instagram"])
def test_write_operations_require_explicit_human_approval(tmp_path: Path, adapter_method: str):
    video = _video(tmp_path)
    with pytest.raises(CentinelaError) as exc_info:
        if adapter_method == "youtube":
            YouTubeAdapter(session=_Session()).upload_private(
                video,
                access_token="token",
                title="Test",
            )
        elif adapter_method == "tiktok":
            TikTokAdapter(session=_Session()).upload_to_inbox(
                video,
                access_token="token",
            )
        else:
            InstagramAdapter(session=_Session()).create_reel_container(
                ig_user_id="123",
                access_token="token",
                video_url="https://example.test/video.mp4",
            )

    assert exc_info.value.code == "human_approval_required"


def test_youtube_upload_is_forced_private(tmp_path: Path):
    session = _Session()
    session.request_responses.append(
        _Response(200, {}, {"Location": "https://upload.youtube.test/session"})
    )
    session.put_responses.append(_Response(201, {"id": "yt123"}))

    result = YouTubeAdapter(session=session).upload_private(
        _video(tmp_path),
        access_token="secret",
        title="Centinela",
        description="Astronomía",
        approved=True,
    )

    assert result.success is True
    assert result.remote_id == "yt123"
    assert result.status == "uploaded_private"
    metadata = session.requests[0][3]["json"]
    assert metadata["status"]["privacyStatus"] == "private"


def test_tiktok_small_file_uploads_as_one_chunk(tmp_path: Path):
    session = _Session()
    session.request_responses.append(
        _Response(
            200,
            {
                "data": {"publish_id": "tt123", "upload_url": "https://upload.tiktok.test"},
                "error": {"code": "ok", "message": ""},
            },
        )
    )
    session.put_responses.append(_Response(201, {}))
    path = _video(tmp_path, size=1024)

    result = TikTokAdapter(session=session).upload_to_inbox(
        path,
        access_token="secret",
        approved=True,
    )

    assert result.success is True
    assert result.remote_id == "tt123"
    source_info = session.requests[0][3]["json"]["source_info"]
    assert source_info == {
        "source": "FILE_UPLOAD",
        "video_size": 1024,
        "chunk_size": 1024,
        "total_chunk_count": 1,
    }
    assert session.puts[0][1]["Content-Range"] == "bytes 0-1023/1024"
    assert result.requires_user_action is True


def test_tiktok_chunk_plan_merges_trailing_bytes_into_last_chunk():
    size = 70 * 1024**2 + 123
    chunk_size, chunk_count = TikTokAdapter._chunk_plan(size)

    assert 5 * 1024**2 <= chunk_size <= 64 * 1024**2
    assert chunk_count == size // chunk_size
    last_chunk = size - (chunk_count - 1) * chunk_size
    assert last_chunk >= chunk_size
    assert last_chunk <= 128 * 1024**2


def test_instagram_container_then_status_then_publish():
    session = _Session()
    session.request_responses.extend(
        [
            _Response(200, {"id": "container123"}),
            _Response(200, {"status_code": "FINISHED", "status": "Finished"}),
            _Response(200, {"id": "media123"}),
        ]
    )
    adapter = InstagramAdapter(session=session)

    container = adapter.create_reel_container(
        ig_user_id="ig123",
        access_token="secret",
        video_url="https://example.test/video.mp4",
        caption="El Centinela",
        approved=True,
    )
    published = adapter.publish_reel(
        ig_user_id="ig123",
        container_id=container.remote_id,
        access_token="secret",
        approved=True,
    )

    assert container.remote_id == "container123"
    assert published.success is True
    assert published.remote_id == "media123"


def test_instagram_rejects_non_https_media_url_before_network_call():
    session = _Session()
    with pytest.raises(CentinelaError) as exc_info:
        InstagramAdapter(session=session).create_reel_container(
            ig_user_id="123",
            access_token="secret",
            video_url="http://localhost/video.mp4",
            approved=True,
        )

    assert exc_info.value.code == "instagram_public_https_url_required"
    assert session.requests == []
