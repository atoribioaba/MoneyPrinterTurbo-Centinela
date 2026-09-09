import json

import pytest

from app.services.centinela.http_json import fetch_json_https


class FakeResponse:
    def __init__(self, payload, *, url="https://api.example.test/data", status=200):
        self._raw = json.dumps(payload).encode("utf-8")
        self._url = url
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def geturl(self):
        return self._url

    def read(self, size=-1):
        if size < 0:
            return self._raw
        return self._raw[:size]


def test_fetch_json_https_accepts_one_allowlisted_https_response():
    calls = []

    def opener(request, timeout):
        calls.append((request.full_url, timeout, request.get_header("User-agent")))
        return FakeResponse({"ok": True})

    payload = fetch_json_https(
        "https://api.example.test/data",
        allowed_hosts={"api.example.test"},
        opener=opener,
    )

    assert payload == {"ok": True}
    assert len(calls) == 1
    assert calls[0][0] == "https://api.example.test/data"
    assert calls[0][1] == 15.0
    assert calls[0][2]


def test_fetch_json_https_rejects_http_and_embedded_credentials():
    with pytest.raises(ValueError, match="HTTPS"):
        fetch_json_https(
            "http://api.example.test/data",
            allowed_hosts={"api.example.test"},
        )
    with pytest.raises(ValueError, match="credentials"):
        fetch_json_https(
            "https://user:secret@api.example.test/data",
            allowed_hosts={"api.example.test"},
        )


def test_fetch_json_https_rejects_redirect_to_unapproved_host():
    def opener(request, timeout):
        return FakeResponse(
            {"ok": True},
            url="https://evil.example.test/redirected",
        )

    with pytest.raises(ValueError, match="not allowlisted"):
        fetch_json_https(
            "https://api.example.test/data",
            allowed_hosts={"api.example.test"},
            opener=opener,
        )


def test_fetch_json_https_is_bounded_and_does_not_retry():
    calls = 0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        return FakeResponse({"blob": "x" * 100})

    with pytest.raises(ValueError, match="byte limit"):
        fetch_json_https(
            "https://api.example.test/data",
            allowed_hosts={"api.example.test"},
            max_bytes=10,
            opener=opener,
        )
    assert calls == 1


def test_fetch_json_https_rejects_non_object_json():
    class ListResponse(FakeResponse):
        def __init__(self):
            self._raw = b"[1, 2, 3]"
            self._url = "https://api.example.test/data"
            self.status = 200

    with pytest.raises(ValueError, match="root must be an object"):
        fetch_json_https(
            "https://api.example.test/data",
            allowed_hosts={"api.example.test"},
            opener=lambda request, timeout: ListResponse(),
        )
