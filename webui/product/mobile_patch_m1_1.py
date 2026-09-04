from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

import streamlit as st


_MADRID = ZoneInfo("Europe/Madrid")
_MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

_JOB_COPY = {
    "SCRIPT: Writer Room iniciado": "Writer Room iniciado",
    "RESEARCH: advancing project state": "Investigación actualizada",
    "RESEARCH: Astronomy Core": "Astronomy Core iniciado",
    "RESEARCH: Fact Lock validado": "Fact Lock validado",
}


def product_datetime_es(value: Any) -> str:
    """Human Madrid-time label for Product UI; evidence remains untouched."""
    if isinstance(value, datetime):
        moment = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return "—"
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        try:
            moment = datetime.fromisoformat(normalized)
        except ValueError:
            return raw

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone(_MADRID)
    return (
        f"{local.day} {_MONTHS_ES[local.month - 1][:3]} {local.year} "
        f"· {local:%H:%M}"
    )


def product_job_message(message: Any, job_type: Any = None) -> str:
    raw = str(message or job_type or "").strip()
    if not raw:
        return "Proceso actualizado"
    if raw in _JOB_COPY:
        return _JOB_COPY[raw]
    if raw.startswith("SCRIPT: "):
        return raw.removeprefix("SCRIPT: ").strip()
    if raw.startswith("RESEARCH: "):
        detail = raw.removeprefix("RESEARCH: ").strip()
        if detail.casefold() == "advancing project state":
            return "Investigación actualizada"
        return f"Investigación · {detail}"
    return raw


def blocked_project_product_copy(project: Any) -> str | None:
    state = str(getattr(getattr(project, "state", None), "value", getattr(project, "state", ""))).upper()
    if state != "BLOCKED":
        return None
    messages = [str(getattr(job, "message", "") or "") for job in getattr(project, "latest_jobs", ())]
    if any("Writer Room" in message for message in messages):
        return (
            "El proyecto se ha detenido de forma segura en Guion. "
            "Esta preview cloud no dispone del Ollama loopback que Writer Room exige; "
            "no se fabrica un guion ni se descarga ningún modelo."
        )
    return "El proyecto se ha detenido de forma segura. Consulta la trazabilidad técnica para conocer el motivo."


def _render_project_timeline(project: Any, ui_module: Any) -> None:
    current_index, completed_through = ui_module._pipeline_position(project)
    pipeline = ui_module._PRODUCT_PIPELINE
    steps: list[str] = []
    for index, (label, _) in enumerate(pipeline):
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

    current_label = pipeline[current_index][0]
    previous_label = pipeline[current_index - 1][0] if current_index > 0 else "—"
    next_label = pipeline[current_index + 1][0] if current_index + 1 < len(pipeline) else "—"

    st.html(
        f"""
        <div class="centinela-stepper-wrap">
          <div class="centinela-stepper-desktop">
            <div class="centinela-stepper__meta">
              <span>FLUJO DE PRODUCCIÓN</span>
              <strong>{escape(current_label)}</strong>
            </div>
            <div class="centinela-stepper" role="list" aria-label="Flujo de producción">
              {''.join(steps)}
            </div>
          </div>
          <div class="centinela-stepper-mobile" role="status" aria-label="Etapa actual del flujo de producción">
            <div class="centinela-stepper-mobile__position">ETAPA {current_index + 1} DE {len(pipeline)}</div>
            <strong class="centinela-stepper-mobile__current"><span aria-hidden="true">●</span> {escape(current_label)}</strong>
            <div class="centinela-stepper-mobile__context">
              <span><b>Anterior:</b> {escape(previous_label)}</span>
              <span><b>Siguiente:</b> {escape(next_label)}</span>
            </div>
          </div>
        </div>
        """
    )


def install_ui_overrides(ui_module: Any) -> None:
    """Install presentation-only overrides before any product page is rendered."""
    ui_module.render_project_timeline = lambda project: _render_project_timeline(project, ui_module)


def render_visual_generation_workspace(
    service: Any,
    project: Any,
    *,
    visual_generation_module: Any,
    ui_module: Any,
) -> None:
    """Product-safe preflight; generation contracts remain in visual_generation.py."""
    try:
        visual_generation_module.load_scene_visual_contexts(service, project.project_id)
    except Exception as exc:
        ui_module.render_section_heading(
            "Visuales por escena",
            "Elige la fuente visual de cada escena. La IA permanece fail-closed hasta certificar el runtime local.",
            eyebrow="MATERIALES",
        )
        ui_module.render_empty_state(
            "Visuales por escena aún no materializados",
            "No se ha podido materializar todavía el siguiente artefacto. La sección permanece detenida de forma segura hasta que existan el plan de escenas y la resolución de medios.",
        )
        with st.expander("Detalles técnicos", expanded=False):
            st.caption("Evidencia diagnóstica preservada. No se ha fabricado ningún artefacto.")
            st.code(f"{type(exc).__name__}: {exc}", language=None)
        return

    visual_generation_module.render_visual_generation_workspace(service, project)
