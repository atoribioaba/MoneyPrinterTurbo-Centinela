from types import SimpleNamespace
from unittest.mock import patch

from app.models.schema import VideoParams
from app.services import task as task_service
from app.services import voice as voice_service


def test_generated_tts_uses_written_audio_file_duration(tmp_path):
    params = VideoParams(
        video_subject="audio timing",
        video_script="",
        voice_name="test-voice",
    )
    sub_maker = SimpleNamespace()
    audio_path = str(tmp_path / "audio.mp3")

    def fake_duration(target):
        return 8.4 if isinstance(target, str) else 7.1

    with (
        patch.object(task_service, "resolve_custom_audio_file", return_value=None),
        patch.object(task_service, "_resolve_reusable_voice_preview", return_value=None),
        patch.object(task_service.utils, "task_dir", return_value=str(tmp_path)),
        patch.object(task_service.voice, "tts", return_value=sub_maker),
        patch.object(
            task_service.voice,
            "get_audio_duration",
            side_effect=fake_duration,
        ) as get_duration,
    ):
        generated_file, duration, generated_sub_maker = task_service.generate_audio(
            "timing-test", params, "Short astronomy narration"
        )

    assert generated_file == audio_path
    assert duration == 9
    assert generated_sub_maker is sub_maker
    assert len(get_duration.call_args_list) == 1
    assert get_duration.call_args_list[0].args[0] == audio_path


def test_generated_tts_falls_back_to_submaker_when_file_duration_unreadable(tmp_path):
    params = VideoParams(
        video_subject="audio timing",
        video_script="",
        voice_name="test-voice",
    )
    sub_maker = SimpleNamespace()

    def fake_duration(target):
        return 0.0 if isinstance(target, str) else 7.1

    with (
        patch.object(task_service, "resolve_custom_audio_file", return_value=None),
        patch.object(task_service, "_resolve_reusable_voice_preview", return_value=None),
        patch.object(task_service.utils, "task_dir", return_value=str(tmp_path)),
        patch.object(task_service.voice, "tts", return_value=sub_maker),
        patch.object(task_service.voice, "get_audio_duration", side_effect=fake_duration),
    ):
        _, duration, _ = task_service.generate_audio(
            "timing-fallback", params, "Short astronomy narration"
        )

    assert duration == 8


def test_siliconflow_timeline_reaches_exact_audio_end(tmp_path):
    audio_duration = 7.3
    expected_end = int(audio_duration * 10_000_000)
    fake_response = SimpleNamespace(status_code=200, content=b"fake-mp3")
    fake_clip = SimpleNamespace(duration=audio_duration, close=lambda: None)

    with (
        patch.object(voice_service.requests, "post", return_value=fake_response),
        patch.object(voice_service, "AudioFileClip", return_value=fake_clip),
        patch.object(voice_service.config, "siliconflow", {"api_key": "test-key"}),
    ):
        result = voice_service.siliconflow_tts(
            text="First sentence. Second sentence. Third sentence. Fourth sentence.",
            model="FunAudioLLM/CosyVoice2-0.5B",
            voice="FunAudioLLM/CosyVoice2-0.5B:alex",
            voice_rate=1.0,
            voice_file=str(tmp_path / "siliconflow.mp3"),
        )

    assert result is not None
    offsets = getattr(result, "offset", [])
    assert len(offsets) > 1
    assert offsets[-1][1] == expected_end
