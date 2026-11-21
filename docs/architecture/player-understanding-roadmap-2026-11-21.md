# Roadmap maestro: comprensión semántica de turnos — 2026-11-21

**Prioridad:** máxima prioridad técnica del proyecto hasta completar la aceptación v3 y la primera integración real con SillyTavern.  
**Fuente de verdad:** este documento.  
**Estado:** activo; creado por PR #292 (documental).  
**Baseline inspeccionada:** main, commit 9bf33899b3505dfd99c8f76087d89b1fcbbce885 (PR #291 integrada).

> Este roadmap reemplaza como prioridad activa de NLU cualquier secuencia anterior que terminase en PR #288/#289. Las PR #285–#288 entregaron building blocks importantes; no activaron v3 en producción. Las auditorías y reportes fechados conservan su valor histórico y no deben reescribirse para aparentar que el trabajo futuro ya estaba implementado.

## 1. Decisión ejecutiva

La máxima prioridad actual es conseguir que Campaign-Manager reconstruya de forma fiable el significado de los mensajes reales del jugador, especialmente cuando combinan varios actos, eventos, actores, referencias, condiciones y hechos de mundo.

No se autoriza una reescritura general del backend. Se conserva:
- El monolito modular y sus límites de paquetes.
- Una única interpretación LLM holística por turno; no dividir una misma semántica en llamadas independientes para actor, verbo, argumentos, discurso y relaciones.
- La autoridad determinista del backend para identidad canónica, visibilidad, selección de acciones, adjudicación, persistencia y commit.
- Los límites durables existentes: idempotencia, lease fencing, revisión de campaña, compare-and-swap, atomicidad y recuperación.
- El camino de compatibilidad para v1/v2 y los registros históricos.

La transformación principal es sustituir progresivamente la representación de intención v2 por una interpretación semántica v3 que separe:
1. Actos comunicativos.
2. Eventos y proposiciones.
3. Estatus epistémico, fase de acción y polaridad.
4. Enlaces discursivos y dependencias.
5. Candidatos de hechos del mundo.
6. Selección backend de acciones jugables.

**No activar v3 en producción por tener DTOs, pruebas deterministas o un test shadow verde.** La promoción exige aceptación semántica, seguridad de persistencia y validación integrada.

## 2. Baseline verificada

### 2.1 Ejecución local compartida — 21/11/2026

| Indicador | Resultado |
|---|---:|
| Commit | 9bf33899b3505dfd99c8f76087d89b1fcbbce885 |
| Modelo | gemma4:12b-it-q4_K_M |
| Ollama | 0.40.17 |
| Thinking | false |
| Suite live | 23 pruebas |
| Passed / failed | 16 / 7 |
| Errors / skipped | 0 / 0 |
| Duración suite Ollama | 2664,61 s (44 min 24,61 s) |
| Duración total del runner | 2676,19 s |
| Procedencia SHA | PASS; cinco informes comprobados |
| A/B Intent vs. Stanza | Omitido |
| Procesadores Stanza Spanish | Etapa de descarga fallida |

La procedencia del run es coherente: el SHA del resumen y el commit inspeccionado coinciden; el runner declara la validación de procedencia como PASS. La antigua discrepancia de metadatos documentada en ejecuciones anteriores no debe repetirse como diagnóstico de este run.

### 2.2 Siete pruebas live fallidas

- test_real_ollama_updates_a_known_npc_only_with_a_new_explicit_fact
- test_real_ollama_meets_shared_player_intent_corpus_v1
- test_real_ollama_compound_intent_understanding_holdout
- test_real_ollama_meets_held_out_discourse_intent_and_resolution_corpus
- test_real_ollama_operation_quality_and_critical_negative_controls
- test_real_ollama_meets_held_out_language_understanding_corpus_v1
- test_real_ollama_meets_held_out_semantic_frame_corpus_v1

Los nombres anteriores identifican la superficie de fallo, no la causa exacta. La causa por escenario debe obtenerse de las aserciones, reportes y salidas estructuradas de cada evaluación; no debe deducirse solo del nombre del test.

### 2.3 Métricas de evaluaciones live

| Evaluación | Escenarios | Llamadas | Tiempo | Resultado relevante |
|---|---:|---:|---:|---|
| Compound intent | 14 | 32 | 185,00 s | 9 fallos críticos, 3 discrepancias observacionales; slot F1 0,9453 |
| Discourse holdout | 24 | 60 | 277,43 s | 1 fallo crítico, 2 discrepancias; callback exact accuracy 56/56 |
| Language intent holdout | 35 | 75 | 995,88 s | slot F1 0,9710; recall 0,9764 |
| Player-turn v3 shadow | 12 | 24 | 156,43 s | F1 0,3150; precision 0,8684; recall 0,1924 |
| Semantic-frame predicate holdout | 20 | 36 | 526,72 s | slot F1 0,9424; precision 0,9170; recall 0,9693 |

Las cifras de diferentes corpus no son combinables en un score general. Un F1 de slots alto no equivale a exactitud de escenarios completos.

El recall v3 de 0,1924 es una señal especialmente grave: la salida del modelo es relativamente precisa en los elementos que emite, pero omite gran parte de los elementos esperados. V3 permanece en shadow y no tiene autoridad de producción.

El callback exact accuracy 56/56 es una señal positiva de un control concreto; no demuestra por sí sola que la resolución de antecedentes, la selección de acciones y la persistencia integrada estén resueltas. No se debe comparar con resultados antiguos de 3/12 sin verificar el mismo denominador y contrato.

### 2.4 Coste de la evaluación

Los ocho tests más lentos acumulan aproximadamente 2470,36 segundos, alrededor del 92,7 % del tiempo de la suite live. Las principales duraciones son language understanding (1000 s), semantic-frame holdout (530,84 s), discourse holdout (285,65 s), compound intent (193,24 s) y v3 shadow (164,68 s).

Se necesitan perfiles rápidos, completos y de aceptación. No se debe acelerar el runner mediante concurrencia agresiva de llamadas al mismo Ollama sin medir la contención y demostrar que las comparaciones siguen siendo válidas.

## 3. Diagnóstico principal

### P0 — Representación semántica

V2 concentra dentro de steps, modality y active_step_index conceptos que pertenecen a planos distintos: fuerza comunicativa, procedencia epistémica, polaridad, fase de acción, condición y selección jugable. Esta mezcla explica por qué el sistema puede acertar actores, verbos o slots aislados y fallar el significado conjunto.

### P0 — Composición y dependencias

El sistema debe distinguir hechos independientes, intentos, resultados, condiciones y acciones sucesoras. Una secuencia gramatical no implica que todos sus fragmentos sean acciones ejecutables. Las dependencias deben ser explícitas y validadas por el backend.

### P0 — Hechos persistentes

Los hechos visibles y explícitos sobre un NPC deben evaluarse independientemente de una acción fallida del mismo mensaje. Participar en una transferencia no demuestra propiedad. Citas, rumores, hipótesis, negaciones y acciones no adjudicadas no deben convertirse en escrituras duraderas.

### P0 — V3 no aceptado

El contrato, prompt, selector y política de hechos existen como building blocks; no son todavía una ruta completa de producción. El shadow test es diagnóstico y declara expresamente que no aplica thresholds live.

### P1 — Normalización

Los normalizadores de superficie han crecido y contienen numerosas reparaciones de patrones específicos. Se deben inventariar reglas, medir activaciones, cubrir negativos y reducir inferencias solapadas. Una regla determinista puede retirar información no fundamentada o normalizar una construcción inequívoca; no debe inventar una lectura ambigua.

### P1 — Discurso y recuperación

La selección histórica y los callbacks son predominantemente léxicos y basados en patrones. Se debe evaluar el recall de antecedentes y su integración, no solo la presencia de hints.

### P1 — Runtime y reproducibilidad

Los parámetros efectivos de generación, la versión del prompt, el schema, el modelo, el contexto y el coste de cada llamada deben quedar identificados para reproducir comparaciones. La telemetría debe seguir excluyendo texto privado de jugador y campaña.

## 4. Building blocks ya integrados

| PR / artefacto | Entregado | Lo que NO significa |
|---|---|---|
| #282 | Auditoría y diseño semántico v3 | No implementa v3 |
| #284 | Hardening v2: tipo obligatorio de entidad, predicados de habla, callbacks y relaciones sombra | No elimina limitaciones de v2 |
| #285 | DTOs v3, decoder estricto, evidence spans, IDs locales y separación de tipos | No activa runtime ni prompt v3 |
| #286 | Prompt holístico y runner v2/v3 shadow con corpus inicial de 12 casos | No hay aceptación live ni autoridad v3 |
| #287 | Selector backend, dependencias, checkpoint durable y recibos | El selector no está conectado a la ruta real |
| #288 | Política backend de elegibilidad y operaciones de hechos | La política no está conectada al runtime |
| #289 | Runner y agregación del informe shadow | No mejora la comprensión |
| #290 | Reparaciones puntuales de regresiones v2 de semántica/discurso | No sustituye la representación v2 |
| #291 | Procedencia SHA y gate de cobertura exacta del 85 % | No valida calidad semántica |

La implementación y el estado real deben comprobarse en código al empezar cada PR. Esta tabla evita volver a implementar piezas ya entregadas y evita declarar como integrada una capacidad aislada.

## 5. Roadmap de PRs: secuencia principal

Los números siguientes son la secuencia reservada/propuesta después de la PR documental #292. Antes de abrir cada PR, se debe comprobar que el número y la rama siguen libres. Si aparece una PR intermedia ajena al programa, actualizar las referencias sin alterar el orden lógico.

Estados:
- [ ] PLANNED: no implementada.
- [~] IN PROGRESS: rama/PR abierta.
- [x] MERGED + VERIFIED: fusionada y con evidencias de aceptación registradas.
- [!] BLOCKED: bloqueada por dependencia o gate fallido.

Una PR no se considera completada porque su código esté escrito, porque CI pase o porque esté abierta. La finalización requiere merge y evidencia correspondiente.

### Track A — Medición fiable y comprensión v3

| PR | Prioridad | Estado | Objetivo y entregables | Dependencias |
|---|---|---|---|---|
| #292 | P0 | [~] IN PROGRESS | Consolidación documental, arquitectura objetivo, evaluación y política obligatoria de roadmap | #291 |
| #293 | P0 | [ ] PLANNED | Diagnóstico por escenario, grafo scorer, métricas de omisiones/extras, manifiesto reproducible de ejecución y parámetros Ollama explícitos | #292 |
| #294 | P0 | [ ] PLANNED | Corpus v3 held-out ampliado, gold relacional completo, negativos y validación de split/leakage | #293 |
| #295 | P0 | [ ] PLANNED | Rediseño del prompt v3 y contrato de generación para aumentar recall sin relajar evidencia/seguridad; evaluación de alineación de spans desde backend | #293–#294 |
| #296 | P0 | [ ] PLANNED | Validación de consistencia del grafo semántico: argumentos, atribuciones, dependencias, citas, extremos y hechos | #294–#295 |
| #297 | P0 | [ ] PLANNED | Evaluación de aceptación v3, ablations controladas de modelo/prompt/parámetros y decisión objetiva de promoción | #293–#296 |

### Track B — Integración durable del significado

| PR | Prioridad | Estado | Objetivo y entregables | Dependencias |
|---|---|---|---|---|
| #298 | P0 | [ ] PLANNED | Integrar action selector y checkpoint v3 en ruta aislada/feature flag; adjudicación de una acción elegible cada vez | #287, #296–#297 |
| #299 | P0 | [ ] PLANNED | Integrar world_fact_policy y recibos en el commit durable; hechos independientes de errores mecánicos; idempotencia y recuperación | #288, #298 |
| #300 | P0 | [ ] PLANNED | Orquestación end-to-end de turnos compuestos, callbacks, dependencias, aclaraciones, fallos mecánicos/técnicos y compatibilidad histórica | #298–#299 |
| #301 | P0 | [ ] PLANNED | Shadow de aceptación ampliado, feature flag de v3, prueba completa Ollama y checklist manual SillyTavern; decidir cutover o mantener v2 | #297–#300 |

### Track C — Robustez y calidad después del cutover inicial

| PR | Prioridad | Estado | Objetivo y entregables | Dependencias |
|---|---|---|---|---|
| #302 | P1 | [ ] PLANNED | Consolidar reglas de normalización: catálogo, precedencia, conflictos, diagnósticos, límites y corpus positivo/negativo | #297–#301 |
| #303 | P1 | [ ] PLANNED | Mejorar callback/antecedent retrieval, resolución de elipsis y continuidad multi-turn con medición Recall@k/MRR | #293–#301 |
| #304 | P1 | [ ] PLANNED | Mejorar recuperación de contexto y ranking híbrido solo a partir de fallos medidos de recall/precision | #293, #303 |
| #305 | P1 | [ ] PLANNED | Evaluar hechos estructurados de NPC con identidad, procedencia, temporalidad, contradicciones y ciclo de vida | #299–#301 |
| #306 | P2 | [ ] PLANNED | Evaluación multilingüe y robustez de paráfrasis; separar idioma de interfaz, campaña y mensajes de jugador | #294–#305 |

## 6. Gates transversales no negociables

Estos gates aplican a toda PR del programa que toque la capa semántica o el runtime:

1. No se debilitan decoders, validación de evidencia, permisos, visibilidad ni autoridad del backend para subir métricas.
2. No se aceptan mutaciones persistentes críticas falsas en ningún control negativo integrado.
3. Una cita, un reporte, un rumor, una hipótesis, una negación, un plan sin condición o un intento fallido no producen hechos no autorizados.
4. Los hechos independientes explícitos no se pierden por una acción no relacionada que falla.
5. Las referencias ambiguas se aclaran o se abstienen; nunca se convierten heurísticamente en IDs canónicos.
6. La evidencia del turno actual no se reconstruye copiando palabras del historial, narración o contexto de mundo.
7. La adjudicación de mecánicas y sus resultados siguen siendo deterministas/autoridad del motor.
8. Los commits mantienen idempotencia, revisión, lease fencing, CAS, atomicidad y recuperación.
9. Los registros históricos v1/v2 siguen siendo decodificables; no se reescriben silenciosamente.
10. Los registros privados de prompts, completions y campañas no se incorporan a informes agregados ni logs generales.

## 7. Objetivos de aceptación propuestos

Los umbrales numéricos finales se fijarán en PR #297, una vez auditados el gold, el scorer y la baseline de PR #293/#294. No se utilizará una media global para esconder un dominio débil.

Criterios obligatorios:
- 100 % de validez estructural en escenarios críticos de aceptación.
- Cero mutaciones persistentes críticas falsas en corpus negativos y pipeline integrado.
- Evaluación por separado de actos, eventos, roles, atribución, enlaces, hechos, evidencia y selección de acciones.
- Alta exactitud de escenario completo, además de precision/recall por nodo y relación.
- Repeticiones de casos críticos para medir estabilidad de generación.
- V3 no se promueve con recall bajo aunque su precision sea alta.
- Una discrepancia crítica no puede compensarse con un F1 agregado elevado.
- El test shadow inicial no sustituye a los gates nuevos.

Los objetivos provisionales de precisión/recall y exactitud de escenario se documentarán en el contrato de aceptación de PR #297, con denominadores y justificación. No se deben modificar golds o umbrales para hacer pasar una salida existente.

## 8. Separación de evidencias

Toda PR y todo informe deben separar:
- **Deterministic CI:** contratos, invariantes, validadores, persistencia, cobertura y pruebas con dobles.
- **Live Ollama:** comportamiento del modelo exacto, digest, versión, parámetros, latencia, tokens, escenarios y errores.
- **Manual SillyTavern:** flujo real conversacional, continuidad multi-turn, regeneración, fallos, reanudación y aislamiento de chats.

Un resultado de una clase no demuestra otra. No afirmar que SillyTavern está aceptado por tener tests unitarios verdes.

## 9. Regla de sincronización del roadmap

Actualizar este documento es trabajo obligatorio, no mantenimiento opcional.

Cada PR de las tracks A, B y C debe:
1. Actualizar su fila en este roadmap: alcance real, estado, PR, dependencias y resultado.
2. Registrar qué criterios se han implementado y cuáles siguen pendientes.
3. Añadir enlaces a los documentos técnicos y reportes producidos.
4. Registrar la evidencia de CI y, cuando corresponda, las evaluaciones Ollama/SillyTavern.
5. Reconciliar las filas de PRs anteriores que ya se hayan fusionado desde la última sincronización, incluyendo SHA de merge y fecha cuando estén disponibles.
6. No marcar una PR como MERGED + VERIFIED antes de que esté efectivamente fusionada y las evidencias estén disponibles.

La revisión del roadmap forma parte de la checklist de aceptación de PR. Una PR de implementación no se considera lista para merge si no sincroniza su fila y no explica cómo satisface los criterios del hito.

## 10. Documentos relacionados

- [Auditoría semántica inicial — 20/11](player-intent-semantic-redesign-audit-2026-11-20.md).
- [Arquitectura objetivo de comprensión — 21/11](player-understanding-target-architecture-2026-11-21.md).
- [Roadmap de evaluación semántica — 21/11](../quality/semantic-understanding-evaluation-roadmap-2026-11-21.md).
- [Roadmap de prompts y runtime Ollama — 21/11](../quality/llm-runtime-reproducibility-and-prompt-roadmap-2026-11-21.md).
- [Proceso de entrega y sincronización de PRs — 21/11](player-understanding-delivery-workflow-2026-11-21.md).
- [Contrato v3](player-turn-interpretation-v3-contract-2026-11-20.md), [shadow v3](player-turn-interpretation-v3-shadow-2026-11-20.md), [selector/checkpoint](player-action-selection-checkpoint-2026-11-20.md) y [política de hechos](player-world-fact-policy-2026-11-20.md).

**Decisión vigente:** mejorar primero la comprensión semántica real, no añadir nuevas funcionalidades de producto. No activar v3 hasta superar el gate completo de calidad, seguridad y aceptación integrada.
