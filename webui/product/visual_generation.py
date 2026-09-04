from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import streamlit as st

from app.models.astronomy_director import AstronomyVideoPlan
from app.models.astromedia import MediaType, Provider, Rights
from app.services.centinela.capabilities import ProviderCapability
from app.services.centinela.generative.contracts import (
    GeneratedMediaType,
    GeneratedVisualAsset,
    GenerationQuality,
    SceneAssetIndex,
    ScientificVisualStatus,
    VisualGenerationMode,
    VisualGenerationRequest,
)
from app.services.centinela.generative.execution import (
    VisualGenerationExecutionError,
    VisualOutOfMemoryError,
    execute_visual_request,
)
from app.services.centinela.generative.mpt_bridge import (
    GeneratedMaterialBridgeError,
    generated_video_to_material,
)
from app.services.centinela.generative.provenance import (
    build_generated_visual_provenance,
)
from app.services.centinela.generative.providers import (
    build_local_generative_provider_definitions,
)
from app.services.centinela.generative.router import (
    ProviderRuntimeState,
    VisualProviderRoutingError,
    required_capability,
)
from app.services.centinela.media_resolver.models import (
    MediaResolutionReport,
    NormalizedMediaCandidate,
)

from . import ui


VISUAL_SOURCE_OWN = "MATERIAL_PROPIO"
VISUAL_SOURCE_ONLINE = "ONLINE_VERIFIED"
VISUAL_SOURCE_AI = "AI_GENERATED"
VISUAL_SOURCE_HYBRID = "HYBRID"
VISUAL_SOURCES = (
    VISUAL_SOURCE_OWN,
    VISUAL_SOURCE_ONLINE,
    VISUAL_SOURCE_AI,
    VISUAL_SOURCE_HYBRID,
)
VISUAL_SOURCE_LABELS = {
    VISUAL_SOURCE_OWN: "Material propio",
    VISUAL_SOURCE_ONLINE: "Online verificado",
    VISUAL_SOURCE_AI: "Generación con IA",
    VISUAL_SOURCE_HYBRID: "Híbrido",
}

MODE_LABELS = {
    VisualGenerationMode.TEXT_TO_IMAGE: "Texto → imagen",
    VisualGenerationMode.IMAGE_TO_VIDEO: "Imagen → vídeo",
    VisualGenerationMode.TEXT_TO_VIDEO: "Texto → vídeo",
}
MODE_PANEL_TITLES = {
    VisualGenerationMode.TEXT_TO_IMAGE: "GENERAR IMAGEN",
    VisualGenerationMode.IMAGE_TO_VIDEO: "ANIMAR IMAGEN",
    VisualGenerationMode.TEXT_TO_VIDEO: "CREAR VÍDEO DESDE TEXTO",
}
QUALITY_LABELS = {
    GenerationQuality.PREVIEW: "PREVIEW",
    GenerationQuality.STANDARD: "STANDARD",
    GenerationQuality.MASTER: "MASTER",
}

AI_SCIENTIFIC_STATUS = ScientificVisualStatus.RECREACION_VISUAL
RUNTIME_STATES_SESSION_KEY = "centinela_visual_runtime_states"
ADAPTERS_SESSION_KEY = "centinela_visual_generation_adapters"
ASSET_INDEX_SESSION_KEY = "centinela_visual_asset_index"
ASSET_REQUESTS_SESSION_KEY = "centinela_visual_asset_requests"
SOURCE_HASHES_SESSION_KEY = "centinela_visual_source_hashes"
SELECTED_ASSETS_SESSION_KEY = "centinela_visual_selected_assets"
MPT_MATERIALS_SESSION_KEY = "centinela_visual_mpt_materials"


@dataclass(frozen=True, slots=True)
class SceneVisualContext:
    scene_number: int
    scene_id: str
    act: str
    duration_seconds: int
    visual_requirement: str
    selection_status: str
    selected_media_id: str | None
    candidates: tuple[NormalizedMediaCandidate, ...]


@dataclass(frozen=True, slots=True)
class SourceImageOption:
    option_id: str
    label: str
    local_path: str
    sha256: str | None
    provider: str
    generated_asset_id: str | None = None


