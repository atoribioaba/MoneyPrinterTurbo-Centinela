# F13 · Smart Ken Burns

Version: `smart-ken-burns-v0.1`

## Responsabilidad

F13 convierte la intención cinematográfica F8 y el encuadre F12 en un plan
determinista de movimiento para **imágenes estáticas**.

F13 no renderiza.

No modifica:

- selección de material;
- Best Moment;
- tracking;
- SmartFocal;
- fit mode;
- identidad del material;
- crop base decidido por F12.

## Mapeo cinematográfico

`MotionIntent` F8:

| MotionIntent | F13 |
| --- | --- |
| `OBSERVE_LOCKED` | `HOLD` |
| `NATURAL_MOTION_ONLY` | `HOLD` |
| `VERY_SLOW_PUSH` | `PUSH_IN` |
| `CONTROLLED_REVEAL` | `CONTROLLED_REVEAL` |
| `GENTLE_PULL_BACK` | `PULL_BACK` |

Una imagen estática con `NATURAL_MOTION_ONLY` se mantiene quieta; F13 no
fabrica movimiento artificial cuando el director pidió movimiento natural.

## FIT

Una imagen F12 `FIT_PASSTHROUGH` produce:

`FIT_STATIC_HOLD`

F13 no cambia `FIT` a `COVER` sólo para crear un Ken Burns.

## COVER

Para una imagen COVER con crop estático F12, F13 usa el focal/crop F12 como
geometría base.

Cada movimiento genera exactamente dos keyframes normalizados:

- `t=0`
- `t=duration_seconds`

La geometría es independiente de resolución. Puede escalarse posteriormente a
1080×1920 o 2160×3840 manteniendo el mismo encuadre.

## Push-in

Empieza en el crop F12 y termina con un crop ligeramente menor alrededor del
mismo focal.

El zoom máximo V0.1 es 9 %.

La magnitud depende de:

- `CinematicPace`
- intensidad F8

Rangos deliberadamente conservadores para evitar un look automático/agresivo.

## Pull-back

Empieza ligeramente cerrado y termina exactamente en el crop F12.

Sirve especialmente para resolución/epílogo y para recuperar contexto.

## Controlled reveal

Empieza ligeramente cerrado y desplazado respecto al focal F12; termina
exactamente en el focal/crop F12.

La dirección inicial se deriva de la posición del focal y de
`CompositionIntent`; no usa aleatoriedad.

## Hold

Para COVER, un hold se representa con dos keyframes idénticos.

## Revisión F12

Si F12 tiene `review_required=true`, F13 no planifica movimiento:

`REFRAMING_REVIEW_REQUIRED`

Esto evita amplificar un encuadre que todavía no ha sido aprobado.

## Vídeo

`VIDEO_NOT_APPLICABLE`

F13 no aplica Ken Burns a vídeo real. El movimiento temporal del vídeo ya
pertenece a la fuente y a F11/F12.

## Recursos

- CPU: LIGHT
- GPU: no
- VRAM: 0
- modelos: ninguno
- downloads: ninguno
- FFmpeg: no ejecutado por F13 planner

## Guardrails

- `uses_llm = false`
- `gpu_required = false`
- `renders_video = false`
- `searches_material = false`
- `changes_material_identity = false`
- `changes_fit_mode = false`
- `best_moment_search_triggered = false`
- `tracking_reexecuted = false`
- `smartfocal_reexecuted = false`
- `reframing_reexecuted = false`
- `auto_publication = false`

## Siguiente fase

F14 podrá trabajar sobre la imagen maestra para `image-to-video` y
microanimación, manteniendo separado el movimiento sintético generativo del
Ken Burns geométrico de F13.
