import unittest

from app.services.centinela.licensing import LicenseDecision
from app.services.centinela.provenance import sanitize_provenance
from app.services.centinela.wikimedia import (
    assess_wikimedia_license,
    normalize_wikimedia_extmetadata,
)


def _field(value):
    return {"value": value, "source": "commons-desc-page"}


class WikimediaLicenseContractTests(unittest.TestCase):
    def test_public_domain_is_accepted(self):
        source = normalize_wikimedia_extmetadata(
            {
                "LicenseShortName": _field("Public domain"),
                "Copyrighted": _field("False"),
                "NonFree": _field("False"),
            }
        )

        result = assess_wikimedia_license(source)

        self.assertEqual(result.decision, LicenseDecision.ACCEPT)

    def test_cc0_is_accepted(self):
        source = normalize_wikimedia_extmetadata(
            {
                "LicenseShortName": _field("CC0 1.0"),
                "NonFree": _field("False"),
            }
        )

        self.assertEqual(
            assess_wikimedia_license(source).decision,
            LicenseDecision.ACCEPT,
        )

    def test_cc_by_requires_attribution(self):
        source = normalize_wikimedia_extmetadata(
            {
                "LicenseShortName": _field("CC BY 4.0"),
                "LicenseUrl": _field(
                    "https://creativecommons.org/licenses/by/4.0/?tracking=x"
                ),
                "Artist": _field(
                    '<a href="https://example.invalid">Jane Doe</a>'
                ),
                "Credit": _field("<b>Example Observatory</b>"),
                "AttributionRequired": _field("True"),
                "NonFree": _field("False"),
            }
        )

        result = assess_wikimedia_license(source)

        self.assertEqual(
            result.decision,
            LicenseDecision.ACCEPT_WITH_ATTRIBUTION,
        )
        self.assertEqual(source["creator"]["name"], "Jane Doe")
        self.assertEqual(source["credit"], "Example Observatory")
        self.assertEqual(
            source["license_url"],
            "https://creativecommons.org/licenses/by/4.0/",
        )

    def test_cc_by_sa_requires_manual_review(self):
        source = normalize_wikimedia_extmetadata(
            {
                "LicenseShortName": _field("CC BY-SA 4.0"),
                "NonFree": _field("False"),
            }
        )

        self.assertEqual(
            assess_wikimedia_license(source).decision,
            LicenseDecision.REVIEW,
        )

    def test_non_free_is_rejected(self):
        source = normalize_wikimedia_extmetadata(
            {
                "LicenseShortName": _field("Example license"),
                "NonFree": _field("True"),
            }
        )

        self.assertEqual(
            assess_wikimedia_license(source).decision,
            LicenseDecision.REJECT,
        )

    def test_nc_or_nd_license_is_rejected(self):
        for license_name in (
            "CC BY-NC 4.0",
            "CC BY-ND 4.0",
        ):
            with self.subTest(license_name=license_name):
                source = normalize_wikimedia_extmetadata(
                    {
                        "LicenseShortName": _field(license_name),
                    }
                )

                self.assertEqual(
                    assess_wikimedia_license(source).decision,
                    LicenseDecision.REJECT,
                )

    def test_restrictions_force_manual_review(self):
        source = normalize_wikimedia_extmetadata(
            {
                "LicenseShortName": _field("Public domain"),
                "Restrictions": _field(
                    ["trademark", "personality"]
                ),
            }
        )

        result = assess_wikimedia_license(source)

        self.assertEqual(result.decision, LicenseDecision.REVIEW)
        self.assertEqual(
            source["restrictions"],
            ["trademark", "personality"],
        )

    def test_deletion_marker_forces_manual_review(self):
        source = normalize_wikimedia_extmetadata(
            {
                "LicenseShortName": _field("CC0 1.0"),
                "DeletionReason": _field("Copyright review"),
            }
        )

        self.assertEqual(
            assess_wikimedia_license(source).decision,
            LicenseDecision.REVIEW,
        )

    def test_missing_license_requires_review(self):
        source = normalize_wikimedia_extmetadata({})

        self.assertEqual(
            assess_wikimedia_license(source).decision,
            LicenseDecision.REVIEW,
        )

    def test_multi_license_requires_review(self):
        source = normalize_wikimedia_extmetadata(
            {
                "LicenseShortName": _field(
                    "CC BY 4.0 / GFDL"
                ),
            }
        )

        self.assertEqual(
            assess_wikimedia_license(source).decision,
            LicenseDecision.REVIEW,
        )

    def test_html_and_unknown_fields_do_not_escape_provenance(self):
        source = normalize_wikimedia_extmetadata(
            {
                "LicenseShortName": _field("<b>CC BY 4.0</b>"),
                "Artist": _field(
                    '<span>Jane Doe</span>'
                    '<script>SECRET_SCRIPT</script>'
                ),
                "Credit": _field("<i>Observatory</i>"),
                "UnknownSecret": _field("DO-NOT-PERSIST"),
            }
        )

        record = sanitize_provenance(source)
        serialized = repr(record)

        self.assertEqual(record["license"], "CC BY 4.0")
        self.assertEqual(
            record["creator"]["name"],
            "Jane Doe",
        )
        self.assertEqual(record["credit"], "Observatory")
        self.assertNotIn("SECRET_SCRIPT", serialized)
        self.assertNotIn("DO-NOT-PERSIST", serialized)


if __name__ == "__main__":
    unittest.main()