@dataclass(slots=True)
class _ObservedAdapter:
    delegate: Any

    def __post_init__(self) -> None:
        self.provider_id = str(getattr(self.delegate, "provider_id", "")).strip()
        self.qualities: list[GenerationQuality] = []

    def generate(self, request: VisualGenerationRequest) -> GeneratedVisualAsset:
        self.qualities.append(request.quality)
        return self.delegate.generate(request)


def build_visual_request(
    *,
    scene_id: str,
    mode: VisualGenerationMode,
    prompt: str,
    quality: GenerationQuality = GenerationQuality.STANDARD,
    aspect_ratio: str = "9:16",
    source_image: str | None = None,
    negative_prompt: str = "",
    seed: int | None = None,
    duration_seconds: float | None = None,
) -> VisualGenerationRequest:
    return VisualGenerationRequest(
        scene_id=scene_id,
        mode=mode,
        prompt=prompt,
        quality=quality,
        aspect_ratio=aspect_ratio,
        source_image=source_image,
        negative_prompt=negative_prompt,
        seed=seed,
        duration_seconds=duration_seconds,
    )


def provider_for_mode(mode: VisualGenerationMode):
    capability = required_capability(mode)
    matches = [
        provider
        for provider in build_local_generative_provider_definitions()
        if provider.supports(ProviderCapability.GENERATE)
        and provider.supports(capability)
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one declared provider for {mode.value}, found {len(matches)}"
        )
    return matches[0]


def normalize_runtime_state(
    value: ProviderRuntimeState | Mapping[str, Any] | None,
) -> ProviderRuntimeState:
    if value is None:
        return ProviderRuntimeState()
    if isinstance(value, ProviderRuntimeState):
        return value
    return ProviderRuntimeState(
        enabled=bool(value.get("enabled", False)),
        adapter_registered=bool(value.get("adapter_registered", False)),
        weights_available=bool(value.get("weights_available", False)),
        hardware_certified=bool(value.get("hardware_certified", False)),
    )


def runtime_state_for(
    provider_id: str,
    runtime_states: Mapping[str, ProviderRuntimeState | Mapping[str, Any]] | None,
) -> ProviderRuntimeState:
    states = runtime_states or {}
    return normalize_runtime_state(states.get(provider_id))


def can_execute_visual_generation(state: ProviderRuntimeState) -> bool:
    return state.ready


def current_upscale_contract_supported() -> bool:
    return any(
        provider.supports(ProviderCapability.UPSCALE)
        for provider in build_local_generative_provider_definitions()
    )


def asset_can_enter_mpt(asset: GeneratedVisualAsset) -> bool:
    return asset.media_type is GeneratedMediaType.VIDEO


def quality_attempts_label(qualities: list[GenerationQuality]) -> str:
    return " → ".join(QUALITY_LABELS[item] for item in qualities)


def correlate_scene_contexts(
    plan: AstronomyVideoPlan,
    report: MediaResolutionReport,
) -> tuple[SceneVisualContext, ...]:
    by_number = {item.scene_number: item for item in report.scenes}
    if len(by_number) != len(report.scenes):
        raise ValueError("media_resolution contains duplicate scene numbers")
    if len(plan.scenes) != report.scene_count:
        raise ValueError("scene_plan and media_resolution scene counts do not match")

    contexts: list[SceneVisualContext] = []
    seen_ids: set[str] = set()
    for scene in plan.scenes:
        evidence = by_number.get(scene.scene_number)
        if evidence is None:
            raise ValueError(f"media_resolution missing scene {scene.scene_number}")
        scene_id = str(evidence.scene_key or "").strip()
        if not scene_id or scene_id in seen_ids:
            raise ValueError("scene_key must be present and unique")
        seen_ids.add(scene_id)
        contexts.append(
            SceneVisualContext(
                scene_number=scene.scene_number,
                scene_id=scene_id,
                act=scene.act.value,
                duration_seconds=scene.duration_seconds,
                visual_requirement=scene.visual_requirement,
                selection_status=evidence.selection_status,
                selected_media_id=evidence.selected_media_id,
                candidates=tuple(evidence.candidates),
            )
        )
    return tuple(contexts)


