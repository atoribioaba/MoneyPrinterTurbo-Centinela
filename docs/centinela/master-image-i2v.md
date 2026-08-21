# F14 · Master Image → I2V

Version: `master-image-i2v-v0.1`

## Responsabilidad

F14 prepara un contrato auditable para transformar una **imagen maestra
seleccionada** en un futuro job image-to-video.

F14 **no ejecuta ningún modelo generativo**.

La ejecución local real pertenece a F15.

## Arquitectura

`F6 selected image + F8 intent + F13 motion fallback → F14 I2V Job → F15`

F14 usa:

- identidad y derechos del material F6;
- visual requirement, objetos astronómicos y motion intent F8;
- estado F13 como fallback geométrico.

## Imagen maestra

F14 sólo usa como master una imagen que ya haya sido seleccionada por el
pipeline.

No crea imágenes maestras.

Por tanto, una escena placeholder sin imagen seleccionada produce:

`MASTER_IMAGE_REQUIRED`

Esto preserva el flujo canónico:

`imagen maestra → image-to-video → microanimación`

sin saltarse AstroMedia/F5/F6.

## Aprobación explícita

Un master válido y con derechos verificados produce inicialmente:

`AWAITING_AI_APPROVAL`

El job y sus prompts pueden revisarse, pero:

`execution_authorized = false`

Sólo una escena incluida explícitamente en `approved_scene_numbers` produce:

`I2V_JOB_READY`

Esta aprobación no ejecuta WanGP. Autoriza únicamente el handoff a F15.

## Derechos

La imagen maestra requiere:

- `CONFIRMED_OWNED`, o
- `VERIFIED_LICENSE`

y además:

`publication_eligible = true`

En caso contrario:

`SOURCE_RIGHTS_BLOCKED`

## Rigor científico

Cualquier vídeo generado mediante I2V se declara desde F14:

- `visual_origin = AI_GENERATED`
- `scientific_status = RECREACION_VISUAL`
- `disclosure_required = true`

Aunque la imagen maestra sea una fotografía real.

F14 no permite que un I2V sea presentado como observación real.

## Preservación astronómica

El prompt exige conservar:

- identidad de los objetos;
- fase lunar;
- forma planetaria;
- anillos;
- posiciones relativas;
- horizonte;
- composición principal.

Y prohíbe explícitamente inventar:

- lunas;
- soles;
- planetas;
- eclipses;
- estrellas;
- constelaciones;
- galaxias.

El objetivo es microanimación, no reinterpretación generativa libre.

## F13 e I2V

F13 Smart Ken Burns permanece como **fallback**.

No se permite:

`Ken Burns + movimiento I2V apilados`

sobre el mismo clip.

Una escena usa una de las rutas:

1. I2V generado por F15, o
2. movimiento geométrico F13.

## WanGP

F14 sólo declara:

`WANGP_API_OR_HEADLESS_RESOLVED_IN_F15`

No fija:

- modelo;
- cuantización;
- resolución nativa;
- steps;
- guidance;
- seed;
- offload;
- VRAM profile;
- CLI/API concreta.

Esos parámetros dependen de la versión WanGP y del modelo finalmente validado.

## Recursos F14

- resource class: LIGHT
- GPU: no
- VRAM: 0
- downloads: 0
- WanGP calls: 0
- render: no

## Guardrails

- `uses_llm = false`
- `gpu_required = false`
- `renders_video = false`
- `downloads_models = false`
- `wangp_invocations = 0`
- `searches_material = false`
- `changes_material_identity = false`
- `best_moment_search_triggered = false`
- `tracking_reexecuted = false`
- `smartfocal_reexecuted = false`
- `reframing_reexecuted = false`
- `ken_burns_rendered = false`
- `auto_publication = false`

## Siguiente fase

F15 validará la instalación local WanGP y resolverá el adapter real
API/headless/modelo/perfil de memoria antes de autorizar cualquier descarga
grande o generación EXCLUSIVE.
