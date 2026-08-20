import unittest
from unittest.mock import patch

import requests

from app.models.schema import VideoAspect
from app.services import material


class _FakeResponse:
    def __init__(
        self,
        payload=None,
        *,
        status_code=200,
        headers=None,
        url="",
    ):
        self._payload = (
            payload
            if payload is not None
            else {}
        )
        self.status_code = status_code
        self.headers = headers or {}
        self.url = url

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"status={self.status_code}"
            )


def _search_payload(
    *,
    nasa_id="NASA_Test",
    title="NASA Test",
    media_type="video",
    description="NASA science video",
    photographer=None,
    secondary_creator=None,
):
    record = {
        "nasa_id": nasa_id,
        "title": title,
        "media_type": media_type,
        "description": description,
        "center": "GSFC",
    }

    if photographer is not None:
        record[
            "photographer"
        ] = photographer

    if secondary_creator is not None:
        record[
            "secondary_creator"
        ] = secondary_creator

    return {
        "collection": {
            "items": [
                {
                    "data": [
                        record
                    ]
                }
            ]
        }
    }


def _asset_url(
    nasa_id,
    rendition,
    extension="mp4",
):
    return (
        "http://images-assets.nasa.gov/"
        f"video/{nasa_id}/"
        f"{nasa_id}~{rendition}.{extension}"
    )


def _metadata_url(
    nasa_id,
):
    return (
        "https://images-assets.nasa.gov/"
        f"video/{nasa_id}/metadata.json"
    )


def _asset_payload(
    nasa_id="NASA_Test",
    renditions=(
        ("orig", "mp4"),
        ("large", "mp4"),
        ("medium", "mp4"),
    ),
):
    return {
        "collection": {
            "items": [
                {
                    "href":
                        _asset_url(
                            nasa_id,
                            label,
                            extension,
                        )
                }
                for label, extension
                in renditions
            ]
        }
    }


def _metadata(
    *,
    duration="0:00:20",
    width=1920,
    height=1080,
    extra=None,
):
    payload = {
        "QuickTime:Duration":
            duration,
        "QuickTime:ImageWidth":
            width,
        "QuickTime:ImageHeight":
            height,
        "File:MIMEType":
            "video/mp4",
        "AVAIL:Center":
            "GSFC",
        "AVAIL:Owner":
            "internal-owner",
    }

    if extra:
        payload.update(extra)

    return payload


def _get_dispatch(
    *,
    nasa_id="NASA_Test",
    search=None,
    assets=None,
    metadata=None,
):
    search_payload = (
        search
        if search is not None
        else _search_payload(
            nasa_id=nasa_id
        )
    )

    asset_payload = (
        assets
        if assets is not None
        else _asset_payload(
            nasa_id=nasa_id
        )
    )

    metadata_payload = (
        metadata
        if metadata is not None
        else _metadata()
    )

    def dispatch(
        url,
        *args,
        **kwargs,
    ):
        if (
            url
            == material._NASA_API_URL
            + "/search"
        ):
            return _FakeResponse(
                search_payload,
                url=url,
            )

        if (
            url.startswith(
                material._NASA_API_URL
                + "/asset/"
            )
        ):
            return _FakeResponse(
                asset_payload,
                url=url,
            )

        if (
            url.startswith(
                material._NASA_API_URL
                + "/metadata/"
            )
        ):
            return _FakeResponse(
                {
                    "location":
                        _metadata_url(
                            nasa_id
                        )
                },
                url=url,
            )

        if (
            url
            == _metadata_url(
                nasa_id
            )
        ):
            return _FakeResponse(
                metadata_payload,
                url=url,
            )

        raise AssertionError(
            "unexpected GET: "
            + str(url)
        )

    return dispatch


def _head_dispatch(
    sizes,
):
    def dispatch(
        url,
        *args,
        **kwargs,
    ):
        label = (
            material.nasa_rendition_label(
                url
            )
        )

        if label not in sizes:
            raise AssertionError(
                "unexpected HEAD rendition: "
                + str(label)
            )

        return _FakeResponse(
            status_code=200,
            headers={
                "Content-Type":
                    "video/mp4",
                "Content-Length":
                    str(
                        sizes[label]
                    ),
                "Accept-Ranges":
                    "bytes",
            },
            url=url,
        )

    return dispatch


