from types import SimpleNamespace

from app.services.centinela_control_plane import (
    CentinelaControlPlane,
    IntegrationStatus,
    get_engineering_inventory,
    inventory_summary,
)


class _SuccessfulOrchestrator:
    def execute(self, plan, handlers=None):
        return SimpleNamespace(
            succeeded=True,
            as_dict=lambda: {"status": "completed", "plan": plan},
        )


class _ExplodingOrchestrator:
    def execute(self, plan, handlers=None):
        raise RuntimeError("Authorization: Bearer should-not-leak")


def test_inventory_does_not_claim_all_engineering_is_wired():
    inventory = get_engineering_inventory()
    statuses = {item.status for item in inventory}

    assert IntegrationStatus.WIRED in statuses
    assert IntegrationStatus.AVAILABLE in statuses
    assert IntegrationStatus.PLACEHOLDER in statuses
    assert any(item.key == "publication_package" and item.status is IntegrationStatus.WIRED for item in inventory)


def test_inventory_summary_matches_inventory_length():
    summary = inventory_summary()
    assert sum(summary.values()) == len(get_engineering_inventory())


def test_control_plane_returns_successful_run_without_rewriting_payload():
    plane = CentinelaControlPlane(orchestrator=_SuccessfulOrchestrator())
    result = plane.execute("plan-for-test")

    assert result.success is True
    assert result.error is None
    assert result.run["status"] == "completed"


def test_control_plane_redacts_unexpected_boundary_error():
    plane = CentinelaControlPlane(orchestrator=_ExplodingOrchestrator())
    result = plane.execute("plan-for-test")

    assert result.success is False
    assert result.run is None
    assert result.error["code"] == "control_plane_execution_failed"
    assert "should-not-leak" not in str(result.error)
