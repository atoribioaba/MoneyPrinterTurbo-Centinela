# EL CENTINELA DEL UNIVERSO — Video Base V1

## Fase 6

Entrada canónica:

`AstronomyVideoPlan + MaterialSelectionPlan → VideoBasePlanner → VideoBasePlan → FFmpegSceneRenderer → video-base.mp4`

## Autoridad de material

`MaterialSelectionPlan` es la única autoridad de selección. F6 sólo puede resolver metadata mediante `AstroMediaCatalog.get(selected_media_id)`.

F6 no puede:

- buscar AstroMedia;
- rankear candidatos;
- sustituir material;
- invocar proveedores;
- ejecutar SmartFocal;
- ejecutar SemanticMatcher;
- ejecutar WanGP;
- publicar.

## Modos

### REVIEW_PARTIAL

Las escenas sin material válido se convierten en placeholders neutros. El motivo exacto se conserva en el plan y en `render-manifest.json`.

### CLEAN_BASE

Cualquier escena unresolved, ausente, inválida o demasiado corta bloquea el plan antes de FFmpeg.

## Contrato V0.1

- 1080×1920;
- 30 fps;
- H.264;
- yuv420p;
- sin audio;
- hard cuts;
- `source_start_s=0`;
- imágenes con duración exacta;
- vídeos demasiado cortos: `SOURCE_TOO_SHORT`;
- sin loops automáticos;
- sin Ken Burns;
- FIT/COVER;
- focal manual/centro;
- rotación explícita;
- NVENC preferido con prueba real de encode;
- `libx264` fallback;
- segmentos normalizados y concat determinista.

## Evidencia

Cada render genera:

- `video-base.mp4`;
- `render-manifest.json`;
- segmentos por escena si `keep_segments=true`.

El manifest conserva codec solicitado/efectivo, fallback, duración, hashes, selección F5, rights/proveedor, focal, rotación, placeholders y validación técnica final.

## Hardware objetivo

Windows 11 + Ryzen 7 3700X + RTX 2060 6 GB + 16 GB RAM.

F6 no requiere Torch ni descarga modelos. El `ResourceGovernor` deja preparado el contrato para fases posteriores de mayor consumo.
