from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime, timezone
from typing import Any, Callable

from app.models.astronomy import ScientificStatus

from .fact_guard import (
    validate_final_candidate_quantities,
    validate_quantitative_claims,
)
from .models import (
    CritiqueBundle,
    DraftPacket,
    FactLock,
    FinalScript,
    FinalScriptCandidate,
    ScriptClaim,
    WRITER_ROOM_LOGICAL_STAGES,
    WRITER_ROOM_VERSION,
    WriterRoomReport,
    WriterRoomRequest,
)
from .runtime import WriterRoomOllamaRuntime


class WriterRoomError(RuntimeError):
    pass


_BODY_ALIASES = {
    "sun": ("sol", "sun"),
    "moon": ("luna", "moon"),
    "mercury": ("mercurio", "mercury"),
    "venus": ("venus",),
    "mars": ("marte", "mars"),
    "jupiter": ("jupiter", "júpiter"),
    "saturn": ("saturno", "saturn"),
    "uranus": ("urano", "uranus"),
    "neptune": ("neptuno", "neptune"),
    "pluto": ("pluton", "plutón", "pluto"),
}


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(
        ch for ch in normalized if not unicodedata.combining(ch)
    ).casefold()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _hash_json(value: Any) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest().upper()


def _selected_facts(fact_lock: FactLock) -> list[dict[str, Any]]:
    folded_subject = _fold(fact_lock.subject)
    body_keys = {
        body
        for body, aliases in _BODY_ALIASES.items()
        if any(_fold(alias) in folded_subject for alias in aliases)
    }

    selected = []
    for fact in fact_lock.facts:
        fact_id = fact.fact_id
        keep = (
            fact_id.startswith("context:")
            or fact_id.startswith("observer:")
            or fact_id.startswith("twilight:")
            or fact_id.startswith("event:")
            or any(
                fact_id.startswith(f"body:{body}:")
                for body in body_keys
            )
            or (
                "moon" in body_keys
                and fact_id.startswith("moon:")
            )
        )
        if keep:
            selected.append(fact)

    if not selected:
        selected = list(fact_lock.facts[:28])

    if len(selected) < 12:
        existing = {fact.fact_id for fact in selected}
        for fact in fact_lock.facts:
            if fact.fact_id in existing:
                continue
            selected.append(fact)
            existing.add(fact.fact_id)
            if len(selected) >= 12:
                break

    return [
        fact.model_dump(mode="json")
        for fact in selected[:40]
    ]


def _validate_claims(
    claims: list[ScriptClaim],
    fact_lock: FactLock,
) -> None:
    by_id = {
        fact.fact_id: fact
        for fact in fact_lock.facts
    }
    for index, claim in enumerate(claims):
        unknown = [
            fact_id
            for fact_id in claim.fact_ids
            if fact_id not in by_id
        ]
        if unknown:
            raise WriterRoomError(
                f"claim {index} references unknown fact_ids: {unknown}"
            )
        if claim.scientific_status == ScientificStatus.HECHO_VERIFICADO:
            invalid = [
                fact_id
                for fact_id in claim.fact_ids
                if by_id[fact_id].scientific_status
                != ScientificStatus.HECHO_VERIFICADO
            ]
            if invalid:
                raise WriterRoomError(
                    "HECHO_VERIFICADO claim references facts that are "
                    f"not HECHO_VERIFICADO: {invalid}"
                )
    validate_quantitative_claims(claims, fact_lock)


def _facts_prompt(fact_lock: FactLock) -> str:
    return _canonical_json(_selected_facts(fact_lock))


