from __future__ import annotations

import socket
from datetime import UTC, datetime

import pytest

from app.models.astronomy import ObserverContext
from app.services.centinela.event_calendar import EventCalendarService
from app.services.centinela.research_adapters.contracts import (
    ResearchContext,
    ResearchPhase,
    ResearchPhaseViolation,
)
from app.services.centinela.research_adapters.router import C3AstronomyResearchRouter
from webui.product import pages


def _observer() -> ObserverContext:
    return ObserverContext(
        latitude_deg=41.6523,
        longitude_deg=-4.7245,
        elevation_m=698.0,
        timezone="Europe/Madrid",
        name="Valladolid product fixture",
    )


class FakeUI:
    def __init__(self) -> None:
        self.session_state: dict = {}
        self.rows: list[dict] = []
        self.errors: list[str] = []

    def subheader(self, *args, **kwargs):
        return None

    def caption(self, *args, **kwargs):
        return None

    def radio(self, *args, **kwargs):
        return pages.AGENDA_FILTER_TODAY

    def button(self, *args, **kwargs):
        return True

    def dataframe(self, rows, **kwargs):
        self.rows = list(rows)

    def info(self, *args, **kwargs):
        return None

    def error(self, message, **kwargs):
        self.errors.append(str(message))


def test_product_control_center_factory_instantiates_c3_research_controller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    class FakeController:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(pages, "C3ResearchControlCenter", FakeController)
    service = pages._new_control_center()

    assert isinstance(service, FakeController)
    assert calls == [{"register_default_av": True}]


def test_agenda_panel_renders_with_local_engine_when_external_network_is_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_network(*args, **kwargs):
        raise AssertionError("Agenda Futura must not require external network")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    fixed_now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    ui = FakeUI()

    pages._render_agenda_futura(
        _observer(),
        ui=ui,
        calendar_factory=lambda observer: EventCalendarService(
            observer,
            now_provider=lambda: fixed_now,
        ),
    )

    assert ui.errors == []
    assert ui.rows
    assert all("Hora local" in row for row in ui.rows)
    assert all("Tipo" in row for row in ui.rows)
    assert all("Observador" in row for row in ui.rows)
    assert all("Detalles" in row for row in ui.rows)


@pytest.mark.parametrize(
    "phase",
    [
        ResearchPhase.SCRIPT,
        ResearchPhase.MEDIA,
        ResearchPhase.AUDIO,
        ResearchPhase.VIDEO_BASE,
        ResearchPhase.REVIEW,
        ResearchPhase.PUBLICATION,
    ],
)
def test_webui_research_router_rejects_non_research_phase_before_network(
    monkeypatch: pytest.MonkeyPatch,
    phase: ResearchPhase,
) -> None:
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network must not be reached outside RESEARCH")

    monkeypatch.setattr(
        "app.services.centinela.research_adapters.transport.requests.get",
        forbidden,
    )
    router = C3AstronomyResearchRouter()

    with pytest.raises(ResearchPhaseViolation):
        router(
            ResearchContext("webui-test", phase),
            {"nasa_apod": {"date": "2026-08-12"}},
        )

    assert called is False
