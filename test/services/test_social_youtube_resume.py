from pathlib import Path

from app.services.social_publication import YouTubeAdapter


class _Response:
    def __init__(self, status_code, *, headers=None, payload=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload or {}
        self.content = b"{}" if payload is not None else b""

    def json(self):
        return self._payload


class _ResumeSession:
    def __init__(self):
        self.put_calls = []

    def request(self, method, url, **kwargs):
        assert method == "POST"
        return _Response(200, headers={"Location": "https://upload.youtube.test/session"}, payload={})

    def put(self, url, **kwargs):
        body = kwargs.get("data")
        payload = body.read() if hasattr(body, "read") else body
        self.put_calls.append({"url": url, "headers": kwargs["headers"], "body": payload})
        if len(self.put_calls) == 1:
            return _Response(308, headers={"Range": "bytes=0-4"})
        return _Response(201, payload={"id": "video-123"})


def test_youtube_resumes_from_last_confirmed_byte(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0123456789")
    session = _ResumeSession()

    result = YouTubeAdapter(session=session).upload_private(
        video,
        access_token="runtime-token",
        title="Astronomy",
        approved=True,
    )

    assert result.success is True
    assert result.remote_id == "video-123"
    assert len(session.put_calls) == 2
    assert session.put_calls[0]["body"] == b"0123456789"
    assert session.put_calls[1]["body"] == b"56789"
    assert session.put_calls[1]["headers"]["Content-Range"] == "bytes 5-9/10"
    assert session.put_calls[1]["headers"]["Content-Length"] == "5"


class _ProbeAfterFailureSession:
    def __init__(self):
        self.put_calls = []
        self.transfer_count = 0

    def request(self, method, url, **kwargs):
        return _Response(200, headers={"Location": "https://upload.youtube.test/session"}, payload={})

    def put(self, url, **kwargs):
        headers = kwargs["headers"]
        if headers.get("Content-Range", "").startswith("bytes */"):
            self.put_calls.append({"kind": "probe", "headers": headers})
            return _Response(308, headers={"Range": "bytes=0-4"})

        self.transfer_count += 1
        body = kwargs["data"]
        payload = body.read()
        self.put_calls.append({"kind": "transfer", "headers": headers, "body": payload})
        if self.transfer_count == 1:
            from requests import ConnectionError

            raise ConnectionError("connection dropped")
        return _Response(201, payload={"id": "video-recovered"})


def test_youtube_probes_session_after_connection_drop_before_resuming(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0123456789")
    session = _ProbeAfterFailureSession()

    result = YouTubeAdapter(session=session).upload_private(
        video,
        access_token="runtime-token",
        title="Astronomy",
        approved=True,
    )

    assert result.remote_id == "video-recovered"
    assert [call["kind"] for call in session.put_calls] == ["transfer", "probe", "transfer"]
    assert session.put_calls[-1]["body"] == b"56789"
    assert session.put_calls[-1]["headers"]["Content-Range"] == "bytes 5-9/10"
