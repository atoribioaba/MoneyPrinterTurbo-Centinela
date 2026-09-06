from importlib.metadata import version

import numpy as np
from moviepy import ImageClip, TextClip
from packaging.version import Version


def test_moviepy_works_with_patched_pillow():
    """Guard the temporary uv override until MoviePy publishes Pillow 12 support."""
    assert Version(version("pillow")) >= Version("12.3.0")

    image = ImageClip(np.zeros((32, 32, 3), dtype=np.uint8))
    resized = image.resized(width=16)
    try:
        frame = resized.get_frame(0)
        assert frame.shape[1] == 16
    finally:
        resized.close()
        image.close()

    text = TextClip(text="Centinela", font_size=24, color="white")
    try:
        frame = text.get_frame(0)
        assert frame.ndim == 3
        assert frame.shape[0] > 0
        assert frame.shape[1] > 0
    finally:
        text.close()
