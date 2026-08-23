from __future__ import annotations

import difflib
import gc
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import textwrap
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.models.astronomy_director import AstronomyVideoPlan
from app.models.material_selection import MaterialSelectionPlan
from app.services.centinela.orchestration import ResourceClass
from app.services.centinela.production_spine import (
    StageArtifact,
    StageBinding,
    StageResult,
)
from app.services.centinela.writer_room import FinalScript
from app.utils import utils

from .models import (
    R7_AV_RUNTIME_VERSION,
    AudioBundle,
    AudioSceneTiming,
    SubtitleCue,
)


QWEN_PYTHON = Path(
    r"E:\IA\Qwen3-TTS\runtime\.venv\Scripts\python.exe"
)
QWEN_ADAPTER = Path(
    r"E:\IA\Qwen3-TTS\runtime\centinela_qwen_adapter.py"
)
QWEN_MODEL = Path(
    r"E:\IA\Qwen3-TTS\models\Qwen3-TTS-12Hz-1.7B-Base"
)
QWEN_VOICE_ID = "qwen3tts:centinela-cinematico"

ALIGNMENT_MIN_RATIO = 0.82
QWEN_TIMEOUT_SECONDS = 1200
FFMPEG_TIMEOUT_SECONDS = 300


class AudioExecutionError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(
        ch for ch in normalized if not unicodedata.combining(ch)
    ).casefold()


def _tokens(value: str) -> list[str]:
    return [
        _fold(item)
        for item in re.findall(r"\w+", str(value or ""), flags=re.UNICODE)
        if item
    ]


def _latest_ref(context: Any, artifact_type: str):
    refs = context.store.list_artifacts(
        context.project_id,
        artifact_type=artifact_type,
    )
    return refs[-1] if refs else None


def _run(
    command: list[str],
    *,
    timeout: int,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(
        {
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }
    )
    if env:
        merged.update(env)
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=merged,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AudioExecutionError(
            f"process failed to execute: {command[0]}: {exc}"
        ) from exc

    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise AudioExecutionError(
            f"process exit={result.returncode}: {message[:1800]}"
        )
    return result


def _ffmpeg() -> Path:
    value = Path(utils.get_ffmpeg_binary())
    if value.is_file():
        return value
    resolved = shutil.which(str(value)) or shutil.which("ffmpeg")
    if not resolved:
        raise AudioExecutionError("FFmpeg is not available")
    return Path(resolved)


def _ffprobe(ffmpeg: Path) -> Path:
    sibling = ffmpeg.with_name(
        "ffprobe.exe" if os.name == "nt" else "ffprobe"
    )
    if sibling.is_file():
        return sibling
    resolved = shutil.which("ffprobe")
    if not resolved:
        raise AudioExecutionError("ffprobe is not available")
    return Path(resolved)


def _probe_audio(path: Path) -> dict[str, Any]:
    ffmpeg = _ffmpeg()
    probe = _run(
        [
            str(_ffprobe(ffmpeg)),
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        timeout=60,
    )
    payload = json.loads(probe.stdout or "{}")
    streams = [
        item
        for item in payload.get("streams", [])
        if item.get("codec_type") == "audio"
    ]
    if len(streams) != 1:
        raise AudioExecutionError(
            f"expected one audio stream, found {len(streams)}"
        )
    stream = streams[0]
    duration = float(
        stream.get("duration")
        or (payload.get("format") or {}).get("duration")
        or 0.0
    )
    if not math.isfinite(duration) or duration <= 0:
        raise AudioExecutionError("audio duration is invalid")
    return {
        "duration": duration,
        "sample_rate": int(stream.get("sample_rate") or 0),
        "channels": int(stream.get("channels") or 0),
        "codec": str(stream.get("codec_name") or ""),
    }


def _parse_loudnorm(stderr: str) -> dict[str, Any]:
    matches = re.findall(r"\{[\s\S]*?\}", stderr)
    for candidate in reversed(matches):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if "input_i" in value and "input_tp" in value:
            return value
    raise AudioExecutionError("FFmpeg loudnorm JSON was not found")


def _master_audio(raw_audio: Path, output: Path) -> dict[str, float]:
    ffmpeg = _ffmpeg()
    pass1 = _run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-nostats",
            "-i",
            str(raw_audio),
            "-af",
            "loudnorm=I=-16:LRA=7:TP=-1:print_format=json",
            "-f",
            "null",
            "-",
        ],
        timeout=FFMPEG_TIMEOUT_SECONDS,
    )
    measured = _parse_loudnorm(pass1.stderr)

    loudnorm = (
        "loudnorm="
        "I=-16:LRA=7:TP=-1:"
        f"measured_I={measured['input_i']}:"
        f"measured_LRA={measured['input_lra']}:"
        f"measured_TP={measured['input_tp']}:"
        f"measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:"
        "linear=true:print_format=summary"
    )
    _run(
        [
            str(ffmpeg),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(raw_audio),
            "-af",
            loudnorm,
            "-ar",
            "48000",
            "-c:a",
            "pcm_s16le",
            str(output),
        ],
        timeout=FFMPEG_TIMEOUT_SECONDS,
    )
    if not output.is_file() or output.stat().st_size <= 44:
        raise AudioExecutionError("mastering produced an invalid WAV")

    verification = _run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-nostats",
            "-i",
            str(output),
            "-af",
            "loudnorm=I=-16:LRA=7:TP=-1:print_format=json",
            "-f",
            "null",
            "-",
        ],
        timeout=FFMPEG_TIMEOUT_SECONDS,
    )
    verified = _parse_loudnorm(verification.stderr)
    integrated = float(verified["input_i"])
    true_peak = float(verified["input_tp"])
    if abs(integrated - (-16.0)) > 0.8:
        raise AudioExecutionError(
            f"master integrated loudness outside tolerance: {integrated}"
        )
    if true_peak > -0.45:
        raise AudioExecutionError(
            f"master true peak outside tolerance: {true_peak}"
        )
    return {
        "verified_i_lufs": integrated,
        "verified_tp_dbtp": true_peak,
    }


