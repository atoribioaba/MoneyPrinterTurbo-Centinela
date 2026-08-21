# AstroMedia + Provenance V0.1

Fase 4 de **EL CENTINELA DEL UNIVERSO**.

## Flujo

ScenePlan → AstroMedia → metadata/provenance/derechos → búsqueda → Fase 5.

## Biblioteca canónica

`D:\ASTRONOMÍA\Medios` se trata como **sólo lectura**.

El índice se guarda fuera:

- `E:\IA\AstroMedia\catalog.sqlite3`
- `E:\IA\AstroMedia\catalog.json`

AstroMedia no mueve, renombra ni elimina medios fuente.

## Derechos

Estados:

- `CONFIRMED_OWNED`
- `VERIFIED_LICENSE`
- `UNVERIFIED`
- `RESTRICTED`

Un medio local sin metadata empieza como:

`LOCAL_MEDIA + UNVERIFIED + publication_eligible=false`.

La procedencia NASA/ESA/Wikimedia no verifica automáticamente la licencia
de un recurso concreto.

## Sidecar opcional

AstroMedia sólo lee:

- `clip.mp4.astromedia.json`
- `clip.astromedia.json`

`ownership_confirmed=true` convierte el medio en `OWN_MEDIA`,
`CONFIRMED_OWNED` y publicable.

## MaterialInfo

`MaterialInfo` de MPT es un `pydantic.dataclasses.dataclass`.

El bridge usa:

- `provider`
- `url`
- `duration`
- `source_info`

No usa `MaterialInfo.model_fields`.

## Búsqueda V0.1

Scoring determinista por objetos, título, tags, search_term,
descripción, filename, provider y derechos.

No activa SigLIP/LAION.

La selección escena→clip corresponde a Fase 5.
