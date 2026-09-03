from __future__ import annotations

from html import escape
from typing import Any, Iterable, Mapping

import streamlit as st


_STATE_LABELS = {
    "NEW": "Nuevo",
    "NEEDS_INPUT": "Necesita información",
    "RESEARCHING": "Investigando",
    "SCRIPTING": "Preparando guion",
    "MEDIA": "Seleccionando medios",
    "VOICE": "Preparando voz",
    "VIDEO": "Montando vídeo",
    "READY_FOR_HUMAN_REVIEW": "Listo para revisión",
    "CHANGES_REQUESTED": "Cambios solicitados",
    "FINAL_APPROVED": "Aprobado",
    "PUBLICATION_PACKAGE_READY": "Listo para publicación manual",
    "BLOCKED": "Bloqueado",
    "FAILED": "Requiere atención",
}

_STATE_TONES = {
    "READY_FOR_HUMAN_REVIEW": "review",
    "FINAL_APPROVED": "success",
    "PUBLICATION_PACKAGE_READY": "success",
    "BLOCKED": "danger",
    "FAILED": "danger",
    "CHANGES_REQUESTED": "warning",
    "NEEDS_INPUT": "warning",
}

_PIPELINE = (
    ("Tema", ("NEW", "NEEDS_INPUT")),
    ("Investigación", ("RESEARCH", "RESEARCHING")),
    ("Guion", ("SCRIPT", "SCRIPTING")),
    ("Medios", ("MEDIA",)),
    ("Voz", ("VOICE", "TTS", "AUDIO")),
    ("Vídeo", ("VIDEO", "VIDEO_BASE", "FINAL_RENDER")),
    ("Revisión", ("READY_FOR_HUMAN_REVIEW", "FINAL_APPROVED", "CHANGES_REQUESTED")),
    ("Publicación", ("PUBLICATION_PACKAGE", "PUBLICATION_PACKAGE_READY")),
)


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip()


def state_display(value: Any) -> str:
    raw = _enum_value(value)
    return _STATE_LABELS.get(raw, raw.replace("_", " ").title() if raw else "—")


def short_identifier(value: Any, *, head: int = 8, tail: int = 6) -> str:
    text = str(value or "—")
    if text == "—" or len(text) <= head + tail + 1:
        return text
    return f"{text[:head]}…{text[-tail:]}"


def render_brand_hero(
    title: str,
    subtitle: str,
    *,
    eyebrow: str = "EL CENTINELA DEL UNIVERSO",
    action_hint: str | None = None,
) -> None:
    safe_eyebrow = escape(eyebrow)
    safe_title = escape(title)
    safe_subtitle = escape(subtitle)
    hint = (
        f'<div class="centinela-hero__hint">{escape(action_hint)}</div>'
        if action_hint
        else ""
    )
    st.markdown(
        f"""
        <section class="centinela-hero">
          <div class="centinela-hero__sky" aria-hidden="true"></div>
          <div class="centinela-hero__content">
            <div class="centinela-eyebrow">{safe_eyebrow}</div>
            <h1>{safe_title}</h1>
            <p>{safe_subtitle}</p>
            {hint}
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_section_heading(
    title: str,
    caption: str | None = None,
    *,
    eyebrow: str | None = None,
) -> None:
    if eyebrow:
        st.markdown(
            f'<div class="centinela-eyebrow centinela-eyebrow--section">{escape(eyebrow)}</div>',
            unsafe_allow_html=True,
        )
    st.subheader(title)
    if caption:
        st.caption(caption)


def render_state_badge(value: Any) -> None:
    raw = _enum_value(value)
    label = state_display(raw)
    tone = _STATE_TONES.get(raw, "neutral")
    st.markdown(
        f'<span class="centinela-badge centinela-badge--{tone}">{escape(label)}</span>',
        unsafe_allow_html=True,
    )


def render_empty_state(title: str, message: str) -> None:
    st.markdown(
        f"""
        <div class="centinela-empty">
          <div class="centinela-empty__orb" aria-hidden="true">✦</div>
          <div>
            <strong>{escape(title)}</strong>
            <p>{escape(message)}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_project_timeline(project: Any) -> None:
    state = _enum_value(getattr(project, "state", ""))
    next_stage = _enum_value(getattr(project, "next_stage", ""))
    current_index = 0

    for index, (_, markers) in enumerate(_PIPELINE):
        if state in markers or next_stage in markers:
            current_index = index
            break
    else:
        if state in {"FINAL_APPROVED"}:
            current_index = 7
        elif state == "PUBLICATION_PACKAGE_READY":
            current_index = 7

    completed_through = max(-1, current_index - 1)
    if state in {"FINAL_APPROVED", "PUBLICATION_PACKAGE_READY"}:
        completed_through = max(completed_through, 6)
    if state == "PUBLICATION_PACKAGE_READY":
        completed_through = 7

    cells: list[str] = []
    for index, (label, _) in enumerate(_PIPELINE):
        if index <= completed_through:
            modifier = "done"
            glyph = "✓"
        elif index == current_index:
            modifier = "current"
            glyph = "●"
        else:
            modifier = "pending"
            glyph = "○"
        cells.append(
            f"""
            <div class="centinela-step centinela-step--{modifier}">
              <span class="centinela-step__dot">{glyph}</span>
              <span class="centinela-step__label">{escape(label)}</span>
            </div>
            """
        )

    st.markdown(
        '<div class="centinela-timeline">' + "".join(cells) + "</div>",
        unsafe_allow_html=True,
    )


def technical_details(
    rows: Mapping[str, Any] | Iterable[tuple[str, Any]],
    *,
    label: str = "Detalles técnicos",
) -> None:
    items = rows.items() if isinstance(rows, Mapping) else rows
    with st.expander(label):
        for key, value in items:
            st.markdown(f"**{key}**")
            st.code(str(value if value not in {None, ""} else "—"), language=None)


def render_manual_publication_notice() -> None:
    st.markdown(
        """
        <div class="centinela-notice centinela-notice--manual">
          <div class="centinela-notice__icon" aria-hidden="true">◈</div>
          <div>
            <strong>Publicación manual</strong>
            <p>El Centinela prepara los archivos. Tú decides cuándo y dónde publicarlos.</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
