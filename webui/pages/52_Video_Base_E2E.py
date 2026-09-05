from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.production_orchestrator import ProductionOrchestratorPlan  # noqa: E402
from app.models.video_base import VideoBaseRenderManifest  # noqa: E402
from app.models.video_base_e2e import (  # noqa: E402
    VideoArtifactProbe,
    VideoBaseE2ERequest,
    VideoBaseE2EStatus,
)
from app.services.video_base_e2e import build_video_base_e2e  # noqa: E402


st.set_page_config(page_title="F52 · El Centinela", layout="wide")
st.title("F52 · Video Base E2E Verifier")
st.caption(
    "Verifica contractualmente evidencia de un CLEAN_BASE real. "
    "No renderiza vídeo, no inspecciona el filesystem y no sustituye la certificación local."
)

orchestrator_file = st.file_uploader(
    "ProductionOrchestratorPlan (JSON)",
    type=["json"],
    key="f52-orchestrator",
)
manifest_file = st.file_uploader(
    "VideoBaseRenderManifest (JSON, opcional)",
    type=["json"],
    key="f52-manifest",
)
probe_file = st.file_uploader(
    "VideoArtifactProbe (JSON, opcional)",
    type=["json"],
    key="f52-probe",
)


def _json_payload(uploaded) -> object:
    return json.loads(uploaded.getvalue().decode("utf-8"))


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido validar la evidencia F52. "
        "No se ha fabricado ningún PASS ni se ha ejecutado ningún paso downstream."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.code(f"{type(exc).__name__}: {exc}", language=None)


if st.button("Verificar evidencia F52", type="primary"):
    try:
        if orchestrator_file is None:
            raise ValueError("carga un ProductionOrchestratorPlan JSON")
        if (manifest_file is None) != (probe_file is None):
            raise ValueError(
                "VideoBaseRenderManifest y VideoArtifactProbe deben aportarse juntos"
            )

        orchestrator = ProductionOrchestratorPlan.model_validate(
            _json_payload(orchestrator_file)
        )
        manifest = (
            VideoBaseRenderManifest.model_validate(_json_payload(manifest_file))
            if manifest_file is not None
            else None
        )
        probe = (
            VideoArtifactProbe.model_validate(_json_payload(probe_file))
            if probe_file is not None
            else None
        )
        result = build_video_base_e2e(
            VideoBaseE2ERequest(
                orchestrator=orchestrator,
                manifest=manifest,
                probe=probe,
            )
        )

        status_labels = {
            VideoBaseE2EStatus.WAITING_FOR_ORCHESTRATOR: "Esperando orquestador",
            VideoBaseE2EStatus.WAITING_FOR_REAL_VIDEO_BASE: "Esperando evidencia del Video Base",
            VideoBaseE2EStatus.WAITING_FOR_CLEAN_VIDEO_BASE: "El vídeo aportado no es CLEAN_BASE",
            VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS: "Contrato F52 superado",
            VideoBaseE2EStatus.VIDEO_BASE_E2E_FAIL: "Contrato F52 no superado",
        }
        if result.status == VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS:
            st.success(status_labels[result.status])
        elif result.status == VideoBaseE2EStatus.VIDEO_BASE_E2E_FAIL:
            st.error(status_labels[result.status])
        else:
            st.warning(status_labels[result.status])

        st.metric("Checks superados", f"{result.passed_count}/{result.check_count}")
        st.metric("Checks fallidos", result.failed_count)
        st.info(
            "La UI valida la evidencia estructurada aportada. No ejecuta ffprobe, "
            "no abre rutas locales y no demuestra por sí sola que el archivo físico exista "
            "en el PC. La certificación local real sigue siendo obligatoria."
        )

        if result.checks:
            st.subheader("Checks F52")
            for check in result.checks:
                icon = "✓" if check.passed else "✗"
                with st.container(border=True):
                    st.markdown(f"### {icon} {check.check_id}")
                    st.caption(check.detail)
        else:
            st.caption("No hay checks de artefacto todavía para este estado.")

        with st.expander("Trazabilidad y guardrails", expanded=False):
            st.write(f"Estado backend: {result.status.value}")
            st.write(f"Hash F52: {result.video_base_e2e_hash}")
            st.write(
                "Source ProductionOrchestrator hash: "
                f"{result.source_production_orchestrator_hash}"
            )
            st.write(f"Real artifact evidence declared: {result.real_artifact_present}")
            st.write(f"Verification only: {result.verification_only}")
            st.write(f"Renders video: {result.renders_video}")
            st.write(f"Modifies media: {result.modifies_media}")
            st.write(f"Network calls: {result.network_calls}")
            st.write(f"Uses LLM: {result.uses_llm}")
            st.write(f"Auto publication: {result.auto_publication}")
            st.write(f"Generated UTC: {result.generated_at_utc.isoformat()}")
    except Exception as exc:
        _render_failure(exc)
