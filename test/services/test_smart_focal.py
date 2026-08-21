import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.smart_focal import (
    FocalDecision,
    _aggregate_importance_maps,
    _best_cover_focal_from_importance,
    _best_cover_window,
    _cover_window_shape,
    _downscale_frame_for_analysis,
    _frame_importance_map,
    _sample_times,
    fallback_focal_decision,
    focal_decision_from_clip,
    focal_decision_from_importance_maps,
    safe_focal_decision_from_clip,
)


def _synthetic_importance_map(
    *,
    side: str,
) -> np.ndarray:
    importance = np.zeros(
        (64, 96),
        dtype=np.float32,
    )

    if side == "left":
        importance[
            20:44,
            8:20,
        ] = 1.0

    elif side == "right":
        importance[
            20:44,
            76:88,
        ] = 1.0

    elif side == "center":
        importance[
            20:44,
            42:54,
        ] = 1.0

    elif side == "flat":
        pass

    else:
        raise ValueError(
            f"unknown side: {side}"
        )

    return importance


def test_aggregate_importance_maps_uses_temporal_median():
    maps = [
        _synthetic_importance_map(
            side="right"
        ),
        _synthetic_importance_map(
            side="right"
        ),
        _synthetic_importance_map(
            side="right"
        ),
        _synthetic_importance_map(
            side="right"
        ),
        _synthetic_importance_map(
            side="left"
        ),
    ]

    aggregated = (
        _aggregate_importance_maps(
            maps
        )
    )

    assert float(
        aggregated[
            30,
            80,
        ]
    ) == 1.0

    assert float(
        aggregated[
            30,
            12,
        ]
    ) == 0.0


def test_temporal_decision_stable_right_subject():
    maps = [
        _synthetic_importance_map(
            side="right"
        )
        for _ in range(5)
    ]

    decision = (
        focal_decision_from_importance_maps(
            importance_maps=maps,
            target_width=1080,
            target_height=1920,
        )
    )

    assert decision.focal_x > 0.5
    assert decision.focal_y == 0.5

    assert decision.confidence == pytest.approx(
        1.0
    )

    assert (
        decision.method
        == "numpy_temporal_median_cover"
    )


def test_temporal_decision_ignores_single_outlier():
    maps = [
        _synthetic_importance_map(
            side="right"
        ),
        _synthetic_importance_map(
            side="right"
        ),
        _synthetic_importance_map(
            side="right"
        ),
        _synthetic_importance_map(
            side="right"
        ),
        _synthetic_importance_map(
            side="left"
        ),
    ]

    decision = (
        focal_decision_from_importance_maps(
            importance_maps=maps,
            target_width=1080,
            target_height=1920,
        )
    )

    assert decision.focal_x > 0.5

    assert (
        0.0
        < decision.confidence
        < 1.0
    )


def test_temporal_decision_flat_maps_use_fallback():
    maps = [
        _synthetic_importance_map(
            side="flat"
        )
        for _ in range(5)
    ]

    decision = (
        focal_decision_from_importance_maps(
            importance_maps=maps,
            target_width=1080,
            target_height=1920,
        )
    )

    assert decision == (
        fallback_focal_decision()
    )


def test_temporal_decision_three_signal_two_flat():
    maps = [
        _synthetic_importance_map(
            side="right"
        ),
        _synthetic_importance_map(
            side="right"
        ),
        _synthetic_importance_map(
            side="right"
        ),
        _synthetic_importance_map(
            side="flat"
        ),
        _synthetic_importance_map(
            side="flat"
        ),
    ]

    decision = (
        focal_decision_from_importance_maps(
            importance_maps=maps,
            target_width=1080,
            target_height=1920,
        )
    )

    assert decision.focal_x > 0.5

    assert decision.confidence == pytest.approx(
        0.6
    )


def test_temporal_aggregation_rejects_shape_mismatch():
    with pytest.raises(ValueError):
        _aggregate_importance_maps(
            [
                np.zeros(
                    (64, 96),
                    dtype=np.float32,
                ),
                np.zeros(
                    (32, 96),
                    dtype=np.float32,
                ),
            ]
        )


def test_temporal_aggregation_rejects_empty_sequence():
    with pytest.raises(ValueError):
        _aggregate_importance_maps(
            []
        )


