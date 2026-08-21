# F12 · Smart Reframing 2.0 + SmartFocal

Version: `smart-reframing-v0.1`

## Responsabilidad

F12 transforma la información espacial disponible en un **plan de crop 9:16**.

No renderiza todavía.

Prioridad:

1. trayectoria F11;
2. decisión SmartFocal V0.1;
3. focal estático F6.

## SmartFocal V0.1 existente

F12 no sustituye `app/services/smart_focal.py`.

Reutiliza su contrato real:

- `FocalDecision`
- `focal_decision_from_clip`
- `safe_focal_decision_from_clip`
- `fallback_focal_decision`

La foundation V0.1 existente es CPU/NumPy y per-clip. Su propio código indica
que `confidence` todavía no es un umbral calibrado de producción, por lo que
F12 no inventa ningún threshold.

El contrato seguro real es `fallback_focal_decision()`:
`method = "fallback_center"`, focal `0.5,0.5`, confidence `0.0`.

F12 no descarga Florence-2, CLIP ni otros modelos.
F12 no añade OpenCV.
F12 no ejecuta el analizador SmartFocal durante el planner; recibe su decisión
como hint cuando exista.

## FIT

`VideoFitMode.fit` se conserva.

Resultado:

`FIT_PASSTHROUGH`

No hay crop ni keyframes.

F12 nunca cambia FIT a COVER automáticamente.

## COVER

Para COVER se calcula la ventana fuente que conserva exactamente el aspect
ratio objetivo `1080x1920`.

El focal se limita a los bordes legales para que el crop nunca salga de la
imagen.

## Vídeo con F11

Un track completo produce:

`DYNAMIC_TRACKING`

Los centros F11 se convierten en focales de crop.

Se aplican:

- dead-zone 4 % del tamaño de crop;
- suavizado EMA dependiente del pace cinematográfico F8;
- límite de velocidad 0.18 de la dimensión fuente por segundo;
- clamp de bordes.

La composición F8 define una pequeña posición vertical objetivo del sujeto:

- `LAYERED_WIDE`: 0.38
- `BALANCED_OBSERVATION`: 0.45
- `SUBJECT_DOMINANT`: 0.50
- `GUIDED_FOLLOW`: 0.45
- `INFORMATIONAL_CLEAN`: 0.42

El eje X se mantiene neutral en 0.50.

## Tracking parcial

`DYNAMIC_TRACKING_PARTIAL`

Se conserva la trayectoria conocida, pero:

- `review_required = true`
- `execution_ready = false`

F12 no inventa el movimiento posterior a la pérdida del objeto.

## SmartFocal estático

Si no hay track F11 y existe una decisión SmartFocal:

- `method != "fallback_center"` → `STATIC_SMARTFOCAL`
- `method == "fallback_center"` → `STATIC_SAFE_CENTER`

No se aplica un umbral de `confidence` inventado por F12. La decisión mantiene:

- focal x/y
- confidence
- method

## Fallback F6

Sin F11 y sin SmartFocal:

`STATIC_F6_FOCAL`

Se conservan `focal_x/focal_y` de F6.

## Rotación

F12 V0.1 conserva la información de rotación.

Si `source_rotation_deg != 0`, genera el plan pero marca:

`SOURCE_ROTATION_REQUIRES_RENDERER_REVIEW`

y no declara la escena execution-ready.

No se asume una convención de metadata de rotación que todavía no haya sido
validada E2E.

## Placeholders

`PLACEHOLDER_NOT_APPLICABLE`

Sin crop.
Sin SmartFocal.
Sin tracking.
Sin renderer.

## Guardrails

- `uses_llm = false`
- `gpu_required = false`
- `renders_video = false`
- `searches_material = false`
- `changes_material_identity = false`
- `changes_fit_mode = false`
- `best_moment_search_triggered = false`
- `tracking_reexecuted = false`
- `smartfocal_analyzer_invocations = 0`
- `auto_publication = false`

## Recursos

Planner F12:

- CPU: LIGHT
- GPU: no
- VRAM: 0
- modelos: ninguno
- downloads: ninguno

El análisis SmartFocal V0.1 sigue siendo una capacidad separada ya existente.

## Siguiente fase

F13 Smart Ken Burns podrá consumir los keyframes F12 para movimiento
cinematográfico en imágenes y para integración de movimiento visual sin volver
a decidir qué objeto seguir.
