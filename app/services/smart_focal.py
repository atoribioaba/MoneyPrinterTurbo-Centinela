from collections.abc import Sequence
from dataclasses import dataclass
import math

import numpy as np


_FALLBACK_FOCAL_X = 0.5
_FALLBACK_FOCAL_Y = 0.5
_FALLBACK_CONFIDENCE = 0.0
_FALLBACK_METHOD = "fallback_center"


@dataclass(frozen=True)
class FocalDecision:
    """
    Result of focal-point selection for one source subclip.

    Coordinates are normalized to the source frame:
    x: 0.0=left, 0.5=center, 1.0=right
    y: 0.0=top,  0.5=center, 1.0=bottom
    """

    focal_x: float
    focal_y: float
    confidence: float
    method: str

    def __post_init__(self):
        if not 0.0 <= self.focal_x <= 1.0:
            raise ValueError(
                "focal_x must be between 0.0 and 1.0"
            )

        if not 0.0 <= self.focal_y <= 1.0:
            raise ValueError(
                "focal_y must be between 0.0 and 1.0"
            )

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "confidence must be between 0.0 and 1.0"
            )

        if not self.method:
            raise ValueError(
                "method must not be empty"
            )


def _normalize_component(
    component: np.ndarray,
) -> np.ndarray:
    """
    Normalize a spatial score to [0, 1].

    A spatially uniform component carries no useful information for
    reframing and therefore becomes an all-zero map.
    """

    component = np.asarray(
        component,
        dtype=np.float32,
    )

    minimum = float(component.min())
    maximum = float(component.max())
    span = maximum - minimum

    if span <= 1e-6:
        return np.zeros_like(
            component,
            dtype=np.float32,
        )

    return (
        (component - minimum)
        / span
    ).astype(
        np.float32,
        copy=False,
    )


def _rgb_luminance(
    frame: np.ndarray,
) -> np.ndarray:
    """
    Convert an RGB MoviePy-style frame to normalized luminance [0, 1].
    """

    frame = np.asarray(frame)

    if (
        frame.ndim != 3
        or frame.shape[0] <= 0
        or frame.shape[1] <= 0
        or frame.shape[2] < 3
    ):
        raise ValueError(
            "frame must have shape (height, width, channels>=3)"
        )

    if np.issubdtype(
        frame.dtype,
        np.integer,
    ):
        maximum = np.iinfo(
            frame.dtype
        ).max

        rgb = (
            frame[..., :3].astype(
                np.float32
            )
            / float(maximum)
        )

    elif np.issubdtype(
        frame.dtype,
        np.floating,
    ):
        rgb = frame[
            ..., :3
        ].astype(
            np.float32,
            copy=False,
        )

        if not np.isfinite(rgb).all():
            raise ValueError(
                "frame must contain only finite values"
            )

        if float(rgb.min()) < 0.0:
            raise ValueError(
                "frame values must not be negative"
            )

        maximum = float(rgb.max())

        if maximum > 255.0:
            raise ValueError(
                "floating frame values must be in [0, 1] or [0, 255]"
            )

        if maximum > 1.0:
            rgb = rgb / 255.0

    else:
        raise ValueError(
            "frame must use an integer or floating dtype"
        )

    rgb = np.clip(
        rgb,
        0.0,
        1.0,
    )

    return (
        rgb[..., 0] * 0.2126
        + rgb[..., 1] * 0.7152
        + rgb[..., 2] * 0.0722
    ).astype(
        np.float32,
        copy=False,
    )


