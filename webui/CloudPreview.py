from __future__ import annotations

from datetime import datetime

import streamlit as st

st.set_page_config(
    page_title="El Centinela del Universo — Cloud Preview",
    page_icon="🌌",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
      --ecu-bg: #07111f;
      --ecu-panel: #0d1b2d;
      --ecu-panel-2: #10243b;
      --ecu-border: rgba(148, 163, 184, .18);
      --ecu-muted: #9fb0c5;
      --ecu-accent: #7dd3fc;
      --ecu-good: #86efac;
      --ecu-warn: #fde68a;
    }
    [data-testid="stAppViewContainer"] {
      background:
        radial-gradient(circle at 15% 0%, rgba(56,189,248,.12), transparent 32rem),
        radial-gradient(circle at 88% 18%, rgba(129,140,248,.10), transparent 28rem),
        linear-gradient(180deg,#06101d 0%,#081525 50%,#07111f 100%);
    }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stSidebar"] {
      background: linear-gradient(180deg,#081523 0%,#0a1828 100%);
      border-right: 1px solid var(--ecu-border);
    }
    .block-container { padding-top: 1.5rem; padding-bottom: 4rem; }
    .ecu-hero {
      border: 1px solid var(--ecu-border);
      background: linear-gradient(135deg, rgba(15,35,57,.96), rgba(8,21,37,.96));
      border-radius: 22px;
      padding: 1.35rem 1.45rem;
      margin-bottom: 1rem;
      box-shadow: 0 20px 60px rgba(0,0,0,.22);
    }
    .ecu-kicker {
      color: var(--ecu-accent);
      font-size: .78rem;
      letter-spacing: .12em;
      text-transform: uppercase;
      font-weight: 700;
    }
    .ecu-title { font-size: clamp(1.55rem, 4vw, 2.6rem); font-weight: 800; margin:.22rem 0; }
    .ecu-sub { color: var(--ecu-muted); margin:0; line-height:1.55; }
    .ecu-card {
      border: 1px solid var(--ecu-border);
      background: rgba(13,27,45,.88);
      border-radius: 18px;
      padding: 1rem 1.05rem;
      min-height: 126px;
    }
    .ecu-card h4 { margin:.05rem 0 .45rem 0; }
    .ecu-muted { color: var(--ecu-muted); }
    .ecu-pill {
      display:inline-block;
      border:1px solid var(--ecu-border);
      background:rgba(15,35,57,.9);
      border-radius:999px;
      padding:.2rem .55rem;
      margin:.12rem .16rem .12rem 0;
      font-size:.78rem;
    }
    .ecu-safe {
      border:1px solid rgba(134,239,172,.28);
      background:rgba(22,101,52,.14);
      color:#bbf7d0;
      border-radius:14px;
      padding:.7rem .85rem;
      margin:.35rem 0 1rem 0;
      font-size:.9rem;
    }
    .ecu-stage {
      border-left:3px solid rgba(125,211,252,.7);
      padding:.5rem .75rem;
      margin:.38rem 0;
      background:rgba(15,35,57,.65);
      border-radius:0 12px 12px 0;
    }
    .ecu-stage.ok { border-left-color:#86efac; }
    .ecu-stage.wait { border-left-color:#fde68a; }
    @media (max-width: 700px) {
      .block-container { padding-left:.75rem; padding-right:.75rem; padding-top:.8rem; }
      .ecu-hero { padding:1rem; border-radius:18px; }
      .ecu-card { min-height:auto; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "demo_project" not in st.session_state:
    st.session_state.demo_project = {
        "title": "La Luna atraviesa Capricornus",
        "duration": 45,
        "profile": "Cinemático",
        "state": "REVIEW_PREP",
    }

if "review" not in st.session_state:
    st.session_state.review = {
        "science": True,
        "media": True,
        "voice": False,
        "subtitles": False,
    }


def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="ecu-hero">
          <div class="ecu-kicker">EL CENTINELA DEL UNIVERSO · CLOUD PREVIEW</div>
          <div class="ecu-title">{title}</div>
          <p class="ecu-sub">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def stage(name: str, state: str, detail: str) -> None:
    css = "ok" if state == "✓" else "wait"
    st.markdown(
        f'<div class="ecu-stage {css}"><b>{state} {name}</b><br>'
        f'<span class="ecu-muted">{detail}</span></div>',
        unsafe_allow_html=True,
    )


with st.sidebar:
    st.markdown("## 🌌 El Centinela")
    st.caption("Astronomy Production Studio")
    page = st.radio(
        "Navegación",
        [
            "Inicio",
            "Crear vídeo",
            "Producción",
            "Revisión",
            "Voz",
            "Medios",
            "Astronomía",
            "Sistema",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("PREVIEW CLOUD · DEMO SEGURA")
    st.caption("Sin acceso a tu PC, API keys, Ollama, Qwen local ni publicación.")

st.markdown(
    '<div class="ecu-safe">🛡️ <b>Modo demostración seguro.</b> '
    'La interfaz es interactiva, pero las acciones usan datos de muestra y no ejecutan producción ni publicación.</div>',
    unsafe_allow_html=True,
)

if page == "Inicio":
    hero(
        "Centro de Producción",
        "Una vista clara del estado del proyecto, la ciencia, el material y la revisión humana.",
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Proyecto", "Lunar V1")
    c2.metric("MEDIA", "5 / 5", "sin unresolved")
    c3.metric("Ciencia", "FactLock", "trazable")
    c4.metric("Estado", "REVIEW_PREP")

    st.subheader("Producción activa")
    left, right = st.columns([1.35, 1])
    with left:
        st.markdown(
            """
            <div class="ecu-card">
              <div class="ecu-kicker">PROYECTO ACTUAL</div>
              <h4>La Luna atraviesa Capricornus</h4>
              <span class="ecu-pill">45 s</span>
              <span class="ecu-pill">9:16</span>
              <span class="ecu-pill">30 fps</span>
              <span class="ecu-pill">Cinemático</span>
              <p class="ecu-muted">Narrativa científica → escenas → material específico → voz → revisión.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            """
            <div class="ecu-card">
              <div class="ecu-kicker">GUARDRAILS</div>
              <h4>Producción controlada</h4>
              <p>✓ MaterialSelector autoridad final<br>
                 ✓ FactLock científico<br>
                 ✓ Sin B-roll irrelevante<br>
                 ✓ Sin autopublicación</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.subheader("Pipeline")
    stage("RESEARCH", "✓", "Contexto astronómico y hechos verificados")
    stage("SCRIPT", "✓", "Writer Room con trazabilidad")
    stage("SCENES", "✓", "Cinco actos con intención visual")
    stage("MEDIA", "✓", "5/5 con especificidad científica")
    stage("AUDIO", "✓", "Perfil de voz preparado")
    stage("VIDEO_BASE", "✓", "Master y social planificados")
    stage("REVIEW_PREP", "•", "Pendiente de aprobación humana")

elif page == "Crear vídeo":
    hero(
        "Crear nuevo vídeo",
        "Define el tema y el sistema construirá una propuesta científica y cinematográfica antes de renderizar.",
    )
    with st.form("create-demo"):
        topic = st.text_input("Tema", "La Luna y Saturno al anochecer")
        col1, col2 = st.columns(2)
        duration = col1.select_slider("Duración", options=[30, 45, 60, 75, 90], value=45)
        profile = col2.selectbox(
            "Perfil narrativo",
            ["Cinemático", "Divulgativo", "Observacional", "Épico contenido"],
        )
        st.selectbox("Formato", ["Reel / TikTok / Shorts · 9:16"])
        submitted = st.form_submit_button("Crear propuesta", use_container_width=True)
    if submitted:
        st.session_state.demo_project = {
            "title": topic,
            "duration": duration,
            "profile": profile,
            "state": "DRAFT",
        }
        st.success("Propuesta demo creada. En producción real aquí arrancaría RESEARCH → FactLock → Writer Room.")
        st.json(st.session_state.demo_project)

elif page == "Producción":
    project = st.session_state.demo_project
    hero(
        project["title"],
        "Seguimiento del pipeline sin exponer la complejidad interna al creador.",
    )
    st.progress(0.86, text="86 % · REVIEW_PREP")
    stage("Investigación", "✓", "Fuentes y contexto astronómico")
    stage("FactLock", "✓", "Hechos bloqueados para el Writer")
    stage("Guion", "✓", "Introducción → desarrollo → clímax → resolución → epílogo")
    stage("Material", "✓", "5 escenas resueltas")
    stage("Voz", "✓", "Perfil masculino ES-ES")
    stage("Vídeo", "✓", "9:16 · 30 fps")
    stage("Revisión", "•", "La decisión final sigue siendo humana")
    if st.button("Simular actualización de estado", use_container_width=True):
        st.toast("Estado actualizado en la demo", icon="✓")

elif page == "Revisión":
    hero(
        "Review Studio",
        "Ciencia, material, voz y subtítulos deben aprobarse antes de preparar publicación.",
    )
    tabs = st.tabs(["Escenas", "Checklist", "Publicación"])
    with tabs[0]:
        scenes = [
            ("01 · Introducción", "Luna gibosa", "NASA / evidencia específica", "VERIFICADO"),
            ("02 · Desarrollo", "Diámetro angular 0,5°", "Scientific Visual · FactLock", "VERIFICADO"),
            ("03 · Clímax", "Magnitud -12,14", "Scientific Visual · FactLock", "VERIFICADO"),
            ("04 · Resolución", "Luna en Capricornus", "Mapa científico específico", "VERIFICADO"),
            ("05 · Epílogo", "Luna como referencia", "Material lunar lexicalmente anclado", "REVISAR"),
        ]
        for title, intent, media, status in scenes:
            with st.expander(f"{title} · {status}", expanded=title.startswith("01")):
                st.write(f"**Intención visual:** {intent}")
                st.write(f"**Material:** {media}")
                st.caption("MaterialSelector sigue siendo la autoridad final.")
    with tabs[1]:
        st.session_state.review["science"] = st.checkbox(
            "Ciencia revisada", value=st.session_state.review["science"]
        )
        st.session_state.review["media"] = st.checkbox(
            "Material visual revisado", value=st.session_state.review["media"]
        )
        st.session_state.review["voice"] = st.checkbox(
            "Voz revisada", value=st.session_state.review["voice"]
        )
        st.session_state.review["subtitles"] = st.checkbox(
            "Subtítulos revisados", value=st.session_state.review["subtitles"]
        )
        ready = all(st.session_state.review.values())
        if ready:
            st.success("Checklist completo. En producción real podría prepararse Publication Package.")
        else:
            st.warning("Aún no está aprobado para preparar publicación.")
    with tabs[2]:
        st.info("AUTO_PUBLICATION = FALSE")
        st.button("Preparar paquete de publicación", disabled=True, use_container_width=True)
        st.caption("Deshabilitado en Cloud Preview.")

elif page == "Voz":
    hero(
        "Voice Studio",
        "Diseña la voz documental de El Centinela y controla pronunciación, ritmo y mastering.",
    )
    col1, col2 = st.columns(2)
    with col1:
        st.selectbox("Motor", ["Qwen3-TTS local · objetivo", "Edge TTS · comparación"])
        st.selectbox("Voz", ["Masculina ES-ES · Centinela"])
        st.slider("Velocidad", 0.85, 1.10, 0.96, 0.01)
        st.slider("Pausa narrativa", 0, 100, 52)
    with col2:
        st.text_area(
            "Lexicon astronómico",
            "Betelgeuse\nCapricornus\nAldebarán\nJúpiter\neclíptica\nperihelio",
            height=190,
        )
    if st.button("Generar muestra A/B", use_container_width=True):
        st.info("Demo: la generación de audio real está desactivada en la preview pública.")
    st.caption("Mastering objetivo: 48 kHz · -16 LUFS · -1 dBTP.")

elif page == "Medios":
    hero(
        "Biblioteca y selección",
        "El sistema prioriza pertinencia científica, derechos y material propio antes que similitud genérica.",
    )
    rows = [
        ["01", "Moon phase", "NASA", "VERIFIED_LICENSE", "✓"],
        ["02", "Angular diameter", "SCIENTIFIC_VISUAL", "FACTLOCK", "✓"],
        ["03", "Visual magnitude", "SCIENTIFIC_VISUAL", "FACTLOCK", "✓"],
        ["04", "Moon + Capricornus", "Scientific map", "VERIFIED_LICENSE", "✓"],
        ["05", "Lunar reference", "OWN_MEDIA / safe fixture", "CONFIRMED", "✓"],
    ]
    st.dataframe(
        rows,
        column_config={
            0: "Escena",
            1: "Requisito",
            2: "Fuente",
            3: "Derechos / provenance",
            4: "Estado",
        },
        hide_index=True,
        use_container_width=True,
    )
    st.success("MEDIA 5/5 · unresolved 0 · object-only shortcut 0")

elif page == "Astronomía":
    hero(
        "Observatorio científico",
        "Los hechos alimentan FactLock; el guion no debe inventar cifras fuera de esta capa.",
    )
    facts = {
        "context:moment_utc": datetime.utcnow().isoformat(timespec="minutes") + "Z · demo",
        "moon:phase_name": "Gibosa creciente · ejemplo",
        "moon:illuminated_fraction": "97,3 % · ejemplo certificado",
        "moon:angular_diameter_deg": "0,5° · ejemplo certificado",
        "body:moon:visual_magnitude": "-12,14 · ejemplo certificado",
        "body:moon:constellation": "Capricornus · ejemplo certificado",
    }
    st.json(facts)
    st.caption("En producción real las efemérides deben proceder de fuentes astronómicas actuales y trazables.")

elif page == "Sistema":
    hero(
        "Estado del sistema",
        "Esta instancia es una demostración cloud; no representa el hardware local.",
    )
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            """
            <div class="ecu-card">
              <div class="ecu-kicker">CLOUD PREVIEW</div>
              <h4>Disponible</h4>
              <p>✓ Streamlit<br>✓ UI interactiva<br>✓ Datos demo<br>✓ Navegación móvil</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            """
            <div class="ecu-card">
              <div class="ecu-kicker">LOCAL PC</div>
              <h4>No conectado</h4>
              <p>— RTX 2060<br>— CUDA / NVENC<br>— Qwen local<br>— D:\\ASTRONOMÍA</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.warning("La preview no puede renderizar, publicar ni acceder a archivos de tu ordenador.")