def load_scene_visual_contexts(
    service: Any,
    project_id: str,
) -> tuple[SceneVisualContext, ...]:
    scene_ref = service.store.get_latest_artifact(project_id, "scene_plan")
    media_ref = service.store.get_latest_artifact(project_id, "media_resolution")
    plan = AstronomyVideoPlan.model_validate(
        service.store.read_json(project_id, scene_ref.artifact_id)
    )
    report = MediaResolutionReport.model_validate(
        service.store.read_json(project_id, media_ref.artifact_id)
    )
    return correlate_scene_contexts(plan, report)


def image_source_options(
    scene: SceneVisualContext,
    asset_index: SceneAssetIndex,
) -> tuple[SourceImageOption, ...]:
    options: list[SourceImageOption] = []
    for candidate in scene.candidates:
        if candidate.media_type is not MediaType.IMAGE:
            continue
        if candidate.rights_status is Rights.RESTRICTED:
            continue
        label = candidate.title.strip() or candidate.media_id
        options.append(
            SourceImageOption(
                option_id=f"catalog:{candidate.media_id}",
                label=f"{label} · {candidate.provider.value}",
                local_path=candidate.local_path,
                sha256=candidate.content_sha256,
                provider=candidate.provider.value,
            )
        )

    for asset in asset_index.for_scene(scene.scene_id):
        if asset.media_type is not GeneratedMediaType.IMAGE:
            continue
        options.append(
            SourceImageOption(
                option_id=f"generated:{asset.asset_id}",
                label=f"{asset.asset_id} · IA",
                local_path=asset.local_path,
                sha256=asset.sha256,
                provider=asset.provider_id,
                generated_asset_id=asset.asset_id,
            )
        )
    return tuple(options)


def candidate_matches_visual_source(
    candidate: NormalizedMediaCandidate,
    source: str,
) -> bool:
    if source == VISUAL_SOURCE_OWN:
        return (
            candidate.provider is Provider.OWN_MEDIA
            and candidate.rights_status is Rights.CONFIRMED_OWNED
        )
    if source == VISUAL_SOURCE_ONLINE:
        return (
            candidate.provider is not Provider.OWN_MEDIA
            and candidate.rights_status is Rights.VERIFIED_LICENSE
            and candidate.publication_eligible
        )
    return False


def _asset_index() -> SceneAssetIndex:
    current = st.session_state.get(ASSET_INDEX_SESSION_KEY)
    if isinstance(current, SceneAssetIndex):
        return current
    current = SceneAssetIndex()
    st.session_state[ASSET_INDEX_SESSION_KEY] = current
    return current


def _session_mapping(key: str) -> dict[str, Any]:
    current = st.session_state.get(key)
    if isinstance(current, dict):
        return current
    current = {}
    st.session_state[key] = current
    return current


def _runtime_states() -> dict[str, ProviderRuntimeState]:
    raw = st.session_state.get(RUNTIME_STATES_SESSION_KEY)
    if not isinstance(raw, Mapping):
        raw = {}
    return {
        provider.provider_id: runtime_state_for(provider.provider_id, raw)
        for provider in build_local_generative_provider_definitions()
    }


def _runtime_status(provider: Any, state: ProviderRuntimeState) -> None:
    ui.render_runtime_status_card(
        provider.display_name,
        ready=state.ready,
        enabled=state.enabled,
        adapter_registered=state.adapter_registered,
        weights_available=state.weights_available,
        hardware_certified=state.hardware_certified,
    )
    if state.ready:
        st.success("Motor local preparado para esta operación.")
    else:
        st.caption(
            "Generación local pendiente de certificación. La configuración está preparada, "
            "pero este motor necesita el runtime local y el hardware certificado antes de "
            "poder generar contenido."
        )
        if not state.hardware_certified:
            st.caption("RTX 2060: certificación pendiente en el PC.")


def _science_notice() -> None:
    ui.render_ai_classification_badge()
    with st.expander("Qué significa RECREACIÓN VISUAL", expanded=False):
        st.write(
            "Contenido generado o transformado mediante IA. No constituye evidencia "
            "observacional directa."
        )


