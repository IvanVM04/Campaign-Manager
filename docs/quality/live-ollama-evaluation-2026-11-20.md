# Evaluación live de Ollama — 2026-11-20

**Fecha de ejecución:** 2026-11-19 23:32:11 +01:00 a 2026-11-20 00:14:48 +01:00  
**Repositorio:** `IvanVM04/Campaign-Manager`  
**Commit declarado por el runner:** `a4a29f3c807dcd062b7261754cd90a86250f0b67`  
**Estado de la ejecución:** **FAILED**  
**Tipo de evidencia:** evaluación live local con Ollama; no es CI determinista ni aceptación SillyTavern.

> Este documento es una instantánea histórica de una ejecución concreta. Conserva los resultados tal como fueron reportados, distingue fallos del modelo de problemas del evaluador/trazabilidad y no convierte los objetivos propuestos en gates aprobados. No demuestra una mejora porcentual respecto a una versión anterior: para eso hace falta un baseline comparable con el mismo scorer, corpus, modelo y configuración.

## 1. Resumen ejecutivo

Se ejecutó la batería `real_llm` sobre cuatro evaluaciones live: intención/lenguaje, discurso, semantic frames/predicados y mensajes compuestos.

| Indicador | Resultado |
|---|---:|
| Pruebas live seleccionadas | 22 |
| Pruebas correctas | 11 (50,0 %) |
| Pruebas fallidas | 11 (50,0 %) |
| Errores de pytest | 0 |
| Pruebas omitidas | 0 |
| Duración total del runner | 2.556,77 s (42 min 36,77 s) |
| Duración registrada por pytest | 2.550,69 s |
| Etapa Ollama real_llm | 2.554,21 s |
| Media aritmética no ponderada del F1 de los cuatro informes | **93,00 %** |

El 93,00 % es únicamente la media simple de cuatro F1 de dominio. No es una métrica global oficial, no está ponderada por el número de slots y no significa que el sistema tenga un 93 % de comprensión general. Los informes evalúan esquemas y conjuntos distintos.

La señal más importante no es el promedio: la modalidad de los pasos compuestos obtiene solo **54,0 % F1** y fallan capacidades críticas como callbacks, atribución de diálogo, persistencia de propuestas tras una acción fallida y extracción de relaciones sin falsos positivos.

La ejecución sí contiene señales positivas: la comprensión general de intención obtiene F1 98,67 %, las referencias a larga distancia y varios casos de habla NPC funcionan bien, y la batería específica de calidad de operaciones obtiene precisión/recall 100 % en sus ocho escenarios. Sin embargo, esos resultados no compensan los fallos de integración observados en otras pruebas.

## 2. Configuración y reproducibilidad

### 2.1 Comando utilizado

```powershell
.\scripts\run-ollama-tests.ps1 -Evaluation all -SkipNlpPilot -SkipDependencySync -Model "gemma4:12b-it-q4_K_M" -Think false -TimeoutSeconds 300 -HardwareLabel "RTX 5070 Ti 16GB"
```

### 2.2 Entorno reportado

| Campo | Valor |
|---|---|
| Modelo | `gemma4:12b-it-q4_K_M` |
| Digest | `6114515d63c17436a7c0417d82820ac65ad643e2806c5a3c89cb62846436ed0b` |
| Ollama | `0.40.16` |
| Think | `false` |
| Timeout | 300 s |
| Hardware label | `RTX 5070 Ti 16GB` |
| Commit del resumen externo | `a4a29f3c807dcd062b7261754cd90a86250f0b67` |

La etiqueta de hardware identifica la máquina indicada para esta ejecución; el resumen no registra telemetría real de utilización de GPU, VRAM, potencia, temperatura ni distribución CPU/GPU. Por tanto, no permite afirmar cuánto se aprovechó la RTX 5070 Ti.

### 2.3 Etapas