def _draft_prompt(
    request: WriterRoomRequest,
    fact_lock: FactLock,
) -> str:
    return f"""
Eres la sala de guion de EL CENTINELA DEL UNIVERSO.

OBJETIVO:
Crear un primer borrador cinematográfico y científicamente controlado para
un vídeo vertical social. El espectador debe sentir que contempla el fenómeno
con el observador, no una concatenación automática de clips.

TEMA: {request.subject}
IDIOMA: {request.language}
AUDIENCIA: {request.audience}
DURACION_OBJETIVO_SEGUNDOS: {request.target_duration_seconds}
MODO_FACT_LOCK: {fact_lock.research_mode}

FACT LOCK:
{_facts_prompt(fact_lock)}

REGLAS NO NEGOCIABLES:
- No inventes datos astronómicos.
- Toda afirmación científica incluida en claims debe citar fact_ids existentes.
- HECHO_VERIFICADO sólo puede derivar de hechos HECHO_VERIFICADO.
- No uses conocimiento externo del modelo para añadir cifras, fechas,
  distancias, posiciones, descubrimientos o efemérides.
- Si una idea no está soportada por Fact Lock, omítela.
- Sin clickbait falso.
- Evita introducciones genéricas del tipo "desde tiempos inmemoriales".
- El arco debe ser exactamente:
  introduction -> development -> climax -> resolution -> epilogue.
- Diseña tres hooks y elige uno.
- El borrador debe ser narrable en español de España.
- visual_beats debe describir imágenes concretas relacionadas con el texto.
- Todo dato factual narrado debe estar representado también en claims.

Devuelve exclusivamente el objeto JSON del schema.
""".strip()


def _critique_prompt(
    request: WriterRoomRequest,
    fact_lock: FactLock,
    draft: DraftPacket,
) -> str:
    return f"""
Actúas como cuatro críticos simultáneos de EL CENTINELA DEL UNIVERSO:
Science Critic, Retention Critic, Visual Critic y Adversarial Reader.

TEMA: {request.subject}
DURACION_OBJETIVO_SEGUNDOS: {request.target_duration_seconds}

FACT LOCK:
{_facts_prompt(fact_lock)}

DRAFT:
{_canonical_json(draft.model_dump(mode="json"))}

EVALUA:
1. SCIENCE: claims sin soporte, exageraciones o saltos de inferencia.
2. RETENTION: hook, densidad, repeticiones, ritmo, payoff y clímax.
3. VISUAL: frases difíciles de representar con material pertinente; rechaza
   B-roll irrelevante y señala cuándo una recreación debería etiquetarse.
4. ADVERSARIAL: busca ambigüedad, clickbait, falsa certeza y lenguaje
   intercambiable con una cuenta genérica de IA.

No reescribas todavía el guion. Devuelve issues concretos, fixes accionables
y cuatro scores de 0 a 10. Devuelve exclusivamente JSON del schema.
""".strip()


def _final_prompt(
    request: WriterRoomRequest,
    fact_lock: FactLock,
    draft: DraftPacket,
    critique: CritiqueBundle,
) -> str:
    return f"""
Eres el editor final de EL CENTINELA DEL UNIVERSO.

Reescribe y pule el guion aplicando TODAS las críticas pertinentes. Esta pasada
realiza REWRITE, FINAL POLISH, SOCIAL COMPRESSION y mapa de pronunciación.

TEMA: {request.subject}
IDIOMA: {request.language}
AUDIENCIA: {request.audience}
DURACION_OBJETIVO_SEGUNDOS: {request.target_duration_seconds}

FACT LOCK:
{_facts_prompt(fact_lock)}

DRAFT:
{_canonical_json(draft.model_dump(mode="json"))}

CRITIQUE:
{_canonical_json(critique.model_dump(mode="json"))}

REGLAS FINALES:
- No inventes datos.
- Cada claim debe citar fact_ids existentes.
- Todo dato factual presente en narración debe figurar también en claims.
- HECHO_VERIFICADO sólo si los fact_ids citados son HECHO_VERIFICADO.
- Cinco segmentos exactos y en este orden:
  introduction, development, climax, resolution, epilogue.
- El hook debe entrar directamente en materia.
- Narrativa cinematográfica, inmersiva, elegante y científicamente rigurosa.
- No B-roll irrelevante.
- No marques nada como aprobado para publicación.
- pronunciation_map sólo para términos cuya lectura TTS pueda ser ambigua.
- social_30s y social_15s son compresiones del mismo contenido factual,
  no versiones con datos nuevos.

Devuelve exclusivamente JSON del schema.
""".strip()


