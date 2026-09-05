from __future__ import annotations

import ast
from pathlib import Path


PAGES = {
    "f23": Path("webui/pages/23_Voice_Studio.py"),
    "f24": Path("webui/pages/24_Audio_Mastering.py"),
    "f25": Path("webui/pages/25_Subtitle_Intelligence.py"),
}


def _source(key: str) -> str:
    return PAGES[key].read_text(encoding="utf-8")


def _tree(key: str) -> ast.AST:
    return ast.parse(_source(key))


def _called_symbols(tree: ast.AST) -> set[str]:
    called: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
    return called


def test_f23_wires_real_voice_studio_contract():
    source = _source("f23")
    called = _called_symbols(_tree("f23"))
    for marker in (
        "AstronomyVideoPlan",
        "SoundDesignPlan",
        "VoiceStudioRequest",
        "build_voice_studio",
        "model_validate",
        "Construir plan de voz",
    ):
        assert marker in source
    assert "build_voice_studio" in called


def test_f23_keeps_voice_runtime_fail_closed():
    source = _source("f23")
    for marker in (
        "plan.tts_invocations",
        "plan.network_calls",
        "plan.downloads_models",
        "plan.generates_audio",
        "utterance.exact_voice_id",
        "VOICE_SELECTION_REQUIRED",
        "No se ha sintetizado audio",
        "PENDING_PC / NOT_EXECUTED",
    ):
        assert marker in source
    forbidden = {"Communicate", "synthesize", "generate_audio", "requests", "post"}
    assert _called_symbols(_tree("f23")).isdisjoint(forbidden)


def test_f24_wires_real_audio_mastering_contract():
    source = _source("f24")
    called = _called_symbols(_tree("f24"))
    for marker in (
        "VoiceStudioPlan",
        "SoundDesignPlan",
        "AudioMasteringRequest",
        "build_audio_mastering",
        "model_validate",
        "Construir plan de mastering",
    ):
        assert marker in source
    assert "build_audio_mastering" in called


def test_f24_preserves_targets_and_zero_execution():
    source = _source("f24")
    for marker in (
        "plan.target_i_lufs",
        "plan.target_tp_dbtp",
        "plan.ffmpeg_invocations",
        "plan.modifies_audio",
        "plan.mastering_ready",
        "No se ha masterizado audio",
        "-16 LUFS",
        "-1 dBTP",
    ):
        assert marker in source
    forbidden = {"system", "Popen", "ffmpeg", "ffprobe", "check_output"}
    assert _called_symbols(_tree("f24")).isdisjoint(forbidden)


def test_f25_wires_native_timestamps_first():
    source = _source("f25")
    called = _called_symbols(_tree("f25"))
    for marker in (
        "VoiceStudioPlan",
        "NativeTimingCue",
        "SubtitleIntelligenceRequest",
        "build_subtitle_intelligence",
        "NATIVE_TTS_BOUNDARIES_FIRST",
        "WAITING_NATIVE_TTS_TIMESTAMPS",
        "Evaluar timestamps nativos",
    ):
        assert marker in source
    assert "build_subtitle_intelligence" in called
    assert "model_validate" in called


def test_f25_never_triggers_whisper_or_fabricates_timestamps():
    source = _source("f25")
    for marker in (
        "plan.whisper_triggered",
        "plan.downloads_models",
        "plan.transcribes_audio",
        "F25 no ejecuta Whisper",
        "no se fabrican timings ni SRT",
        "No se ha ejecutado Whisper ni fabricado ningún timestamp",
    ):
        assert marker in source
    forbidden = {"WhisperModel", "transcribe", "download_model", "download"}
    assert _called_symbols(_tree("f25")).isdisjoint(forbidden)


def test_batch_i_pages_are_product_safe_mobile_and_runtime_free():
    runtime_forbidden = {
        "system",
        "popen",
        "Popen",
        "check_call",
        "check_output",
        "ffmpeg",
        "ffprobe",
        "Communicate",
        "synthesize",
        "transcribe",
        "WhisperModel",
        "download",
        "post",
        "upload",
        "webhook",
        "mark_published",
        "unlink",
        "remove",
        "rmtree",
    }
    desktop_only = {"columns", "dataframe", "table"}

    for key in PAGES:
        source = _source(key)
        called = _called_symbols(_tree(key))
        assert "Detalles técnicos" in source
        assert "except Exception as exc" in source
        assert called.isdisjoint(runtime_forbidden)
        assert called.isdisjoint(desktop_only)