def _apply_pronunciations(
    scene_texts: list[str],
    pronunciation_map,
) -> tuple[list[str], list[str], list[str]]:
    transformed = list(scene_texts)
    applied: list[str] = []
    deferred: list[str] = []

    for entry in pronunciation_map:
        written = entry.written.strip()
        spoken = entry.spoken_es.strip()
        if not written or not spoken:
            continue
        if len(_tokens(written)) != len(_tokens(spoken)):
            deferred.append(written)
            continue

        pattern = re.compile(
            rf"(?<!\w){re.escape(written)}(?!\w)",
            flags=re.IGNORECASE,
        )
        changed = False
        candidate_scenes: list[str] = []
        for current in transformed:
            candidate, count = pattern.subn(spoken, current)
            candidate_scenes.append(candidate)
            changed = changed or count > 0

        if not changed:
            continue
        if any(
            len(_tokens(before)) != len(_tokens(after))
            for before, after in zip(
                transformed,
                candidate_scenes,
                strict=True,
            )
        ):
            deferred.append(written)
            continue

        transformed = candidate_scenes
        applied.append(written)

    return transformed, applied, deferred


def _run_qwen(
    context: Any,
    text: str,
    output_dir: Path,
) -> Path:
    for path, label in (
        (QWEN_PYTHON, "Qwen Python"),
        (QWEN_ADAPTER, "Qwen adapter"),
        (QWEN_MODEL, "Qwen model"),
    ):
        if not path.exists():
            raise AudioExecutionError(f"{label} is missing: {path}")

    text_file = output_dir / "qwen-input.txt"
    raw_audio = output_dir / "voice-raw.wav"
    stdout_file = output_dir / "qwen.stdout.txt"
    stderr_file = output_dir / "qwen.stderr.txt"
    text_file.write_text(text, encoding="utf-8", newline="\n")

    env = os.environ.copy()
    env.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }
    )

    command = [
        str(QWEN_PYTHON),
        str(QWEN_ADAPTER),
        "--text-file",
        str(text_file),
        "--output",
        str(raw_audio),
    ]

    started = time.monotonic()
    with stdout_file.open("w", encoding="utf-8") as stdout, stderr_file.open(
        "w", encoding="utf-8"
    ) as stderr:
        process = subprocess.Popen(
            command,
            cwd=QWEN_ADAPTER.parent,
            env=env,
            stdout=stdout,
            stderr=stderr,
            text=True,
            shell=False,
        )
        try:
            while process.poll() is None:
                context.check_cancelled()
                if time.monotonic() - started > QWEN_TIMEOUT_SECONDS:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise AudioExecutionError(
                        f"Qwen synthesis exceeded {QWEN_TIMEOUT_SECONDS}s"
                    )
                time.sleep(0.25)
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
            raise

    if process.returncode != 0:
        diagnostic = stderr_file.read_text(
            encoding="utf-8",
            errors="replace",
        ).strip()
        raise AudioExecutionError(
            f"Qwen synthesis failed exit={process.returncode}: "
            f"{diagnostic[-1800:]}"
        )
    if not raw_audio.is_file() or raw_audio.stat().st_size <= 44:
        raise AudioExecutionError("Qwen did not produce a valid WAV")
    return raw_audio