def _seed_value(key: str) -> int | None:
    use_seed = st.checkbox("Fijar seed", value=False, key=f"{key}-use-seed")
    if not use_seed:
        return None
    return int(
        st.number_input(
            "Seed",
            min_value=0,
            value=0,
            step=1,
            key=f"{key}-seed",
        )
    )


def _advanced_generation_fields(key: str) -> tuple[int | None, str]:
    with st.expander("Opciones avanzadas", expanded=False):
        seed = _seed_value(key)
        negative_prompt = st.text_area(
            "Negative prompt · opcional",
            value="",
            key=f"{key}-negative",
            height=88,
        )
        st.caption(
            "El prompt bruto no se persiste en provenance; se conserva su hash SHA-256."
        )
    return seed, negative_prompt


def _render_existing_source(scene: SceneVisualContext, source: str) -> None:
    matches = [
        candidate
        for candidate in scene.candidates
        if candidate_matches_visual_source(candidate, source)
    ]
    if not matches:
        ui.render_empty_state(
            "No hay material elegible en esta categoría",
            "La selección actual no contiene candidatos que cumplan este origen y estado de derechos.",
        )
        return

    for candidate in matches[:4]:
        with st.container(border=True):
            st.markdown(f"### {candidate.title or candidate.media_id}")
            st.caption(
                f"{candidate.provider.value} · {candidate.media_type.value} · "
                f"{candidate.rights_status.value}"
            )
            if candidate.media_id == scene.selected_media_id:
                st.success("Seleccionado actualmente por MaterialSelector")
            if candidate.attribution:
                st.caption(candidate.attribution)


def _show_safe_provenance(
    request: VisualGenerationRequest,
    asset: GeneratedVisualAsset,
    source_sha256: str | None,
) -> None:
    try:
        record = build_generated_visual_provenance(
            request,
            asset,
            source_image_sha256=source_sha256,
        )
    except ValueError as exc:
        ui.render_error_state(
            "No se pudo presentar la trazabilidad segura de este asset.",
            technical_detail=exc,
        )
        return

    with st.expander("Trazabilidad", expanded=False):
        st.write(f"**Proveedor:** {record.get('provider', asset.provider_id)}")
        st.write(f"**Modelo:** {record.get('model', asset.model_id)}")
        st.write(f"**Clasificación:** {record.get('scientific_status')}")
        st.code(ui.short_identifier(record.get("sha256")), language=None)
        st.caption(f"Asset SHA · {ui.short_identifier(record.get('sha256'))}")
        st.caption(f"Prompt SHA · {ui.short_identifier(record.get('prompt_sha256'))}")
        if record.get("source_image_sha256"):
            st.caption(
                "Source SHA · "
                f"{ui.short_identifier(record.get('source_image_sha256'))}"
            )
        if record.get("seed") is not None:
            st.write(f"**Seed:** {record['seed']}")
        st.caption("Las rutas locales absolutas y el prompt bruto no se muestran aquí.")


def _select_for_mpt(
    scene: SceneVisualContext,
    asset: GeneratedVisualAsset,
    request: VisualGenerationRequest | None,
    source_sha256: str | None,
) -> None:
    if not asset_can_enter_mpt(asset):
        st.caption(
            "Una imagen generada no puede entrar directamente en el compositor de vídeo. "
            "Debe pasar por Imagen → vídeo."
        )
        return
    if request is None:
        ui.render_error_state(
            "Falta el request original necesario para validar el handoff a MPT."
        )
        return

    if st.button(
        "Usar en esta escena",
        key=f"use-generated-{scene.scene_id}-{asset.asset_id}",
        use_container_width=True,
    ):
        try:
            material = generated_video_to_material(
                request,
                asset,
                source_image_sha256=source_sha256,
                require_existing_file=True,
            )
        except (GeneratedMaterialBridgeError, ValueError) as exc:
            ui.render_error_state(
                "Este asset no puede entrar todavía en el compositor.",
                action="El bridge permanece bloqueado hasta que el archivo real sea válido.",
                technical_detail=exc,
            )
            return
        _session_mapping(SELECTED_ASSETS_SESSION_KEY)[scene.scene_id] = asset.asset_id
        _session_mapping(MPT_MATERIALS_SESSION_KEY)[scene.scene_id] = material
        st.success("Asset seleccionado para esta escena y validado por el bridge MPT.")