class TestNasaMaterialAdapter(
    unittest.TestCase
):
    def test_search_selects_policy_rendition_and_preserves_rights(self):
        nasa_id = (
            "GSFC_20220315_"
            "Webb_Alignment_Briefing"
        )

        with (
            patch.object(
                material.requests,
                "get",
                side_effect=_get_dispatch(
                    nasa_id=nasa_id,
                    search=_search_payload(
                        nasa_id=nasa_id,
                        title=(
                            "James Webb Space Telescope "
                            "Mirror Alignment Update"
                        ),
                        photographer=
                            "Mike McClare",
                        secondary_creator=
                            "Michael Starobin",
                    ),
                ),
            ) as get,
            patch.object(
                material.requests,
                "head",
                side_effect=_head_dispatch(
                    {
                        "orig":
                            4180226916,
                        "large":
                            2098679174,
                        "medium":
                            961279524,
                    }
                ),
            ) as head,
        ):
            results = (
                material.search_videos_nasa(
                    "James Webb",
                    minimum_duration=5,
                    video_aspect=
                        VideoAspect.landscape,
                )
            )

        self.assertEqual(
            len(results),
            1,
        )

        item = results[0]

        self.assertEqual(
            item.provider,
            "nasa",
        )

        self.assertEqual(
            item.duration,
            20,
        )

        self.assertTrue(
            item.url.startswith(
                "https://"
                "images-assets.nasa.gov/"
            )
        )

        self.assertIn(
            "~medium.mp4",
            item.url,
        )

        source = item.source_info

        self.assertEqual(
            source["provider"],
            "nasa",
        )

        self.assertEqual(
            source["asset_id"],
            nasa_id,
        )

        self.assertEqual(
            source["search_term"],
            "James Webb",
        )

        self.assertEqual(
            source["credit"],
            "NASA",
        )

        self.assertEqual(
            source["attribution"],
            "NASA",
        )

        self.assertTrue(
            source[
                "attribution_required"
            ]
        )

        self.assertEqual(
            source[
                "rights_basis"
            ],
            "NASA Media Usage Guidelines",
        )

        self.assertNotIn(
            "license",
            source,
        )

        self.assertEqual(
            source["mime"],
            "video/mp4",
        )

        self.assertEqual(
            source["rendition"]["id"],
            "medium",
        )

        self.assertEqual(
            source["rendition"]["width"],
            1920,
        )

        self.assertEqual(
            source["rendition"]["height"],
            1080,
        )

        self.assertEqual(
            source[
                "rendition"
            ][
                "dimensions_basis"
            ],
            "source_metadata",
        )

        self.assertEqual(
            source[
                "creator"
            ][
                "name"
            ],
            (
                "Mike McClare; "
                "Michael Starobin"
            ),
        )

        search_call = (
            get.call_args_list[0]
        )

        self.assertEqual(
            search_call.args[0],
            material._NASA_API_URL
            + "/search",
        )

        params = (
            search_call.kwargs[
                "params"
            ]
        )

        self.assertEqual(
            params["q"],
            "James Webb",
        )

        self.assertEqual(
            params["media_type"],
            "video",
        )

        self.assertNotIn(
            "key",
            params,
        )

        self.assertNotIn(
            "Authorization",
            search_call.kwargs[
                "headers"
            ],
        )

        self.assertEqual(
            head.call_count,
            3,
        )


    def test_third_party_rights_signal_never_reaches_head(self):
        search = _search_payload(
            description=(
                "Courtesy of "
                "Example Observatory"
            )
        )

        with (
            patch.object(
                material.requests,
                "get",
                side_effect=_get_dispatch(
                    search=search,
                ),
            ),
            patch.object(
                material.requests,
                "head",
            ) as head,
        ):
            results = (
                material.search_videos_nasa(
                    "example",
                    minimum_duration=5,
                    video_aspect=
                        VideoAspect.landscape,
                )
            )

        self.assertEqual(
            results,
            [],
        )

        head.assert_not_called()


    def test_explicit_copyright_metadata_never_auto_enters(self):
        metadata = _metadata(
            extra={
                "Copyright":
                    "Example Studio"
            }
        )

        with (
            patch.object(
                material.requests,
                "get",
                side_effect=_get_dispatch(
                    metadata=metadata,
                ),
            ),
            patch.object(
                material.requests,
                "head",
            ) as head,
        ):
            results = (
                material.search_videos_nasa(
                    "example",
                    minimum_duration=5,
                    video_aspect=
                        VideoAspect.landscape,
                )
            )

        self.assertEqual(
            results,
            [],
        )

        head.assert_not_called()


    def test_wrong_orientation_fails_before_rendition_head(self):
        with (
            patch.object(
                material.requests,
                "get",
                side_effect=_get_dispatch(),
            ),
            patch.object(
                material.requests,
                "head",
            ) as head,
        ):
            results = (
                material.search_videos_nasa(
                    "landscape",
                    minimum_duration=5,
                    video_aspect=
                        VideoAspect.portrait,
                )
            )

        self.assertEqual(
            results,
            [],
        )

        head.assert_not_called()


    def test_missing_or_invalid_duration_fails_closed(self):
        for duration in (
            None,
            "",
            "not-a-duration",
            "0:00:00",
        ):
            with self.subTest(
                duration=duration
            ):
                metadata = _metadata(
                    duration=duration
                )

                with (
                    patch.object(
                        material.requests,
                        "get",
                        side_effect=
                            _get_dispatch(
                                metadata=
                                    metadata,
                            ),
                    ),
                    patch.object(
                        material.requests,
                        "head",
                    ) as head,
                ):
                    results = (
                        material.search_videos_nasa(
                            "example",
                            minimum_duration=5,
                            video_aspect=
                                VideoAspect.landscape,
                        )
                    )

                self.assertEqual(
                    results,
                    [],
                )

                head.assert_not_called()


    def test_mov_original_is_not_auto_selected_until_transport_supports_mov(self):
        nasa_id = (
            "GSFC_20140421_"
            "EarthOrbit_m11525"
        )

        assets = _asset_payload(
            nasa_id=nasa_id,
            renditions=(
                ("orig", "mov"),
                ("medium", "mp4"),
            ),
        )

        with (
            patch.object(
                material.requests,
                "get",
                side_effect=_get_dispatch(
                    nasa_id=nasa_id,
                    search=_search_payload(
                        nasa_id=nasa_id,
                        title=
                            "Earth from Orbit 2013",
                    ),
                    assets=assets,
                ),
            ),
            patch.object(
                material.requests,
                "head",
                side_effect=_head_dispatch(
                    {
                        "medium":
                            65068407,
                    }
                ),
            ) as head,
        ):
            results = (
                material.search_videos_nasa(
                    "Earth",
                    minimum_duration=5,
                    video_aspect=
                        VideoAspect.landscape,
                )
            )

        self.assertEqual(
            len(results),
            1,
        )

        self.assertIn(
            "~medium.mp4",
            results[0].url,
        )

        self.assertNotIn(
            ".mov",
            results[0].url,
        )

        self.assertEqual(
            head.call_count,
            1,
        )


    def test_external_asset_host_is_rejected(self):
        nasa_id = "NASA_Test"

        assets = {
            "collection": {
                "items": [
                    {
                        "href":
                            "https://example.com/"
                            "NASA_Test~large.mp4"
                    }
                ]
            }
        }

        with (
            patch.object(
                material.requests,
                "get",
                side_effect=_get_dispatch(
                    nasa_id=nasa_id,
                    assets=assets,
                ),
            ),
            patch.object(
                material.requests,
                "head",
            ) as head,
        ):
            results = (
                material.search_videos_nasa(
                    "example",
                    minimum_duration=5,
                    video_aspect=
                        VideoAspect.landscape,
                )
            )

        self.assertEqual(
            results,
            [],
        )

        head.assert_not_called()


    def test_head_mime_mismatch_rejects_candidate(self):
        def bad_head(
            url,
            *args,
            **kwargs,
        ):
            return _FakeResponse(
                status_code=200,
                headers={
                    "Content-Type":
                        "text/html",
                    "Content-Length":
                        "1000",
                },
                url=url,
            )

        with (
            patch.object(
                material.requests,
                "get",
                side_effect=_get_dispatch(),
            ),
            patch.object(
                material.requests,
                "head",
                side_effect=bad_head,
            ),
        ):
            results = (
                material.search_videos_nasa(
                    "example",
                    minimum_duration=5,
                    video_aspect=
                        VideoAspect.landscape,
                )
            )

        self.assertEqual(
            results,
            [],
        )


    def test_search_network_failure_returns_empty_without_fallback(self):
        with patch.object(
            material.requests,
            "get",
            side_effect=
                requests.ConnectionError(
                    "temporary NASA failure"
                ),
        ):
            results = (
                material.search_videos_nasa(
                    "Saturn",
                    minimum_duration=5,
                    video_aspect=
                        VideoAspect.landscape,
                )
            )

        self.assertEqual(
            results,
            [],
        )


    def test_registered_nasa_routes_to_search_adapter(self):
        self.assertTrue(
            callable(
                material.search_videos_nasa
            )
        )

        provider_id, adapter = (
            material._resolve_remote_video_search_provider(
                "nasa"
            )
        )

        self.assertEqual(
            provider_id,
            "nasa",
        )

        self.assertIs(
            adapter,
            material.search_videos_nasa,
        )


if __name__ == "__main__":
    unittest.main()
