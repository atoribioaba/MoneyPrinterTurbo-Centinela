# C3 — FactLock adversarial certification

Fecha de consolidación: 2026-08-31  
Ámbito: cloud/static mechanism audit  
Rama: `centinela-cert/c3-f58-readiness-v0.1`

## Estado

```text
FACTLOCK_ADVERSARIAL_MECHANISM=PASS_STATIC
FACTLOCK_ADVERSARIAL_EXECUTION=PENDING_STEP_EXECUTION
CI_PRE_STEP_EXECUTION_BLOCKER=CONTROL_PLANE
AUTO_PUBLICATION=FALSE
NETWORK_ADDED_BY_FACT_GUARD=FALSE
LLM_ADDED_BY_FACT_GUARD=FALSE
LOCAL_FINAL_CERTIFICATION_REQUIRED=TRUE
```

`PASS_STATIC` significa que el bypass reproducible se ha cerrado en la ruta productiva por inspección de código y regresiones añadidas. No significa que pytest haya sido ejecutado por GitHub Actions: el control plane de Actions continúa bloqueando la ejecución antes del primer step.

## Bypass demostrado

La validación anterior de Writer Room comprobaba:

1. que cada `fact_id` citado existiese en FactLock;
2. que un claim `HECHO_VERIFICADO` sólo citase hechos `HECHO_VERIFICADO`.

No comprobaba que una cantidad escrita en el texto mantuviese el orden de magnitud y la unidad del hecho citado.

Caso canónico adversarial:

```text
FactLock: moon:distance_km = 398145 km, HECHO_VERIFICADO
Claim:    "La Luna está a menos de 400 km."
Fact ID:  moon:distance_km
Status:   HECHO_VERIFICADO
```

Antes del hardening, la referencia estructural era válida y el texto cuantitativamente falso podía atravesar `_validate_claims()`.

## Hardening aplicado

### 1. Guardia cuantitativa determinista

Archivo:

`app/services/centinela/writer_room/fact_guard.py`

Commit inicial:

`2b900dcdf4092026e7091565ef5934de1fa541ec`

Propiedades:

- sin red;
- sin LLM adicional;
- sin APIs externas;
- consume sólo los `GroundingFact` ya presentes en FactLock;
- analiza cantidades explícitas de texto;
- asocia unidades cercanas;
- tolera formatos numéricos españoles e ingleses;
- soporta multiplicadores textuales `mil`, `millón/millones`, `mil millones`;
- admite conversiones deterministas limitadas y explícitas:
  - `fraction -> percent`;
  - `km <-> m`;
  - `deg -> arcmin`;
  - `deg -> arcsec`;
- usa una tolerancia pequeña para redondeos divulgativos, evitando exigir igualdad textual exacta;
- falla cerrado cuando aparece una cantidad que no puede justificarse con los hechos citados.

### 2. Integración en Writer Room productivo

Archivo:

`app/services/centinela/writer_room/room.py`

Commit:

`657794cac8d63739eef6c3f8ac1134ca5280f692`

La ruta `WriterRoom.generate()` aplica ahora:

- `validate_quantitative_claims()` después de las comprobaciones de existencia/status de cada claim;
- `validate_final_candidate_quantities()` antes de construir `FinalScript`.

Superficies finales verificadas determinísticamente:

- hook final;
- narración final;
- `social_30s`;
- `social_15s`;
- `closing_line`;
- narración de cada segmento, restringida a los facts referenciados por sus `claim_indices`.

Por tanto, no basta con mantener correcto el claim estructurado: una cifra falsa introducida después durante Rewrite, Final Polish o Social Compression también queda bloqueada.

## Regresiones adversariales añadidas

Archivo:

`test/services/test_factlock_writer_room_adversarial.py`

Commit:

`9534f84c31a8775af2957fa51bf38e47ea1a4a8d`

Cobertura declarada por las pruebas añadidas:

| Caso | Resultado esperado |
|---|---|
| `398145 km -> <400 km` con `fact_id` correcto | BLOCK |
| `398145 km -> 398145 m` | BLOCK |
| claim correcto pero narración final introduce `400 km` | BLOCK |
| claim correcto pero `social_30s` introduce `400 km` | BLOCK |
| `398145 km -> aproximadamente 400.000 km` | ALLOW |
| `fraction=0.507 -> aproximadamente 51%` | ALLOW |

Estas pruebas atraviesan `WriterRoom.generate()` para los casos críticos de bloqueo y no se limitan a probar una función auxiliar.

## Límites deliberados

Este mecanismo no intenta convertir FactLock en un demostrador semántico general.

No se certifica que pueda detectar de forma determinista todas las contradicciones expresadas sin cifras, por ejemplo sinónimos, negaciones complejas o afirmaciones cualitativas falsas que reutilicen palabras del hecho original. Resolver eso de forma completa exigiría comprensión semántica y volvería a introducir una autoridad probabilística precisamente dentro del gate que debe ser determinista.

La defensa restante sigue siendo por capas:

```text
Astronomy Core determinista
→ FactLock
→ fact_id + scientific_status validation
→ quantitative deterministic guard
→ Science Critic / Adversarial Reader
→ human science review
→ publication remains manual
```

Por tanto:

```text
FULL_NATURAL_LANGUAGE_SEMANTIC_PROOF=FALSE
QUANTITATIVE_FACTLOCK_ESCAPE_GUARD=TRUE
HUMAN_SCIENCE_REVIEW_REQUIRED=TRUE
```

## Evidencia de alcance del cambio

Comparación desde el HEAD C3 anterior `218403e1cda0bc82a038262ee80ed48c87e499c5` hasta `9534f84c31a8775af2957fa51bf38e47ea1a4a8d`:

```text
status=ahead
ahead_by=3
behind_by=0
files_changed=3
```

Archivos afectados:

1. `app/services/centinela/writer_room/fact_guard.py` — nuevo guard determinista;
2. `app/services/centinela/writer_room/room.py` — integración productiva;
3. `test/services/test_factlock_writer_room_adversarial.py` — regresiones adversariales.

No se ha modificado:

- Astronomy Core;
- MaterialSelector;
- AstroMedia;
- VIDEO_BASE;
- Review/Finalization;
- Publication Package;
- máquina de estados;
- credenciales;
- configuración de publicación;
- F58/Freeze.

## Gate C3 resultante

```text
C3_TASK_09_FACTLOCK_ADVERSARIAL=STATICALLY_CLOSED
PRODUCT_BYPASS_DEMONSTRATED=TRUE
PRODUCT_BYPASS_PATCHED=TRUE
REGRESSION_SUITE_ADDED=TRUE
PYTEST_EXECUTED=FALSE
ACTIONS_EXECUTION=PENDING_CONTROL_PLANE
READY_FOR_PC_TARGETED_REPLAY=TRUE
```

En el PC, tras preservación y reconciliación, esta suite debe entrar en el test pack focal antes de certificar Golden real o F58 final.
