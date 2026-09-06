from types import SimpleNamespace

from app.services.centinela_control_plane import (
    CentinelaControlPlane,
    IntegrationStatus,
    get_engineering_inventory,
    inventory_summary,
)


class _SuccessfulBuilder:
    def __call__(self, request):
        return SimpleNamespace(
            model_dump=lambda mode="json": {"status": "WAITING_FOR_HUMAN_REVIEW", "request": request}
        )


class _ExplodingBuilder:
    def __call__(self, request):
        raise RuntimeError("Authorization: Bearer should-not-leak")


def test_inventory_does_not_claim_all_engineering_is_wired():
    inventory = get_engineering_inventory()
    statuses = {item.status for item in inventory}

    assert IntegrationStatus.WIRED in statuses
    assert IntegrationStatus.AVAILABLE in statuses
    assert IntegrationStatus.PARTIAL in statuses
    assert any(
        item.key == "production_orchestrator" and item.status is IntegrationStatus.WIRED
        for item in inventory
    )
    assert any(
        item.key == "publication_package" and item.status is IntegrationStatus.PARTIAL
        for item in inventory
    )


def test_inventory_summary_matches_inventory_length():
    summary = inventory_summary()
    assert sum(summary.values()) == len(get_engineering_inventory())


def test_control_plane_returns_builder_plan_without_rewriting_payload():
    plane = CentinelaControlPlane(builder=_SuccessfulBuilder())
    result = plane.build("request-for-test")

    assert result.success is True
    assert result.error is None
    assert result.plan["status"] == "WAITING_FOR_HUMAN_REVIEW"


def test_control_plane_redacts_unexpected_boundary_error():
    plane = CentinelaControlPlane(builder=_ExplodingBuilder())
    result = plane.build("request-for-test")

    assert result.success is False
    assert result.plan is None
    assert result.error["code"] == "control_plane_build_failed"
    assert "should-not-leak" not in str(result.error)
