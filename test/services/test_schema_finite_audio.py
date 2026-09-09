import math

import pytest
from pydantic import ValidationError

from app.models.schema import AudioRequest, SubtitleRequest, VideoParams


@pytest.mark.parametrize("model_cls,base", [
    (VideoParams, {"video_subject": "Saturno"}),
    (SubtitleRequest, {"video_script": "Saturno"}),
    (AudioRequest, {"video_script": "Saturno"}),
])
@pytest.mark.parametrize("field_name", ["voice_rate", "voice_volume", "bgm_volume"])
@pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf])
def test_public_audio_models_reject_non_finite_numbers(
    model_cls,
    base,
    field_name,
    bad_value,
):
    with pytest.raises(ValidationError):
        model_cls(**base, **{field_name: bad_value})


@pytest.mark.parametrize("model_cls,base", [
    (VideoParams, {"video_subject": "Saturno"}),
    (SubtitleRequest, {"video_script": "Saturno"}),
    (AudioRequest, {"video_script": "Saturno"}),
])
def test_public_audio_models_keep_normal_finite_values_compatible(model_cls, base):
    model = model_cls(
        **base,
        voice_rate=1.05,
        voice_volume=0.9,
        bgm_volume=0.2,
    )
    assert model.voice_rate == 1.05
    assert model.voice_volume == 0.9
    assert model.bgm_volume == 0.2