def _whisper_words(
    audio_file: Path,
) -> tuple[list[dict[str, float | str]], dict[str, str]]:
    import app.services.subtitle as subtitle_service

    if subtitle_service.WhisperModel is None:
        raise AudioExecutionError("faster-whisper is not installed")

    local_model = (
        Path(utils.root_dir())
        / "models"
        / f"whisper-{subtitle_service.model_size}"
    )
    if not local_model.is_dir() or not (local_model / "model.bin").is_file():
        raise AudioExecutionError(
            "local Whisper model is missing; R7 will not download it"
        )

    subtitle_service._prepare_cuda_runtime()
    model = subtitle_service.WhisperModel(
        model_size_or_path=str(local_model),
        device=subtitle_service.device,
        compute_type=subtitle_service.compute_type,
    )
    words: list[dict[str, float | str]] = []
    try:
        kwargs: dict[str, Any] = {}
        if subtitle_service.initial_prompt:
            kwargs["initial_prompt"] = subtitle_service.initial_prompt

        segments, info = model.transcribe(
            str(audio_file),
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            **kwargs,
        )
        for segment in segments:
            for word in segment.words or []:
                start = float(word.start)
                end = float(word.end)
                if (
                    math.isfinite(start)
                    and math.isfinite(end)
                    and end > start
                ):
                    words.append(
                        {
                            "start": start,
                            "end": end,
                            "word": str(word.word),
                        }
                    )
        return words, {
            "model": subtitle_service.model_size,
            "device": subtitle_service.device,
            "compute_type": subtitle_service.compute_type,
            "language": str(getattr(info, "language", "") or ""),
        }
    finally:
        try:
            inner = getattr(model, "model", None)
            if inner is not None and hasattr(inner, "unload_model"):
                inner.unload_model(to_cpu=False)
        finally:
            del model
            gc.collect()


def _expanded_whisper_tokens(
    words: list[dict[str, float | str]],
) -> tuple[list[str], list[tuple[float, float]]]:
    tokens: list[str] = []
    timings: list[tuple[float, float]] = []
    for item in words:
        normalized = _tokens(str(item["word"]))
        if not normalized:
            continue
        start = float(item["start"])
        end = float(item["end"])
        width = (end - start) / len(normalized)
        for index, token in enumerate(normalized):
            tokens.append(token)
            timings.append(
                (
                    start + index * width,
                    start + (index + 1) * width,
                )
            )
    return tokens, timings


def _align_script_tokens(
    script_tokens: list[str],
    words: list[dict[str, float | str]],
    audio_duration: float,
) -> tuple[list[tuple[float, float]], float]:
    whisper_tokens, whisper_timings = _expanded_whisper_tokens(words)
    if not script_tokens or not whisper_tokens:
        raise AudioExecutionError("subtitle alignment has no tokens")

    matcher = difflib.SequenceMatcher(
        None,
        script_tokens,
        whisper_tokens,
        autojunk=False,
    )
    mapping: dict[int, tuple[float, float]] = {}
    matched = 0
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            mapping[block.a + offset] = whisper_timings[block.b + offset]
            matched += 1

    ratio = matched / len(script_tokens)
    if ratio < ALIGNMENT_MIN_RATIO:
        raise AudioExecutionError(
            "Whisper/script alignment below threshold: "
            f"{ratio:.3f} < {ALIGNMENT_MIN_RATIO:.3f}"
        )

    output: list[tuple[float, float] | None] = [
        mapping.get(index) for index in range(len(script_tokens))
    ]

    index = 0
    while index < len(output):
        if output[index] is not None:
            index += 1
            continue
        start_index = index
        while index < len(output) and output[index] is None:
            index += 1
        end_index = index - 1
        previous = output[start_index - 1] if start_index > 0 else None
        following = output[index] if index < len(output) else None
        left = float(previous[1]) if previous is not None else 0.0
        right = (
            float(following[0])
            if following is not None
            else audio_duration
        )
        count = end_index - start_index + 1
        if right <= left:
            right = min(audio_duration, left + 0.06 * count)
        width = max(0.01, (right - left) / count)
        for offset in range(count):
            output[start_index + offset] = (
                left + offset * width,
                left + (offset + 1) * width,
            )

    normalized_output: list[tuple[float, float]] = []
    previous_end = 0.0
    for item in output:
        assert item is not None
        start = max(previous_end, min(audio_duration, float(item[0])))
        end = max(start + 0.01, min(audio_duration, float(item[1])))
        if end > audio_duration:
            end = audio_duration
            start = min(start, max(0.0, end - 0.01))
        normalized_output.append((start, end))
        previous_end = end

    return normalized_output, ratio