| Etapa | Estado | Duración / detalle |
|---|---|---:|
| Sincronización de dependencias | Omitida por parámetro | 0 s |
| Preflight Python 3.12+ | Correcta | 0,05 s |
| Preparación de modelos Stanza | Omitida por `-SkipNlpPilot` | 0 s |
| Benchmark NLP offline | Omitido por `-SkipNlpPilot` | 0 s |
| Preflight de Ollama/modelo | Correcta | 2,08 s |
| Suite Ollama `real_llm` | **Fallida** | 2.554,21 s; exit code 1 |
| A/B live Intent vs. Stanza | No ejecutada | Requiere `-RunNlpAb` |
| Agregación de informes | Correcta | 0,26 s |
| Generación del resumen Markdown/JSON | Correcta | 0,13 s |

`-Evaluation all` cubrió las evaluaciones Ollama configuradas para este runner, pero no significa que se ejecutaran el piloto NLP, la comparación A/B o la aceptación manual de SillyTavern.

### 2.4 Discrepancia de trazabilidad del commit

El resumen exterior declara el commit:

`a4a29f3c807dcd062b7261754cd90a86250f0b67`

Ese SHA coincide con el `main` consultado al preparar este documento y contiene la integración de PR #280. Sin embargo, los cuatro informes JSON internos declaran:

`98d8759e9ed8648c481141b92a040c761b041287`

El modelo, digest, versión de Ollama, `think` y timeout sí coinciden entre informes. La discrepancia impide atribuir con total confianza los cuatro informes internos al SHA exterior, aunque no demuestra por sí sola que se ejecutara código antiguo.

La inspección del runner encontró que `CAMPAIGN_MANAGER_GIT_COMMIT` se inicializa mediante `Set-EnvDefault`. Si la variable ya existe en el entorno, puede conservar un SHA anterior. Es la explicación más probable, pero debe confirmarse con una corrección y una nueva ejecución.

**Acción necesaria:** establecer el commit actual de forma incondicional al inicio del runner, propagarlo a los procesos hijos y verificar que el resumen exterior y los cuatro JSON registran el mismo SHA.

## 3. Resultados por evaluación

### 3.1 Comparativa de alto nivel

| Informe | F1 | Precisión | Recall | Volumen indicado |
|---|---:|---:|---:|---|
| `language_intent_holdout.json` | **98,67 %** | 98,28 % | 99,06 % | 635 slots gold; 35 escenarios; 75 llamadas |
| `discourse-holdout.json` | **95,86 %** | 96,43 % | 95,29 % | Evaluación de discurso y resolución |
| `semantic_frame_predicate_holdout.json` | **92,24 %** | 90,68 % | 93,86 % | 228 slots gold; 20 escenarios; 36 llamadas |
| `compound-intent.json` | **85,24 %** | 85,67 % | 84,82 % | 32 ejecuciones de escenarios sumadas por familias |

La media aritmética de los cuatro F1 es:

`(98,67 + 95,86 + 92,24 + 85,24) / 4 = 93,0025 %`

Se conserva como indicador orientativo y no debe utilizarse como sustituto de las métricas por familia, campo o escenario.

### 3.2 Intención y lenguaje

**F1 98,67 % · precisión 98,28 % · recall 99,06 %.**

Resultados destacados por familia:

| Familia | Casos correctos |
|---|---:|
| Incertidumbre epistémica | 12/12 |
| Habla citada | 4/4 |
| Acción compuesta | 13/14 |
| Intento de acción | 6/9 |
| Fallos por negación | 17/18 |

El corpus base muestra una puntuación de slots alta. Aun así, el 50 % de las pruebas live de toda la suite falla, por lo que este F1 no debe interpretarse como evidencia de que la interpretación compuesta o la integración completa estén resueltas.

### 3.3 Discurso y resolución

**F1 95,86 % · precisión 96,43 % · recall 95,29 %.**

| Capacidad | Resultado |
|---|---:|
| Callback | 3/12 (25 %) |
| Elipsis de acción pendiente | 1/4 (25 %) |
| Referencias a larga distancia | 10/10 (100 %) |
| Habla citada de NPC | 10/10 (100 %) |
| Referencias distantes con contexto | 4/4 (100 %) |
| Abstenciones correctas | 12 |
| Abstenciones incorrectas | 0 |
| Cambios persistentes críticos falsos contabilizados por este informe | 0 |

