from importlib.metadata import version

from packaging.version import Version
from moviepy import TextClip


def test_moviepy_textclip_supports_pillow_security_floor():
    """Guard the exact compatibility boundary that requires the MoviePy source pin."""

    assert Version(version("pillow")) >= Version("12.3.0")

    clip = TextClip(
        text="El Centinela del Universo",
        font_size=24,
        color="white",
        bg_color="black",
        duration=0.1,
    )
    try:
        frame = clip.get_frame(0)
        assert frame.ndim == 3
        assert frame.shape[0] > 0
        assert frame.shape[1] > 0
        assert frame.shape[2] in (3, 4)
    finally:
        clip.close()
