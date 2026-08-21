# F11 · Astronomical Object Tracker

Version: `astronomical-object-tracker-v0.1`

## Responsabilidad

F11 sigue espacialmente **un único objeto explícitamente sembrado** dentro de
la ventana temporal ya elegida por F10.

No busca otro material.
No vuelve a buscar Best Moment.
No decide el encuadre final.
No ejecuta SmartFocal.
No renderiza.
No publica.

## Entradas

- F6 `VideoBasePlan`
- F8 `VisualStoryGraph`
- F9 `ShotQualityPlan`
- F10 `BestMomentPlan`
- cero o una `TrackingSeed` por escena

F11 valida identidad de material, `source_path`, hashes, versiones y orden de
escenas antes de trackear.

## Semilla explícita

F11 V0.1 no infiere automáticamente "Luna", "Sol", "Júpiter", etc. desde
texto libre.

La semilla contiene:

- `scene_number`
- `subject_label`
- bounding box normalizada `x/y/width/height`
- origen `MANUAL` o `EXTERNAL_GROUNDING`

Esto mantiene separado el tracking del grounding/detección semántica.

## Backend OpenCV CSRT

Existe un backend `opencv_csrt` cargado de forma lazy.

F11 **no añade OpenCV a pyproject.toml ni descarga paquetes**.

Si el entorno actual dispone de una build compatible con CSRT, puede usarse.
Si no existe, una escena con seed retorna:

`BACKEND_UNAVAILABLE`

sin romper el pipeline ni alterar dependencias.

## Tracking

El tracker:

1. usa exactamente la ventana `selected_start_s → selected_end_s` de F10;
2. inicializa con la bbox normalizada;
3. actualiza el tracker sobre los frames;
4. registra puntos a `2 Hz` por defecto;
5. guarda bounding boxes y centros normalizados.

Si el track se pierde después de obtener puntos:

`TRACKED_PARTIAL`

No se inventa una trayectoria.

## Placeholders

`PLACEHOLDER_NOT_APPLICABLE`

No backend.
No OpenCV.
No GPU.

## Imágenes

`STATIC_IMAGE_NOT_APPLICABLE`

F11 es tracking temporal; una imagen estática no se trackea.

## Vídeo sin seed

`SEED_REQUIRED`

No se infiere el objeto.

## Recursos

F11 real sobre vídeo es CPU y puede ser MEDIUM.

- GPU requerida: no
- VRAM requerida: 0
- LLM: no
- FFmpeg: no necesario para el tracker
- OpenCV CSRT: opcional/lazy
- SmartFocal: no

OpenCV documenta la familia `Tracker` como seguimiento de un objeto a partir de
una bounding box inicial; CSRT pertenece al módulo de tracking/contrib.

## Guardrails

- `uses_llm = false`
- `gpu_required = false`
- `renders_video = false`
- `searches_material = false`
- `changes_material_identity = false`
- `best_moment_search_triggered = false`
- `smartfocal_triggered = false`
- `reframing_triggered = false`
- `auto_publication = false`

## F12

F12 podrá consumir la trayectoria normalizada y decidir un reencuadre
cinematográfico. F11 no mueve la cámara ni recorta el vídeo.
