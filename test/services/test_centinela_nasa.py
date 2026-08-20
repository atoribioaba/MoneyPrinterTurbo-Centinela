from app.services.centinela.licensing import (
    LicenseDecision,
)
from app.services.centinela.nasa import (
    NASA_MEDIA_USAGE_GUIDELINES,
    NASA_MEDIA_USAGE_GUIDELINES_URL,
    NASA_RENDITION_SOFT_CAP_BYTES,
    assess_nasa_rights,
    normalize_nasa_asset_url,
    normalize_nasa_rights,
    nasa_rendition_label,
    parse_nasa_duration,
    select_nasa_rendition,
)
from app.services.centinela.provenance import (
    sanitize_provenance,
)


def nasa_url(
    nasa_id,
    rendition,
    extension="mp4",
    scheme="http",
):
    return (
        f"{scheme}://images-assets.nasa.gov/"
        f"video/{nasa_id}/"
        f"{nasa_id}~{rendition}.{extension}"
    )


def test_asset_url_upgrades_only_trusted_nasa_host():
    raw = nasa_url(
        "Moon and Saturn",
        "orig",
    )

    normalized = (
        normalize_nasa_asset_url(
            raw
        )
    )

    assert normalized.startswith(
        "https://images-assets.nasa.gov/"
    )

    assert (
        normalize_nasa_asset_url(
            "http://example.com/video.mp4"
        )
        == ""
    )


def test_duration_parses_live_nasa_exiftool_shapes():
    assert (
        parse_nasa_duration(
            "0:14:23"
        )
        == 863.0
    )

    assert (
        parse_nasa_duration(
            "1:10:15"
        )
        == 4215.0
    )

    assert (
        parse_nasa_duration(
            104
        )
        == 104.0
    )

    assert (
        parse_nasa_duration(
            "not-a-duration"
        )
        is None
    )

    assert (
        parse_nasa_duration(
            "0:00:00"
        )
        is None
    )


def test_nasa_rights_accepts_official_asset_with_attribution():
    source = normalize_nasa_rights(
        {
            "title":
                "Orion Sees the Moon and Saturn",
            "description":
                "On flight day 4 Orion caught this view.",
        },
        {
            "AVAIL:Center": "JSC",
            "AVAIL:Owner": "lcheshie",
            "AVAIL:Photographer": "",
        },
        asset_url=nasa_url(
            "Moon and Saturn",
            "orig",
        ),
    )

    assessment = (
        assess_nasa_rights(
            source
        )
    )

    assert (
        assessment.decision
        is LicenseDecision.ACCEPT_WITH_ATTRIBUTION
    )

    assert source["credit"] == "NASA"
    assert source[
        "attribution"
    ] == "NASA"

    assert (
        source[
            "attribution_required"
        ]
        is True
    )

    assert (
        source["rights_basis"]
        == NASA_MEDIA_USAGE_GUIDELINES
    )

    assert (
        source["rights_url"]
        == NASA_MEDIA_USAGE_GUIDELINES_URL
    )

    assert "license" not in source

    # AVAIL:Owner is operational metadata,
    # not interpreted as a copyright holder.
    assert (
        source[
            "third_party_signal"
        ]
        is False
    )


def test_nasa_rights_preserves_creators_without_rejecting():
    source = normalize_nasa_rights(
        {
            "photographer":
                "Mike McClare",
            "secondary_creator":
                "Michael Starobin",
        },
        {
            "AVAIL:Owner": "rmelnick",
        },
        asset_url=nasa_url(
            "GSFC_Webb",
            "large",
        ),
    )

    assert source["creator"] == {
        "name":
            "Mike McClare; Michael Starobin"
    }

    assert (
        assess_nasa_rights(
            source
        ).decision
        is LicenseDecision.ACCEPT_WITH_ATTRIBUTION
    )


def test_nasa_rights_reviews_explicit_third_party_signals():
    for description in (
        "Copyright Example Studio",
        "© Example Studio",
        "Used with permission from Example Studio",
        "Courtesy of Example Observatory",
        "All rights reserved",
    ):
        source = normalize_nasa_rights(
            {
                "description":
                    description,
            },
            {},
            asset_url=nasa_url(
                "ThirdPartyCase",
                "large",
            ),
        )

        assert (
            assess_nasa_rights(
                source
            ).decision
            is LicenseDecision.REVIEW
        )


def test_courtesy_of_nasa_is_not_third_party_signal():
    source = normalize_nasa_rights(
        {
            "description":
                "Courtesy of NASA.",
        },
        {},
        asset_url=nasa_url(
            "NasaCourtesy",
            "large",
        ),
    )

    assert (
        source[
            "third_party_signal"
        ]
        is False
    )

    assert (
        assess_nasa_rights(
            source
        ).decision
        is LicenseDecision.ACCEPT_WITH_ATTRIBUTION
    )


