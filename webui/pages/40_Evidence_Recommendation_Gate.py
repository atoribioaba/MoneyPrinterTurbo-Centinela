from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.evidence_recommendation_gate import (  # noqa: E402
    EvidenceRecommendationGateRequest,
    EvidenceRecommendationStatus,
)
from app.models.experiment_evidence_ledger import (  # noqa: E402
    ExperimentEvidenceLedgerPlan,
)
from app.services.evidence_recommendation_gate import (  # noqa: E402
    build_evidence_recommendation_gate,
)


UI_PREVIEW_LIMIT = 20

st.set_page_config(page_title="F40 · El Centinela", layout="wide")
st.title("F40 · Evidence Recommendation Gate")
st.caption(
    "Deriva recomendaciones candidatas sólo desde registros F39 elegibles. "
    "No prueba causalidad, no modifica políticas y no publica."
)

ledger_upload = st.file_uploader(
    "ExperimentEvidenceLedgerPlan de F39 (JSON)",
    type=["json"],
    key="f40_experiment_evidence_ledger",
    help="Carga un ExperimentEvidenceLedgerPlan real generado por F39.",
)


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido evaluar el ledger F39. "
        "Comprueba que el JSON corresponde a un plan F39 válido."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "F40 falla cerrado: no corrige el ledger, no genera evidencia "
            "y no crea ni activa políticas."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


if st.button("Evaluar recomendaciones candidatas", type="primary"):
    try:
        if ledger_upload is None:
            raise ValueError(
                "selecciona un ExperimentEvidenceLedgerPlan JSON de F39"
            )

        ledger = ExperimentEvidenceLedgerPlan.model_validate_json(
            ledger_upload.getvalue()
        )
        request = EvidenceRecommendationGateRequest(ledger=ledger)
        result = build_evidence_recommendation_gate(request)

        st.subheader("Recommendation gate status")
        st.metric("Estado", result.status.value)
        st.metric(
            "Recomendaciones candidatas",
            result.recommendation_count,
        )

        if (
            result.status
            == EvidenceRecommendationStatus.WAITING_FOR_CONFIRMED_EXPERIMENT_RESULTS
        ):
            st.warning(
                "No hay resultados F39 elegibles y mejorados suficientes "
                "para producir una recomendación candidata."
            )
        else:
            st.success(
                "Existen recomendaciones candidatas para revisión humana. "
                "No son políticas aprobadas ni efectos causales demostrados."
            )

        for index, item in enumerate(
            result.recommendations[:UI_PREVIEW_LIMIT],
            1,
        ):
            with st.expander(
                f"Recomendación {index} · {item.recommendation_id}",
                expanded=False,
            ):
                st.write(f"Experimento: {item.experiment_id}")
                st.write(f"Hipótesis: {item.hypothesis_id}")
                st.write(f"Plataforma: {item.platform.value}")
                st.write(f"Variable: {item.variable}")
                st.write(
                    "Definición candidata: "
                    f"{item.recommended_definition}"
                )
                st.write(f"Métrica: {item.success_metric}")
                st.write(f"Delta observado: {item.observed_delta}")
                st.write(f"Clase de evidencia: {item.evidence_class}")
                st.write(
                    "Requiere aprobación humana: "
                    f"{item.requires_human_approval}"
                )
                st.write(f"Auto apply: {item.auto_apply}")
                st.write(f"Auto publish: {item.auto_publish}")
                st.caption(
                    "La comparación de medias observada no equivale a "
                    "significancia estadística ni a causalidad probada."
                )

        st.info(
            "F40 termina en EvidenceRecommendationGatePlan. "
            "No llama F41 automáticamente y no actualiza Cinematic Director."
        )

        with st.expander("Detalles técnicos", expanded=False):
            st.write(
                "Hash F39: "
                f"{result.source_experiment_evidence_ledger_hash}"
            )
            st.write(
                "Hash F40: "
                f"{result.evidence_recommendation_gate_hash}"
            )
            st.write(f"Generado UTC: {result.generated_at_utc.isoformat()}")
            st.write(f"Planning only: {result.planning_only}")
            st.write(
                "Association-only recommendations: "
                f"{result.association_only_recommendations}"
            )
            st.write(f"Causal claims: {result.causal_claims}")
            st.write(f"Edits project: {result.edits_project}")
            st.write(
                "Updates director policy: "
                f"{result.updates_director_policy}"
            )
            st.write(f"Auto apply: {result.auto_apply}")
            st.write(f"Auto publication: {result.auto_publication}")
            st.write(f"Uses LLM: {result.uses_llm}")
            st.write(f"Network calls: {result.network_calls}")

    except Exception as exc:
        _render_failure(exc)
