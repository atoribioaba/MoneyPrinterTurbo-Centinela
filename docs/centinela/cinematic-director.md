# F7 · Cinematic Director 2.0

## Estado

Versión: `cinematic-director-v0.1`

F7 es una capa de **dirección cinematográfica determinista** situada entre la
planificación narrativa/material ya validada y las fases posteriores de
tracking, reframing, movimiento, color, transiciones, audio y subtítulos.

## Entrada

- `AstronomyVideoPlan` (F3).
- `VideoBasePlan` (F6).

F7 exige alineación exacta de:

- `context_hash`;
- número de escenas;
- `scene_number`;
- duración por escena.

No corrige silenciosamente desalineaciones.

## Salida

`CinematicDirectionPlan` con:

- perfil cinematográfico;
- rol narrativo por escena;
- curva de intensidad;
- pacing;
- mood;
- intención de composición;
- intención semántica de movimiento;
- intención de transición de salida;
- motivación de corte;
- grupo de continuidad;
- safe areas;
- hints explícitos para fases futuras;
- hash determinista del núcleo de dirección.

## Principios de EL CENTINELA DEL UNIVERSO

1. contemplación antes que movimiento gratuito;
2. el clímax debe ser el pico estructural de intensidad;
3. la resolución libera tensión;
4. el epílogo deja respirar;
5. no se sustituye material;
6. los placeholders F6 se preservan;
7. no se inventa contenido astronómico;
8. F7 no publica.

## Límites deliberados

F7 V0.1 **NO**:

- ejecuta FFmpeg;
- renderiza vídeo;
- busca o rankea material;
- descarga material;
- llama a Ollama/LLM;
- usa GPU;
- ejecuta SmartFocal;
- ejecuta SemanticMatcher;
- ejecuta WanGP;
- hace tracking;
- aplica Ken Burns;
- aplica color;
- aplica transiciones reales;
- genera TTS;
- usa Whisper;
- publica.

Los campos `motion_intent`, `transition_out_intent` y `future_phase_hints`
son **metadatos semánticos**, no ejecución.

## Curva narrativa

Base orientativa:

- introduction ≈ 0.28
- development ≈ 0.50–0.60
- climax ≈ 0.93+
- resolution ≈ 0.52
- epilogue ≈ 0.24

El clímax se fuerza a ser el máximo incluso al aplicar perfil y
`intensity_bias`.

## Perfiles

- `AUTO`
- `CENTINELA_CINEMATIC`
- `EVENT_EPIC`
- `CELESTIAL_LANDSCAPE`
- `DEEP_SPACE_IMMERSIVE`
- `SCIENTIFIC_EXPLAINER`

`AUTO` usa clasificación determinista por términos del tema, requisitos
visuales, objetos y keywords. No usa IA.

## Compatibilidad hardware

Clase de recurso: `LIGHT`.

- CPU: sí.
- RAM: baja.
- VRAM: 0 requerida.
- Ollama: no.
- WanGP: no.
- FFmpeg/NVENC: no durante F7.

## Consumidores futuros

- F8 Visual Story Graph.
- F11 Astronomical Object Tracker.
- F12 Smart Reframing 2.0.
- F13 Smart Ken Burns.
- F21 Transition Director.

Los hints no disparan ninguna de esas fases.
