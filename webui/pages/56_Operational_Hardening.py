from __future__ import annotations

import json

import streamlit as st

from app.models.operational_hardening import (
    FindingSeverity,
    OperationalEnvironmentSnapshot,
    OperationalHardeningRequest,
    OperationalHardeningStatus,
)
from app.services.operational_hardening import build_operational_hardening


st.set_page_config(page_title="F56 · El Centinela", layout="wide")
st.title("F56 · Operational Hardening Audit")
st.caption(
    "Auditoría contractual de preparación operativa a partir de un snapshot aportado. "
    "F56 no inspecciona el PC, no cambia configuración, no toca la red y no borra archivos."
)

st.info(
    "**Límite de evidencia:** un resultado PASS demuestra que el snapshot cargado satisface "
    "el contrato F56. No certifica por sí solo el estado físico actual del PC."
)

uploaded = st.file_uploader(
    "OperationalEnvironmentSnapshot JSON",
    type=["json"],
    help=(
        "Carga un snapshot estructurado de capacidades operativas. Se valida en memoria; "
        "esta página no ejecuta comandos del sistema ni sondea el filesystem."
    ),
)


def _read_snapshot() -> OperationalEnvironmentSnapshot:
    if uploaded is None:
        raise ValueError("selecciona un OperationalEnvironmentSnapshot JSON")
    payload = json.loads(uploaded.getvalue().decode("utf-8"))
    return OperationalEnvironmentSnapshot.model_validate(payload)


def _status_label(status: OperationalHardeningStatus) -> str:
    return {
        OperationalHardeningStatus.HARDENING_PASS: "PASS",
        OperationalHardeningStatus.HARDENING_WARN: "WARN",
        OperationalHardeningStatus.HARDENING_BLOCKED: "BLOCKED",
    }[status]


def _render_result(plan) -> None:
    if plan.status == OperationalHardeningStatus.HARDENING_PASS:
        st.success("F56 PASS · El snapshot no contiene bloqueos ni advertencias.")
    elif plan.status == OperationalHardeningStatus.HARDENING_WARN:
        st.warning("F56 WARN · El pipeline no está bloqueado, pero hay advertencias visibles.")
    else:
        st.error("F56 BLOCKED · El snapshot contiene al menos un bloqueo operativo.")

    with st.container(horizontal=True, gap="medium"):
        st.metric("Estado", _status_label(plan.status))
        st.metric("Bloqueos", plan.block_count)
        st.metric("Advertencias", plan.warning_count)
        st.metric("Hallazgos", plan.finding_count)

    st.write(
        "Pipeline permitido por contrato:",
        "sí" if plan.safe_to_run_pipeline else "no",
    )

    st.subheader("Capacidades declaradas en el snapshot")
    snapshot = plan.snapshot
    capabilities = {
        "Repositorio": snapshot.repo_exists,
        "Python del entorno": snapshot.venv_python_exists,
        "Git": snapshot.git_present,
        "FFmpeg": snapshot.ffmpeg_present,
        "Gitleaks": snapshot.gitleaks_present,
        "Certifier": snapshot.certifier_present,
        "Backup root": snapshot.backup_root_exists,
        "Resource governor": snapshot.resource_governor_available,
    }
    st.dataframe(
        [
            {"Capacidad": label, "Declarada": "sí" if available else "no"}
            for label, available in capabilities.items()
        ],
        hide_index=True,
        use_container_width=True,
    )

    with st.container(horizontal=True, gap="medium"):
        st.metric("Espacio libre declarado", f"{snapshot.free_space_gb:.1f} GB")
        st.metric("Bundles de backup", snapshot.backup_bundle_count)
        st.metric("RAM objetivo", f"{snapshot.ram_target_gb:.1f} GB")
        st.metric("VRAM objetivo", f"{snapshot.vram_target_gb:.1f} GB")

    st.subheader("Hallazgos")
    if not plan.findings:
        st.caption("No hay hallazgos en el snapshot aportado.")
    else:
        for finding in plan.findings:
            icon = {
                FindingSeverity.INFO: "ℹ️",
                FindingSeverity.WARN: "⚠️",
                FindingSeverity.BLOCK: "⛔",
            }[finding.severity]
            with st.container(border=True):
                st.markdown(f"### {icon} {finding.finding_id}")
                st.write(finding.detail)
                st.caption(f"Severidad: {finding.severity.value}")

    with st.expander("Trazabilidad y guardrails", expanded=False):
        st.write(f"Estado backend: {plan.status.value}")
        st.write(f"Hash F56: {plan.operational_hardening_hash}")
        st.write(f"Generado UTC: {plan.generated_at_utc.isoformat()}")
        st.write(f"Audit only: {plan.audit_only}")
        st.write(f"Resource class: {plan.resource_class}")
        st.write(f"Modifica config: {plan.modifies_config}")
        st.write(f"Resetea red: {plan.resets_network}")
        st.write(f"Borra archivos: {plan.deletes_files}")
        st.write(f"Descarga dependencias: {plan.downloads_dependencies}")
        st.write(f"Network calls: {plan.network_calls}")

    st.caption(
        "F56 sólo evalúa el snapshot recibido. La verificación física de repo, Git, FFmpeg, "
        "gitleaks, backups, espacio libre y recursos sigue requiriendo evidencia del entorno real."
    )


if st.button("Validar snapshot operativo", type="primary"):
    try:
        snapshot = _read_snapshot()
        plan = build_operational_hardening(
            OperationalHardeningRequest(snapshot=snapshot)
        )
        _render_result(plan)
    except Exception as exc:
        st.error(
            "No se ha podido validar el snapshot operativo. "
            "No se ha modificado el sistema ni ejecutado ningún paso downstream."
        )
        with st.expander("Detalles técnicos", expanded=False):
            st.code(f"{type(exc).__name__}: {exc}", language=None)