def _frame_importance_map(
    frame: np.ndarray,
) -> np.ndarray:
    """
    Build the first CPU-only SmartFocal spatial importance map.

    V0.1 combines:
    - local luminance contrast;
    - horizontal/vertical gradients;
    - spatial brightness prominence.

    No model, OpenCV, GPU or temporal information is used here.
    """

    luminance = _rgb_luminance(
        frame
    )

    padded = np.pad(
        luminance,
        pad_width=1,
        mode="edge",
    )

    local_mean = (
        padded[1:-1, 1:-1]
        + padded[:-2, 1:-1]
        + padded[2:, 1:-1]
        + padded[1:-1, :-2]
        + padded[1:-1, 2:]
    ) / 5.0

    local_contrast = np.abs(
        luminance - local_mean
    )

    gradient_x = np.zeros_like(
        luminance,
        dtype=np.float32,
    )
    gradient_y = np.zeros_like(
        luminance,
        dtype=np.float32,
    )

    gradient_x[:, 1:] = np.abs(
        np.diff(
            luminance,
            axis=1,
        )
    )

    gradient_y[1:, :] = np.abs(
        np.diff(
            luminance,
            axis=0,
        )
    )

    gradient = np.sqrt(
        gradient_x * gradient_x
        + gradient_y * gradient_y
    )

    contrast_score = _normalize_component(
        local_contrast
    )
    gradient_score = _normalize_component(
        gradient
    )
    brightness_score = _normalize_component(
        luminance
    )

    importance = (
        0.45 * contrast_score
        + 0.45 * gradient_score
        + 0.10 * brightness_score
    )

    return _normalize_component(
        importance
    )


@dataclass(frozen=True)
class _CoverWindow:
    """
    Best source-space crop window for a target COVER aspect ratio.
    """

    x1: int
    y1: int
    width: int
    height: int
    score: float


def _cover_window_shape(
    source_width: int,
    source_height: int,
    target_width: int,
    target_height: int,
) -> tuple[int, int]:
    """
    Return the source-space window retained by COVER.

    The whole source is preserved on one axis. The other axis is cropped
    to the target aspect ratio.
    """

    dimensions = (
        source_width,
        source_height,
        target_width,
        target_height,
    )

    if any(
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
        for value in dimensions
    ):
        raise ValueError(
            "source and target dimensions must be positive integers"
        )

    # Compare aspect ratios without introducing floating-point error.
    source_cross = (
        source_width
        * target_height
    )
    target_cross = (
        target_width
        * source_height
    )

    if source_cross > target_cross:
        # Source is wider than target: crop horizontally.
        crop_width = round(
            source_height
            * target_width
            / target_height
        )

        return (
            max(
                1,
                min(
                    source_width,
                    crop_width,
                ),
            ),
            source_height,
        )

    if source_cross < target_cross:
        # Source is taller than target: crop vertically.
        crop_height = round(
            source_width
            * target_height
            / target_width
        )

        return (
            source_width,
            max(
                1,
                min(
                    source_height,
                    crop_height,
                ),
            ),
        )

    return (
        source_width,
        source_height,
    )


def _best_cover_window(
    importance: np.ndarray,
    target_width: int,
    target_height: int,
) -> _CoverWindow:
    """
    Find the COVER crop retaining the largest total visual importance.

    Ties deliberately prefer the crop whose center is closest to the
    source-frame center. This makes uniform or ambiguous maps fall back
    naturally to historical centered COVER behavior.
    """

    importance = np.asarray(
        importance,
        dtype=np.float32,
    )

    if (
        importance.ndim != 2
        or importance.shape[0] <= 0
        or importance.shape[1] <= 0
    ):
        raise ValueError(
            "importance must be a non-empty 2D array"
        )

    if not np.isfinite(
        importance
    ).all():
        raise ValueError(
            "importance must contain only finite values"
        )

    if (
        float(importance.min()) < 0.0
        or float(importance.max()) > 1.0
    ):
        raise ValueError(
            "importance values must be in [0, 1]"
        )

    source_height, source_width = (
        importance.shape
    )

    crop_width, crop_height = (
        _cover_window_shape(
            source_width=source_width,
            source_height=source_height,
            target_width=target_width,
            target_height=target_height,
        )
    )

    # Integral image gives every candidate window sum without Python loops.
    integral = np.pad(
        importance.astype(
            np.float64,
            copy=False,
        ),
        (
            (1, 0),
            (1, 0),
        ),
        mode="constant",
    ).cumsum(
        axis=0
    ).cumsum(
        axis=1
    )

    window_scores = (
        integral[
            crop_height:,
            crop_width:,
        ]
        - integral[
            :-crop_height,
            crop_width:,
        ]
        - integral[
            crop_height:,
            :-crop_width,
        ]
        + integral[
            :-crop_height,
            :-crop_width,
        ]
    )

    best_score = float(
        window_scores.max()
    )

    # np.argmax alone would choose top-left on a tie. SmartFocal should
    # instead preserve centered COVER when evidence is ambiguous.
    best_mask = np.isclose(
        window_scores,
        best_score,
        rtol=1e-6,
        atol=1e-9,
    )

    candidates = np.argwhere(
        best_mask
    )

    source_center_x = (
        source_width / 2.0
    )
    source_center_y = (
        source_height / 2.0
    )

    candidate_center_x = (
        candidates[:, 1]
        + crop_width / 2.0
    )
    candidate_center_y = (
        candidates[:, 0]
        + crop_height / 2.0
    )

    distance_sq = (
        (
            candidate_center_x
            - source_center_x
        ) ** 2
        + (
            candidate_center_y
            - source_center_y
        ) ** 2
    )

    winner = candidates[
        int(
            np.argmin(
                distance_sq
            )
        )
    ]

    y1 = int(
        winner[0]
    )
    x1 = int(
        winner[1]
    )

    return _CoverWindow(
        x1=x1,
        y1=y1,
        width=crop_width,
        height=crop_height,
        score=best_score,
    )