Las referencias distantes y la atribución de habla NPC son fortalezas de este conjunto. Callback y elipsis siguen siendo déficits muy claros. Además, el resultado de cero cambios persistentes falsos del informe no evita el fallo independiente del pipeline integrado descrito en la sección 4.7.

### 3.4 Semantic frames y predicados

**F1 92,24 % · precisión 90,68 % · recall 93,86 %.**

| Dimensión / familia | Resultado observado |
|---|---:|
| Predicados de acción | 18/18 |
| Predicados de relación | 16/18 |
| Escenarios completos de transferencia | 1/6 (16,7 %) |
| Definición/instancia de objeto | 3/4 (75 %) |
| Escenarios completos de dirección de relación | 0/9 |
| Escenarios completos de modalidad epistémica relacional | 0/6 |
| Escenarios completos de temporalidad relacional | 0/3 |

Los resultados de predicado superficial son mejores que los resultados de escenario completo. En transferencias, por ejemplo, los argumentos pueden puntuarse correctamente mientras el sistema añade relaciones que no estaban expresadas. Un escenario solo pasa cuando cumple todo su contrato; no debe confundirse un F1 de slots alto con un porcentaje equivalente de escenarios completos correctos.

Se detectaron cinco falsos positivos de presencia de relación en los casos de transferencia señalados en el análisis del informe, además de falsos positivos en casos de creación/definición de objetos. Las dimensiones de dirección, modalidad y temporalidad requieren intervención específica.

### 3.5 Intención compuesta

**F1 85,24 % · precisión 85,67 % · recall 84,82 %.**

Se contabilizan 32 ejecuciones de escenarios agrupadas por familias; 8 pasan el contrato completo (25 %). La familia `player_dialogue_then_action` pasa 5/6 y `sequential_player_actions` pasa 3/3. Las restantes familias incluidas en esta suma no pasan ningún caso completo.

La puntuación agregada por dimensión, calculada sumando TP/FP/FN de las familias, es:

| Dimensión | TP | FP | FN | F1 |
|---|---:|---:|---:|---:|
| Actor por paso | 67 | 1 | 2 | **97,8 %** |
| Modalidad por paso | 37 | 31 | 32 | **54,0 %** |
| Polaridad por paso | 67 | 1 | 2 | **97,8 %** |
| Categoría compuesta | 25 | 7 | 7 | **78,1 %** |
| Número de pasos | 31 | 1 | 1 | **96,9 %** |
| Índice del paso activo | 30 | 2 | 2 | **93,8 %** |

El fallo dominante es la modalidad: el modelo suele identificar quién habla/actúa, la polaridad y la estructura de pasos, pero confunde si el paso es diálogo observado, reporte, intención o acción. Esto degrada escenarios completos aunque otras dimensiones sean correctas.

### 3.6 Calidad de operaciones de mundo

El informe de calidad de operaciones contiene ocho escenarios:

| Control | Resultado |
|---|---:|
| Precisión de operaciones | 100 % |
| Recall de operaciones | 100 % |
| Controles negativos de persistencia | 6/6 |
| Creación positiva de entidad | 1/1 |
| Actualización positiva de entidad | 1/1 |
| Cambios persistentes críticos falsos contabilizados | 0 |
| Filtraciones de secretos | 0 |

Estos ocho escenarios no son equivalentes a todas las pruebas integradas. En particular, coexisten con el fallo de propuesta de NPC sin `entity_type` y con el test integrado que observó una operación de mundo no esperada. Los resultados deben conservar sus denominadores y ámbitos separados.

## 4. Inventario de las 11 pruebas fallidas

La suite registró 22 pruebas, 11 correctas, 11 fallidas, cero errores de infraestructura y cero omitidas. Los nombres siguientes proceden del resumen JUnit/JSON de la ejecución.

