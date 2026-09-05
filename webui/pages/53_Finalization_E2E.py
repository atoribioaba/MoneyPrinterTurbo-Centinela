from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.finalization_e2e import (  # noqa: E402
    FinalVideoArtifactProbe,
    FinalizationE2ERequest,
    FinalizationE2EStatus,
    HumanFinalReviewRecord,
)
from app.models.video_base_e2e import VideoBaseE2EPlan  # noqa: E402
from app.services.finalization_e2e import build_finalization_e2e  # noqa: E402


st.set_page_config(page_title="F53 · El Centinela", layout="wide")
st.title("F53 · Human Review and Finalization E2E")
st.caption(
    "Certifica el contrato F52 → revisión humana → renders finales. "
    "No sustituye Review Studio, no renderiza y no autoriza publicación."
)

video_base_file = st.file_uploader(
    "VideoBaseE2EPlan (JSON)",
    type=["json"],
    key="f53-video-base",
)
review_file = st.file_uploader(
    "HumanFinalReviewRecord (JSON, opcional)",
    type=["json"],
    key="f53-review",
)
artifacts_file = st.file_uploader(
    "FinalVideoArtifactProbe[] (JSON, opcional)",
    type=["json"],
    key="f53-artifacts",
)


def _json_payload(uploaded) -> object:
    return json.loads(uploaded.getvalue().decode("utf-8"))


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido validar la evidencia F53. "
        "No se ha aprobado ningún proyecto ni se ha autorizado publicación."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.code(f"{type(exc).__name__}: {exc}", language=None)


if st.button("Verificar finalización F53", type="primary"):
    try:
        if video_base_file is None:
            raise ValueError("carga un VideoBaseE2EPlan JSON")

        video_base = VideoBaseE2EPlan.model_validate(_json_payload(video_base_file))
        review = (
            HumanFinalReviewRecord.model_validate(_json_payload(review_file))
            if review_file is not None
            else None
        )

        artifacts_payload = (
            _json_payload(artifacts_file) if artifacts_file is not None else []
        )
        if not isinstance(artifacts_payload, list):
            raise ValueError("FinalVideoArtifactProbe debe ser una lista JSON")
        artifacts = [
            FinalVideoArtifactProbe.model_validate(item) for item in artifacts_payload
        ]

        result = build_finalization_e2e(
            FinalizationE2ERequest(
                video_base=video_base,
                human_review=review,
                artifacts=artifacts,
            )
        )

        success_status = result.status == FinalizationE2EStatus.FINALIZATION_E2E_PASS
        fail_status = result.status in {
            FinalizationE2EStatus.FINALIZATION_E2E_FAIL,
            FinalizationE2EStatus.HUMAN_REVIEW_REJECTED,
            FinalizationE2EStatus.HUMAN_REVIEW_CHANGES_REQUESTED,
        }
        if success_status:
            st.success("Contrato F53 superado")
        elif fail_status:
            st.error(f"F53: {result.status.value}")
        else:
            st.warning(f"F53: {result.status.value}")

        st.metric("Checks superados", f"{result.passed_count}/{result.check_count}")
        st.metric("Checks fallidos", result.failed_count)
        st.metric("Renders declarados", result.artifact_count)

        st.info(
            "F53 consume un registro de revisión humana ya existente; esta página "
            "no crea una aprobación paralela. Los probes pueden validar contratos en cloud, "
            "pero los archivos físicos y el visionado humano final requieren certificación local."
        )

        if result.checks:
            st.subheader("Checks F53")
            for check in result.checks:
                icon = "✓" if check.passed else "✗"
                with st.container(border=True):
                    st.markdown(f"### {icon} {check.check_id}")
                    st.caption(check.detail)

        with st.expander("Trazabilidad y guardrails", expanded=False):
            st.write(f"Estado backend: {result.status.value}")
            st.write(f"Hash F53: {result.finalization_e2e_hash}")
            st.write(f"Source F52 hash: {result.source_video_base_e2e_hash}")
            st.write(f"Human review recorded: {result.human_review_recorded}")
            st.write(f"Human review required: {result.human_review_required}")
            st.write(
                f"Local final certification required: "
                f"{result.local_final_certification_required}"
            )
            st.write(f"Authorization to publish: {result.authorization_to_publish}")
            st.write(f"Uploads files: {result.uploads_files}")
            st.write(f"Webhook calls: {result.webhook_calls}")
            st.write(f"Marks published: {result.marks_published}")
            st.write(f"Auto publication: {result.auto_publication}")
            st.write(f"Generated UTC: {result.generated_at_utc.isoformat()}")
    except Exception as exc:
        _render_failure(exc)