class WriterRoom:
    version = WRITER_ROOM_VERSION

    def __init__(
        self,
        runtime: WriterRoomOllamaRuntime | None = None,
    ) -> None:
        self.runtime = runtime or WriterRoomOllamaRuntime()

    def generate(
        self,
        request: WriterRoomRequest,
        fact_lock: FactLock,
        *,
        report_progress: Callable[[int, str], Any] | None = None,
        check_cancelled: Callable[[], None] | None = None,
    ) -> tuple[FinalScript, WriterRoomReport]:
        if request.subject.strip().casefold() != fact_lock.subject.strip().casefold():
            raise WriterRoomError(
                "WriterRoomRequest subject does not match FactLock subject"
            )

        progress = report_progress or (lambda value, message: None)
        cancelled = check_cancelled or (lambda: None)

        cancelled()
        model = self.runtime.resolve_model(request.model)
        progress(18, "SCRIPT: tesis, arquitectura, hooks y draft")

        generated_draft = self.runtime.generate(
            DraftPacket,
            model=model,
            prompt=_draft_prompt(request, fact_lock),
            temperature=request.temperature,
        )
        draft = generated_draft.value
        assert isinstance(draft, DraftPacket)
        _validate_claims(draft.claims, fact_lock)

        cancelled()
        progress(34, "SCRIPT: críticas científica, retención, visual y adversarial")
        generated_critique = self.runtime.generate(
            CritiqueBundle,
            model=model,
            prompt=_critique_prompt(request, fact_lock, draft),
            temperature=0.1,
        )
        critique = generated_critique.value
        assert isinstance(critique, CritiqueBundle)

        cancelled()
        progress(50, "SCRIPT: reescritura, pulido y compresión social")
        generated_final = self.runtime.generate(
            FinalScriptCandidate,
            model=model,
            prompt=_final_prompt(
                request,
                fact_lock,
                draft,
                critique,
            ),
            temperature=0.15,
        )
        candidate = generated_final.value
        assert isinstance(candidate, FinalScriptCandidate)
        _validate_claims(candidate.claims, fact_lock)
        validate_final_candidate_quantities(candidate, fact_lock)

        llm_request_count = (
            generated_draft.request_count
            + generated_critique.request_count
            + generated_final.request_count
        )
        candidate_payload = candidate.model_dump(mode="json")
        content_hash = _hash_json(candidate_payload)

        final_script = FinalScript(
            **candidate_payload,
            subject=request.subject,
            language=request.language,
            audience=request.audience,
            target_duration_seconds=request.target_duration_seconds,
            creative_thesis=draft.creative_thesis,
            fact_lock_hash=fact_lock.context_hash,
            model_used=model,
            logical_stages=list(WRITER_ROOM_LOGICAL_STAGES),
            inference_passes=3,
            llm_request_count=llm_request_count,
            source_ids=list(fact_lock.source_ids),
            scientifically_grounded=True,
            requires_human_review=True,
            approved_for_publication=False,
            primary_source_verification_required_for_publication=(
                fact_lock.primary_source_verification_required_for_publication
            ),
            generated_at_utc=datetime.now(timezone.utc),
            content_hash=content_hash,
        )

        report = WriterRoomReport(
            subject=request.subject,
            model_used=model,
            draft=draft,
            critique=critique,
            final_script_hash=content_hash,
            logical_stages=list(WRITER_ROOM_LOGICAL_STAGES),
            inference_passes=3,
            llm_request_count=llm_request_count,
            generated_at_utc=datetime.now(timezone.utc),
        )
        progress(58, "SCRIPT: FinalScript validado")
        return final_script, report
