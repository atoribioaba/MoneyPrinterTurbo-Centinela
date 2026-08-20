import unittest

from app.services.centinela.provenance import (
    safe_public_url,
    sanitize_provenance,
)


class ProvenanceTests(unittest.TestCase):
    def test_public_url_removes_query_and_fragment(self):
        result = safe_public_url(
            "https://example.org/file/video.mp4?token=SECRET#section"
        )

        self.assertEqual(
            result,
            "https://example.org/file/video.mp4",
        )

    def test_url_with_credentials_is_rejected(self):
        self.assertIsNone(
            safe_public_url(
                "https://user:password@example.org/private"
            )
        )

    def test_non_http_url_is_rejected(self):
        self.assertIsNone(
            safe_public_url("file:///C:/secret/video.mp4")
        )

    def test_provenance_keeps_only_local_filename(self):
        record = sanitize_provenance(
            {"provider": "wikimedia"},
            local_path=r"D:\private\folder\video.mp4",
        )

        self.assertEqual(record["local_file"], "video.mp4")
        self.assertNotIn(r"D:\private", str(record))

    def test_license_and_attribution_metadata_are_preserved(self):
        source = {
            "provider": "wikimedia",
            "asset_id": "File:Example.webm",
            "source_page": (
                "https://commons.wikimedia.org/wiki/"
                "File:Example.webm?tracking=abc"
            ),
            "license": "CC BY 4.0",
            "license_url": (
                "https://creativecommons.org/licenses/by/4.0/"
                "?utm_source=test"
            ),
            "credit": "Example Observatory",
            "attribution": "Example Author",
            "attribution_required": True,
            "non_free": False,
            "mime": "video/webm",
            "sha256": (
                "0123456789abcdef"
                "0123456789abcdef"
                "0123456789abcdef"
                "0123456789abcdef"
            ),
        }

        record = sanitize_provenance(source)

        self.assertEqual(record["provider"], "wikimedia")
        self.assertEqual(record["license"], "CC BY 4.0")
        self.assertEqual(
            record["license_url"],
            "https://creativecommons.org/licenses/by/4.0/",
        )
        self.assertEqual(record["credit"], "Example Observatory")
        self.assertEqual(record["attribution"], "Example Author")
        self.assertTrue(record["attribution_required"])
        self.assertFalse(record["non_free"])
        self.assertEqual(record["mime"], "video/webm")
        self.assertEqual(len(record["sha256"]), 64)

    def test_title_and_public_file_url_are_preserved(self):
        source = {
            "provider": "wikimedia",
            "title": "File:Saturn Lightning.ogv",
            "file_url": (
                "https://upload.wikimedia.org/wikipedia/"
                "commons/f/fc/Saturn_Lightning.ogv"
                "?utm_source=commons"
            ),
            "signed_url": (
                "https://example.invalid/download"
                "?token=DO-NOT-PERSIST"
            ),
        }

        record = sanitize_provenance(source)

        self.assertEqual(
            record["title"],
            "File:Saturn Lightning.ogv",
        )
        self.assertEqual(
            record["file_url"],
            (
                "https://upload.wikimedia.org/wikipedia/"
                "commons/f/fc/Saturn_Lightning.ogv"
            ),
        )

        serialized = repr(record)

        self.assertNotIn("signed_url", record)
        self.assertNotIn("DO-NOT-PERSIST", serialized)


    def test_unknown_and_secret_fields_are_not_persisted(self):
        source = {
            "provider": "example",
            "api_key": "DO-NOT-SAVE",
            "authorization": "Bearer SECRET",
            "signed_url": "https://example.org/?token=SECRET",
            "password": "SECRET",
            "unknown_field": "value",
        }

        record = sanitize_provenance(source)

        self.assertEqual(record, {"provider": "example"})

        serialized = repr(record)

        self.assertNotIn("DO-NOT-SAVE", serialized)
        self.assertNotIn("Bearer SECRET", serialized)
        self.assertNotIn("password", serialized)
        self.assertNotIn("signed_url", serialized)

    def test_creator_and_rendition_are_whitelisted(self):
        source = {
            "provider": "example",
            "creator": {
                "id": 123,
                "name": "Jane Doe",
                "profile_page": (
                    "https://example.org/users/jane?token=secret"
                ),
                "private_email": "private@example.org",
            },
            "rendition": {
                "id": "hd",
                "width": 1920,
                "height": 1080,
                "secret": "ignore",
            },
        }

        record = sanitize_provenance(source)

        self.assertEqual(
            record["creator"],
            {
                "id": "123",
                "name": "Jane Doe",
                "profile_page": "https://example.org/users/jane",
            },
        )

        self.assertEqual(
            record["rendition"],
            {
                "id": "hd",
                "width": 1920,
                "height": 1080,
            },
        )


if __name__ == "__main__":
    unittest.main()
