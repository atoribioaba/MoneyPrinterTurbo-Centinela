import unittest
from unittest.mock import Mock, patch

from app.models.schema import VideoAspect
from app.services import material


def _extmetadata(
    license_name="Public domain",
    *,
    attribution_required=False,
    non_free=False,
    restrictions=None,
):
    metadata = {
        "LicenseShortName": {
            "value": license_name,
        },
        "Artist": {
            "value": "<b>Example Author</b>",
        },
        "Credit": {
            "value": "Example Observatory",
        },
        "AttributionRequired": {
            "value": (
                "true"
                if attribution_required
                else "false"
            ),
        },
        "NonFree": {
            "value": (
                "true"
                if non_free
                else "false"
            ),
        },
    }

    if license_name == "CC BY 4.0":
        metadata["LicenseUrl"] = {
            "value": (
                "https://creativecommons.org/"
                "licenses/by/4.0/"
            )
        }

    if license_name == "CC BY-SA 4.0":
        metadata["LicenseUrl"] = {
            "value": (
                "https://creativecommons.org/"
                "licenses/by-sa/4.0/"
            )
        }

    if restrictions:
        metadata["Restrictions"] = {
            "value": restrictions,
        }

    return metadata


def _page(
    *,
    title,
    url,
    mime,
    width,
    height,
    duration,
    license_name="Public domain",
    attribution_required=False,
    non_free=False,
    mediatype="VIDEO",
    restrictions=None,
):
    return {
        "pageid": 123,
        "title": title,
        "canonicalurl": (
            "https://commons.wikimedia.org/wiki/"
            + title.replace(" ", "_")
            + "?tracking=drop"
        ),
        "imageinfo": [
            {
                "url": url,
                "mime": mime,
                "mediatype": mediatype,
                "width": width,
                "height": height,
                "metadata": [
                    {
                        "name": "length",
                        "value": duration,
                    }
                ],
                "extmetadata": _extmetadata(
                    license_name,
                    attribution_required=(
                        attribution_required
                    ),
                    non_free=non_free,
                    restrictions=restrictions,
                ),
            }
        ],
    }


def _response(pages):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "query": {
            "pages": pages,
        }
    }
    return response


