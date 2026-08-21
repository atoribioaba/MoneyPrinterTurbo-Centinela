from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.astronomy import AstronomyBody, AstronomyContextRequest, ObserverContext  # noqa: E402
from app.models.astronomy_director import AstronomyDirectorRequest  # noqa: E402
from app.services.astronomy_director import (  # noqa: E402
    AstronomyDirectorError,
    generate_astronomy_video_plan,
    get_director_health,
)

st.set_page_config(
    page_title="Astronomy Director · El Centinela del Universo",
    layout="wide",
)
st.title("Astronomy Director · El Centinela del Universo")
st.caption("AstronomyContext → GroundingPacket → AstronomyVideoPlan → ScenePlan")

health = get_director_health()
if not health.ollama_reachable:
    st.error("Ollama local no está accesible. No se utilizará ninguna API comercial.")
    st.stop()
if not health.available_models:
    st.error(
        "No hay modelos Ollama instalados. No se descargará ninguno automáticamente."
    )
    st.stop()

subject = st.text_input("Tema", value="La Luna y Júpiter en el cielo de esta noche")
col1, col2, col3 = st.columns(3)
with col1:
    latitude = st.number_input("Latitud", -90.0, 90.0, 41.6523, format="%.6f")
    longitude = st.number_input("Longitud", -180.0, 180.0, -4.7245, format="%.6f")
with col2:
    elevation = st.number_input("Elevación (m)", -500.0, 100000.0, 698.0)
    timezone_name = st.text_input("Zona horaria IANA", value="Europe/Madrid")

try:
    zone = ZoneInfo(timezone_name)
except ZoneInfoNotFoundError:
    st.error("Zona horaria IANA no válida")
    st.stop()

local_now = datetime.now(zone)
with col3:
    date_value = st.date_input("Fecha", value=local_now.date())
    time_value = st.time_input(
        "Hora local",
        value=local_now.time().replace(microsecond=0),
    )

preferred = health.preferred_model or health.available_models[0]
model = st.selectbox(
    "Modelo Ollama local",
    health.available_models,
    index=health.available_models.index(preferred),
)
target_duration = st.slider("Duración objetivo (s)", 30, 180, 60, 5)
scene_count = st.slider("Número de escenas", 5, 10, 7)
allow_fallback = st.checkbox(
    "Permitir fallback determinista si el LLM falla dos veces",
    value=True,
)

if st.button("Generar AstronomyVideoPlan", type="primary"):
    try:
        moment = datetime.combine(date_value, time_value, tzinfo=zone)
        request = AstronomyDirectorRequest(
            subject=subject,
            astronomy=AstronomyContextRequest(
                observer=ObserverContext(
                    latitude_deg=latitude,
                    longitude_deg=longitude,
                    elevation_m=elevation,
                    timezone=timezone_name,
                ),
                moment=moment,
                bodies=list(AstronomyBody),
                event_window_days=35,
                include_eclipses=False,
            ),
            target_duration_seconds=target_duration,
            scene_count=scene_count,
            model=model,
            allow_fallback=allow_fallback,
        )

        with st.spinner("Generando plan grounded con Ollama local..."):
            plan = generate_astronomy_video_plan(request)

        st.success("Plan generado. Revisión humana obligatoria.")
        st.metric("Duración total", f"{plan.total_duration_seconds} s")
        st.write("**Origen:**", plan.generation_origin.value)
        st.write("**Modelo:**", plan.model_used)
        st.write("**Hook:**", plan.hook)
        if plan.external_research_required:
            st.warning("El plan requiere investigación externa antes de publicación.")
            for question in plan.research_questions:
                st.write("-", question)

        for scene in plan.scenes:
            with st.expander(
                f"Escena {scene.scene_number} · {scene.act.value} · "
                f"{scene.duration_seconds}s",
                expanded=True,
            ):
                st.write("**Narración:**", scene.narration)
                st.write("**Visual:**", scene.visual_requirement)
                st.write("**Plano:**", scene.shot_type.value)
                st.write("**Keywords:**", ", ".join(scene.material_keywords))
                for claim in scene.claims:
                    st.write("-", claim.statement, claim.fact_ids)

        st.download_button(
            "Guardar plan JSON",
            data=plan.model_dump_json(indent=2),
            file_name="astronomy-video-plan.json",
            mime="application/json",
        )
    except (AstronomyDirectorError, ValueError) as exc:
        st.error(str(exc))
