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

_PRODUCT_PIPELINE = (
    ("Investigación", ("NEW", "NEEDS_INPUT", "RESEARCH", "RESEARCHING")),
    ("Guion", ("SCRIPT", "SCRIPTING", "SCENES")),
    ("Medios", ("MEDIA",)),
    ("Voz", ("VOICE", "TTS", "AUDIO")),
    ("Vídeo", ("VIDEO", "VIDEO_BASE", "FINAL_RENDER", "REVIEW_PREP")),
    ("Revisión", ("READY_FOR_HUMAN_REVIEW", "CHANGES_REQUESTED")),
    ("Publicación", ("FINAL_APPROVED", "PUBLICATION_PACKAGE", "PUBLICATION_PACKAGE_READY")),
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


def render_brand_lockup(*, compact: bool = False) -> None:
    modifier = " centinela-lockup--compact" if compact else ""
    st.html(
        f"""
        <div class="centinela-lockup{modifier}">
          <div class="centinela-lockup__mark" aria-hidden="true">
            <span>✦</span><span class="centinela-lockup__scope">◌</span>
          </div>
          <div class="centinela-lockup__copy">
            <strong>EL CENTINELA DEL UNIVERSO</strong>
            <span>Studio de producción astronómica</span>
          </div>
        </div>
        """
    )


def render_brand_manifesto() -> None:
    st.html(
        """
        <section class="centinela-manifesto" aria-label="Identidad de producto">
          <div class="centinela-manifesto__brand">
            <div class="centinela-manifesto__orb" aria-hidden="true">✦</div>
            <div>
              <div class="centinela-manifesto__title">EL CENTINELA DEL UNIVERSO</div>
              <div class="centinela-manifesto__subtitle">STUDIO DE PRODUCCIÓN ASTRONÓMICA</div>
            </div>
          </div>
          <div class="centinela-manifesto__panel">
            <strong>VISIÓN</strong>
            <p>Observar. Comprender. Contar el cielo.</p>
            <p>Transformamos fenómenos del Universo en historias visuales con rigor y belleza.</p>
          </div>
          <div class="centinela-manifesto__panel">
            <strong>PRINCIPIOS</strong>
            <ul>
              <li>Cinematográfico y elegante</li>
              <li>Ciencia rigurosa</li>
              <li>Producción audiovisual profesional</li>
              <li>Claro, privado y seguro</li>
            </ul>
          </div>
        </section>
        """
    )


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
    st.html(
        f"""
        <section class="centinela-hero">
          <div class="centinela-hero__stars" aria-hidden="true"></div>
          <div class="centinela-hero__horizon" aria-hidden="true"></div>
          <div class="centinela-hero__content">
            <div class="centinela-eyebrow">{safe_eyebrow}</div>
            <h1>{safe_title}</h1>
            <p>{safe_subtitle}</p>
            {hint}
          </div>
        </section>
        """
    )


def render_section_heading(
    title: str,
    caption: str | None = None,
    *,
    eyebrow: str | None = None,
) -> None:
    if eyebrow:
        st.html(
            f'<div class="centinela-eyebrow centinela-eyebrow--section">'
            f"{escape(eyebrow)}</div>"
        )
    st.subheader(title)
    if caption:
        st.caption(caption)


def render_state_badge(value: Any) -> None:
    raw = _enum_value(value)
    label = state_display(raw)
    tone = _STATE_TONES.get(raw, "neutral")
    st.html(
        f'<span class="centinela-badge centinela-badge--{tone}">'
        f"{escape(label)}</span>"
    )


def render_ai_classification_badge() -> None:
    st.html(
        '<span class="centinela-badge centinela-badge--ai">'
        "RECREACIÓN VISUAL</span>"
    )


def render_format_chips(items: Iterable[str]) -> None:
    markup = "".join(
        f'<span class="centinela-chip">{escape(str(item))}</span>' for item in items
    )
    st.html(f'<div class="centinela-chip-row">{markup}</div>')


def render_empty_state(title: str, message: str, *, action: str | None = None) -> None:
    action_markup = (
        f'<div class="centinela-empty__action">{escape(action)}</div>' if action else ""
    )
    st.html(
        f"""
        <div class="centinela-empty">
          <div class="centinela-empty__orb" aria-hidden="true">✦</div>
          <div>
            <strong>{escape(title)}</strong>
            <p>{escape(message)}</p>
            {action_markup}
          </div>
        </div>
        """
    )


def _pipeline_position(project: Any) -> tuple[int, int]:
    state = _enum_value(getattr(project, "state", ""))
    next_stage = _enum_value(getattr(project, "next_stage", ""))
    current_index = 0

    for index, (_, markers) in enumerate(_PRODUCT_PIPELINE):
        if state in markers or next_stage in markers:
            current_index = index
            break

    if state == "FINAL_APPROVED":
        current_index = 6
    elif state == "PUBLICATION_PACKAGE_READY":
        current_index = 6

    completed_through = max(-1, current_index - 1)
    if state == "FINAL_APPROVED":
        completed_through = 5
    elif state == "PUBLICATION_PACKAGE_READY":
        completed_through = 6
    return current_index, completed_through


def render_project_timeline(project: Any) -> None:
    current_index, completed_through = _pipeline_position(project)
    steps = []
    for index, (label, _) in enumerate(_PRODUCT_PIPELINE):
        if index <= completed_through:
            tone = "completed"
            glyph = "✓"
            status = "Completado"
        elif index == current_index:
            tone = "current"
            glyph = "●"
            status = "Etapa actual"
        else:
            tone = "future"
            glyph = "○"
            status = "Pendiente"
        steps.append(
            f"""
            <div class="centinela-stepper__item centinela-stepper__item--{tone}"
                 role="listitem" aria-label="{escape(label)} · {status}">
              <span class="centinela-stepper__dot" aria-hidden="true">{glyph}</span>
              <span class="centinela-stepper__label">{escape(label)}</span>
            </div>
            """
        )
    current_label = _PRODUCT_PIPELINE[current_index][0]
    st.html(
        f"""
        <div class="centinela-stepper-wrap">
          <div class="centinela-stepper__meta">
            <span>FLUJO DE PRODUCCIÓN</span>
            <strong>{escape(current_label)}</strong>
          </div>
          <div class="centinela-stepper" role="list" aria-label="Flujo de producción">
            {''.join(steps)}
          </div>
        </div>
        """
    )


def render_kpi_card(
    label: str,
    value: Any,
    *,
    detail: str | None = None,
    tone: str = "neutral",
) -> None:
    del tone
    with st.container(border=True):
        st.caption(label.upper())
        st.markdown(f"### {value}")
        if detail:
            st.caption(detail)


def render_key_value_card(
    label: str,
    value: Any,
    *,
    detail: str | None = None,
    technical: bool = False,
) -> None:
    with st.container(border=True):
        st.caption(label)
        if technical:
            st.code(str(value if value not in {None, ""} else "—"), language=None)
        else:
            st.markdown(f"**{value if value not in {None, ''} else '—'}**")
        if detail:
            st.caption(detail)


def render_runtime_status_card(
    display_name: str,
    *,
    ready: bool,
    enabled: bool,
    adapter_registered: bool,
    weights_available: bool,
    hardware_certified: bool,
) -> None:
    tone = "success" if ready else "warning"
    state_label = "Preparado" if ready else "Pendiente de activación"
    st.html(
        f"""
        <div class="centinela-runtime centinela-runtime--{tone}">
          <div>
            <span class="centinela-runtime__eyebrow">MOTOR</span>
            <strong>{escape(display_name)}</strong>
          </div>
          <span class="centinela-runtime__state">{escape(state_label)}</span>
          <p>{
              "El runtime local está certificado para esta operación."
              if ready
              else "El motor está integrado, pero necesita el runtime local certificado."
          }</p>
        </div>
        """
    )
    with st.expander("Detalles técnicos del motor", expanded=False):
        rows = (
            ("Contrato", True),
            ("Motor habilitado", enabled),
            ("Adaptador", adapter_registered),
            ("Pesos", weights_available),
            ("Hardware", hardware_certified),
        )
        for label, value in rows:
            st.write(f"{'✓' if value else '—'} **{label}**")


def render_capability_card(
    label: str,
    *,
    connected: bool,
    backend: str,
    resource: str,
) -> None:
    with st.container(border=True):
        status = "Disponible" if connected else "No disponible"
        icon = "✓" if connected else "!"
        st.markdown(f"### {icon} {label}")
        st.caption(status)
        st.write(f"**Backend:** {backend or '—'}")
        st.write(f"**Capacidad:** {resource or '—'}")


def render_error_state(
    message: str,
    *,
    action: str | None = None,
    technical_detail: Any | None = None,
) -> None:
    st.error(message)
    if action:
        st.caption(action)
    if technical_detail is not None:
        with st.expander("Detalle técnico", expanded=False):
            st.code(str(technical_detail), language=None)


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
    st.html(
        """
        <div class="centinela-notice centinela-notice--manual">
          <div class="centinela-notice__icon" aria-hidden="true">◈</div>
          <div>
            <strong>PUBLICACIÓN MANUAL</strong>
            <p>El Centinela prepara los archivos. Tú decides cuándo y dónde publicarlos.</p>
            <p><strong>Esto no publica nada automáticamente.</strong></p>
          </div>
        </div>
        """
    )