def test_sample_times_use_expected_fractions():
    assert _sample_times(
        10.0
    ) == pytest.approx(
        (
            1.0,
            3.0,
            5.0,
            7.0,
            9.0,
        )
    )


def test_downscale_frame_limits_largest_dimension():
    frame = np.zeros(
        (1080, 1920, 3),
        dtype=np.uint8,
    )

    reduced = (
        _downscale_frame_for_analysis(
            frame,
            max_dimension=320,
        )
    )

    assert max(
        reduced.shape[:2]
    ) == 320

    assert reduced.shape[2] == 3


class _FakeSmartFocalClip:
    def __init__(
        self,
        *,
        side="right",
        duration=10.0,
        fail=False,
    ):
        self.side = side
        self.duration = duration
        self.fail = fail
        self.requested_times = []

    def get_frame(
        self,
        timestamp,
    ):
        self.requested_times.append(
            timestamp
        )

        if self.fail:
            raise RuntimeError(
                "synthetic frame failure"
            )

        frame = np.zeros(
            (64, 96, 3),
            dtype=np.uint8,
        )

        if self.side == "right":
            frame[
                20:44,
                76:88,
                :,
            ] = 255

        elif self.side == "left":
            frame[
                20:44,
                8:20,
                :,
            ] = 255

        return frame


def test_focal_decision_from_clip_samples_five_frames():
    clip = _FakeSmartFocalClip(
        side="right"
    )

    decision = focal_decision_from_clip(
        clip=clip,
        target_width=1080,
        target_height=1920,
        max_analysis_dimension=320,
    )

    assert clip.requested_times == pytest.approx(
        [
            1.0,
            3.0,
            5.0,
            7.0,
            9.0,
        ]
    )

    assert decision.focal_x > 0.5
    assert decision.focal_y == 0.5
    assert decision.confidence > 0.0


def test_safe_focal_decision_from_clip_fails_to_center():
    clip = _FakeSmartFocalClip(
        fail=True
    )

    decision = safe_focal_decision_from_clip(
        clip=clip,
        target_width=1080,
        target_height=1920,
    )

    assert decision == (
        fallback_focal_decision()
    )


def test_cover_window_shape_landscape_to_portrait():
    assert _cover_window_shape(
        source_width=96,
        source_height=64,
        target_width=1080,
        target_height=1920,
    ) == (
        36,
        64,
    )


def test_cover_window_shape_portrait_to_landscape():
    assert _cover_window_shape(
        source_width=64,
        source_height=96,
        target_width=1920,
        target_height=1080,
    ) == (
        64,
        36,
    )


def test_cover_window_shape_matching_aspect_keeps_full_frame():
    assert _cover_window_shape(
        source_width=160,
        source_height=90,
        target_width=1920,
        target_height=1080,
    ) == (
        160,
        90,
    )


def test_best_cover_window_flat_map_prefers_center():
    importance = np.zeros(
        (64, 96),
        dtype=np.float32,
    )

    window = _best_cover_window(
        importance=importance,
        target_width=1080,
        target_height=1920,
    )

    assert window.width == 36
    assert window.height == 64
    assert window.x1 == 30
    assert window.y1 == 0
    assert window.score == 0.0

    focal_x, focal_y = (
        _best_cover_focal_from_importance(
            importance=importance,
            target_width=1080,
            target_height=1920,
        )
    )

    assert focal_x == 0.5
    assert focal_y == 0.5


def test_best_cover_focal_moves_right_for_right_subject():
    importance = np.zeros(
        (64, 96),
        dtype=np.float32,
    )

    importance[
        20:44,
        76:88,
    ] = 1.0

    focal_x, focal_y = (
        _best_cover_focal_from_importance(
            importance=importance,
            target_width=1080,
            target_height=1920,
        )
    )

    assert focal_x > 0.5
    assert focal_y == 0.5


def test_best_cover_focal_moves_left_for_left_subject():
    importance = np.zeros(
        (64, 96),
        dtype=np.float32,
    )

    importance[
        20:44,
        8:20,
    ] = 1.0

    focal_x, focal_y = (
        _best_cover_focal_from_importance(
            importance=importance,
            target_width=1080,
            target_height=1920,
        )
    )

    assert focal_x < 0.5
    assert focal_y == 0.5