def _scene_ranges(
    scene_texts: list[str],
) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    cursor = 0
    for text in scene_texts:
        count = len(_tokens(text))
        if count <= 0:
            raise AudioExecutionError("scene narration has no words")
        result.append((cursor, cursor + count - 1))
        cursor += count
    return result


def _scene_timings(
    ranges: list[tuple[int, int]],
    token_timings: list[tuple[float, float]],
    audio_duration: float,
) -> list[AudioSceneTiming]:
    boundaries = [0.0]
    for left, right in zip(ranges, ranges[1:]):
        previous_end = token_timings[left[1]][1]
        next_start = token_timings[right[0]][0]
        boundary = (
            (previous_end + next_start) / 2.0
            if next_start >= previous_end
            else previous_end
        )
        boundaries.append(boundary)
    boundaries.append(audio_duration)

    result: list[AudioSceneTiming] = []
    for scene_number, ((token_start, token_end), start, end) in enumerate(
        zip(ranges, boundaries[:-1], boundaries[1:], strict=True),
        start=1,
    ):
        if end <= start:
            raise AudioExecutionError(
                f"invalid real audio timing for scene {scene_number}"
            )
        result.append(
            AudioSceneTiming(
                scene_number=scene_number,
                start_s=round(start, 4),
                end_s=round(end, 4),
                duration_s=round(end - start, 4),
                token_start=token_start,
                token_end=token_end,
            )
        )
    return result


