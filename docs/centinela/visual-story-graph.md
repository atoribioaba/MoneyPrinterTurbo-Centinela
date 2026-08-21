# F8 · Visual Story Graph

Version: `visual-story-graph-v0.1`

## Objetivo

F8 convierte la planificación ya validada en F3/F6/F7 en un grafo explícito
de continuidad narrativa y visual.

No decide si un plano es "bueno" o "malo". Eso pertenece a F9.
No detecta el mejor instante de un clip. Eso pertenece a F10.
No hace tracking. Eso pertenece a F11.
No reencuadra. Eso pertenece a F12.
No ejecuta transiciones. Eso pertenece a F21.

## Entradas

- `AstronomyVideoPlan` (F3)
- `VideoBasePlan` (F6)
- `CinematicDirectionPlan` (F7)

F8 exige alineación exacta de:

- `context_hash`;
- versión de Video Base;
- versión del selector;
- `scene_number`;
- orden de escenas;
- duración;
- acto narrativo;
- estado placeholder F6/F7.

No corrige desalineaciones silenciosamente.

## Nodos

Cada escena se convierte en un `VisualStoryNode` con:

- acto;
- rol F7;
- pacing;
- intensidad;
- mood;
- composición;
- motion intent;
- transition intent;
- requisito visual;
- objetos astronómicos;
- claves normalizadas de sujeto;
- continuidad;
- placeholders;
- hints para fases posteriores.

## Aristas

F8 V0.1 crea exactamente una arista dirigida entre cada par de escenas
adyacentes.

Una arista describe:

- relación narrativa;
- continuidad de sujeto;
- relación de composición;
- delta de intensidad;
- transición F7 de salida;
- motivación de corte;
- flags de continuidad;
- consumidores futuros.

No contiene un quality score.

## Threads astronómicos

Los `StorySubjectThread` agrupan apariciones explícitas del mismo objeto
astronómico a lo largo del vídeo.

F8 no infiere objetos desde texto libre: sólo utiliza
`AstronomyVideoPlan.astronomy_objects`.

## Spans narrativos

`StoryActSpan` representa cada tramo contiguo de:

`introduction → development → climax → resolution → epilogue`.

## Guardrails

F8:

- `uses_llm = false`
- `gpu_required = false`
- `renders_video = false`
- `searches_material = false`
- `auto_publication = false`

Clase de recurso: `LIGHT`.

## Consumidores futuros

- F9 Shot Quality Scorer
- F10 Best Moment Detector
- F11 Astronomical Object Tracker
- F12 Smart Reframing 2.0
- F20 Shot Matching
- F21 Transition Director

F8 sólo emite estructura y metadatos para esos consumidores.