def _prepare_i2v_from_asset(scene_id: str, asset_id: str) -> None:
    st.session_state[f"visual-mode-{scene_id}"] = VisualGenerationMode.IMAGE_TO_VIDEO
    st.session_state[
        f"visual-{scene_id}-{VisualGenerationMode.IMAGE_TO_VIDEO.value}-source"
    ] = f"generated:{asset_id}"


def _render_asset_history(scene: SceneVisualContext, asset_index: SceneAssetIndex) -> None:
    assets = asset_index.for_scene(scene.scene_id)
    ui.render_section_heading(
        "Versiones de la escena",
        "Las versiones anteriores se conservan y la trazabilidad técnica permanece plegada.",
        eyebrow="HISTORIAL",
    )
    if not assets:
        ui.render_empty_state(
            "Todavía no hay visuales generados para esta escena.",
            "Cuando exista un asset real aparecerá aquí con versión, clasificación y trazabilidad.",
        )
        return

    requests = _session_mapping(ASSET_REQUESTS_SESSION_KEY)
    source_hashes = _session_mapping(SOURCE_HASHES_SESSION_KEY)
    selected = _session_mapping(SELECTED_ASSETS_SESSION_KEY).get(scene.scene_id)

    for version, asset in enumerate(assets, start=1):
        with st.container(border=True):
            st.caption(f"v{version}")
            title = (
                "Vídeo generado"
                if asset.media_type is GeneratedMediaType.VIDEO
                else "Imagen generada"
            )
            st.markdown(f"### {title}")
            st.caption(f"{asset.provider_id} · {asset.model_id}")
            ui.render_ai_classification_badge()
            st.code(ui.short_identifier(asset.sha256), language=None)
            if selected == asset.asset_id:
                st.success("● Seleccionado")
            if asset.generation_seconds is not None:
                st.caption(f"Generación: {asset.generation_seconds:.2f} s")

            local_path = Path(asset.local_path)
            if local_path.is_file():
                if asset.media_type is GeneratedMediaType.IMAGE:
                    st.image(str(local_path))
                else:
                    st.video(str(local_path))

            request = requests.get(asset.asset_id)
            source_sha256 = source_hashes.get(asset.asset_id)
            if isinstance(request, VisualGenerationRequest):
                _show_safe_provenance(request, asset, source_sha256)

            if asset.media_type is GeneratedMediaType.IMAGE:
                st.caption(
                    "Esta imagen debe pasar por Imagen → vídeo antes de entrar en el montaje."
                )
                st.button(
                    "Animar para vídeo",
                    key=f"animate-generated-{scene.scene_id}-{asset.asset_id}",
                    use_container_width=True,
                    on_click=_prepare_i2v_from_asset,
                    args=(scene.scene_id, asset.asset_id),
                )
            else:
                _select_for_mpt(scene, asset, request, source_sha256)