def _cover_window_to_focal(
    window: _CoverWindow,
    source_width: int,
    source_height: int,
) -> tuple[float, float]:
    """
    Convert a source-space crop center to renderer focal coordinates.
    """

    if (
        source_width <= 0
        or source_height <= 0
    ):
        raise ValueError(
            "source dimensions must be positive"
        )

    focal_x = (
        window.x1
        + window.width / 2.0
    ) / source_width

    focal_y = (
        window.y1
        + window.height / 2.0
    ) / source_height

    return (
        float(
            np.clip(
                focal_x,
                0.0,
                1.0,
            )
        ),
        float(
            np.clip(
                focal_y,
                0.0,
                1.0,
            )
        ),
    )


def _best_cover_focal_from_importance(
    importance: np.ndarray,
    target_width: int,
    target_height: int,
) -> tuple[float, float]:
    """
    Select the normalized focal point whose COVER crop preserves the
    maximum importance for the requested target aspect ratio.
    """

    window = _best_cover_window(
        importance=importance,
        target_width=target_width,
        target_height=target_height,
    )

    source_height, source_width = (
        importance.shape
    )

    return _cover_window_to_focal(
        window=window,
        source_width=source_width,
        source_height=source_height,
    )


def _validated_importance_maps(
    importance_maps: Sequence[np.ndarray],
) -> list[np.ndarray]:
    """
    Validate temporal SmartFocal maps.

    All maps must correspond to the same source-frame geometry.
    """

    if not importance_maps:
        raise ValueError(
            "importance_maps must not be empty"
        )

    validated = []
    expected_shape = None

    for importance in importance_maps:
        importance = np.asarray(
            importance,
            dtype=np.float32,
        )

        if (
            importance.ndim != 2
            or importance.shape[0] <= 0
            or importance.shape[1] <= 0
        ):
            raise ValueError(
                "each importance map must be a non-empty 2D array"
            )

        if not np.isfinite(
            importance
        ).all():
            raise ValueError(
                "importance maps must contain only finite values"
            )

        if (
            float(importance.min()) < 0.0
            or float(importance.max()) > 1.0
        ):
            raise ValueError(
                "importance map values must be in [0, 1]"
            )

        if expected_shape is None:
            expected_shape = importance.shape
        elif importance.shape != expected_shape:
            raise ValueError(
                "all importance maps must have the same shape"
            )

        validated.append(
            importance
        )

    return validated


def _aggregate_importance_maps(
    importance_maps: Sequence[np.ndarray],
) -> np.ndarray:
    """
    Robust temporal aggregation for one source subclip.

    V0.1 uses the temporal median so a transient flash, reflection,
    light source or outlier frame cannot dominate the crop.
    """

    validated = _validated_importance_maps(
        importance_maps
    )

    stacked = np.stack(
        validated,
        axis=0,
    )

    return np.median(
        stacked,
        axis=0,
    ).astype(
        np.float32,
        copy=False,
    )