class WikimediaSearchAdapterTests(unittest.TestCase):
    def test_search_returns_only_auto_accepted_requested_orientation(self):
        pages = [
            _page(
                title="File:Accepted portrait.webm",
                url=(
                    "https://upload.wikimedia.org/"
                    "accepted-portrait.webm?utm_source=commons"
                ),
                mime="video/webm",
                width=1080,
                height=1920,
                duration=12.8,
                license_name="CC BY 4.0",
                attribution_required=True,
            ),
            _page(
                title="File:Review portrait.webm",
                url=(
                    "https://upload.wikimedia.org/"
                    "review-portrait.webm"
                ),
                mime="video/webm",
                width=1080,
                height=1920,
                duration=20,
                license_name="CC BY-SA 4.0",
                attribution_required=True,
            ),
            _page(
                title="File:Landscape public domain.ogv",
                url=(
                    "https://upload.wikimedia.org/"
                    "landscape-public-domain.ogv"
                ),
                mime="application/ogg",
                width=1920,
                height=1080,
                duration=30,
                license_name="Public domain",
            ),
            _page(
                title="File:Too short.webm",
                url=(
                    "https://upload.wikimedia.org/"
                    "too-short.webm"
                ),
                mime="video/webm",
                width=1080,
                height=1920,
                duration=2,
                license_name="Public domain",
            ),
        ]

        response = _response(pages)

        with patch.object(
            material.requests,
            "get",
            return_value=response,
        ) as request:
            results = material.search_videos_wikimedia(
                "Saturn",
                minimum_duration=5,
                video_aspect=VideoAspect.portrait,
            )

        self.assertEqual(len(results), 1)

        item = results[0]

        self.assertEqual(item.provider, "wikimedia")
        self.assertEqual(item.duration, 12)
        self.assertEqual(
            item.url,
            (
                "https://upload.wikimedia.org/"
                "accepted-portrait.webm"
            ),
        )

        source = item.source_info

        self.assertEqual(
            source["title"],
            "File:Accepted portrait.webm",
        )
        self.assertEqual(
            source["asset_id"],
            "File:Accepted portrait.webm",
        )
        self.assertEqual(
            source["search_term"],
            "Saturn",
        )
        self.assertEqual(
            source["license"],
            "CC BY 4.0",
        )
        self.assertTrue(
            source["attribution_required"]
        )
        self.assertEqual(
            source["mime"],
            "video/webm",
        )
        self.assertEqual(
            source["rendition"],
            {
                "id": "original",
                "width": 1080,
                "height": 1920,
            },
        )
        self.assertNotIn(
            "tracking=drop",
            source["source_page"],
        )

        kwargs = request.call_args.kwargs

        self.assertEqual(
            request.call_args.args[0],
            material._WIKIMEDIA_API_URL,
        )
        self.assertEqual(
            kwargs["params"]["generator"],
            "search",
        )
        self.assertEqual(
            kwargs["params"]["gsrnamespace"],
            6,
        )
        self.assertEqual(
            kwargs["params"]["gsrsearch"],
            "Saturn",
        )
        self.assertIn(
            "extmetadata",
            kwargs["params"]["iiprop"],
        )
        self.assertIn(
            "LicenseShortName",
            kwargs["params"][
                "iiextmetadatafilter"
            ],
        )
        self.assertNotIn(
            "key",
            kwargs["params"],
        )
        self.assertIn("verify", kwargs)
        self.assertIn("proxies", kwargs)

    def test_public_domain_ogv_application_ogg_is_accepted(self):
        page = _page(
            title="File:Saturn Lightning.ogv",
            url=(
                "https://upload.wikimedia.org/"
                "wikipedia/commons/f/fc/"
                "Saturn_Lightning.ogv"
                "?utm_source=commons"
            ),
            mime="application/ogg",
            width=1280,
            height=720,
            duration=149.4,
            license_name="Public domain",
        )

        with patch.object(
            material.requests,
            "get",
            return_value=_response([page]),
        ):
            results = material.search_videos_wikimedia(
                "Saturn Lightning",
                minimum_duration=5,
                video_aspect=VideoAspect.landscape,
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0].url,
            (
                "https://upload.wikimedia.org/"
                "wikipedia/commons/f/fc/"
                "Saturn_Lightning.ogv"
            ),
        )
        self.assertEqual(
            results[0].source_info["license"],
            "Public domain",
        )
        self.assertEqual(
            results[0].source_info["mime"],
            "application/ogg",
        )

    def test_review_reject_and_restricted_material_never_auto_enter(self):
        pages = [
            _page(
                title="File:Share alike.webm",
                url=(
                    "https://upload.wikimedia.org/"
                    "share-alike.webm"
                ),
                mime="video/webm",
                width=1920,
                height=1080,
                duration=20,
                license_name="CC BY-SA 4.0",
            ),
            _page(
                title="File:Non free.webm",
                url=(
                    "https://upload.wikimedia.org/"
                    "non-free.webm"
                ),
                mime="video/webm",
                width=1920,
                height=1080,
                duration=20,
                non_free=True,
            ),
            _page(
                title="File:Restricted.webm",
                url=(
                    "https://upload.wikimedia.org/"
                    "restricted.webm"
                ),
                mime="video/webm",
                width=1920,
                height=1080,
                duration=20,
                restrictions="Trademark restrictions",
            ),
        ]

        with patch.object(
            material.requests,
            "get",
            return_value=_response(pages),
        ):
            results = material.search_videos_wikimedia(
                "restricted",
                minimum_duration=5,
                video_aspect=VideoAspect.landscape,
            )

        self.assertEqual(results, [])

    def test_non_video_or_unsupported_container_is_rejected(self):
        pages = [
            _page(
                title="File:Not video.jpg",
                url=(
                    "https://upload.wikimedia.org/"
                    "not-video.jpg"
                ),
                mime="image/jpeg",
                width=1920,
                height=1080,
                duration=20,
                mediatype="BITMAP",
            ),
            _page(
                title="File:Unsupported.avi",
                url=(
                    "https://upload.wikimedia.org/"
                    "unsupported.avi"
                ),
                mime="video/x-msvideo",
                width=1920,
                height=1080,
                duration=20,
            ),
        ]

        with patch.object(
            material.requests,
            "get",
            return_value=_response(pages),
        ):
            results = material.search_videos_wikimedia(
                "example",
                minimum_duration=5,
                video_aspect=VideoAspect.landscape,
            )

        self.assertEqual(results, [])

    def test_missing_or_invalid_duration_fails_closed(self):
        for value in (
            None,
            "",
            "not-a-number",
            0,
            -1,
        ):
            with self.subTest(value=value):
                info = {
                    "metadata": [
                        {
                            "name": "length",
                            "value": value,
                        }
                    ]
                }

                self.assertIsNone(
                    material._wikimedia_duration_seconds(
                        info
                    )
                )

    def test_square_output_keeps_crop_compatible_accepted_video(self):
        page = _page(
            title="File:Landscape.webm",
            url=(
                "https://upload.wikimedia.org/"
                "landscape.webm"
            ),
            mime="video/webm",
            width=1920,
            height=1080,
            duration=20,
        )

        with patch.object(
            material.requests,
            "get",
            return_value=_response([page]),
        ):
            results = material.search_videos_wikimedia(
                "landscape",
                minimum_duration=5,
                video_aspect=VideoAspect.square,
            )

        self.assertEqual(len(results), 1)

    def test_registered_wikimedia_routes_to_search_adapter(self):
        provider_id, adapter = (
            material._resolve_remote_video_search_provider(
                "wikimedia"
            )
        )

        self.assertEqual(
            provider_id,
            "wikimedia",
        )
        self.assertIs(
            adapter,
            material.search_videos_wikimedia,
        )

    def test_network_failure_returns_empty_without_fallback(self):
        with patch.object(
            material.requests,
            "get",
            side_effect=RuntimeError(
                "temporary Commons failure"
            ),
        ):
            results = material.search_videos_wikimedia(
                "Saturn",
                minimum_duration=5,
                video_aspect=VideoAspect.landscape,
            )

        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
