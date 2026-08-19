import gc
import json
import os.path
import re
from timeit import default_timer as timer

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None
from loguru import logger

from app.config import config
from app.utils import utils

model_size = config.whisper.get("model_size", "large-v3")
device = config.whisper.get("device", "cpu")
compute_type = config.whisper.get("compute_type", "int8")
initial_prompt = config.whisper.get("initial_prompt", "") or None
cuda_dll_dir = config.whisper.get("cuda_dll_dir", "") or ""
model = None
_cuda_dll_handle = None


def _prepare_cuda_runtime():
    """Expose an optional Windows CUDA/cuDNN runtime only to this process."""
    global _cuda_dll_handle

    if device != "cuda" or os.name != "nt" or not cuda_dll_dir:
        return

    dll_dir = os.path.abspath(
        os.path.expandvars(
            os.path.expanduser(str(cuda_dll_dir))
        )
    )

    if not os.path.isdir(dll_dir):
        raise RuntimeError(
            f"Whisper CUDA DLL directory does not exist: {dll_dir}"
        )

    current_path = os.environ.get("PATH", "")
    path_items = [
        item.strip().lower()
        for item in current_path.split(os.pathsep)
        if item.strip()
    ]

    if dll_dir.lower() not in path_items:
        os.environ["PATH"] = (
            dll_dir
            + os.pathsep
            + current_path
        )

    if hasattr(os, "add_dll_directory") and _cuda_dll_handle is None:
        _cuda_dll_handle = os.add_dll_directory(dll_dir)

    logger.info(
        f"Whisper CUDA runtime directory enabled: {dll_dir}"
    )



def release_model():
    """
    Release the global faster-whisper / CTranslate2 model.

    This project runs Qwen3-TTS and Whisper sequentially on a
    6 GB RTX 2060, so Whisper must not remain resident between tasks.
    """
    global model

    if model is None:
        return

    try:
        ct2_model = getattr(model, "model", None)

        if (
            ct2_model is not None
            and hasattr(ct2_model, "unload_model")
        ):
            ct2_model.unload_model(to_cpu=False)

    except Exception as exc:
        logger.warning(
            f"failed to explicitly unload Whisper model: {exc}"
        )

    finally:
        model = None
        gc.collect()
        logger.info("Whisper model released")



def create(audio_file, subtitle_file: str = "", video_script: str = ""):
    global model
    if WhisperModel is None:
        logger.warning("faster_whisper not available, skipping whisper subtitle generation")
        return ""
    if not model:
        model_path = f"{utils.root_dir()}/models/whisper-{model_size}"
        model_bin_file = f"{model_path}/model.bin"
        if not os.path.isdir(model_path) or not os.path.isfile(model_bin_file):
            model_path = model_size

        logger.info(
            f"loading model: {model_path}, device: {device}, compute_type: {compute_type}"
        )
        try:
            _prepare_cuda_runtime()
            model = WhisperModel(
                model_size_or_path=model_path, device=device, compute_type=compute_type
            )
        except Exception as e:
            logger.error(
                f"failed to load model: {e} \n\n"
                f"********************************************\n"
                f"this may be caused by network issue. \n"
                f"please download the model manually and put it in the 'models' folder. \n"
                f"see [README.md FAQ](https://github.com/harry0703/MoneyPrinterTurbo) for more details.\n"
                f"********************************************\n\n"
            )
            return None

    logger.info(f"start, output file: {subtitle_file}")
    if not subtitle_file:
        subtitle_file = f"{audio_file}.srt"

    segments, info = model.transcribe(
        audio_file,
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        **({"initial_prompt": initial_prompt} if initial_prompt else {}),
    )

    logger.info(
        f"detected language: '{info.language}', probability: {info.language_probability:.2f}"
    )

    start = timer()
    subtitles = []
    word_items = []

    def recognized(seg_text, seg_start, seg_end):
        seg_text = seg_text.strip()
        if not seg_text:
            return

        msg = "[%.2fs -> %.2fs] %s" % (seg_start, seg_end, seg_text)
        logger.debug(msg)

        subtitles.append(
            {"msg": seg_text, "start_time": seg_start, "end_time": seg_end}
        )

    for segment in segments:
        words_idx = 0
        words_len = len(segment.words)

        seg_start = 0
        seg_end = 0
        seg_text = ""

        if segment.words:
            is_segmented = False
            for word in segment.words:
                word_items.append(
                    {
                        "start": float(word.start),
                        "end": float(word.end),
                        "word": str(word.word),
                    }
                )

                if not is_segmented:
                    seg_start = word.start
                    is_segmented = True

                seg_end = word.end
                # If it contains punctuation, then break the sentence.
                seg_text += word.word

                if utils.str_contains_punctuation(word.word):
                    # remove last char
                    seg_text = seg_text[:-1]
                    if not seg_text:
                        continue

                    recognized(seg_text, seg_start, seg_end)

                    is_segmented = False
                    seg_text = ""

                if words_idx == 0 and segment.start < word.start:
                    seg_start = word.start
                if words_idx == (words_len - 1) and segment.end > word.end:
                    seg_end = word.end
                words_idx += 1

        if not seg_text:
            continue

        recognized(seg_text, seg_start, seg_end)

    end = timer()

    diff = end - start
    logger.info(f"complete, elapsed: {diff:.2f} s")

    idx = 1
    lines = []
    for subtitle in subtitles:
        text = subtitle.get("msg")
        if text:
            lines.append(
                utils.text_to_srt(
                    idx, text, subtitle.get("start_time"), subtitle.get("end_time")
                )
            )
            idx += 1

    sub = "\n".join(lines) + "\n"
    with open(subtitle_file, "w", encoding="utf-8") as f:
        f.write(sub)
    logger.info(f"subtitle file created: {subtitle_file}")

    social_enabled = bool(
        config.whisper.get("social_subtitles", False)
    )

    if social_enabled and video_script:
        try:
            max_words = int(
                config.whisper.get(
                    "social_max_words",
                    8,
                )
            )

            min_words = int(
                config.whisper.get(
                    "social_min_words",
                    2,
                )
            )
        except (TypeError, ValueError):
            max_words = 8
            min_words = 2

        max_words = max(3, max_words)
        min_words = max(
            1,
            min(
                min_words,
                max_words - 1,
            ),
        )

        social_created = create_social_subtitle_from_words(
            video_script=video_script,
            word_items=word_items,
            subtitle_file=subtitle_file,
            max_words=max_words,
            min_words=min_words,
        )

        if social_created:
            logger.info(
                "social subtitle segmentation accepted"
            )
            return True

        logger.warning(
            "social subtitle segmentation rejected; "
            "keeping standard Whisper SRT for legacy correction"
        )

    return False