| # | Prueba | Error o síntoma registrado |
|---:|---|---|
| 1 | `test_real_ollama_proposal_records_an_explicitly_introduced_npc` | La propuesta devolvió `entity_type = ""`; la aserción esperaba `"npc"`. |
| 2 | `test_real_ollama_does_not_persist_non_executed_or_quoted_intent[quoted-untrusted-instruction]` | `IntentInterpreterError: invalid_object_shape`, campo `steps[]`. |
| 3 | `test_real_ollama_keeps_only_the_confirmed_step_in_a_compound_action` | Se esperaba conservar un único paso confirmado; se obtuvieron cero. |
| 4 | `test_real_ollama_meets_shared_player_intent_corpus_v1` | Desajuste de modalidad en diálogo NPC: esperado `dialogue`, obtenido `reported`. |
| 5 | `test_real_ollama_meets_semantic_frame_corpus_v1` | Desajuste de predicado en relación de parentesco dirigida: gold `hermana` frente a la salida observada. |
| 6 | `test_real_ollama_compound_intent_understanding_holdout` | Fallos en varias familias de mensajes compuestos, sobre todo modalidad por paso y algunos índices de paso activo. |
| 7 | `test_real_ollama_discourse_callback_survives_integrated_turn_pipeline` | El test esperaba cero operaciones de mundo, pero el pipeline produjo una operación persistente. |
| 8 | `test_real_ollama_integrated_pipeline_preserves_one_explicit_npc_fact` | El detalle explícito `cicatriz` no quedó preservado en `description` o `notes` del NPC existente. |
| 9 | `test_real_ollama_meets_held_out_discourse_intent_and_resolution_corpus` | Fallos de callback, categoría discursiva y argumentos de acción. |
| 10 | `test_real_ollama_meets_held_out_language_understanding_corpus_v1` | Fallos en familias como intento fallido de forzar una cerradura, incertidumbre no relacionada y secuencia de NPC reportado seguida de rechazo/acción del jugador. |
| 11 | `test_real_ollama_meets_held_out_semantic_frame_corpus_v1` | Relaciones falsas en casos de transferencia/creación de objetos y problemas de atributos epistémicos de relaciones. |

### 4.1 Diálogo citado y verbos de habla

Caso visible: `Aldric me advierte: «No cruces el puente durante la noche».`

El holdout espera diálogo atribuido a Aldric, pero la salida se clasifica como reporte. La inspección de código encontró que el extractor de señales de habla no incluye las formas españolas `advierte/advirtió`, aunque otra normalización sí reconoce construcciones cercanas de reporte indirecto. La forma con dos puntos y cita necesita cobertura explícita, con negativos para evitar que cualquier verbo de advertencia o texto citado se convierta automáticamente en diálogo.

### 4.2 Mensajes compuestos y modalidad

La modalidad por paso tiene 54,0 % F1, mientras que actor y polaridad rondan 97,8 %. Esto apunta a una separación imperfecta entre:
- diálogo literal de un NPC;
- hechos reportados por el jugador;
- observaciones;
- intención/plan;
- acción intentada o ejecutada;
- rechazo o condición que modifica un paso posterior.

La siguiente intervención debe corregir la interpretación de la modalidad sin romper la alta precisión de actor, polaridad, recuento de pasos e índice activo. No conviene mejorar el score copiando casos held-out al prompt.

### 4.3 Relaciones: precisión y consistencia del gold

Además de los falsos positivos de relaciones sobre transferencias y creación de objetos, se identificó una discrepancia entre anotaciones: el caso `Mara es hermana de Aldric.` usa `hermana` en el fixture del corpus, mientras que un test determinista de normalización espera `es hermana` como superficie del predicado.

Antes de atribuir todo el fallo de parentesco al modelo, debe unificarse el contrato entre fixture, normalizador y tests deterministas. No se debe modificar el gold para hacer pasar la salida observada; debe decidirse y documentarse qué forma literal se puntúa.

### 4.4 Persistencia y acción no ejecutada

El fallo del pipeline integrado que produjo una operación de mundo cuando el test esperaba ninguna es prioritario por su impacto en la integridad del mundo de campaña. Debe comprobarse la relación entre:
- el resultado mecánico del intento;
- la confirmación de cada paso compuesto;
- callbacks o referencias a acciones pasadas;
- propuesta de efectos persistentes.