def _importance_map_is_informative(
    importance: np.ndarray,
) -> bool:
    """
    Return whether the map contains usable spatial preference.
    """

    importance = np.asarray(
        importance,
        dtype=np.float32,
    )

    if (
        importance.ndim != 2
        or importance.size == 0
    ):
        return False

    if not np.isfinite(
        importance
    ).all():
        return False

    span = (
        float(importance.max())
        - float(importance.min())
    )

    total = float(
        importance.sum()
    )

    return (
        span > 1e-6
        and total > 1e-6
    )


def _temporal_focal_confidence(
    importance_maps: Sequence[np.ndarray],
    final_focal_x: float,
    final_focal_y: float,
    target_width: int,
    target_height: int,
) -> float:
    """
    Initial model-free confidence.

    Components:
    - fraction of informative temporal samples;
    - spatial consistency of their independent focal decisions.

    This is NOT yet a calibrated production confidence threshold.
    """

    validated = _validated_importance_maps(
        importance_maps
    )

    informative = [
        importance
        for importance in validated
        if _importance_map_is_informative(
            importance
        )
    ]

    if not informative:
        return 0.0

    focal_points = [
        _best_cover_focal_from_importance(
            importance=importance,
            target_width=target_width,
            target_height=target_height,
        )
        for importance in informative
    ]

    distances = [
        float(
            np.hypot(
                focal_x - final_focal_x,
                focal_y - final_focal_y,
            )
        )
        for focal_x, focal_y in focal_points
    ]

    mean_distance = float(
        np.mean(
            distances
        )
    )

    maximum_normalized_distance = float(
        np.sqrt(2.0)
    )

    stability = float(
        np.clip(
            1.0
            - mean_distance
            / maximum_normalized_distance,
            0.0,
            1.0,
        )
    )

    informative_fraction = (
        len(informative)
        / len(validated)
    )

    return float(
        np.clip(
            stability
            * informative_fraction,
            0.0,
            1.0,
        )
    )


def focal_decision_from_importance_maps(
    importance_maps: Sequence[np.ndarray],
    target_width: int,
    target_height: int,
) -> FocalDecision:
    """
    Produce one fixed focal decision for one source subclip.

    SmartFocal V0.1 deliberately performs per-clip framing,
    not dynamic frame-by-frame tracking.
    """

    validated = _validated_importance_maps(
        importance_maps
    )

    aggregated = _aggregate_importance_maps(
        validated
    )

    if not _importance_map_is_informative(
        aggregated
    ):
        return fallback_focal_decision()

    focal_x, focal_y = (
        _best_cover_focal_from_importance(
            importance=aggregated,
            target_width=target_width,
            target_height=target_height,
        )
    )

    confidence = _temporal_focal_confidence(
        importance_maps=validated,
        final_focal_x=focal_x,
        final_focal_y=focal_y,
        target_width=target_width,
        target_height=target_height,
    )

    return FocalDecision(
        focal_x=focal_x,
        focal_y=focal_y,
        confidence=confidence,
        method="numpy_temporal_median_cover",
    )


_DEFAULT_SAMPLE_FRACTIONS = (
    0.10,
    0.30,
    0.50,
    0.70,
    0.90,
)

_DEFAULT_MAX_ANALYSIS_DIMENSION = 320


def _sample_times(
    duration: float,
    sample_fractions: Sequence[float] = _DEFAULT_SAMPLE_FRACTIONS,
) -> tuple[float, ...]:
    """
    Convert normalized temporal positions into clip timestamps.
    """

    try:
        duration = float(
            duration
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "duration must be a positive finite number"
        ) from exc

    if (
        not math.isfinite(duration)
        or duration <= 0.0
    ):
        raise ValueError(
            "duration must be a positive finite number"
        )

    if not sample_fractions:
        raise ValueError(
            "sample_fractions must not be empty"
        )

    times = []

    for fraction in sample_fractions:
        try:
            fraction = float(
                fraction
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "sample fractions must be finite numbers between 0 and 1"
            ) from exc

        if (
            not math.isfinite(fraction)
            or fraction <= 0.0
            or fraction >= 1.0
        ):
            raise ValueError(
                "sample fractions must be strictly between 0 and 1"
            )

        times.append(
            duration * fraction
        )

    return tuple(
        times
    )


