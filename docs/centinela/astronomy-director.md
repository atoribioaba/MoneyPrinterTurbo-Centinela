# EL CENTINELA DEL UNIVERSO — Astronomy Director + ScenePlan V0.1

## Fase 3

Flujo canónico:

    AstronomyContext
        ↓
    GroundingPacket / fact_id
        ↓
    AstronomyDirector
        ↓
    Ollama local
        ↓
    structured output JSON schema
        ↓
    validación Pydantic
        ↓
    reparación única si procede
        ↓
    AstronomyVideoPlan / ScenePlan

## Ollama y Qwen

El Director usa únicamente `http://127.0.0.1:11434`.

Para modelos Qwen 3.x se desactiva explícitamente el razonamiento durante la
salida estructurada (`think=false`). Esto evita consumir el presupuesto de
tokens en `message.thinking` cuando lo que el pipeline necesita es el JSON
final en `message.content`.

El campo `format` recibe el JSON Schema real generado por Pydantic, en lugar de
usar únicamente `format="json"`.

No se usan APIs de pago ni se descargan modelos automáticamente.

## Grounding científico

Cada dato verificable se expone con `fact_id`. Un claim `HECHO_VERIFICADO`
queda invalidado si referencia un ID inexistente.

Si el vídeo necesita información no incluida en AstronomyContext, el plan debe
marcar `external_research_required=true` y formular `research_questions`.

## Narrativa

Orden obligatorio:

1. introduction
2. development
3. climax
4. resolution
5. epilogue

## Prioridad visual

1. OWN_MEDIA
2. ASTRONOMY_SPECIFIC_FREE
3. NASA
4. ESA
5. WIKIMEDIA
6. PEXELS
7. PIXABAY
8. COVERR
9. AI_GENERATED_LAST_RESORT

## Seguridad editorial

Todo plan sale con:

    requires_human_review = true
    approved_for_publication = false

La Fase 3 no publica contenido.

## WebUI

Página multipágina independiente:

    webui/pages/03_Astronomy_Director.py

No modifica el gran `webui/Main.py`.

## Siguiente fase

FASE 4 — AstroMedia + provenance.
