from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.models.astronomy import AstronomyContext, ScientificStatus
from app.models.astronomy_director import (
    AstronomyDirectorHealth,
    AstronomyDirectorRequest,
    AstronomyVideoPlan,
    AstronomyVideoPlanDraft,
    DirectorBackend,
    GenerationOrigin,
    GroundingFact,
    GroundingPacket,
    NarrativeAct,
    PlanScientificClaim,
    ScenePlan,
    ShotType,
)
from app.services.astronomy_core import build_astronomy_context


SOURCE_PRIORITY = [
    "OWN_MEDIA",
    "ASTRONOMY_SPECIFIC_FREE",
    "NASA",
    "ESA",
    "WIKIMEDIA",
    "PEXELS",
    "PIXABAY",
    "COVERR",
    "AI_GENERATED_LAST_RESORT",
]

ACT_ORDER = {
    NarrativeAct.INTRODUCTION: 0,
    NarrativeAct.DEVELOPMENT: 1,
    NarrativeAct.CLIMAX: 2,
    NarrativeAct.RESOLUTION: 3,
    NarrativeAct.EPILOGUE: 4,
}

PREFERRED_OLLAMA_MODELS = (
    "qwen3.5:4b-q4_K_M",
    "qwen3.5:4b",
    "qwen3:4b",
    "qwen2.5:7b",
)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\\s*(.*?)\\s*```", re.IGNORECASE | re.DOTALL)


class AstronomyDirectorError(RuntimeError):
    pass


class PlanValidationError(AstronomyDirectorError):
    pass


class OllamaLocalAdapter:
    """Minimal local-only Ollama REST adapter.

    The Director deliberately does not inherit MPT's global provider because the
    global provider may be commercial. Phase 3 is pinned to loopback Ollama.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 180.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        if self.base_url != "http://127.0.0.1:11434":
            raise AstronomyDirectorError(
                "Phase 3 only permits Ollama on http://127.0.0.1:11434"
            )

    def _request_json(
        self,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        method: str | None = None,
    ) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AstronomyDirectorError(
                "Ollama local request failed: " + str(exc)
            ) from exc

        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AstronomyDirectorError("Ollama returned invalid HTTP JSON") from exc

        if not isinstance(value, dict):
            raise AstronomyDirectorError("Unexpected Ollama response payload")
        return value

    def available_models(self) -> list[str]:
        payload = self._request_json("/api/tags", method="GET")
        result = []
        for item in payload.get("models", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if name:
                result.append(name)
        return sorted(set(result))

    def resolve_model(self, requested: str | None) -> str:
        available = self.available_models()
        if requested:
            requested = requested.strip()
            if requested not in available:
                raise AstronomyDirectorError(
                    f"Ollama model is not installed: {requested}. "
                    "No model will be downloaded automatically."
                )
            return requested

        for model in PREFERRED_OLLAMA_MODELS:
            if model in available:
                return model

        qwen = [name for name in available if "qwen" in name.casefold()]
        if qwen:
            return qwen[0]
        if available:
            return available[0]
        raise AstronomyDirectorError(
            "Ollama is reachable but has no installed models. "
            "No model will be downloaded automatically."
        )

    def generate_json(
        self,
        *,
        model: str,
        prompt: str,
        temperature: float,
        schema: dict[str, Any],
    ) -> str:
        # Qwen 3.x thinking is enabled by default in Ollama. For strict JSON we
        # explicitly disable it so the token budget is spent on final content.
        payload = self._request_json(
            "/api/chat",
            method="POST",
            payload={
                "model": model,
                "stream": False,
                "think": False,
                "format": schema,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Devuelve exclusivamente el objeto JSON solicitado. "
                            "No incluyas markdown, análisis ni texto fuera del JSON."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "options": {
                    "temperature": temperature,
                    "num_ctx": 8192,
                    "num_predict": 4096,
                },
                "keep_alive": "5m",
            },
        )

        message = payload.get("message")
        if not isinstance(message, dict):
            raise AstronomyDirectorError("Ollama response is missing message")

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            thinking = message.get("thinking")
            thinking_chars = len(thinking) if isinstance(thinking, str) else 0
            done_reason = str(payload.get("done_reason") or "unknown")
            eval_count = payload.get("eval_count")
            raise AstronomyDirectorError(
                "Ollama returned empty final content with think=false. "
                f"done_reason={done_reason}; thinking_chars={thinking_chars}; "
                f"eval_count={eval_count}."
            )

        return content.strip()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest().upper()


def _event_value(value):
    return None if value is None else value.model_dump(mode="json")


def build_grounding_packet(context: AstronomyContext) -> GroundingPacket:
    facts: list[GroundingFact] = []

    def add(fact_id, label, value, unit, status, source_ids):
        facts.append(
            GroundingFact(
                fact_id=fact_id,
                label_es=label,
                value=value,
                unit=unit,
                scientific_status=status,
                source_ids=source_ids,
            )
        )

    add(
        "context:moment_utc",
        "Instante UTC",
        context.moment_utc.isoformat(),
        None,
        context.scientific_status,
        [],
    )
    add(
        "context:moment_local",
        "Instante local",
        context.moment_local.isoformat(),
        None,
        context.scientific_status,
        [],
    )
    add(
        "observer:latitude_deg",
        "Latitud del observador",
        context.observer.latitude_deg,
        "deg",
        context.scientific_status,
        [],
    )
    add(
        "observer:longitude_deg",
        "Longitud del observador",
        context.observer.longitude_deg,
        "deg",
        context.scientific_status,
        [],
    )

    for body in context.bodies:
        prefix = f"body:{body.body.value}"
        for suffix, label, value, unit in (
            (
                "altitude_apparent_deg",
                "Altitud aparente",
                body.altitude_apparent_deg,
                "deg",
            ),
            ("azimuth_deg", "Azimut", body.azimuth_deg, "deg"),
            ("constellation", "Constelación", body.constellation_name, None),
            (
                "geocentric_distance_km",
                "Distancia geocéntrica",
                body.geocentric_distance_km,
                "km",
            ),
            ("visual_magnitude", "Magnitud visual", body.visual_magnitude, "mag"),
            (
                "illuminated_fraction",
                "Fracción iluminada",
                body.illuminated_fraction,
                "fraction",
            ),
            ("next_rise", "Próxima salida", _event_value(body.next_rise), None),
            ("next_set", "Próxima puesta", _event_value(body.next_set), None),
            (
                "next_culmination",
                "Próxima culminación",
                _event_value(body.next_culmination),
                None,
            ),
        ):
            add(
                f"{prefix}:{suffix}",
                f"{body.body.value}: {label}",
                value,
                unit,
                body.scientific_status,
                list(body.source_ids),
            )

    moon = context.moon
    for suffix, label, value, unit in (
        ("phase_name", "Fase lunar", moon.phase_name_es, None),
        (
            "illuminated_fraction",
            "Fracción lunar iluminada",
            moon.illuminated_fraction,
            "fraction",
        ),
        ("distance_km", "Distancia lunar", moon.geocentric_distance_km, "km"),
        (
            "angular_diameter_deg",
            "Diámetro angular lunar",
            moon.apparent_angular_diameter_deg,
            "deg",
        ),
        (
            "libration_latitude_deg",
            "Libración lunar latitud",
            moon.libration_latitude_deg,
            "deg",
        ),
        (
            "libration_longitude_deg",
            "Libración lunar longitud",
            moon.libration_longitude_deg,
            "deg",
        ),
    ):
        add(
            f"moon:{suffix}",
            label,
            value,
            unit,
            moon.scientific_status,
            list(moon.source_ids),
        )

    twilight = context.twilight
    for suffix, label, value in (
        ("sunrise", "Próxima salida del Sol", twilight.next_sunrise),
        ("sunset", "Próxima puesta del Sol", twilight.next_sunset),
        ("civil_dusk", "Próximo crepúsculo civil", twilight.next_civil_dusk),
        ("nautical_dusk", "Próximo crepúsculo náutico", twilight.next_nautical_dusk),
        (
            "astronomical_dusk",
            "Próximo crepúsculo astronómico",
            twilight.next_astronomical_dusk,
        ),
    ):
        add(
            f"twilight:{suffix}",
            label,
            _event_value(value),
            None,
            twilight.scientific_status,
            [],
        )

    for index, event in enumerate(context.events, start=1):
        add(
            f"event:{index}:{event.event_type.value}",
            event.label_es,
            {
                "event_type": event.event_type.value,
                "time": event.time.model_dump(mode="json"),
                "body": event.body.value if event.body is not None else None,
                "details": event.details,
            },
            None,
            event.scientific_status,
            list(event.source_ids),
        )

    source_ids = sorted({source_id for fact in facts for source_id in fact.source_ids})
    payload = {
        "facts": [fact.model_dump(mode="json") for fact in facts],
        "source_ids": source_ids,
    }
    return GroundingPacket(
        context_hash=_hash_json(payload),
        facts=facts,
        source_ids=source_ids,
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    match = _JSON_FENCE_RE.search(text)
    if match:
        text = match.group(1).strip()

    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise PlanValidationError("No JSON object found in LLM output")
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise PlanValidationError("Malformed LLM JSON") from exc

    if not isinstance(value, dict):
        raise PlanValidationError("LLM output must be one JSON object")
    return value


def _build_prompt(request, context, grounding) -> str:
    # The JSON schema is supplied separately through Ollama's `format` field.
    # Keeping the natural-language prompt compact reduces KV/context pressure on
    # the RTX 2060 while still exposing every grounded fact to the model.
    facts = [fact.model_dump(mode="json") for fact in grounding.facts]
    return (
        "Eres AstronomyDirector de EL CENTINELA DEL UNIVERSO. "
        "Diseña un vídeo vertical 9:16 cinematográfico, inmersivo, elegante, "
        "contemplativo y científicamente riguroso.\n\n"
        "REGLAS:\n"
        "- No inventes datos astronómicos.\n"
        "- Todo claim HECHO_VERIFICADO debe citar fact_ids existentes.\n"
        "- Si falta información, external_research_required=true y formula "
        "research_questions; no inventes la respuesta.\n"
        "- Orden narrativo obligatorio: introduction, development, climax, "
        "resolution, epilogue; al menos una escena por acto.\n"
        f"- Genera exactamente {request.scene_count} escenas.\n"
        f"- Duración objetivo total: {request.target_duration_seconds} s.\n"
        "- Español de España. Sin clickbait falso.\n"
        "- Evita B-roll irrelevante. El espectador debe sentir que contempla "
        "el fenómeno con el observador.\n"
        "- visual_requirement debe decir qué debe verse de forma concreta.\n"
        "- material_keywords deben servir para buscar el material real.\n"
        "- Prioriza material real; IA visual sólo como último recurso y "
        "RECREACION_VISUAL.\n"
        "- source_priority puede devolverse vacío; la aplicación lo impone.\n\n"
        f"TEMA: {request.subject}\n"
        f"MOMENTO_LOCAL: {context.moment_local.isoformat()}\n"
        "OBSERVADOR: "
        + json.dumps(context.observer.model_dump(mode="json"), ensure_ascii=False)
        + "\nCONTEXT_HASH: "
        + grounding.context_hash
        + "\nGROUNDING_FACTS: "
        + json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
    )


def _repair_prompt(
    invalid_output: str, error: Exception, grounding: GroundingPacket
) -> str:
    # Do not repeat the entire original prompt here: that was the context-heavy
    # path that exposed the empty-content failure with thinking enabled.
    valid_ids = [fact.fact_id for fact in grounding.facts]
    return (
        "Corrige el objeto JSON anterior. Devuelve exclusivamente JSON válido "
        "que respete el schema estructurado impuesto por Ollama. No inventes "
        "fact_ids.\nERROR: "
        + str(error)[:3000]
        + "\nVALID_FACT_IDS: "
        + json.dumps(valid_ids, ensure_ascii=False)
        + "\nINVALID_OUTPUT: "
        + invalid_output[:9000]
    )


def _normalize_durations(scenes: list[ScenePlan], target: int) -> list[ScenePlan]:
    current = sum(scene.duration_seconds for scene in scenes)
    if current <= 0:
        raise PlanValidationError("Invalid total duration")

    values = [
        max(2, min(45, round(scene.duration_seconds * target / current)))
        for scene in scenes
    ]
    delta = target - sum(values)

    for _ in range(10000):
        if delta == 0:
            break
        changed = False
        indices = range(len(values)) if delta > 0 else range(len(values) - 1, -1, -1)
        for index in indices:
            if delta == 0:
                break
            if delta > 0 and values[index] < 45:
                values[index] += 1
                delta -= 1
                changed = True
            elif delta < 0 and values[index] > 2:
                values[index] -= 1
                delta += 1
                changed = True
        if not changed:
            break

    if delta != 0:
        raise PlanValidationError("Could not normalize scene durations")

    return [
        scene.model_copy(update={"duration_seconds": values[index]})
        for index, scene in enumerate(scenes)
    ]


def _validate_draft(draft, request, grounding):
    if len(draft.scenes) != request.scene_count:
        raise PlanValidationError(
            f"Expected {request.scene_count} scenes; received {len(draft.scenes)}"
        )

    numbers = [scene.scene_number for scene in draft.scenes]
    if numbers != list(range(1, len(draft.scenes) + 1)):
        raise PlanValidationError("scene_number must be sequential from 1")

    acts = [scene.act for scene in draft.scenes]
    for required in NarrativeAct:
        if required not in acts:
            raise PlanValidationError(f"Missing narrative act: {required.value}")
    order = [ACT_ORDER[act] for act in acts]
    if order != sorted(order):
        raise PlanValidationError("Narrative acts are out of order")

    valid_fact_ids = {fact.fact_id for fact in grounding.facts}
    normalized = []
    for scene in draft.scenes:
        for claim in scene.claims:
            unknown = set(claim.fact_ids) - valid_fact_ids
            if unknown:
                raise PlanValidationError(
                    f"Unknown grounding fact_ids in scene {scene.scene_number}: "
                    f"{sorted(unknown)}"
                )

        updates = {"source_priority": list(SOURCE_PRIORITY)}
        if scene.scientific_status == ScientificStatus.RECREACION_VISUAL:
            updates["ai_recreation_allowed"] = True
        normalized.append(scene.model_copy(update=updates))

    normalized = _normalize_durations(
        normalized,
        request.target_duration_seconds,
    )
    return draft.model_copy(
        update={
            "subject": request.subject,
            "language": "es-ES",
            "narrative_arc": list(NarrativeAct),
            "scenes": normalized,
        }
    )


def _parse_plan(output, request, grounding):
    payload = _extract_json_object(output)
    try:
        draft = AstronomyVideoPlanDraft.model_validate(payload)
    except ValidationError as exc:
        raise PlanValidationError(str(exc)) from exc
    return _validate_draft(draft, request, grounding)


def _fallback_acts(scene_count: int) -> list[NarrativeAct]:
    # Always includes all five canonical acts, with development/resolution taking
    # the extra scenes. This avoids fragile rounding logic.
    middle = scene_count - 3
    development_count = (middle + 1) // 2
    resolution_count = middle - development_count
    return (
        [NarrativeAct.INTRODUCTION]
        + [NarrativeAct.DEVELOPMENT] * development_count
        + [NarrativeAct.CLIMAX]
        + [NarrativeAct.RESOLUTION] * resolution_count
        + [NarrativeAct.EPILOGUE]
    )


def _fallback_plan(request, grounding):
    available = {fact.fact_id: fact for fact in grounding.facts}
    preferred = [
        "moon:phase_name",
        "body:moon:altitude_apparent_deg",
        "twilight:sunset",
        "twilight:astronomical_dusk",
        "body:jupiter:altitude_apparent_deg",
    ]
    selected = [fact_id for fact_id in preferred if fact_id in available]
    if not selected and grounding.facts:
        selected = [grounding.facts[0].fact_id]

    scenes = []
    for index, act in enumerate(_fallback_acts(request.scene_count), start=1):
        claims = []
        if selected:
            fact_id = selected[(index - 1) % len(selected)]
            fact = available[fact_id]
            claims.append(
                PlanScientificClaim(
                    statement=f"{fact.label_es}: {fact.value}",
                    fact_ids=[fact_id],
                    scientific_status=fact.scientific_status,
                )
            )

        scenes.append(
            ScenePlan(
                scene_number=index,
                act=act,
                duration_seconds=max(
                    2, request.target_duration_seconds // request.scene_count
                ),
                narration=(
                    "Borrador determinista de seguridad; requiere revisión humana."
                ),
                visual_requirement=(
                    "Material astronómico real y directamente relacionado con el tema."
                ),
                astronomy_objects=[],
                shot_type=ShotType.WIDE,
                material_keywords=[request.subject],
                source_priority=list(SOURCE_PRIORITY),
                transition="corte limpio",
                claims=claims,
                ai_recreation_allowed=False,
                scientific_status=ScientificStatus.INFERENCIA,
            )
        )

    draft = AstronomyVideoPlanDraft(
        subject=request.subject,
        language="es-ES",
        audience="divulgación astronómica general",
        hook="Borrador de seguridad tras dos salidas LLM inválidas.",
        scientific_context_summary="Sólo utiliza datos presentes en GroundingPacket.",
        narrative_arc=list(NarrativeAct),
        scenes=scenes,
        epilogue="Cierre contemplativo pendiente de revisión humana.",
        external_research_required=False,
        research_questions=[],
    )
    return _validate_draft(draft, request, grounding)


def _finalize(draft, grounding, model, origin, repair_attempted):
    return AstronomyVideoPlan(
        **draft.model_dump(),
        context_hash=grounding.context_hash,
        generation_origin=origin,
        model_used=model,
        repair_attempted=repair_attempted,
        total_duration_seconds=sum(scene.duration_seconds for scene in draft.scenes),
        requires_human_review=True,
        approved_for_publication=False,
        generated_at_utc=datetime.now(timezone.utc),
    )


def get_director_health(adapter=None):
    adapter = adapter or OllamaLocalAdapter()
    try:
        models = adapter.available_models()
        reachable = True
    except AstronomyDirectorError:
        models = []
        reachable = False

    preferred = None
    if reachable and models:
        try:
            preferred = adapter.resolve_model(None)
        except AstronomyDirectorError:
            preferred = None

    return AstronomyDirectorHealth(
        status="ok" if reachable and models else "degraded",
        backend=DirectorBackend.OLLAMA_LOCAL,
        ollama_reachable=reachable,
        available_models=models,
        preferred_model=preferred,
        network_scope="loopback_only",
        thinking_disabled_for_structured_output=True,
        structured_output_schema_enabled=True,
        paid_api_used=False,
    )


def generate_astronomy_video_plan(
    request: AstronomyDirectorRequest,
    *,
    adapter=None,
) -> AstronomyVideoPlan:
    if request.backend != DirectorBackend.OLLAMA_LOCAL:
        raise AstronomyDirectorError("Only ollama_local is enabled in Phase 3")

    context = build_astronomy_context(request.astronomy)
    grounding = build_grounding_packet(context)
    adapter = adapter or OllamaLocalAdapter()
    model = adapter.resolve_model(request.model)
    schema = AstronomyVideoPlanDraft.model_json_schema()
    prompt = _build_prompt(request, context, grounding)

    first_output = adapter.generate_json(
        model=model,
        prompt=prompt,
        temperature=request.temperature,
        schema=schema,
    )

    try:
        draft = _parse_plan(first_output, request, grounding)
        return _finalize(
            draft,
            grounding,
            model,
            GenerationOrigin.LLM_VALIDATED,
            False,
        )
    except PlanValidationError as first_error:
        second_output = adapter.generate_json(
            model=model,
            prompt=_repair_prompt(first_output, first_error, grounding),
            temperature=0.0,
            schema=schema,
        )
        try:
            draft = _parse_plan(second_output, request, grounding)
            return _finalize(
                draft,
                grounding,
                model,
                GenerationOrigin.LLM_REPAIRED,
                True,
            )
        except PlanValidationError as second_error:
            if not request.allow_fallback:
                raise PlanValidationError(
                    "LLM failed strict validation twice. "
                    f"First={first_error}; Second={second_error}"
                ) from second_error
            draft = _fallback_plan(request, grounding)
            return _finalize(
                draft,
                grounding,
                model,
                GenerationOrigin.DETERMINISTIC_FALLBACK,
                True,
            )