def file_to_subtitles(filename):
    if not filename or not os.path.isfile(filename):
        return []

    times_texts = []
    current_times = None
    current_text = ""
    index = 0
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            times = re.findall("([0-9]*:[0-9]*:[0-9]*,[0-9]*)", line)
            if times:
                current_times = line
            elif line.strip() == "" and current_times:
                index += 1
                times_texts.append((index, current_times.strip(), current_text.strip()))
                current_times, current_text = None, ""
            elif current_times:
                current_text += line

    # Flush the final block. SRT files whose last subtitle is not followed by a
    # trailing blank line never hit the blank-line branch above, so without this
    # the last subtitle would be silently dropped.
    if current_times:
        index += 1
        times_texts.append((index, current_times.strip(), current_text.strip()))
    return times_texts



def _social_normalize_tokens(text):
    """Return normalized Unicode word tokens for strict subtitle alignment."""
    return re.findall(
        r"\w+",
        str(text or "").casefold(),
        flags=re.UNICODE,
    )


def create_social_subtitle_from_words(
    video_script,
    word_items,
    subtitle_file,
    max_words=8,
    min_words=2,
):
    """
    Build short social-video subtitles from an approved script and
    Whisper word timestamps.

    Safety rule:
    if Whisper words do not align exactly with the approved script
    after case/punctuation normalization, return False and leave the
    normal MPT subtitle workflow available as fallback.
    """
    script = str(video_script or "").strip()

    if not script or not word_items:
        logger.warning(
            "social subtitle segmentation skipped: "
            "missing script or Whisper words"
        )
        return False

    script_matches = list(
        re.finditer(
            r"\w+",
            script,
            flags=re.UNICODE,
        )
    )

    script_tokens = [
        match.group(0).casefold()
        for match in script_matches
    ]

    whisper_tokens = []
    normalized_words = []

    for item in word_items:
        try:
            start = float(item["start"])
            end = float(item["end"])
            raw_word = str(item["word"])
        except (KeyError, TypeError, ValueError):
            logger.warning(
                "social subtitle segmentation skipped: "
                f"invalid Whisper word item: {item!r}"
            )
            return False

        tokens = _social_normalize_tokens(raw_word)

        if len(tokens) != 1:
            logger.warning(
                "social subtitle segmentation skipped: "
                f"cannot normalize Whisper word: {raw_word!r}"
            )
            return False

        whisper_tokens.append(tokens[0])

        normalized_words.append(
            {
                "start": start,
                "end": end,
                "word": raw_word,
            }
        )

    if script_tokens != whisper_tokens:
        logger.warning(
            "social subtitle segmentation skipped: "
            "approved script and Whisper words do not align exactly "
            f"(script={len(script_tokens)} words, "
            f"whisper={len(whisper_tokens)} words)"
        )
        return False

    def text_after_word(index):
        start = script_matches[index].end()

        if index + 1 < len(script_matches):
            end = script_matches[index + 1].start()
        else:
            end = len(script)

        return script[start:end]

    def piece_text(start_index, end_index):
        start = script_matches[start_index].start()

        if end_index + 1 < len(script_matches):
            end = script_matches[end_index + 1].start()
        else:
            end = len(script)

        return script[start:end].strip()

    # Hard linguistic boundaries: sentence/major-clause punctuation.
    sentence_ranges = []
    sentence_start = 0

    for index in range(len(script_matches)):
        trailing = text_after_word(index)

        if (
            re.search(r"[.!?;:…]", trailing)
            or index == len(script_matches) - 1
        ):
            sentence_ranges.append(
                (sentence_start, index)
            )
            sentence_start = index + 1

    preferred_single = {
        "y": 8,
        "pero": 8,
        "aunque": 8,
        "porque": 8,
        "cuando": 6,
        "como": 7,
        "durante": 7,
        "mediante": 8,
    }

    preferred_phrases = {
        ("que", "cuando"): 10,
        ("de", "cómo"): 10,
        ("en", "la", "forma"): 10,
        ("para", "que"): 9,
    }

    # Words that should normally not be stranded at the end of a card.
    hanging_endings = {
        "el", "la", "los", "las",
        "un", "una", "unos", "unas",
        "de", "del",
        "a", "al",
        "en", "con", "sin",
        "por", "para",
        "y", "o",
        "que", "como",
        "mediante", "durante",
    }

    def cut_score(start_index, end_index, sentence_end):
        word_count = end_index - start_index + 1

        duration = (
            normalized_words[end_index]["end"]
            - normalized_words[start_index]["start"]
        )

        chars = len(
            piece_text(
                start_index,
                end_index,
            )
        )

        score = 0.0

        # Prefer compact cards around 5-6 words and ~1.7 seconds.
        score -= abs(word_count - 5.5) * 1.2
        score -= abs(duration - 1.7) * 1.4

        # Penalize visually/temporally dense cards.
        if duration > 2.4:
            score -= (duration - 2.4) * 10

        if chars > 44:
            score -= (chars - 44) * 0.6

        if end_index == sentence_end:
            score += 4

        trailing = text_after_word(end_index)

        # Strong preference for punctuation boundaries.
        if "," in trailing:
            score += 12

        if re.search(r"[;:]", trailing):
            score += 14

        if end_index + 1 <= sentence_end:
            next_token = script_tokens[end_index + 1]

            score += preferred_single.get(
                next_token,
                0,
            )

            for phrase, value in preferred_phrases.items():
                candidate = tuple(
                    script_tokens[
                        end_index + 1:
                        end_index + 1 + len(phrase)
                    ]
                )

                if candidate == phrase:
                    score += value

            gap = (
                normalized_words[end_index + 1]["start"]
                - normalized_words[end_index]["end"]
            )

            if gap >= 0.12:
                score += min(
                    6,
                    gap * 20,
                )

        if script_tokens[end_index] in hanging_endings:
            score -= 15

        return score

    chunks = []

    for sentence_start, sentence_end in sentence_ranges:
        current = sentence_start

        while current <= sentence_end:
            remaining = sentence_end - current + 1

            duration = (
                normalized_words[sentence_end]["end"]
                - normalized_words[current]["start"]
            )

            chars = len(
                piece_text(
                    current,
                    sentence_end,
                )
            )

            # Short, compact remainder: leave it intact.
            if (
                remaining <= max_words
                and duration <= 2.4
                and chars <= 36
            ):
                chunks.append(
                    (current, sentence_end)
                )
                break

            maximum_end = min(
                sentence_end,
                current + max_words - 1,
            )

            candidates = []

            first_candidate = (
                current + min_words - 1
            )

            for candidate_end in range(
                first_candidate,
                maximum_end + 1,
            ):
                words_left = (
                    sentence_end - candidate_end
                )

                # Avoid leaving a useless 1-word tail.
                if (
                    words_left
                    and words_left < min_words
                ):
                    continue

                candidates.append(
                    (
                        cut_score(
                            current,
                            candidate_end,
                            sentence_end,
                        ),
                        candidate_end,
                    )
                )

            if candidates:
                _, chosen_end = max(
                    candidates,
                    key=lambda item: (
                        item[0],
                        item[1],
                    ),
                )
            else:
                chosen_end = maximum_end

            chunks.append(
                (current, chosen_end)
            )

            current = chosen_end + 1

    lines = []

    for index, (start_index, end_index) in enumerate(
        chunks,
        start=1,
    ):
        text_piece = piece_text(
            start_index,
            end_index,
        )

        start_time = normalized_words[
            start_index
        ]["start"]

        end_time = normalized_words[
            end_index
        ]["end"]

        lines.append(
            utils.text_to_srt(
                index,
                text_piece,
                start_time,
                end_time,
            )
        )

    subtitle_text = "\n".join(lines) + "\n"

    with open(
        subtitle_file,
        "w",
        encoding="utf-8",
    ) as file:
        file.write(subtitle_text)

    logger.info(
        "social subtitle segmentation created "
        f"{len(chunks)} cards from "
        f"{len(normalized_words)} aligned words"
    )

    return True


def levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def similarity(a, b):
    distance = levenshtein_distance(a.lower(), b.lower())
    max_length = max(len(a), len(b))
    return 1 - (distance / max_length)


def correct(subtitle_file, video_script):
    subtitle_items = file_to_subtitles(subtitle_file)
    normalized_script = utils.normalize_script_for_subtitle_matching(video_script)
    script_lines = utils.split_string_by_punctuations(normalized_script)

    corrected = False
    new_subtitle_items = []
    script_index = 0
    subtitle_index = 0

    while script_index < len(script_lines) and subtitle_index < len(subtitle_items):
        script_line = script_lines[script_index].strip()
        subtitle_line = subtitle_items[subtitle_index][2].strip()

        if script_line == subtitle_line:
            new_subtitle_items.append(subtitle_items[subtitle_index])
            script_index += 1
            subtitle_index += 1
        else:
            combined_subtitle = subtitle_line
            start_time = subtitle_items[subtitle_index][1].split(" --> ")[0]
            end_time = subtitle_items[subtitle_index][1].split(" --> ")[1]
            next_subtitle_index = subtitle_index + 1

            while next_subtitle_index < len(subtitle_items):
                next_subtitle = subtitle_items[next_subtitle_index][2].strip()
                if similarity(
                    script_line, combined_subtitle + " " + next_subtitle
                ) > similarity(script_line, combined_subtitle):
                    combined_subtitle += " " + next_subtitle
                    end_time = subtitle_items[next_subtitle_index][1].split(" --> ")[1]
                    next_subtitle_index += 1
                else:
                    break

            if similarity(script_line, combined_subtitle) > 0.8:
                logger.warning(
                    f"Merged/Corrected - Script: {script_line}, Subtitle: {combined_subtitle}"
                )
                new_subtitle_items.append(
                    (
                        len(new_subtitle_items) + 1,
                        f"{start_time} --> {end_time}",
                        script_line,
                    )
                )
                corrected = True
            else:
                logger.warning(
                    f"Mismatch - Script: {script_line}, Subtitle: {combined_subtitle}"
                )
                new_subtitle_items.append(
                    (
                        len(new_subtitle_items) + 1,
                        f"{start_time} --> {end_time}",
                        script_line,
                    )
                )
                corrected = True

            script_index += 1
            subtitle_index = next_subtitle_index

    # Process the remaining lines of the script.
    while script_index < len(script_lines):
        logger.warning(f"Extra script line: {script_lines[script_index]}")
        if subtitle_index < len(subtitle_items):
            new_subtitle_items.append(
                (
                    len(new_subtitle_items) + 1,
                    subtitle_items[subtitle_index][1],
                    script_lines[script_index],
                )
            )
            subtitle_index += 1
        else:
            new_subtitle_items.append(
                (
                    len(new_subtitle_items) + 1,
                    "00:00:00,000 --> 00:00:00,000",
                    script_lines[script_index],
                )
            )
        script_index += 1
        corrected = True

    if corrected:
        with open(subtitle_file, "w", encoding="utf-8") as fd:
            for i, item in enumerate(new_subtitle_items):
                fd.write(f"{i + 1}\n{item[1]}\n{item[2]}\n\n")
        logger.info("Subtitle corrected")
    else:
        logger.success("Subtitle is correct")


if __name__ == "__main__":
    task_id = "c12fd1e6-4b0a-4d65-a075-c87abe35a072"
    task_dir = utils.task_dir(task_id)
    subtitle_file = f"{task_dir}/subtitle.srt"
    audio_file = f"{task_dir}/audio.mp3"

    subtitles = file_to_subtitles(subtitle_file)
    print(subtitles)

    script_file = f"{task_dir}/script.json"
    with open(script_file, "r") as f:
        script_content = f.read()
    s = json.loads(script_content)
    script = s.get("script")

    correct(subtitle_file, script)

    subtitle_file = f"{task_dir}/subtitle-test.srt"
    create(audio_file, subtitle_file)