def test_best_cover_focal_moves_down_for_low_subject():
    importance = np.zeros(
        (96, 64),
        dtype=np.float32,
    )

    importance[
        74:88,
        20:44,
    ] = 1.0

    focal_x, focal_y = (
        _best_cover_focal_from_importance(
            importance=importance,
            target_width=1920,
            target_height=1080,
        )
    )

    assert focal_x == 0.5
    assert focal_y > 0.5


def test_best_cover_window_rejects_invalid_importance():
    invalid = np.zeros(
        (32, 32),
        dtype=np.float32,
    )
    invalid[0, 0] = np.nan

    with pytest.raises(ValueError):
        _best_cover_window(
            importance=invalid,
            target_width=1080,
            target_height=1920,
        )


def test_frame_importance_map_flat_frame_is_zero():
    frame = np.zeros(
        (48, 64, 3),
        dtype=np.uint8,
    )

    importance = _frame_importance_map(
        frame
    )

    assert importance.shape == (
        48,
        64,
    )
    assert importance.dtype == np.float32
    assert np.all(
        importance == 0.0
    )


def test_frame_importance_map_favors_structured_bright_region():
    frame = np.zeros(
        (64, 96, 3),
        dtype=np.uint8,
    )

    # Synthetic subject deliberately placed on the right side.
    frame[
        20:44,
        70:90,
        :,
    ] = 255

    importance = _frame_importance_map(
        frame
    )

    assert importance.shape == (
        64,
        96,
    )

    assert np.isfinite(
        importance
    ).all()

    assert float(
        importance.min()
    ) >= 0.0

    assert float(
        importance.max()
    ) <= 1.0

    left_score = float(
        importance[:, :48].sum()
    )

    right_score = float(
        importance[:, 48:].sum()
    )

    assert right_score > left_score


def test_frame_importance_map_accepts_unit_float_rgb():
    frame = np.zeros(
        (24, 32, 3),
        dtype=np.float32,
    )

    frame[
        8:16,
        20:28,
        :,
    ] = 1.0

    importance = _frame_importance_map(
        frame
    )

    assert importance.shape == (
        24,
        32,
    )

    assert np.isfinite(
        importance
    ).all()


@pytest.mark.parametrize(
    "frame",
    [
        np.zeros(
            (32, 32),
            dtype=np.uint8,
        ),
        np.zeros(
            (32, 32, 2),
            dtype=np.uint8,
        ),
        np.zeros(
            (0, 32, 3),
            dtype=np.uint8,
        ),
    ],
)
def test_frame_importance_map_rejects_invalid_shape(
    frame,
):
    with pytest.raises(ValueError):
        _frame_importance_map(
            frame
        )


def test_frame_importance_map_rejects_nonfinite_float():
    frame = np.zeros(
        (16, 16, 3),
        dtype=np.float32,
    )
    frame[0, 0, 0] = np.nan

    with pytest.raises(ValueError):
        _frame_importance_map(
            frame
        )


def test_fallback_focal_decision_contract():
    decision = fallback_focal_decision()

    assert decision == FocalDecision(
        focal_x=0.5,
        focal_y=0.5,
        confidence=0.0,
        method="fallback_center",
    )


def test_focal_decision_accepts_valid_values():
    decision = FocalDecision(
        focal_x=0.66,
        focal_y=0.48,
        confidence=0.87,
        method="test_method",
    )

    assert decision.focal_x == 0.66
    assert decision.focal_y == 0.48
    assert decision.confidence == 0.87
    assert decision.method == "test_method"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("focal_x", -0.01),
        ("focal_x", 1.01),
        ("focal_y", -0.01),
        ("focal_y", 1.01),
        ("confidence", -0.01),
        ("confidence", 1.01),
    ],
)
def test_focal_decision_rejects_out_of_range_values(
    field_name,
    value,
):
    kwargs = {
        "focal_x": 0.5,
        "focal_y": 0.5,
        "confidence": 0.5,
        "method": "test_method",
    }
    kwargs[field_name] = value

    with pytest.raises(ValueError):
        FocalDecision(**kwargs)


def test_focal_decision_rejects_empty_method():
    with pytest.raises(ValueError):
        FocalDecision(
            focal_x=0.5,
            focal_y=0.5,
            confidence=0.5,
            method="",
        )
