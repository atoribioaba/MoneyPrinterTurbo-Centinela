# C3 — Writer Room adversarial regression certification

Fecha de consolidación: 2026-08-31  
Ámbito: cloud/static mechanism audit  
Rama: `centinela-cert/c3-f58-readiness-v0.1`

## Estado

```text
WRITER_ROOM_ADVERSARIAL_MECHANISM=PASS_STATIC
WRITER_ROOM_ADVERSARIAL_EXECUTION=PENDING_STEP_EXECUTION
CI_PRE_STEP_EXECUTION_BLOCKER=CONTROL_PLANE
AUTO_PUBLICATION=FALSE
EXTERNAL_MODEL_DOWNLOAD=FALSE
LOCAL_FINAL_CERTIFICATION_REQUIRED=TRUE
```

No se declara pytest ejecutado. GitHub Actions continúa bloqueado antes del primer step por el incidente de control plane ya clasificado en C3.

## Alcance

Este bloque es complementario al hardening cuantitativo FactLock. No repite la comprobación `398145 km -> <400 km`; congela adversarialmente las fronteras estructurales del Writer Room y su runtime local estructurado.

## Controles productivos verificados por inspección

### Subject binding

`WriterRoom.generate()` compara el tema de `WriterRoomRequest` con el `FactLock.subject` antes de resolver modelo o generar contenido. Un cambio de sujeto no puede consumir silenciosamente el FactLock de otro tema.

### Claim grounding en draft y final

`_validate_claims()` se ejecuta:

1. sobre `DraftPacket.claims`;
2. de nuevo sobre `FinalScriptCandidate.claims` después de Rewrite/Final Polish.

La segunda validación es necesaria porque la pasada final puede devolver claims distintos de los del draft.

Guards existentes:

- `fact_id` desconocido -> BLOCK;
- claim `HECHO_VERIFICADO` respaldado por un fact no `HECHO_VERIFICADO` -> BLOCK;
- cantidades fuera del FactLock -> BLOCK por el guard C3 cuantitativo.

### Manual review boundary

Un `FinalScript` exitoso se construye con:

```text
requires_human_review=True
approved_for_publication=False
```

La verificación primaria requerida por FactLock se propaga al script final. Writer Room no autoriza publicación.

### Runtime estructurado

`WriterRoomOllamaRuntime`:

- usa el adapter local Ollama;
- solicita JSON con schema Pydantic;
- si la primera salida no valida, permite una sola reparación;
- la reparación usa `temperature=0.0`;
- si la segunda salida vuelve a fallar, lanza `WriterRoomRuntimeError`;
- no contiene ruta de descarga de modelos.

## Regresiones añadidas

Archivo:

`test/services/test_writer_room_adversarial_regression.py`

Commit:

`15efa1ed71bd0aeb5ea515e58fa0efe9f1aa34aa`

| Caso adversarial | Resultado esperado |
|---|---|
| request `Júpiter` + FactLock `Saturno` | BLOCK antes de resolver/generar modelo |
| claim `HECHO_VERIFICADO` + fact `NO_VERIFICADO` | BLOCK |
| draft válido + final claim con `fact_id` inventado | BLOCK en segunda validación |
| generación correcta | `requires_human_review=True`, `approved_for_publication=False` |
| primera salida JSON inválida + segunda válida | una reparación, `request_count=2` |
| dos salidas estructuradas inválidas | FAIL CLOSED tras segundo intento |
| modelo solicitado no instalado | error de resolución; cero generaciones |

## Decisión sobre jerarquía de scientific_status

Durante la auditoría no se encontró en el código revisado una jerarquía canónica completa que ordene entre sí:

- `APROXIMACION_DIVULGATIVA`;
- `INFERENCIA`;
- `HIPOTESIS`;
- `RECREACION_VISUAL`;
- `NO_VERIFICADO`.

Por ello C3 **no inventa** una jerarquía nueva ni introduce un ranking de certeza no especificado. Se conserva el contrato explícito existente: `HECHO_VERIFICADO` sólo puede derivar de facts `HECHO_VERIFICADO`.

Si en una fase posterior se define formalmente una matriz de transiciones de scientific status, deberá añadirse como política explícita y probarse por separado.

```text
SCIENTIFIC_STATUS_TOTAL_ORDER_DEFINED=FALSE
NEW_STATUS_HIERARCHY_INVENTED=FALSE
HECHO_VERIFICADO_LAUNDERING_BLOCKED=TRUE
```

## Limitación deliberada

Writer Room no se declara demostrador semántico completo. El control factual sigue siendo por capas:

```text
Astronomy Core
→ FactLock
→ claims estructurados
→ guard cuantitativo determinista
→ Science Critic + Adversarial Reader
→ revisión humana de ciencia
```

Afirmaciones cualitativas falsas sin cifras pueden requerir crítica semántica y revisión humana. No se sobredeclara una capacidad determinista que el código no posee.

## Gate C3 resultante

```text
C3_TASK_10_WRITER_ROOM_ADVERSARIAL=STATICALLY_CLOSED
PRODUCTION_PATCH_REQUIRED=FALSE
ADVERSARIAL_REGRESSION_SUITE_ADDED=TRUE
PYTEST_EXECUTED=FALSE
ACTIONS_EXECUTION=PENDING_CONTROL_PLANE
READY_FOR_PC_TARGETED_REPLAY=TRUE
```