Una propuesta no debe convertir una acción fallida, citada, hipotética o no ejecutada en un hecho duradero. El resultado del informe de operaciones (6/6 controles negativos) no elimina la necesidad de cerrar el caso integrado que falló.

### 4.5 Creación y actualización de hechos de NPC

Dos problemas diferentes aparecen en las pruebas:
- para una persona introducida explícitamente, la propuesta de creación llegó con `entity_type` vacío en vez de `npc`;
- para una entidad existente, el hecho visible y duradero `cicatriz` no quedó guardado en `description` ni `notes`.

La guía de prompt ya reforzada en PR #280 no basta como garantía. La validación de operaciones debe exigir campos obligatorios no vacíos y la extracción debe preservar los detalles explícitos, sin inventar información ni duplicar entidades conocidas.

## 5. Lectura global: fortalezas, riesgos y límites

### Fortalezas respaldadas por esta ejecución

- Intención/lenguaje general: F1 98,67 %.
- Incertidumbre epistémica y habla citada en el holdout de intención: 12/12 y 4/4.
- Referencias distantes y atribución de habla NPC en el holdout de discurso: 10/10 en ambas familias.
- Predicados superficiales de acción: 18/18.
- Predicados superficiales de relación: 16/18.
- Calidad de operaciones en su batería de ocho escenarios: precisión/recall 100 %, sin filtraciones de secretos reportadas.

### Riesgos que impiden declarar la comprensión lista

1. Modalidad compuesta: 54,0 % F1.
2. Callback: 3/12; elipsis de acción pendiente: 1/4.
3. Integración: una operación persistente inesperada tras el escenario de callback.
4. Relaciones: falsos positivos en transferencias/creación de objetos y familias completas de dirección/epistemicidad/temporalidad con 0 casos completos.
5. Hechos de NPC: tipo de entidad vacío y detalle explícito no preservado.
6. Suite live: 11/22 pruebas fallidas.
7. Trazabilidad: discrepancia entre el SHA del resumen exterior y los metadatos de los informes internos.

### Lo que esta ejecución no demuestra

- No mide mejora porcentual frente a una baseline anterior comparable.
- No certifica comprensión general del idioma ni todos los tipos de mensajes de una partida.
- No certifica una sesión real con SillyTavern.
- No mide cobertura de código, utilización de GPU/VRAM ni consumo energético.
- No demuestra que el código ejecutado pertenezca inequívocamente al SHA exterior, dado el desajuste de metadatos.
- No permite fusionar los cuatro F1 en una puntuación global oficial.

## 6. Objetivos de referencia propuestos

Los siguientes son objetivos sugeridos durante el análisis posterior a esta ejecución. **No son gates existentes ni han sido aprobados como contrato de producto.** Deben confirmarse después de corregir la trazabilidad y repetir el mismo benchmark.

| Indicador | Resultado de esta ejecución | Objetivo provisional |
|---|---:|---:|
| Media simple de F1 por informe | 93,00 % | ≥95 % |
| F1 mínimo por dominio | 85,24 % | ≥90 % |
| Modalidad por paso compuesto | 54,0 % | ≥85 % |
| Callback | 25 % | ≥80 % |
| Escenario completo de transferencia | 16,7 % | ≥80 % |
| Suite live seleccionada | 11/22 (50 %) | 22/22 |
| Cambios persistentes críticos falsos | 0 en el aggregate de operaciones; un test integrado detectó una operación inesperada | 0 en todos los controles, incluido pipeline integrado |
| Filtraciones de secretos | 0 | 0 |

Estos objetivos no deben perseguirse a costa de más falsos positivos. En especial, subir el recall de callback o de relaciones no justifica enlazar entidades ambiguas ni convertir narración en escritura persistente.

## 7. Orden de trabajo recomendado tras el benchmark

### P0 — Recuperar reproducibilidad

