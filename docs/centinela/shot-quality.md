# F9 · Shot Quality Scorer

Version: `shot-quality-v0.1`

## Objetivo

F9 mide **calidad técnica de la toma ya seleccionada**.

No vuelve a seleccionar material.
No decide el mejor instante de un vídeo.
No hace tracking.
No reencuadra.
No renderiza.

La autoridad de material sigue siendo F5/F6.
La búsqueda temporal del mejor momento pertenece a F10.

## Entradas

- `VideoBasePlan` (F6)
- `VisualStoryGraph` (F8)

Se exige alineación exacta de:

- `context_hash`;
- versión de Video Base;
- versión del selector;
- número y orden de escenas;
- duración;
- estado placeholder.

## Política temporal

Para vídeo se analiza exactamente **un frame** en:

`VideoBaseScenePlan.source_start_s`

En F6 V0.1 ese valor es determinista y actualmente parte de 0 s.

F9 no busca otros timestamps.

## Diagnóstico FFmpeg

Un frame se decodifica por CPU con:

- `blurdetect`
- `signalstats`
- `metadata=mode=print`

Se guardan:

- `lavfi.blur`
- `YMIN`
- `YMAX`
- `YAVG`
- `SATAVG`
- rango de luminancia

No se reencoda vídeo.

## Heurística TECHNICAL_V01

El score final es una heurística técnica versionada:

- 40 % adecuación de resolución;
- 25 % eficiencia de encuadre para FIT/COVER;
- 20 % nitidez relativa entre tomas evaluables;
- 15 % rango de luminancia.

No es una métrica científica ni un juicio artístico.

### Nitidez relativa

`blurdetect` produce una métrica de blur por frame.

F9 V0.1 la usa **relativamente dentro del mismo plan**:

- menor blur relativo → mayor componente de nitidez;
- si todas las tomas tienen el mismo valor o sólo hay una, el componente es
  neutral `0.5`.

Esto evita fijar un umbral absoluto no calibrado para todo tipo de
astrofotografía.

### Exposición astronómica

F9 no penaliza automáticamente un `YAVG` bajo: un cielo nocturno oscuro es
esperable.

El componente de luminancia valora el rango tonal y genera flags
conservadores para:

- `LOW_LUMA_RANGE`
- `NEAR_BLACK_FRAME`
- `NEAR_WHITE_FRAME`

## FIT / COVER

Se calcula:

- upsampling requerido;
- ocupación de frame en FIT;
- fracción retenida tras crop en COVER.

Flags posibles:

- `UPSCALE_REQUIRED`
- `LOW_RESOLUTION_FOR_OUTPUT`
- `LOW_FRAME_OCCUPANCY`
- `HEAVY_CROP`

## Placeholders

Una escena F6 placeholder:

- `status = NOT_SCORABLE`
- no obtiene score;
- no ejecuta FFmpeg;
- conserva su razón F6.

Esto permite trabajar con planes incompletos sin inventar calidad.

## Fallos de análisis

Si la escena tiene material pero FFmpeg no puede obtener el frame o sus
metadatos:

- `status = ANALYSIS_FAILED`
- no se inventa score;
- el error queda registrado.

## Bands

- `EXCELLENT >= 0.85`
- `GOOD >= 0.70`
- `USABLE >= 0.50`
- `WEAK < 0.50`

Las bands pertenecen a `TECHNICAL_V01`, no a una verdad estética universal.

## Recursos

F9 analiza un frame por toma:

- CPU: sí;
- GPU: no requerida;
- VRAM: 0;
- OpenCV: no;
- Torch: no;
- Ollama: no;
- NVENC: no.

## Guardrails

- `uses_llm = false`
- `gpu_required = false`
- `renders_video = false`
- `searches_material = false`
- `best_moment_search_triggered = false`
- `tracking_triggered = false`
- `smartfocal_triggered = false`
- `auto_publication = false`

## Relación con fases posteriores

F10 podrá usar F9 como baseline técnico antes de buscar el mejor momento
temporal de un vídeo.

F11/F12 podrán consumir flags de resolución/encuadre, pero F9 no ejecuta
tracking ni reframing.
