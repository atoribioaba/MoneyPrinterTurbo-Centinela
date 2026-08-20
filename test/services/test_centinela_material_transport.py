import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.models.schema import MaterialInfo, VideoAspect
from app.services import cache_manager, material, material_cache


class _FakeVideoFileClip:
    duration = 3
    fps = 30

    def __init__(self, path):
        self.path = path

    def close(self):
        return None


class RemoteVideoContainerTests(unittest.TestCase):
    def test_known_remote_video_suffixes_are_preserved(self):
        cases = (
            ("https://example.org/video.mp4?token=x", ".mp4"),
            ("https://example.org/video.webm?token=x", ".webm"),
            ("https://example.org/video.ogv?token=x", ".ogv"),
            ("https://example.org/video.ogg?token=x", ".ogg"),
        )

        for url, expected in cases:
            with self.subTest(url=url):
                self.assertEqual(
                    material._remote_video_suffix(url),
                    expected,
                )

    def test_extensionless_or_unknown_remote_url_falls_back_to_mp4(self):
        for url in (
            "https://example.org/download?token=x",
            "https://example.org/video.php?id=1",
            "not-a-url",
            "",
        ):
            with self.subTest(url=url):
                self.assertEqual(
                    material._remote_video_suffix(url),
                    ".mp4",
                )

    def test_save_video_preserves_ogv_container_suffix(self):
        fake_response = SimpleNamespace(content=b"fake-video")

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(
                    material.requests,
                    "get",
                    return_value=fake_response,
                ),
                patch.object(
                    material,
                    "VideoFileClip",
                    _FakeVideoFileClip,
                ),
            ):
                path = material.save_video(
                    "https://upload.wikimedia.org/example.ogv?tracking=x",
                    save_dir=temp_dir,
                )

            self.assertTrue(path)
            self.assertTrue(os.path.exists(path))
            self.assertEqual(Path(path).suffix.lower(), ".ogv")

    def test_save_video_keeps_mp4_fallback_for_extensionless_provider_url(self):
        fake_response = SimpleNamespace(content=b"fake-video")

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(
                    material.requests,
                    "get",
                    return_value=fake_response,
                ),
                patch.object(
                    material,
                    "VideoFileClip",
                    _FakeVideoFileClip,
                ),
            ):
                path = material.save_video(
                    "https://storage.example.org/videos/abc/download?token=x",
                    save_dir=temp_dir,
                )

            self.assertTrue(path)
            self.assertEqual(Path(path).suffix.lower(), ".mp4")


class LegalMaterialCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_patch = patch(
            "app.services.material_cache.utils.storage_dir",
            return_value=self.temp_dir.name,
        )
        self.storage_patch.start()

    def tearDown(self):
        self.storage_patch.stop()
        self.temp_dir.cleanup()

    def _wikimedia_item(self):
        return MaterialInfo(
            provider="wikimedia",
            url="https://upload.wikimedia.org/example.webm",
            duration=12,
            source_info={
                "provider": "wikimedia",
                "search_term": "private Saturn search",
                "asset_id": "File:Example.webm",
                "source_page": (
                    "https://commons.wikimedia.org/wiki/"
                    "File:Example.webm?tracking=drop"
                ),
                "creator": {
                    "name": "Jane Doe",
                    "profile_page": (
                        "https://commons.wikimedia.org/wiki/"
                        "User:Jane?token=drop"
                    ),
                    "private_email": "secret@example.org",
                },
                "rendition": {
                    "id": "original",
                    "width": 1920,
                    "height": 1080,
                    "secret": "drop-me",
                },
                "license": "CC BY 4.0",
                "license_url": (
                    "https://creativecommons.org/licenses/by/4.0/"
                    "?tracking=drop"
                ),
                "credit": "Example Observatory",
                "attribution": "Jane Doe",
                "attribution_required": True,
                "non_free": False,
                "restrictions": ["trademark"],
                "copyright_status": "copyrighted",
                "deletion_reason": "review-note",
                "mime": "video/webm",
                "sha256": (
                    "0123456789abcdef"
                    "0123456789abcdef"
                    "0123456789abcdef"
                    "0123456789abcdef"
                ),
                "api_key": "DO-NOT-CACHE",
                "signed_url": "https://example.org/?secret=yes",
            },
        )

    def test_cache_round_trip_preserves_legal_provenance(self):
        item = self._wikimedia_item()

        saved = material_cache.save_material_search_cache(
            provider="wikimedia",
            search_term="private Saturn search",
            minimum_duration=5,
            video_aspect=VideoAspect.landscape,
            items=[item],
        )

        loaded = material_cache.load_material_search_cache(
            provider="wikimedia",
            search_term="private Saturn search",
            minimum_duration=5,
            video_aspect=VideoAspect.landscape,
        )

        self.assertTrue(saved)
        self.assertEqual(len(loaded), 1)

        source = loaded[0].source_info

        self.assertEqual(source["license"], "CC BY 4.0")
        self.assertEqual(
            source["license_url"],
            "https://creativecommons.org/licenses/by/4.0/",
        )
        self.assertEqual(source["credit"], "Example Observatory")
        self.assertEqual(source["attribution"], "Jane Doe")
        self.assertTrue(source["attribution_required"])
        self.assertFalse(source["non_free"])
        self.assertEqual(source["restrictions"], ["trademark"])
        self.assertEqual(source["copyright_status"], "copyrighted")
        self.assertEqual(source["deletion_reason"], "review-note")
        self.assertEqual(source["mime"], "video/webm")
        self.assertEqual(len(source["sha256"]), 64)

        # Search term is restored from the caller, not persisted.
        self.assertEqual(
            source["search_term"],
            "private Saturn search",
        )

    def test_cache_payload_does_not_persist_query_or_secret_fields(self):
        material_cache.save_material_search_cache(
            provider="wikimedia",
            search_term="private Saturn search",
            minimum_duration=5,
            video_aspect=VideoAspect.landscape,
            items=[self._wikimedia_item()],
        )

        files = list(Path(self.temp_dir.name).glob("*.json"))
        self.assertEqual(len(files), 1)

        raw = files[0].read_text(encoding="utf-8")
        payload = json.loads(raw)

        self.assertNotIn("private Saturn search", raw)
        self.assertNotIn("DO-NOT-CACHE", raw)
        self.assertNotIn("secret@example.org", raw)
        self.assertNotIn("token=drop", raw)
        self.assertNotIn("tracking=drop", raw)
        self.assertNotIn("signed_url", raw)
        self.assertNotIn("api_key", raw)

        source = payload["items"][0]["source_info"]
        self.assertEqual(source["license"], "CC BY 4.0")
        self.assertEqual(source["mime"], "video/webm")


class MultiformatVideoCacheManagerTests(unittest.TestCase):
    def test_cache_manager_accepts_supported_video_cache_extensions(self):
        digest = "a" * 32

        for suffix in (".mp4", ".webm", ".ogv", ".ogg"):
            with self.subTest(suffix=suffix):
                self.assertIsNotNone(
                    cache_manager._VIDEO_CACHE_FILE_PATTERN.fullmatch(
                        f"vid-{digest}{suffix}"
                    )
                )

    def test_cache_manager_rejects_unmanaged_extensions(self):
        digest = "a" * 32

        for suffix in (".txt", ".json", ".exe", ".mkv", ""):
            with self.subTest(suffix=suffix):
                self.assertIsNone(
                    cache_manager._VIDEO_CACHE_FILE_PATTERN.fullmatch(
                        f"vid-{digest}{suffix}"
                    )
                )


