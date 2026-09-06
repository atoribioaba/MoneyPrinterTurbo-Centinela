import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.upload_post import UploadPostService


_CONFIG_BASE = {
    "upload_post_enabled": True,
    "upload_post_api_key": "test-key",
    "upload_post_username": "testuser",
    "upload_post_platforms": ["tiktok", "instagram", "youtube"],
    # Historical setting deliberately remains true in the fixture: the service
    # must ignore it and keep AUTO_PUBLICATION disabled.
    "upload_post_auto_upload": True,
    "upload_post_youtube_privacy_status": "unlisted",
}


def _mock_response(success=True):
    response = MagicMock()
    response.json.return_value = {"success": success, "request_id": "abc123"}
    response.raise_for_status = MagicMock()
    return response


def _get(data, key):
    for item_key, value in data:
        if item_key == key:
            return value
    return None


def _get_all(data, key):
    return [value for item_key, value in data if item_key == key]


def _has_key(data, key):
    return any(item_key == key for item_key, _value in data)


class TestUploadPostManualFallback(unittest.TestCase):
    @patch("app.services.upload_post.config.app", _CONFIG_BASE)
    @patch("app.services.upload_post.requests.post")
    def test_missing_human_approval_blocks_before_any_network_request(self, mock_post):
        service = UploadPostService()

        result = service.upload_video("/fake/v.mp4", "Title")

        self.assertFalse(result["success"])
        self.assertIn("explicit human approval", result["error"])
        mock_post.assert_not_called()

    @patch("app.services.upload_post.config.app", _CONFIG_BASE)
    def test_historical_auto_upload_setting_is_ignored(self):
        service = UploadPostService()
        self.assertFalse(service.auto_upload)

    @patch("app.services.upload_post.config.app", _CONFIG_BASE)
    @patch("app.services.upload_post.AUTO_PUBLICATION", True)
    def test_modified_auto_publication_invariant_fails_closed(self):
        service = UploadPostService()
        with self.assertRaisesRegex(RuntimeError, "AUTO_PUBLICATION invariant"):
            service.upload_video("/fake/v.mp4", "Title", approved=True)

    @patch(
        "app.services.upload_post.config.app",
        {**_CONFIG_BASE, "upload_post_enabled": False},
    )
    @patch("app.services.upload_post.requests.post")
    def test_unconfigured_service_skips_request_after_approval(self, mock_post):
        result = UploadPostService().upload_video(
            "/fake/v.mp4", "Title", approved=True
        )

        self.assertFalse(result["success"])
        self.assertIn("not configured", result["error"])
        mock_post.assert_not_called()

    @patch("app.services.upload_post.config.app", _CONFIG_BASE)
    @patch("app.services.upload_post.os.path.exists", return_value=False)
    @patch("app.services.upload_post.requests.post")
    def test_missing_video_skips_request(self, mock_post, _exists):
        result = UploadPostService().upload_video(
            "/missing/v.mp4", "Title", approved=True
        )

        self.assertFalse(result["success"])
        self.assertIn("Video file not found", result["error"])
        mock_post.assert_not_called()

    @patch("app.services.upload_post.config.app", _CONFIG_BASE)
    @patch("app.services.upload_post.os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data=b"fake"))
    @patch("app.services.upload_post.requests.post")
    def test_request_error_is_redacted_and_stable(self, mock_post, _exists):
        mock_post.side_effect = requests.exceptions.Timeout(
            "upload timed out with api key test-key"
        )

        result = UploadPostService().upload_video(
            "/fake/v.mp4", "Title", approved=True
        )

        self.assertFalse(result["success"])
        self.assertIn("upload timed out", result["error"])
        self.assertNotIn("test-key", result["error"])
        self.assertIn("***", result["error"])

    @patch("app.services.upload_post.config.app", _CONFIG_BASE)
    @patch("app.services.upload_post.requests.get")
    def test_check_status_is_read_only_and_does_not_require_new_approval(self, mock_get):
        response = _mock_response()
        response.json.return_value = {"success": True, "status": "processing"}
        mock_get.return_value = response
        service = UploadPostService()

        self.assertEqual(
            service.check_status("request-123"),
            {"success": True, "status": "processing"},
        )

        mock_get.side_effect = requests.exceptions.ConnectionError("offline")
        failed = service.check_status("request-123")
        self.assertFalse(failed["success"])
        self.assertIn("offline", failed["error"])


class TestUploadPostPayload(unittest.TestCase):
    @patch("app.services.upload_post.config.app", _CONFIG_BASE)
    @patch("app.services.upload_post.os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data=b"fake"))
    @patch("app.services.upload_post.requests.post")
    def test_youtube_fields_are_sent_only_after_approval(self, mock_post, _exists):
        mock_post.return_value = _mock_response()
        service = UploadPostService()

        service.upload_video(
            "/fake/v.mp4",
            "Título",
            youtube_extra={
                "youtube_title": "Mi Short",
                "youtube_description": "Descripción",
                "tags": ["ia", "shorts"],
                "privacyStatus": "unlisted",
            },
            approved=True,
        )

        data = mock_post.call_args.kwargs["data"]
        self.assertEqual(_get(data, "youtube_title"), "Mi Short")
        self.assertEqual(_get(data, "youtube_description"), "Descripción")
        self.assertEqual(_get_all(data, "tags[]"), ["ia", "shorts"])
        self.assertEqual(_get(data, "privacyStatus"), "unlisted")
        self.assertEqual(_get(data, "containsSyntheticMedia"), "true")

    @patch(
        "app.services.upload_post.config.app",
        {
            **_CONFIG_BASE,
            "upload_post_youtube_privacy_status": "private",
        },
    )
    @patch("app.services.upload_post.os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data=b"fake"))
    @patch("app.services.upload_post.requests.post")
    def test_youtube_fallback_defaults_to_private(self, mock_post, _exists):
        mock_post.return_value = _mock_response()
        service = UploadPostService()

        service.upload_video(
            "/fake/v.mp4",
            "T",
            youtube_extra={"youtube_title": "Private first"},
            approved=True,
        )

        data = mock_post.call_args.kwargs["data"]
        self.assertEqual(_get(data, "privacyStatus"), "private")

    @patch(
        "app.services.upload_post.config.app",
        {
            **_CONFIG_BASE,
            "upload_post_youtube_privacy_status": "not-a-real-status",
        },
    )
    def test_invalid_saved_youtube_privacy_fails_safe_to_private(self):
        self.assertEqual(UploadPostService().youtube_privacy_status, "private")

    @patch("app.services.upload_post.config.app", _CONFIG_BASE)
    @patch("app.services.upload_post.os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data=b"fake"))
    @patch("app.services.upload_post.requests.post")
    def test_contains_synthetic_media_is_always_true(self, mock_post, _exists):
        mock_post.return_value = _mock_response()
        service = UploadPostService()

        service.upload_video(
            "/fake/v.mp4",
            "T",
            youtube_extra={"containsSyntheticMedia": False},
            approved=True,
        )

        data = mock_post.call_args.kwargs["data"]
        self.assertEqual(_get(data, "containsSyntheticMedia"), "true")

    @patch(
        "app.services.upload_post.config.app",
        {**_CONFIG_BASE, "upload_post_platforms": ["tiktok", "instagram"]},
    )
    @patch("app.services.upload_post.os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data=b"fake"))
    @patch("app.services.upload_post.requests.post")
    def test_non_youtube_targets_do_not_receive_youtube_fields(self, mock_post, _exists):
        mock_post.return_value = _mock_response()
        service = UploadPostService()
        service.upload_video("/fake/v.mp4", "T", approved=True)

        data = mock_post.call_args.kwargs["data"]
        self.assertFalse(_has_key(data, "youtube_title"))
        self.assertFalse(_has_key(data, "containsSyntheticMedia"))
        self.assertFalse(_has_key(data, "privacyStatus"))

    @patch("app.services.upload_post.config.app", _CONFIG_BASE)
    @patch("app.services.upload_post.os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data=b"fake"))
    @patch("app.services.upload_post.requests.post")
    def test_endpoint_and_platform_format_remain_compatible(self, mock_post, _exists):
        mock_post.return_value = _mock_response()
        service = UploadPostService()
        service.upload_video("/fake/v.mp4", "T", approved=True)

        self.assertTrue(mock_post.call_args.args[0].endswith("/api/upload"))
        platforms = _get_all(mock_post.call_args.kwargs["data"], "platform[]")
        self.assertIn("tiktok", platforms)
        self.assertIn("instagram", platforms)
        self.assertIn("youtube", platforms)


if __name__ == "__main__":
    unittest.main()