def _downscale_frame_for_analysis(
    frame: np.ndarray,
    max_dimension: int = _DEFAULT_MAX_ANALYSIS_DIMENSION,
) -> np.ndarray:
    """
    Reduce analysis resolution using deterministic NumPy sampling.

    This avoids GPU use, avoids extra model dependencies and prevents
    full-HD/4K source frames from unnecessarily increasing CPU/RAM cost.
    """

    frame = np.asarray(
        frame
    )

    if (
        frame.ndim != 3
        or frame.shape[0] <= 0
        or frame.shape[1] <= 0
        or frame.shape[2] < 3
    ):
        raise ValueError(
            "frame must have shape (height, width, channels>=3)"
        )

    if (
        not isinstance(max_dimension, int)
        or isinstance(max_dimension, bool)
        or max_dimension <= 0
    ):
        raise ValueError(
            "max_dimension must be a positive integer"
        )

    height = int(
        frame.shape[0]
    )
    width = int(
        frame.shape[1]
    )

    largest = max(
        height,
        width,
    )

    rgb = frame[
        ...,
        :3
    ]

    if largest <= max_dimension:
        return rgb

    scale = (
        max_dimension
        / float(largest)
    )

    target_height = max(
        1,
        int(
            round(
                height * scale
            )
        ),
    )

    target_width = max(
        1,
        int(
            round(
                width * scale
            )
        ),
    )

    y_indices = np.linspace(
        0,
        height - 1,
        target_height,
    ).round().astype(
        np.intp
    )

    x_indices = np.linspace(
        0,
        width - 1,
        target_width,
    ).round().astype(
        np.intp
    )

    return rgb[
        y_indices[:, None],
        x_indices[None, :],
        :,
    ]


def focal_decision_from_clip(
    clip,
    target_width: int,
    target_height: int,
    sample_fractions: Sequence[float] = _DEFAULT_SAMPLE_FRACTIONS,
    max_analysis_dimension: int = _DEFAULT_MAX_ANALYSIS_DIMENSION,
) -> FocalDecision:
    """
    Analyze one MoviePy-compatible source subclip.

    Required clip interface:
    - .duration
    - .get_frame(time)

    The returned focal point is fixed for the complete subclip.
    """

    if not hasattr(
        clip,
        "duration",
    ):
        raise ValueError(
            "clip must expose duration"
        )

    if not callable(
        getattr(
            clip,
            "get_frame",
            None,
        )
    ):
        raise ValueError(
            "clip must expose get_frame(time)"
        )

    times = _sample_times(
        duration=clip.duration,
        sample_fractions=sample_fractions,
    )

    importance_maps = []

    for timestamp in times:
        frame = clip.get_frame(
            timestamp
        )

        analysis_frame = (
            _downscale_frame_for_analysis(
                frame,
                max_dimension=max_analysis_dimension,
            )
        )

        importance_maps.append(
            _frame_importance_map(
                analysis_frame
            )
        )

    return focal_decision_from_importance_maps(
        importance_maps=importance_maps,
        target_width=target_width,
        target_height=target_height,
    )


def safe_focal_decision_from_clip(
    clip,
    target_width: int,
    target_height: int,
    sample_fractions: Sequence[float] = _DEFAULT_SAMPLE_FRACTIONS,
    max_analysis_dimension: int = _DEFAULT_MAX_ANALYSIS_DIMENSION,
) -> FocalDecision:
    """
    Fail-safe wrapper intended for future production integration.

    Any unexpected analysis failure returns the historical centered
    COVER fallback instead of breaking video generation.
    """

    try:
        return focal_decision_from_clip(
            clip=clip,
            target_width=target_width,
            target_height=target_height,
            sample_fractions=sample_fractions,
            max_analysis_dimension=max_analysis_dimension,
        )
    except Exception:
        return fallback_focal_decision()


def fallback_focal_decision() -> FocalDecision:
    """
    Return the deterministic low-confidence center fallback.

    SmartFocal V0.1 must fail safely to the historical centered COVER
    behavior whenever automatic analysis cannot make a reliable decision.
    """

    return FocalDecision(
        focal_x=_FALLBACK_FOCAL_X,
        focal_y=_FALLBACK_FOCAL_Y,
        confidence=_FALLBACK_CONFIDENCE,
        method=_FALLBACK_METHOD,
    )
