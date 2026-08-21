# Material Selection V1

Fase 5 de **EL CENTINELA DEL UNIVERSO**.

Flujo:

`ScenePlan → AstroMedia catalog → candidatos → SceneMaterialSelection → MaterialSelectionPlan`.

Política V0.1:

1. override manual;
2. material propio realmente adecuado;
3. material astronómico real adecuado;
4. NASA / ESA / Wikimedia;
5. proveedores genéricos;
6. IA sólo como último recurso.

El proveedor nunca sustituye a la relevancia visual.

La Fase 5 consume directamente los items normalizados de AstroMedia y aplica
su propio scoring determinista.

`RESTRICTED` nunca se selecciona automáticamente.

`UNVERIFIED` puede utilizarse en un borrador, pero fuerza revisión y bloquea
`publication_ready`.

La reutilización aplica una penalización, no una prohibición absoluta.

Si no hay material adecuado devuelve:

- `NO_ADEQUATE_MEDIA`, o
- `AI_RECREATION_REQUIRED` cuando la escena permite recreación IA.

Un item `AI_GENERATED` existente sólo puede seleccionarse si:

- no existe candidato real adecuado;
- `allow_ai_last_resort=true`;
- `scene.ai_recreation_allowed=true`.

Esta fase:

- no descarga proveedores;
- no descarga modelos;
- no activa SigLIP/LAION;
- no invoca WanGP;
- no publica;
- no modifica `D:\ASTRONOMÍA\Medios`.

Siguiente fase:

**FASE 6 — VIDEO BASE V1**.