class MaterialArtifactProvenanceTests(unittest.TestCase):
    def test_material_source_record_preserves_legal_provenance(self):
        item = MaterialInfo(
            provider="wikimedia",
            url=(
                "https://upload.wikimedia.org/"
                "example/Saturn.webm?tracking=remote"
            ),
            duration=42,
            source_info={
                "provider": "wikimedia",
                "search_term": "Saturn lightning",
                "asset_id": "File:Saturn.webm",
                "source_page": (
                    "https://commons.wikimedia.org/wiki/"
                    "File:Saturn.webm?tracking=drop"
                ),
                "creator": {
                    "name": "Example Author",
                    "profile_page": (
                        "https://commons.wikimedia.org/wiki/"
                        "User:Example?token=drop"
                    ),
                    "private_email": "secret@example.org",
                },
                "rendition": {
                    "id": "original",
                    "width": 1920,
                    "height": 1080,
                    "private_field": "drop-me",
                },
                "license": "CC BY 4.0",
                "license_url": (
                    "https://creativecommons.org/"
                    "licenses/by/4.0/?tracking=drop"
                ),
                "credit": "Example Observatory",
                "attribution": "Example Author",
                "attribution_required": True,
                "non_free": False,
                "restrictions": ["trademark"],
                "copyright_status": "copyrighted",
                "deletion_reason": "manual-review-note",
                "mime": "video/webm",
                "sha256": (
                    "0123456789abcdef"
                    "0123456789abcdef"
                    "0123456789abcdef"
                    "0123456789abcdef"
                ),
                "api_key": "DO-NOT-PERSIST",
                "signed_url": (
                    "https://example.invalid/"
                    "?token=DO-NOT-PERSIST"
                ),
            },
        )

        record = material._material_source_record(
            item,
            r"D:\private\task\vid-example.webm",
        )

        self.assertEqual(record["provider"], "wikimedia")
        self.assertEqual(
            record["local_file"],
            "vid-example.webm",
        )
        self.assertEqual(record["duration"], 42)
        self.assertEqual(
            record["search_term"],
            "Saturn lightning",
        )
        self.assertEqual(
            record["asset_id"],
            "File:Saturn.webm",
        )
        self.assertEqual(
            record["source_page"],
            (
                "https://commons.wikimedia.org/wiki/"
                "File:Saturn.webm"
            ),
        )

        self.assertEqual(
            record["creator"]["name"],
            "Example Author",
        )
        self.assertEqual(
            record["rendition"],
            {
                "id": "original",
                "width": 1920,
                "height": 1080,
            },
        )

        self.assertEqual(
            record["license"],
            "CC BY 4.0",
        )
        self.assertEqual(
            record["license_url"],
            (
                "https://creativecommons.org/"
                "licenses/by/4.0/"
            ),
        )
        self.assertEqual(
            record["credit"],
            "Example Observatory",
        )
        self.assertEqual(
            record["attribution"],
            "Example Author",
        )
        self.assertTrue(
            record["attribution_required"]
        )
        self.assertFalse(record["non_free"])
        self.assertEqual(
            record["restrictions"],
            ["trademark"],
        )
        self.assertEqual(
            record["copyright_status"],
            "copyrighted",
        )
        self.assertEqual(
            record["deletion_reason"],
            "manual-review-note",
        )
        self.assertEqual(
            record["mime"],
            "video/webm",
        )
        self.assertEqual(
            len(record["sha256"]),
            64,
        )

        serialized = repr(record)

        self.assertNotIn(
            "DO-NOT-PERSIST",
            serialized,
        )
        self.assertNotIn(
            "secret@example.org",
            serialized,
        )
        self.assertNotIn(
            "private_field",
            serialized,
        )
        self.assertNotIn(
            r"D:\private\task",
            serialized,
        )


class MaterialLocalSha256Tests(unittest.TestCase):
    def test_material_source_record_hashes_downloaded_local_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            local_path = Path(temp_dir) / "vid-example.webm"
            payload = b"Centinela local material provenance"
            local_path.write_bytes(payload)

            item = MaterialInfo(
                provider="wikimedia",
                url=(
                    "https://upload.wikimedia.org/"
                    "example.webm"
                ),
                duration=12,
                source_info={
                    "provider": "wikimedia",
                    "title": "File:Example.webm",
                    "file_url": (
                        "https://upload.wikimedia.org/"
                        "example.webm?tracking=drop"
                    ),
                    # Must never override the hash of the actual file.
                    "sha256": "0" * 64,
                },
            )

            record = material._material_source_record(
                item,
                str(local_path),
            )

            expected = hashlib.sha256(payload).hexdigest()

            self.assertEqual(record["sha256"], expected)
            self.assertNotEqual(record["sha256"], "0" * 64)
            self.assertEqual(
                record["local_file"],
                "vid-example.webm",
            )
            self.assertEqual(
                record["title"],
                "File:Example.webm",
            )
            self.assertEqual(
                record["file_url"],
                (
                    "https://upload.wikimedia.org/"
                    "example.webm"
                ),
            )


if __name__ == "__main__":
    unittest.main()
