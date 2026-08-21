from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from loguru import logger

from app.config import config


_DEFAULT_PYTHON = (
    r"E:\IA\SemanticMatcher\venv\Scripts\python.exe"
)

_DEFAULT_SCRIPT = (
    r"E:\IA\SemanticMatcher\matcher.py"
)

_DEFAULT_MODEL_DIR = (
    r"E:\IA\SemanticMatcher\model"
)

_DEFAULT_TIMEOUT_SECONDS = 600

_DEFAULT_MAX_SEGMENTS = 8

_DEFAULT_SAMPLE_FRACTIONS = (
    0.20,
    0.50,
    0.80,
)


@dataclass(
    frozen=True
)
class SemanticMatchOutcome:
    video_paths: tuple[str, ...]
    queries: tuple[str, ...] = ()
    matches: tuple[dict, ...] = ()
    method: str = "disabled"
    elapsed_seconds: float = 0.0
    error: str = ""

    @property
    def analyzed(
        self,
    ) -> bool:
        return self.method.startswith(
            "siglip2"
        )


def _app_value(
    name: str,
    default,
):
    app_config = getattr(
        config,
        "app",
        {},
    )

    getter = getattr(
        app_config,
        "get",
        None,
    )

    if callable(
        getter
    ):
        return getter(
            name,
            default,
        )

    return default


def _bool_value(
    value,
) -> bool:
    if isinstance(
        value,
        str,
    ):
        return (
            value.strip().lower()
            in {
                "1",
                "true",
                "yes",
                "on",
            }
        )

    return bool(
        value
    )


def is_enabled() -> bool:
    return _bool_value(
        _app_value(
            "semantic_matcher_enabled",
            False,
        )
    )


def _normalized_terms(
    video_terms,
) -> list[str]:
    if isinstance(
        video_terms,
        str,
    ):
        raw_terms = re.split(
            r"[,，]",
            video_terms,
        )

    elif isinstance(
        video_terms,
        Sequence,
    ):
        raw_terms = video_terms

    else:
        return []

    result = []

    for raw in raw_terms:
        value = str(
            raw
        ).strip()

        if (
            value
            and value not in result
        ):
            result.append(
                value
            )

    return result


def _split_script(
    video_script: str,
) -> list[str]:
    script = str(
        video_script
        or ""
    ).strip()

    if not script:
        return []

    pieces = re.split(
        r"(?<=[.!?。！？])\s+|[\r\n]+",
        script,
    )

    pieces = [
        piece.strip()
        for piece in pieces
        if len(
            piece.strip()
        ) >= 4
    ]

    if len(
        pieces
    ) <= 1:
        pieces = [
            piece.strip()
            for piece in re.split(
                r"[,，;；:：]+",
                script,
            )
            if len(
                piece.strip()
            ) >= 4
        ]

    return pieces


def _group_segments(
    segments: list[str],
    target_count: int,
) -> list[str]:
    if (
        not segments
        or target_count <= 0
    ):
        return []

    if len(
        segments
    ) <= target_count:
        return list(
            segments
        )

    result = []

    total = len(
        segments
    )

    for index in range(
        target_count
    ):
        start = round(
            index
            * total
            / target_count
        )

        end = round(
            (
                index
                + 1
            )
            * total
            / target_count
        )

        value = " ".join(
            segments[
                start:end
            ]
        ).strip()

        if value:
            result.append(
                value
            )

    return result


def build_semantic_queries(
    video_script: str,
    video_terms,
    candidate_count: int,
    max_segments: int | None = None,
) -> list[str]:
    if candidate_count <= 0:
        return []

    if max_segments is None:
        max_segments = int(
            _app_value(
                "semantic_matcher_max_segments",
                _DEFAULT_MAX_SEGMENTS,
            )
        )

    target_count = min(
        candidate_count,
        max(
            1,
            int(
                max_segments
            ),
        ),
    )

    queries = _group_segments(
        _split_script(
            video_script
        ),
        target_count,
    )

    for term in _normalized_terms(
        video_terms
    ):
        if len(
            queries
        ) >= target_count:
            break

        if term not in queries:
            queries.append(
                term
            )

    return queries[
        :target_count
    ]


def _fallback(
    video_paths,
    *,
    method: str,
    error: str = "",
    elapsed_seconds: float = 0.0,
) -> SemanticMatchOutcome:
    return SemanticMatchOutcome(
        video_paths=tuple(
            str(path)
            for path in video_paths
        ),
        method=method,
        elapsed_seconds=float(
            elapsed_seconds
        ),
        error=str(
            error
            or ""
        ),
    )