def _execute_request(
    request: VisualGenerationRequest,
    *,
    provider: Any,
    state: ProviderRuntimeState,
    source_sha256: str | None,
    asset_index: SceneAssetIndex,
) -> None:
    if not state.ready:
        return

    adapters = st.session_state.get(ADAPTERS_SESSION_KEY)
    if not isinstance(adapters, Mapping):
        adapters = {}
    delegate = adapters.get(provider.provider_id)
    if delegate is None:
        ui.render_error_state(
            "El estado indica que el adaptador está registrado, pero no está disponible en esta sesión.",
            action="No se ha ejecutado ninguna generación.",
        )
        return

    observed = _ObservedAdapter(delegate)
    runtime_states = _runtime_states()
    try:
        with st.spinner("Generando material visual local…", show_time=True):
            asset = execute_visual_request(
                request,
                providers=build_local_generative_provider_definitions(),
                runtime_states=runtime_states,
                adapters={provider.provider_id: observed},
                preferred_provider_id=provider.provider_id,
                allow_provider_fallback=False,
            )
    except VisualOutOfMemoryError as exc:
        attempted = quality_attempts_label(observed.qualities)
        ui.render_error_state(
            "No se pudo completar la generación con la memoria disponible.",
            action=(
                f"Intentos: {attempted or QUALITY_LABELS[request.quality]}. "
                "No se han realizado más intentos ni se ha cambiado de proveedor."
            ),
            technical_detail=exc,
        )
        return
    except (VisualProviderRoutingError, VisualGenerationExecutionError, ValueError) as exc:
        ui.render_error_state(
            "La generación se detuvo de forma segura.",
            action="No se ha creado ningún asset.",
            technical_detail=exc,
        )
        return

    asset_index.register(asset)
    _session_mapping(ASSET_REQUESTS_SESSION_KEY)[asset.asset_id] = request
    _session_mapping(SOURCE_HASHES_SESSION_KEY)[asset.asset_id] = source_sha256

    if len(observed.qualities) > 1:
        initial, final = observed.qualities[0], observed.qualities[-1]
        st.warning(
            f"{QUALITY_LABELS[initial]} no pudo completarse por memoria. "
            f"Se utilizó el único fallback permitido: {QUALITY_LABELS[final]}."
        )
    st.success("Asset generado y añadido al historial de esta escena.")


def _render_generation_panel(
    scene: SceneVisualContext,
    asset_index: SceneAssetIndex,
) -> None:
    with st.container(border=True):
        st.caption("GENERACIÓN VISUAL")
        _science_notice()

        mode = st.radio(
            "Modo",
            options=list(VisualGenerationMode),
            format_func=lambda value: MODE_LABELS[value],
            key=f"visual-mode-{scene.scene_id}",
            horizontal=True,
        )
        st.markdown(f"### {MODE_PANEL_TITLES[mode]}")

        provider = provider_for_mode(mode)
        state = runtime_state_for(provider.provider_id, _runtime_states())

        key = f"visual-{scene.scene_id}-{mode.value}"
        source_option: SourceImageOption | None = None

        if mode is VisualGenerationMode.IMAGE_TO_VIDEO:
            source_options = image_source_options(scene, asset_index)
            if source_options:
                source_map = {item.option_id: item for item in source_options}
                selected_source = st.selectbox(
                    "Imagen maestra",
                    options=list(source_map),
                    format_func=lambda value: source_map[value].label,
                    key=f"{key}-source",
                )
                source_option = source_map[selected_source]
                source_path = Path(source_option.local_path)
                if source_path.is_file():
                    st.image(str(source_path), caption="Imagen maestra seleccionada")
            else:
                st.warning(
                    "Imagen → vídeo necesita una imagen real o generada asociada a esta escena."
                )

        prompt_label = (
            "Movimiento"
            if mode is VisualGenerationMode.IMAGE_TO_VIDEO
            else "Prompt"
        )
        prompt = st.text_area(
            prompt_label,
            placeholder=(
                "Describe un movimiento contenido, cinematográfico y coherente con la escena."
                if mode is VisualGenerationMode.IMAGE_TO_VIDEO
                else "Describe el visual que debe representar esta escena."
            ),
            key=f"{key}-prompt",
            height=132,
        )

        quality = st.radio(
            "Calidad",
            options=list(GenerationQuality),
            index=1,
            format_func=lambda value: QUALITY_LABELS[value].title(),
            key=f"{key}-quality",
            horizontal=True,
        )

        st.caption("Formato")
        ui.render_format_chips(("9:16",))
        aspect_ratio = "9:16"

        duration_seconds: float | None = None
        if mode is not VisualGenerationMode.TEXT_TO_IMAGE:
            duration_seconds = float(
                st.number_input(
                    "Duración (s)",
                    min_value=0.5,
                    max_value=45.0,
                    value=float(scene.duration_seconds),
                    step=0.5,
                    key=f"{key}-duration",
                )
            )

        seed, negative_prompt = _advanced_generation_fields(key)
        _runtime_status(provider, state)

        request: VisualGenerationRequest | None = None
        validation_error: Exception | None = None
        if prompt.strip():
            try:
                request = build_visual_request(
                    scene_id=scene.scene_id,
                    mode=mode,
                    prompt=prompt,
                    quality=quality,
                    aspect_ratio=aspect_ratio,
                    source_image=source_option.local_path if source_option else None,
                    negative_prompt=negative_prompt,
                    seed=seed,
                    duration_seconds=duration_seconds,
                )
            except ValueError as exc:
                validation_error = exc

        if validation_error is not None:
            st.warning(str(validation_error))

        source_missing = (
            mode is VisualGenerationMode.IMAGE_TO_VIDEO and source_option is None
        )
        disabled = (
            not state.ready
            or request is None
            or validation_error is not None
            or source_missing
        )
        button_label = (
            "Generar imagen"
            if mode is VisualGenerationMode.TEXT_TO_IMAGE
            else "Generar vídeo"
        )
        clicked = st.button(
            button_label,
            type="primary",
            disabled=disabled,
            key=f"{key}-generate",
            use_container_width=True,
        )
        if clicked and request is not None:
            _execute_request(
                request,
                provider=provider,
                state=state,
                source_sha256=source_option.sha256 if source_option else None,
                asset_index=asset_index,
            )

        if not state.ready:
            st.caption("Generación local pendiente de certificación.")


