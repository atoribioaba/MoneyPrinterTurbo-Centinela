import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models.schema import FocalMode, VideoAspect, VideoFitMode, VideoParams


class TestVideoAspect(unittest.TestCase):
    def test_to_resolution_known_aspects(self):
        self.assertEqual(VideoAspect.landscape.to_resolution(), (1920, 1080))
        self.assertEqual(VideoAspect.portrait.to_resolution(), (1080, 1920))
        self.assertEqual(VideoAspect.square.to_resolution(), (1080, 1080))

    def test_to_resolution_rejects_unsupported_value(self):
        with self.assertRaises(ValueError):
            VideoAspect.to_resolution("4:5")


class TestFocalMode(unittest.TestCase):
    def test_focal_mode_schema_contract(self):
        self.assertEqual(
            [item.value for item in FocalMode],
            ["manual", "smart"],
        )

        # Smart focal selection is orthogonal to FIT/COVER.
        self.assertEqual(
            [item.value for item in VideoFitMode],
            ["fit", "cover"],
        )

    def test_focal_mode_default_and_explicit_smart(self):
        default_params = VideoParams(
            video_subject="focal mode default"
        )
        self.assertEqual(
            getattr(
                default_params.focal_mode,
                "value",
                default_params.focal_mode,
            ),
            "manual",
        )

        smart_params = VideoParams(
            video_subject="focal mode smart",
            focal_mode="smart",
        )
        self.assertEqual(
            getattr(
                smart_params.focal_mode,
                "value",
                smart_params.focal_mode,
            ),
            "smart",
        )


class TestFocalModeSerialization(unittest.TestCase):
    def test_default_is_real_focal_mode_enum(self):
        params = VideoParams(
            video_subject="focal enum default"
        )

        self.assertIs(
            params.focal_mode,
            FocalMode.manual,
        )

    def test_default_serializes_as_manual(self):
        params = VideoParams(
            video_subject="focal serialization"
        )

        payload = params.model_dump()

        self.assertEqual(
            payload["focal_mode"],
            FocalMode.manual,
        )

        json_payload = (
            params.model_dump_json()
        )

        self.assertIn(
            '"focal_mode":"manual"',
            json_payload,
        )


class TestVideoParams(unittest.TestCase):
    def test_rejects_non_positive_generation_counts(self):
        for field_name in ("video_clip_duration", "video_count"):
            for value in (0, -1, None):
                with self.subTest(field_name=field_name, value=value):
                    with self.assertRaises(ValidationError):
                        VideoParams(video_subject="Coffee", **{field_name: value})

    def test_accepts_positive_generation_counts(self):
        params = VideoParams(
            video_subject="Coffee", video_clip_duration=1, video_count=1
        )

        self.assertEqual(params.video_clip_duration, 1)
        self.assertEqual(params.video_count, 1)


if __name__ == "__main__":
    unittest.main()
