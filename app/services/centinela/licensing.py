"""Generic licensing decisions used by Centinela material providers."""

from dataclasses import dataclass
from enum import Enum


class LicenseDecision(str, Enum):
    ACCEPT = "accept"
    ACCEPT_WITH_ATTRIBUTION = "accept_with_attribution"
    REVIEW = "review"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class LicenseAssessment:
    decision: LicenseDecision
    reason: str