def _timestamp(value: float) -> str:
    milliseconds = max(0, int(round(value * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def _cue_text(
    text: str,
    matches: list[re.Match[str]],
    start: int,
    end: int,
) -> str:
    begin = matches[start].start()
    if end + 1 < len(matches):
        finish = matches[end + 1].start()
    else:
        finish = len(text)
    return text[begin:finish].strip()


def _build_subtitles(
    scene_texts: list[str],
    token_timings: list[tuple[float, float]],
    ranges: list[tuple[int, int]],
    output_path: Path,
) -> list[SubtitleCue]:
    cues: list[SubtitleCue] = []
    srt_blocks: list[str] = []

    for scene_number, (text, global_range) in enumerate(
        zip(scene_texts, ranges, strict=True),
        start=1,
    ):
        matches = list(re.finditer(r"\w+", text, flags=re.UNICODE))
        local = 0
        while local < len(matches):
            maximum = min(len(matches) - 1, local + 5)
            end = maximum

            for candidate in range(maximum, local, -1):
                tail_start = matches[candidate].end()
                tail_end = (
                    matches[candidate + 1].start()
                    if candidate + 1 < len(matches)
                    else len(text)
                )
                if re.search(r"[.!?;:,…]", text[tail_start:tail_end]):
                    end = candidate
                    break

            while end > local:
                candidate_text = _cue_text(text, matches, local, end)
                wrapped = textwrap.wrap(
                    candidate_text,
                    width=32,
                    break_long_words=False,
                    break_on_hyphens=False,
                )
                if len(wrapped) <= 2:
                    break
                end -= 1

            candidate_text = _cue_text(text, matches, local, end)
            wrapped = textwrap.wrap(
                candidate_text,
                width=32,
                break_long_words=False,
                break_on_hyphens=False,
            )
            display = "\n".join(wrapped[:2]) or candidate_text

            global_start = global_range[0] + local
            global_end = global_range[0] + end
            start_s = token_timings[global_start][0]
            end_s = token_timings[global_end][1]
            if end_s <= start_s:
                end_s = start_s + 0.05

            cue = SubtitleCue(
                index=len(cues) + 1,
                scene_number=scene_number,
                start_s=round(start_s, 4),
                end_s=round(end_s, 4),
                text=display,
            )
            cues.append(cue)
            srt_blocks.append(
                f"{cue.index}\n"
                f"{_timestamp(cue.start_s)} --> {_timestamp(cue.end_s)}\n"
                f"{cue.text}\n"
            )
            local = end + 1

    output_path.write_text(
        "\n".join(srt_blocks) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise AudioExecutionError("subtitle SRT was not created")
    return cues


class AudioStageAdapter:
    def __call__(
        self,
        context: Any,
        payload: dict[str, Any],
    ) -> StageResult:
        del payload

        final_ref = _latest_ref(context, "final_script")
        scene_ref = _latest_ref(context, "scene_plan")
        material_ref = _latest_ref(context, "material_selection")
        if final_ref is None or scene_ref is None or material_ref is None:
            return StageResult.needs_input(
                "FinalScript, scene_plan and material_selection are required for AUDIO"
            )

        try:
            final_script = FinalScript.model_validate(
                context.store.read_json(
                    context.project_id,
                    final_ref.artifact_id,
                )
            )
            scene_plan = AstronomyVideoPlan.model_validate(
                context.store.read_json(
                    context.project_id,
                    scene_ref.artifact_id,
                )
            )
            materials = MaterialSelectionPlan.model_validate(
                context.store.read_json(
                    context.project_id,
                    material_ref.artifact_id,
                )
            )
        except (ValidationError, TypeError, ValueError) as exc:
            return StageResult.blocked(
                "R7 AUDIO input artifact validation failed",
                details={
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1600],
                },
            )

        if materials.unresolved_count != 0:
            return StageResult.needs_input(
                "R7 AUDIO refuses to run while media scenes are unresolved",
                details={
                    "unresolved_count": materials.unresolved_count,
                    "irrelevant_broll_substituted": False,
                },
            )
        if scene_plan.context_hash != final_script.fact_lock_hash:
            return StageResult.blocked(
                "scene plan and FinalScript scientific lineage do not match"
            )

        output_dir = (
            Path(utils.task_dir(context.job_context.job_id))
            / "r7-audio"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        original_scene_texts = [
            scene.narration for scene in scene_plan.scenes
        ]
        tts_scene_texts, applied, deferred = _apply_pronunciations(
            original_scene_texts,
            final_script.pronunciation_map,
        )
        original_ranges = _scene_ranges(original_scene_texts)
        tts_ranges = _scene_ranges(tts_scene_texts)
        if original_ranges != tts_ranges:
            return StageResult.blocked(
                "pronunciation mapping changed token counts; unsafe for subtitle alignment"
            )
        tts_text = "\n\n".join(tts_scene_texts).strip()

        context.report_progress(18, "AUDIO: Qwen3-TTS local")
        try:
            raw_audio = _run_qwen(
                context,
                tts_text,
                output_dir,
            )
            context.check_cancelled()

            context.report_progress(42, "AUDIO: mastering -16 LUFS / -1 dBTP")
            master_audio = output_dir / "voice-master.wav"
            loudness = _master_audio(raw_audio, master_audio)
            probe = _probe_audio(master_audio)
            if probe["sample_rate"] != 48000:
                raise AudioExecutionError(
                    f"master sample rate is {probe['sample_rate']}, expected 48000"
                )

            context.report_progress(58, "AUDIO: faster-whisper local alignment")
            words, whisper_info = _whisper_words(master_audio)
            script_tokens = _tokens(tts_text)
            token_timings, alignment_ratio = _align_script_tokens(
                script_tokens,
                words,
                probe["duration"],
            )
            scenes = _scene_timings(
                original_ranges,
                token_timings,
                probe["duration"],
            )

            context.report_progress(72, "AUDIO: subtitles from approved script")
            subtitle_path = output_dir / "subtitles-es.srt"
            subtitles = _build_subtitles(
                original_scene_texts,
                token_timings,
                original_ranges,
                subtitle_path,
            )
        except Exception as exc:
            return StageResult.blocked(
                "R7 local audio execution failed",
                details={
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1800],
                    "external_network_used": False,
                    "model_downloads": False,
                    "qwen_offline": True,
                },
            )

        raw_id = "r7-voice-raw-" + uuid4().hex
        master_id = "r7-voice-master-" + uuid4().hex
        subtitle_id = "r7-subtitles-" + uuid4().hex

        bundle = AudioBundle(
            subject=scene_plan.subject,
            source_plan_context_hash=scene_plan.context_hash,
            source_final_script_hash=final_script.content_hash,
            source_material_selector_version=materials.selector_version,
            qwen_runtime_python=str(QWEN_PYTHON),
            qwen_adapter=str(QWEN_ADAPTER),
            qwen_model_path=str(QWEN_MODEL),
            whisper_model=whisper_info["model"],
            whisper_device=whisper_info["device"],
            whisper_compute_type=whisper_info["compute_type"],
            alignment_ratio=round(alignment_ratio, 6),
            pronunciation_applied=applied,
            pronunciation_deferred=deferred,
            voice_raw_artifact_id=raw_id,
            voice_master_artifact_id=master_id,
            subtitle_artifact_id=subtitle_id,
            voice_raw_sha256=_sha256(raw_audio),
            voice_master_sha256=_sha256(master_audio),
            subtitle_sha256=_sha256(subtitle_path),
            duration_seconds=round(probe["duration"], 4),
            channels=probe["channels"],
            verified_i_lufs=loudness["verified_i_lufs"],
            verified_tp_dbtp=loudness["verified_tp_dbtp"],
            scene_count=len(scenes),
            scenes=scenes,
            subtitle_cue_count=len(subtitles),
            subtitles=subtitles,
            generated_at_utc=datetime.now(timezone.utc),
        )

        common_inputs = (
            final_ref.artifact_id,
            scene_ref.artifact_id,
            material_ref.artifact_id,
        )
        return StageResult.complete(
            StageArtifact(
                artifact_type="voice_raw",
                source_path=str(raw_audio),
                suffix=".wav",
                artifact_id=raw_id,
                input_artifact_ids=common_inputs,
                provenance={
                    "av_runtime_version": R7_AV_RUNTIME_VERSION,
                    "tts_backend": "QWEN3_TTS_LOCAL",
                    "qwen_offline": True,
                    "weights_license": "NO_VERIFICADA",
                },
                metadata={
                    "duration_seconds": probe["duration"],
                    "mastered": False,
                },
            ),
            StageArtifact(
                artifact_type="voice_master",
                source_path=str(master_audio),
                suffix=".wav",
                artifact_id=master_id,
                input_artifact_ids=common_inputs,
                provenance={
                    "av_runtime_version": R7_AV_RUNTIME_VERSION,
                    "normalization": "FFMPEG_LOUDNORM_TWO_PASS",
                },
                metadata={
                    "target_i_lufs": -16.0,
                    "target_tp_dbtp": -1.0,
                    "sample_rate_hz": 48000,
                },
            ),
            StageArtifact(
                artifact_type="subtitle_srt",
                source_path=str(subtitle_path),
                suffix=".srt",
                artifact_id=subtitle_id,
                input_artifact_ids=common_inputs,
                provenance={
                    "av_runtime_version": R7_AV_RUNTIME_VERSION,
                    "timestamp_method": "FASTER_WHISPER_SCRIPT_ALIGNED",
                    "subtitle_text_authority": "APPROVED_SCRIPT",
                },
                metadata={
                    "cue_count": len(subtitles),
                    "alignment_ratio": alignment_ratio,
                    "language": "es-ES",
                },
            ),
            StageArtifact(
                artifact_type="audio_bundle",
                payload=bundle.model_dump(mode="json"),
                input_artifact_ids=(
                    raw_id,
                    master_id,
                    subtitle_id,
                    *common_inputs,
                ),
                provenance={
                    "av_runtime_version": R7_AV_RUNTIME_VERSION,
                    "qwen_offline": True,
                    "model_downloads": False,
                    "external_network_used": False,
                },
                metadata={
                    "duration_seconds": bundle.duration_seconds,
                    "scene_count": bundle.scene_count,
                    "subtitle_cue_count": bundle.subtitle_cue_count,
                    "alignment_ratio": bundle.alignment_ratio,
                    "auto_publication": False,
                },
            ),
            message="R7 generated local voice, mastered audio and aligned subtitles",
            details={
                "duration_seconds": bundle.duration_seconds,
                "alignment_ratio": bundle.alignment_ratio,
                "qwen_native_timestamps": False,
                "timestamp_method": bundle.timestamp_method,
                "model_downloads": False,
                "external_network_used": False,
                "auto_publication": False,
            },
        )


def build_audio_stage_binding() -> StageBinding:
    return StageBinding(
        adapter_id="r7_audio_executor_v01",
        handler=AudioStageAdapter(),
        resource_class=ResourceClass.HEAVY,
        producer_version=R7_AV_RUNTIME_VERSION,
        invokes_network=False,
        invokes_llm=False,
        invokes_render=True,
        auto_publication=False,
    )