def _render_upscale_status() -> None:
    with st.expander("Funciones adicionales", expanded=False):
        st.markdown("**Upscale**")
        if current_upscale_contract_supported():
            st.info("Capacidad declarada; la ejecución depende del runtime certificado.")
        else:
            st.caption("Próximamente / runtime no disponible")
            st.caption(
                "Los providers visuales V1 actuales no declaran Upscale y "
                "VisualGenerationRequest no expone ese modo. No existe CTA operativo."
            )


def render_visual_generation_workspace(service: Any, project: Any) -> None:
    ui.render_section_heading(
        "Visuales por escena",
        "Elige la fuente visual de cada escena. La IA permanece fail-closed hasta certificar el runtime local.",
        eyebrow="MATERIALES",
    )
    try:
        scenes = load_scene_visual_contexts(service, project.project_id)
    except Exception as exc:
        ui.render_empty_state(
            "Visuales por escena aún no disponibles",
            "Esta sección aparecerá cuando existan el plan de escenas y la resolución de medios del proyecto.",
        )
        with st.expander("Detalle", expanded=False):
            st.caption(type(exc).__name__)
        return

    scene_map = {scene.scene_id: scene for scene in scenes}
    scene_id = st.selectbox(
        "Escena",
        options=list(scene_map),
        format_func=lambda value: (
            f"Escena {scene_map[value].scene_number:02d} · "
            f"{scene_map[value].act.replace('_', ' ').title()}"
        ),
        key=f"visual-scene-{project.project_id}",
    )
    scene = scene_map[scene_id]

    with st.container(border=True):
        st.caption(f"ESCENA {scene.scene_number:02d}")
        st.markdown(f"### {scene.visual_requirement}")
        st.caption(
            f"{scene.act.replace('_', ' ').title()} · "
            f"{scene.duration_seconds} s · {scene.selection_status}"
        )

    source = st.radio(
        "Fuente visual",
        options=list(VISUAL_SOURCES),
        format_func=lambda value: VISUAL_SOURCE_LABELS[value],
        key=f"visual-source-{scene.scene_id}",
        horizontal=True,
    )

    if source in {VISUAL_SOURCE_OWN, VISUAL_SOURCE_ONLINE}:
        _render_existing_source(scene, source)
    elif source == VISUAL_SOURCE_AI:
        _render_generation_panel(scene, _asset_index())
    else:
        with st.container(border=True):
            st.markdown("### Flujo híbrido")
            st.caption(
                "Combina material existente con generación IA sin sustituir la autoridad de MaterialSelector."
            )
            if scene.selected_media_id:
                st.write(f"Material existente seleccionado: **{scene.selected_media_id}**")
        _render_generation_panel(scene, _asset_index())

    _render_upscale_status()
    _render_asset_history(scene, _asset_index())
