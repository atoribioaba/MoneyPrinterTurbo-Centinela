# Centinela Product UX — 10/10 acceptance contract

## Goal

The Product UI must make scientific truth, uncertainty, missing evidence and human gates easier to understand than the legacy technical surfaces. Visual polish cannot hide state.

## Information architecture

Final RC should expose one coherent path:
`Inicio → Crear → Cielo → Proyecto → Revisión → Publicación`.

Avoid parallel user-facing authorities for the same decision. Legacy WebUI may remain as an engineering/fallback surface but must not contradict Product UI state.

## Cielo / Observation Intelligence

Never show an opaque single quality score alone. Show:
- observing grade;
- completeness percentage;
- target altitude / airmass;
- darkness state;
- Moon interference;
- cloud cover;
- seeing when truly sourced;
- transparency when truly sourced;
- wind/dew risk;
- sky quality evidence;
- source/provider and timestamp;
- missing or stale inputs.

Forecast, measured and inferred values must be visibly distinguishable.

## Equipment / framing

Show:
- telescope/lens/binocular/camera profile;
- aperture/focal/effective focal/f-ratio;
- sensor dimensions and pixel pitch when known;
- horizontal × vertical FOV;
- image scale;
- target-fit preview;
- warnings for unknown equipment values;
- sampling guidance labelled approximate.

Do not recommend buying equipment merely because a calculated score is lower.

## Solar safety

Solar safety blocks override convenience/creative actions.
- unsafe optical states must be visually blocking, not warning-only;
- no generative model or user preset can override the safety gate silently;
- software must not auto-authorize filter removal during totality;
- authoritative sources should be reachable from the safety explanation.

## Scientific status

Every publication-critical claim/visual must retain one of:
`HECHO_VERIFICADO / APROXIMACION_DIVULGATIVA / HIPOTESIS / RECREACION_VISUAL / INFERENCIA / NO_VERIFICADO`.

Generated visual assets cannot be visually presented as observational evidence.

## Human review / publication

`APPROVED != AUTHORIZED_TO_PUBLISH` must be understandable in normal language.

Publication requires an explicit action after Review. `AUTO_PUBLICATION=FALSE` is invariant.

## Accessibility

Required final-RC checks:
- keyboard-operable primary workflow;
- visible focus;
- labelled form controls;
- meaningful status text independent of color;
- contrast review;
- mobile touch targets;
- reduced-motion behavior for nonessential animation;
- no information conveyed only by hover;
- responsive 360–430 px mobile widths;
- no horizontal overflow on primary workflow.

## Error UX

Errors must expose stage and next safe action, not raw stack traces alone.

Preferred structure:
`ERROR DETECTADO / ETAPA / CAUSA MÁS PROBABLE / EVIDENCIA / SOLUCIÓN / VERIFICACIÓN`.

Fail-closed scientific/media/publication errors should explain why stopping is safer than substituting irrelevant content.

## 10/10 acceptance

UX reaches 10 only after:
- final integrated RC, not historical UI branch;
- mobile human review;
- desktop human review;
- accessibility pass;
- stale/missing-data cases tested;
- unsafe solar state tested;
- inadequate-media state tested;
- Review rejection and changes-requested state tested;
- publication remains impossible without explicit human action;
- no duplicate/conflicting authority across surfaces.