def reorder_videos_for_script(
    *,
    video_script: str,
    video_terms,
    video_paths,
) -> SemanticMatchOutcome:
    original_paths = [
        str(path)
        for path in (
            video_paths
            or []
        )
    ]

    if not is_enabled():
        return _fallback(
            original_paths,
            method="disabled",
        )

    if len(
        original_paths
    ) < 2:
        return _fallback(
            original_paths,
            method="not_enough_candidates",
        )

    queries = build_semantic_queries(
        video_script=video_script,
        video_terms=video_terms,
        candidate_count=len(
            original_paths
        ),
    )

    if not queries:
        return _fallback(
            original_paths,
            method="no_queries",
        )

    python_executable = str(
        _app_value(
            "semantic_matcher_python",
            _DEFAULT_PYTHON,
        )
        or _DEFAULT_PYTHON
    )

    sidecar_script = str(
        _app_value(
            "semantic_matcher_script",
            _DEFAULT_SCRIPT,
        )
        or _DEFAULT_SCRIPT
    )

    model_dir = str(
        _app_value(
            "semantic_matcher_model_dir",
            _DEFAULT_MODEL_DIR,
        )
        or _DEFAULT_MODEL_DIR
    )

    timeout_seconds = max(
        10,
        int(
            _app_value(
                "semantic_matcher_timeout_seconds",
                _DEFAULT_TIMEOUT_SECONDS,
            )
        ),
    )

    sample_fractions = _app_value(
        "semantic_matcher_sample_fractions",
        list(
            _DEFAULT_SAMPLE_FRACTIONS
        ),
    )

    if not Path(
        python_executable
    ).is_file():
        return _fallback(
            original_paths,
            method="runtime_missing",
            error=(
                "semantic matcher Python missing: "
                f"{python_executable}"
            ),
        )

    if not Path(
        sidecar_script
    ).is_file():
        return _fallback(
            original_paths,
            method="runtime_missing",
            error=(
                "semantic matcher script missing: "
                f"{sidecar_script}"
            ),
        )

    if not Path(
        model_dir
    ).is_dir():
        return _fallback(
            original_paths,
            method="runtime_missing",
            error=(
                "semantic matcher model missing: "
                f"{model_dir}"
            ),
        )

    resolved_original = [
        str(
            Path(path).resolve()
        )
        for path in original_paths
    ]

    request = {
        "model_dir":
            model_dir,

        "queries":
            queries,

        "video_paths":
            resolved_original,

        "sample_fractions":
            [
                float(value)
                for value in sample_fractions
            ],

        "unique_assignment":
            True,
    }

    started = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory(
            prefix="mpt-semantic-"
        ) as temporary:
            temporary = Path(
                temporary
            )

            request_path = (
                temporary
                / "request.json"
            )

            output_path = (
                temporary
                / "result.json"
            )

            request_path.write_text(
                json.dumps(
                    request,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            environment = os.environ.copy()

            environment[
                "HF_HUB_OFFLINE"
            ] = "1"

            environment[
                "TRANSFORMERS_OFFLINE"
            ] = "1"

            environment[
                "PYTHONNOUSERSITE"
            ] = "1"

            process = subprocess.run(
                [
                    python_executable,
                    sidecar_script,
                    "--request",
                    str(
                        request_path
                    ),
                    "--output",
                    str(
                        output_path
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                env=environment,
            )

            if process.returncode != 0:
                raise RuntimeError(
                    "sidecar exit "
                    f"{process.returncode}: "
                    f"{process.stderr.strip()}"
                )

            if not output_path.is_file():
                raise RuntimeError(
                    "sidecar result JSON missing"
                )

            result = json.loads(
                output_path.read_text(
                    encoding="utf-8"
                )
            )

    except Exception as exc:
        elapsed = (
            time.perf_counter()
            - started
        )

        logger.warning(
            "semantic matching failed; "
            "preserving original order: "
            f"{type(exc).__name__}: {exc}"
        )

        return _fallback(
            original_paths,
            method="fallback_original_order",
            error=(
                f"{type(exc).__name__}: {exc}"
            ),
            elapsed_seconds=elapsed,
        )

    elapsed = (
        time.perf_counter()
        - started
    )

    ordered_paths = [
        str(value)
        for value in result.get(
            "ordered_paths",
            [],
        )
    ]

    if (
        len(
            ordered_paths
        )
        != len(
            resolved_original
        )
        or Counter(
            ordered_paths
        )
        != Counter(
            resolved_original
        )
    ):
        return _fallback(
            original_paths,
            method="fallback_invalid_result",
            error="invalid ordered_paths",
            elapsed_seconds=elapsed,
        )

    matches = result.get(
        "matches",
        []
    )

    if not isinstance(
        matches,
        list,
    ):
        matches = []

    method = str(
        result.get(
            "method",
            "siglip2_unknown",
        )
    )

    logger.info(
        "semantic clip matching completed, "
        f"queries: {len(queries)}, "
        f"clips: {len(original_paths)}, "
        f"method: {method}, "
        f"elapsed: {elapsed:.2f}s"
    )

    return SemanticMatchOutcome(
        video_paths=tuple(
            ordered_paths
        ),
        queries=tuple(
            queries
        ),
        matches=tuple(
            dict(item)
            for item in matches
            if isinstance(
                item,
                dict,
            )
        ),
        method=method,
        elapsed_seconds=elapsed,
    )