- Sobrescribir `CAMPAIGN_MANAGER_GIT_COMMIT` con el SHA real al iniciar el runner.
- Verificar que todos los reportes JSON, el resumen y el commit probado declaran el mismo SHA.
- Repetir el mismo comando y conservar los cuatro JSON y el JUnit.
- Añadir una aserción/check al runner que detecte y falle ante metadatos internos incoherentes.

### P0 — Corregir modalidad y atribución de diálogo

- Ampliar las señales de habla con `advierte/advirtió` y la forma explícita con dos puntos/cita, acotando el span y preservando la atribución literal.
- Separar diálogo, reporte, observación, intención y ejecución en los pasos compuestos.
- Mantener negativos para citas no confiables, instrucciones citadas y habla de NPC que no sea una acción del jugador.
- Repetir los holdouts sin introducir sus utterances al prompt.

### P0 — Cerrar el límite entre acción y persistencia

- Reproducir el caso integrado de callback que emitió una operación inesperada.
- Hacer que el resultado mecánico y la confirmación del paso gobiernen qué operaciones persistentes se pueden proponer.
- Asegurar que callbacks y referencias históricas no autorizan por sí solos cambios de mundo.
- Mantener cero cambios persistentes críticos falsos en controles unitarios y end-to-end.

### P0/P1 — Reducir falsos positivos semánticos

- Rastrear la fuente de las cinco relaciones falsas detectadas en transferencias y las relaciones en creación/definición de objetos.
- Distinguir relaciones explícitas de destinatarios/roles de acción.
- Reconciliar la superficie `hermana` / `es hermana` entre fixture y normalización.
- Medir presencia, extremos, dirección, polaridad, modalidad y temporalidad por separado.

### P1 — Endurecer hechos de NPC

- Validar `entity_type` como campo obligatorio no vacío para `create_entity`.
- Verificar creación de NPC con tipo explícito y ausencia de duplicados.
- Preservar detalles estables explícitos (`cicatriz`) en la entidad existente y no convertir diálogo/rumor en hechos.
- Añadir pruebas para campo vacío, ausente y mal formado.

### P1 — Repetición completa y aceptación SillyTavern

- Repetir el mismo conjunto y configuración para poder calcular deltas fiables.
- Corregir las 11 familias de fallos antes de aceptar la batería.
- Mantener CI determinista y live Ollama como evidencias separadas.
- Tras pasar la batería, ejecutar y registrar el checklist manual de SillyTavern, incluyendo dos chats aislados, callback, NPC, cita, acción fallida, cambio persistente y recuperación tras reinicio.

## 8. Artefactos de la ejecución local

El resumen consolidado recibido declara estos artefactos:

- `logs/00-python-version.log`
- `logs/30-ollama.log`
- `logs/32-ollama-report.log`
- `logs/99-report.log`
- `logs/ollama.junit.xml`
- `ollama/reports/compound-intent.json`
- `ollama/reports/discourse-holdout.json`
- `ollama/reports/language_intent_holdout.json`
- `ollama/reports/semantic_frame_predicate_holdout.json`

Los ficheros originales pertenecen a la ejecución local y no se incorporan aquí. Este informe registra métricas agregadas, errores y metadatos relevantes sin copiar prompts, completions, narrativas de campaña ni otros datos de la conversación.

## 9. Contexto de cambios integrados

Las PR #279 y #280 estaban fusionadas antes de esta ejecución. El commit exterior `a4a29f3c807dcd062b7261754cd90a86250f0b67` corresponde al `main` consultado para este informe y contiene la integración de PR #280.

Este run es, por tanto, la primera lectura live compartida después de esa ronda de hardening. Sus fallos no invalidan automáticamente el diseño de las PR; muestran que las garantías deterministas y las instrucciones de prompt todavía no consiguen resultados consistentes en todos los casos reales con el modelo seleccionado.

---

**Conclusión:** la infraestructura de evaluación ya ofrece señales útiles y varias dimensiones están en un nivel alto, pero la calidad no está lista para declararse cerrada. La prioridad no es aumentar el número de prompts o tests sin dirección: es corregir, por evidencia, modalidad compuesta, callbacks, autorización de persistencia, precisión relacional, preservación de hechos de NPC y trazabilidad de los benchmarks.
