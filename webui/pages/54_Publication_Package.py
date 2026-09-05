from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.finalization_e2e import FinalizationE2EPlan  # noqa: E402
from app.models.publication_package import (  # noqa: E402
    PublicationMetadata,
    PublicationPackageRequest,
    PublicationPackageStatus,
    PublicationSupportManifest,
)
from app.services.publication_package import build_publication_package  # noqa: E402


st.set_page_config(page_title="F54 · El Centinela", layout="wide")
st.title("F54 · Manual Publication Package")
st.caption(
    "Valida el plan contractual del paquete de publicación manual. "
    "No crea archivos, no sube contenido y no publica."
)

finalization_file = st.file_uploader(
    "FinalizationE2EPlan (JSON)",
    type=["json"],
    key="f54-finalization",
)
support_file = st.file_uploader(
    "PublicationSupportManifest (JSON, opcional)",
    type=["json"],
    key="f54-support",
)

st.subheader("Metadata editorial")
title = st.text_input("Título")
caption = st.text_area("Caption", height=120)
hashtags_text = st.text_input(
    "Hashtags",
    placeholder="#astronomia #astrofotografia",
)
youtube_description = st.text_area(
    "Descripción de YouTube (opcional)",
    height=100,
)


def _json_payload(uploaded) -> object:
    return json.loads(uploaded.getvalue().decode("utf-8"))


def _hashtags(value: str) -> list[str]:
    return [item.strip() for item in value.split() if item.strip()]


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido preparar el plan F54. "
        "No se ha escrito, subido ni publicado ningún archivo."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.code(f"{type(exc).__name__}: {exc}", language=None)


if st.button("Validar plan de paquete F54", type="primary"):
    try:
        if finalization_file is None:
            raise ValueError("carga un FinalizationE2EPlan JSON")

        finalization = FinalizationE2EPlan.model_validate(
            _json_payload(finalization_file)
        )
        support = (
            PublicationSupportManifest.model_validate(_json_payload(support_file))
            if support_file is not None
            else PublicationSupportManifest()
        )
        metadata = None
        if any((title.strip(), caption.strip(), hashtags_text.strip(), youtube_description.strip())):
            if not title.strip() or not caption.strip():
                raise ValueError(
                    "si aportas metadata, título y caption son obligatorios"
                )
            metadata = PublicationMetadata(
                title=title.strip(),
                caption=caption.strip(),
                hashtags=_hashtags(hashtags_text),
                youtube_description=youtube_description.strip() or None,
            )

        result = build_publication_package(
            PublicationPackageRequest(
                finalization=finalization,
                metadata=metadata,
                support=support,
            )
        )

        if result.status == PublicationPackageStatus.READY_FOR_MANUAL_PACKAGE:
            st.success("Contrato F54 listo para paquete manual")
        else:
            st.warning(f"F54: {result.status.value}")

        st.metric(
            "Assets requeridos presentes",
            f"{result.present_required_asset_count}/{result.required_asset_count}",
        )
        st.metric(
            "Assets requeridos con SHA256",
            f"{result.hashed_required_asset_count}/{result.required_asset_count}",
        )
        st.metric("Derechos preparados", "Sí" if result.rights_ready else "No")

        st.info(
            "READY_FOR_MANUAL_PACKAGE sólo significa que el contrato está listo. "
            "Esta página no materializa el paquete, no escribe archivos y no autoriza "
            "ni ejecuta publicación."
        )

        if result.assets:
            st.subheader("Assets contractuales")
            for asset in result.assets:
                icon = "✓" if asset.present and asset.sha256 else "•"
                with st.container(border=True):
                    st.markdown(f"### {icon} {asset.target_filename}")
                    st.caption(f"asset_id: {asset.asset_id}")
                    st.write(f"Present: {asset.present}")
                    st.write(f"SHA256: {asset.sha256 or '—'}")
                    st.write(
                        f"Publication rights ready: {asset.publication_rights_ready}"
                    )
        else:
            st.caption("F54 aún no ha construido assets para el estado actual.")

        with st.expander("Trazabilidad y guardrails", expanded=False):
            st.write(f"Estado backend: {result.status.value}")
            st.write(f"Hash F54: {result.publication_package_hash}")
            st.write(f"Source F53 hash: {result.source_finalization_e2e_hash}")
            st.write(f"Planning only: {result.planning_only}")
            st.write(f"Manual publication only: {result.manual_publication_only}")
            st.write(f"Writes files: {result.writes_files}")
            st.write(f"Uploads files: {result.uploads_files}")
            st.write(f"Network calls: {result.network_calls}")
            st.write(f"Webhook calls: {result.webhook_calls}")
            st.write(f"Authorization to publish: {result.authorization_to_publish}")
            st.write(f"Marks published: {result.marks_published}")
            st.write(f"Auto publication: {result.auto_publication}")
            st.write(
                "Local final certification required: "
                f"{result.local_final_certification_required}"
            )
            st.write(f"Generated UTC: {result.generated_at_utc.isoformat()}")
    except Exception as exc:
        _render_failure(exc)
