from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.services import voice


class _OkResponse:
    status_code = 200
    content = b"fake-mp3"
    text = ""

    @staticmethod
    def json():
        return {}


class _BrokenClip:
    def __init__(self, close_calls):
        self._close_calls = close_calls

    @property
    def duration(self):
        raise RuntimeError("FFmpeg duration probe failed")

    def close(self):
        self._close_calls.append(True)


def test_elevenlabs_closes_audio_clip_when_duration_probe_fails(tmp_path):
    close_calls = []
    output = tmp_path / "elevenlabs.mp3"

    with (
        patch.object(voice, "get_elevenlabs_api_key", return_value="test-key"),
        patch.object(voice.requests, "post", return_value=_OkResponse()),
        patch.object(
            voice,
            "AudioFileClip",
            side_effect=lambda _: _BrokenClip(close_calls),
        ),
    ):
        result = voice.elevenlabs_tts("Hello world.", "voice-id", str(output))

    assert result is None
    assert close_calls, "AudioFileClip.close() must run even if .duration raises"


def test_chatterbox_closes_audio_clip_when_duration_probe_fails(tmp_path):
    close_calls = []
    output = tmp_path / "chatterbox.mp3"

    with (
        patch.object(
            voice.config,
            "chatterbox",
            {"base_url": "http://localhost:4123", "api_key": "", "model_id": "chatterbox"},
        ),
        patch.object(voice.requests, "post", return_value=_OkResponse()),
        patch.object(
            voice,
            "AudioFileClip",
            side_effect=lambda _: _BrokenClip(close_calls),
        ),
    ):
        result = voice.chatterbox_tts("Hello world.", "default", str(output))

    assert result is None
    assert close_calls, "AudioFileClip.close() must run even if .duration raises"


def test_cli_force_utf8_console_reconfigures_both_streams():
    import cli

    stdout = SimpleNamespace(reconfigure=Mock())
    stderr = SimpleNamespace(reconfigure=Mock())

    with (
        patch.object(cli.sys, "stdout", stdout),
        patch.object(cli.sys, "stderr", stderr),
    ):
        cli._force_utf8_console()

    stdout.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")
    stderr.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")
