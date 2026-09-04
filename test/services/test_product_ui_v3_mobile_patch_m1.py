from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.services.centinela.event_calendar import RawCalendarEvent
from webui.product import mobile_pages


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _event_with_provenance(provenance: dict) -> SimpleNamespace:
    return SimpleNamespace(
        canonical_quantity=SimpleNamespace(provenance=provenance),
        event_type="apparent_conjunction",
        label_es="Conjunción aparente de moon y uranus",
        body="moon",
        details={"body_pair": ["moon", "uranus"]},
    )


def test_future_agenda_excludes_past_events_with_timezone_aware_cutoff() -> None:
    madrid = ZoneInfo("Europe/Madrid")
    now_local = datetime(2026, 9, 4, 18, 0, tzinfo=madrid)
    events = (
        RawCalendarEvent(
            event_type="past_day",
            label_es="Pasado",
            time_utc=datetime(2026, 9, 3, 20, 0, tzinfo=UTC),
        ),
        RawCalendarEvent(
            event_type="past_same_day",
            label_es="Hoy ya pasado",
            time_utc=datetime(2026, 9, 4, 15, 0, tzinfo=UTC),
        ),
        RawCalendarEvent(
            event_type="future_same_day",
            label_es="Hoy futuro",
            time_utc=datetime(2026, 9, 4, 17, 0, tzinfo=UTC),
        ),
        RawCalendarEvent(
            event_type="future_day",
            label_es="Mañana",
            time_utc=datetime(2026, 9, 5, 8, 0, tzinfo=UTC),
        ),
    )

    result = mobile_pages._future_only_events(events, now_local)

    assert [event.event_type for event in result] == ["future_same_day", "future_day"]
    assert all(event.time_utc >= now_local.astimezone(UTC) for event in result)


def test_future_agenda_rejects_naive_time_authority() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        mobile_pages._future_only_events((), datetime(2026, 9, 4, 18, 0))


def test_astronomy_product_localization_covers_observed_conjunction() -> None:
    event = RawCalendarEvent(
        event_type="apparent_conjunction",
        label_es="Conjunción aparente de moon y uranus",
        time_utc=datetime(2026, 9, 5, 8, 0, tzinfo=UTC),
        body="moon",
        details={"body_pair": ["moon", "uranus"]},
    )

    assert mobile_pages.body_label_es("moon") == "Luna"
    assert mobile_pages.body_label_es("uranus") == "Urano"
    assert mobile_pages.event_title_es(event) == "Conjunción aparente de la Luna y Urano"


def test_primary_event_time_is_human_readable_and_has_no_microseconds_or_offset_dump() -> None:
    event = _event_with_provenance(
        {
            "official_madrid_time": {
                "iso8601": "2026-09-04T22:34:07.712739+02:00",
                "abbreviation": "CEST",
                "utc_offset": "+02:00",
            }
        }
    )

    rendered = mobile_pages.event_time_es(event)

    assert rendered == "4 de septiembre de 2026 · 22:34 CEST"
    assert "712739" not in rendered
    assert "+02:00" not in rendered


def test_visibility_and_scientific_details_are_structured_without_english_backend_copy() -> None:
    reason = "this event has no scientifically defined terrestrial maximum point"
    provenance = {
        "local_circumstances": {
            "altitude_deg": -10.8798321,
            "azimuth_deg": 39.8124612,
            "above_horizon": False,
        },
        "global_maximum": {
            "status": "not_applicable",
            "reason": reason,
        },
        "celestial_region": {
            "right_ascension_hours": 4.1563,
            "declination_deg": 25.433,
        },
    }
    event = _event_with_provenance(provenance)

    visibility = mobile_pages._visibility_presentation(event)
    rows = dict(mobile_pages._scientific_detail_rows(event))

    assert visibility["label"] == "NO VISIBLE DESDE TU UBICACIÓN"
    assert visibility["detail"] == "Bajo el horizonte"
    assert rows["Altitud"] == "−10,88°"
    assert rows["Azimut"] == "39,81°"
    assert rows["Ascensión recta"] == "4 h 09 min"
    assert rows["Declinación"] == "+25° 26′"
    assert rows["Máximo terrestre"] == "No aplica a este tipo de fenómeno."
    assert reason not in " ".join(rows.values())
    assert provenance["global_maximum"]["reason"] == reason
    assert provenance["local_circumstances"]["altitude_deg"] == -10.8798321


def test_m1_mobile_nav_is_five_columns_compact_and_reserves_content_space() -> None:
    source = _read("webui/Centinela.py")
    css = _read("webui/product/v3_patch.css")

    assert "mobile_slots = st.columns(5" in source
    for slot in ("mobile-home", "mobile-create", "mobile-projects", "mobile-review"):
        assert f'slot="{slot}"' in source
    assert 'key="centinela-mobile-more-menu"' in source
    assert "--centinela-mobile-nav-height: 64px" in css
    assert "width: 20% !important" in css
    assert "env(safe-area-inset-bottom)" in css
    assert "padding-bottom: calc(var(--centinela-mobile-nav-height)" in css
    assert "background: rgba(211, 163, 63, .12) !important" in css


def test_m1_mobile_header_is_single_row_with_compact_menu_and_top_offset() -> None:
    source = _read("webui/Centinela.py")
    css = _read("webui/product/v3_patch.css")

    assert "mobile_brand, mobile_menu = st.columns([9, 1]" in source
    assert 'key="centinela-mobile-header-menu"' in source
    assert "--centinela-mobile-header-height: 60px" in css
    assert "max-height: var(--centinela-mobile-header-height)" in css
    assert "width: 44px !important" in css
    assert "font-size: 0 !important" in css
    assert "padding-top: calc(var(--centinela-mobile-header-height)" in css
    assert "scroll-margin-top" in css


def test_m1_home_cta_hierarchy_has_no_duplicate_plus_and_stacks_on_narrow_mobile() -> None:
    source = _read("webui/product/studio.py")
    css = _read("webui/product/v3_patch.css")

    assert 'label="Crear una historia"' in source
    assert 'label="＋ Crear una historia"' not in source
    assert 'a[href$="/crear"]' in css
    assert 'a[href$="/cielo"]' in css
    assert "@media (max-width: 430px)" in css
    assert "grid-template-columns: minmax(0, 1fr)" in css


def test_m1_agenda_product_copy_uses_structured_presentation_not_backend_dump() -> None:
    source = _read("webui/product/mobile_pages.py")
    css = _read("webui/product/v3_patch.css")

    assert "_future_agenda_events(calendar, selected_filter)" in source
    assert "_future_only_events(stored_events, _agenda_now_utc(calendar))" in source
    assert "pages._visibility_and_maximum(event)" not in source
    assert "centinela-science-row" in source
    assert "centinela-event-visibility" in source
    assert "No aplica a este tipo de fenómeno." in source
    assert "font-size: clamp(1.65rem, 7.7vw, 1.82rem)" in css
