# F10 · Best Moment Detector

Version: `best-moment-v0.1`

## Responsabilidad

F10 selecciona una **ventana temporal** dentro del mismo vídeo ya seleccionado
por F5/F6.

No cambia el `media_id`.
No busca otro material.
No hace tracking.
No reencuadra.
No renderiza.
No publica.

## Entradas

- `VideoBasePlan` F6
- `VisualStoryGraph` F8
- `ShotQualityPlan` F9

F10 valida hashes, versiones, escena, placeholder, `media_id` y `source_path`.

## Candidatos

Para cada vídeo:

1. `max_start = source_duration - requested_duration`.
2. Se generan hasta 9 inicios equiespaciados por defecto.
3. Cada ventana se evalúa por un frame en el centro temporal.
4. Se cubren explícitamente el inicio `0` y el último inicio válido.

Si el vídeo sólo cabe una vez, existe un único candidato.

## Scoring TEMPORAL_TECHNICAL_V01

Dentro de cada vídeo:

- 65 % nitidez relativa mediante `lavfi.blur`;
- 35 % rango tonal `YMAX - YMIN`.

El cielo oscuro no se penaliza por `YAVG` bajo.

Este score es una heurística técnica temporal. No es un juicio artístico ni
científico.

## Desempate

Si dos candidatos obtienen el mismo score, gana el inicio más temprano.

Esto hace el resultado determinista.

## Placeholders e imágenes

- placeholder → `PLACEHOLDER_NOT_APPLICABLE`
- imagen → `STATIC_IMAGE`

Ninguno ejecuta FFmpeg.

## Fallos

Si un vídeo no puede analizarse:

`ANALYSIS_FAILED`

F10 no inventa una ventana.

## Recursos

Cada vídeo usa hasta 9 decodificaciones puntuales de un frame.

- CPU: sí
- GPU: no requerida
- VRAM: 0
- NVENC: no
- OpenCV: no
- Torch: no
- Ollama: no

Clase práctica: LIGHT/MEDIUM según cantidad de vídeo.

## Guardrails

- `uses_llm = false`
- `gpu_required = false`
- `renders_video = false`
- `searches_material = false`
- `changes_material_identity = false`
- `tracking_triggered = false`
- `smartfocal_triggered = false`
- `auto_publication = false`

## Fases posteriores

F11 podrá hacer seguimiento del objeto astronómico dentro de la ventana
elegida por F10.

F12 podrá reencuadrar esa misma ventana con Smart Reframing/SmartFocal.