def test_explicit_rights_metadata_requires_review():
    source = normalize_nasa_rights(
        {},
        {
            "Copyright":
                "Example Studio",
        },
        asset_url=nasa_url(
            "ExplicitRights",
            "large",
        ),
    )

    assert source[
        "rights_evidence"
    ]

    assert (
        assess_nasa_rights(
            source
        ).decision
        is LicenseDecision.REVIEW
    )


def test_external_asset_host_requires_review():
    source = normalize_nasa_rights(
        {},
        {},
        asset_url=(
            "https://example.com/"
            "third-party.mp4"
        ),
    )

    assert (
        assess_nasa_rights(
            source
        ).decision
        is LicenseDecision.REVIEW
    )


def test_provenance_preserves_nasa_rights_basis_not_fake_license():
    source = normalize_nasa_rights(
        {},
        {},
        asset_url=nasa_url(
            "Moon and Saturn",
            "orig",
        ),
    )

    record = sanitize_provenance(
        source,
        provider="nasa",
    )

    assert (
        record["rights_basis"]
        == NASA_MEDIA_USAGE_GUIDELINES
    )

    assert (
        record["rights_url"]
        == NASA_MEDIA_USAGE_GUIDELINES_URL
    )

    assert record["credit"] == "NASA"
    assert (
        record[
            "attribution_required"
        ]
        is True
    )

    assert "license" not in record


def test_rendition_label_supports_mp4_and_original_mov():
    assert (
        nasa_rendition_label(
            nasa_url(
                "Example",
                "large",
            )
        )
        == "large"
    )

    assert (
        nasa_rendition_label(
            nasa_url(
                "EarthOrbit",
                "orig",
                extension="mov",
            )
        )
        == "orig"
    )


def test_rendition_policy_matches_moon_saturn_evidence():
    result = select_nasa_rendition(
        [
            {
                "url":
                    nasa_url(
                        "Moon and Saturn",
                        "orig",
                    ),
                "content_length":
                    124708737,
            },
            {
                "url":
                    nasa_url(
                        "Moon and Saturn",
                        "large",
                    ),
                "content_length":
                    588152751,
            },
            {
                "url":
                    nasa_url(
                        "Moon and Saturn",
                        "medium",
                    ),
                "content_length":
                    266472359,
            },
        ]
    )

    assert result["label"] == "large"


def test_rendition_policy_matches_mars_evidence():
    result = select_nasa_rendition(
        [
            {
                "url":
                    nasa_url(
                        "Mars",
                        "orig",
                    ),
                "content_length":
                    576129829,
            },
            {
                "url":
                    nasa_url(
                        "Mars",
                        "medium",
                    ),
                "content_length":
                    1229845404,
            },
        ]
    )

    assert result["label"] == "orig"


def test_rendition_policy_matches_webb_evidence():
    result = select_nasa_rendition(
        [
            {
                "url":
                    nasa_url(
                        "Webb",
                        "orig",
                    ),
                "content_length":
                    4180226916,
            },
            {
                "url":
                    nasa_url(
                        "Webb",
                        "large",
                    ),
                "content_length":
                    2098679174,
            },
            {
                "url":
                    nasa_url(
                        "Webb",
                        "medium",
                    ),
                "content_length":
                    961279524,
            },
        ]
    )

    assert result["label"] == "medium"


def test_rendition_policy_matches_earth_orbit_evidence():
    result = select_nasa_rendition(
        [
            {
                "url":
                    nasa_url(
                        "EarthOrbit",
                        "orig",
                        extension="mov",
                    ),
                "content_length":
                    256191407,
            },
            {
                "url":
                    nasa_url(
                        "EarthOrbit",
                        "medium",
                    ),
                "content_length":
                    65068407,
            },
        ]
    )

    assert result["label"] == "orig"
    assert result["suffix"] == ".mov"


def test_rendition_unknown_size_uses_conservative_fallback():
    result = select_nasa_rendition(
        [
            {
                "url":
                    nasa_url(
                        "Unknown",
                        "orig",
                    ),
            },
            {
                "url":
                    nasa_url(
                        "Unknown",
                        "large",
                    ),
            },
            {
                "url":
                    nasa_url(
                        "Unknown",
                        "medium",
                    ),
            },
        ]
    )

    assert result["label"] == "medium"


def test_rendition_falls_back_to_mobile_when_primary_absent():
    result = select_nasa_rendition(
        [
            {
                "url":
                    nasa_url(
                        "Fallback",
                        "preview",
                    ),
            },
            {
                "url":
                    nasa_url(
                        "Fallback",
                        "mobile",
                    ),
            },
        ]
    )

    assert result["label"] == "mobile"


def test_rendition_rejects_external_and_nonvideo_assets():
    assert (
        select_nasa_rendition(
            [
                {
                    "url":
                        "https://example.com/video.mp4",
                    "content_length":
                        1000,
                },
                {
                    "url":
                        (
                            "https://images-assets.nasa.gov/"
                            "image/example.jpg"
                        ),
                    "content_length":
                        1000,
                },
            ]
        )
        is None
    )


def test_default_soft_cap_is_one_gib():
    assert (
        NASA_RENDITION_SOFT_CAP_BYTES
        == 1073741824
    )
