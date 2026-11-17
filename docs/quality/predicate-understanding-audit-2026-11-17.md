# Auditoría de comprensión de predicados y siguiente fase de calidad

**Fecha:** 2026-11-17  
**Repositorio auditado:** `IvanVM04/Campaign-Manager`  
**Baseline de código:** `main` en `3b059f1898fe1ceed399052266614c9b8aa03ca6` (PR #249 documental fusionada sobre #248)  
**Objetivo:** mejorar la comprensión del modelo sobre los predicados de acción y relación expresados por el jugador, mantener su evidencia literal y cerrar los fallos de discurso que todavía impiden aceptar esta fase.

> Esta auditoría separa hechos verificables del repositorio, resultados de ejecuciones compartidas y estimaciones. No considera un test de contrato de prompt como prueba de que el modelo obedece el prompt.

## 1. Resumen ejecutivo

La arquitectura de comprensión ya tiene una base sólida: Intent compartido, semantic frames v2, evidencia literal estricta, resolución determinista, señales discursivas tipadas, referencias plurales transitorias y puertas de autorización separadas. No se recomienda reescribirla ni multiplicar las llamadas al modelo.

El mayor hueco que aparece al inspeccionar el código no es solamente de prompting: **la evaluación no mide de forma suficiente si el modelo elige el predicado semánticamente correcto para una acción**.

Hay que distinguir cuatro preguntas:

1. **Grounding literal:** ¿el valor emitido para `predicate` aparece literalmente en el mensaje actual y en el excerpt del paso?
2. **Identidad morfológica:** ¿se conserva la forma escrita, incluida conjugación, persona, tiempo, número, clíticos y acentos?
3. **Comprensión semántica:** ¿el verbo/predicado representa la acción o relación que el jugador quiso expresar?
4. **Valencia y estructura:** ¿el modelo asigna correctamente quién actúa, qué recibe la acción, destinatario, origen, destino, instrumento y dirección de la relación?

El código actual protege especialmente la primera pregunta. El corpus y el evaluador protegen parcialmente la tercera y la cuarta mediante familia semántica, argumentos y claims. No existe aún un score live independiente y completo de exactitud de `action_frame.predicate`.

**Diagnóstico:** infraestructura semántica y límites de seguridad, avanzados; medición de predicados y aceptación live, incompletas. La siguiente mejora debe empezar por medir, no por añadir una lista más larga de instrucciones.

## 2. Estado del repositorio y alcance observado

En la consulta del 2026-11-17, GitHub no devolvió PRs abiertas para el repositorio. La última entrega visible en `main` es:

- **#247 — fusionada:** alinea la selección de historial usada por Intent, recuperación suplementaria y resolución.
- **#248 — fusionada:** consolida señales de superficie, spans de pronombres, señales de habla, selección discursiva tipada, referencias plurales transitorias, protecciones para mecánicas y gates live de callbacks/topic boundaries.
- **#235 — fusionada:** aclara el contrato de evidencia literal en prompts y JSON Schema.
- **#236 — fusionada:** distingue diálogo in-fiction, preguntas al DM y reportes de eventos NPC.
- **#246 — fusionada:** mejora continuidad, callbacks, elipsis, atribución de actor y límites de evidencia.

No se encontró una PR abierta nueva identificable como la mejora de predicados mencionada. Por tanto, esta auditoría toma `main` en el SHA indicado como baseline. La PR nueva, si todavía no es visible en GitHub, deberá revisarse por separado al aparecer; no se atribuyen cambios no observados.

La auditoría se centra en predicados y calidad del lenguaje. No propone modificar los workflows durables, correcciones pendientes, transacciones, visibilidad, permisos de escritura ni autorización de mecánicas.

## 3. Hallazgo principal: la evaluación de acción no puntúa el predicado

### 3.1 Qué valida el código

En `models/semantic_frames.py`, `SemanticActionFrame.from_payload()` valida que el predicado sea texto válido y que aparezca en la evidencia mediante `_is_literal()`. La comparación usa normalización Unicode NFKC y casefold, y una comprobación de substring.

En `models/player_intent_analysis.py`, el predicado del frame también debe estar anclado al `source_excerpt` del paso. Esto es correcto como límite de confianza: un verbo recuperado exclusivamente del historial no debe convertirse en evidencia actual.

**Pero una coincidencia literal no acredita comprensión semántica.** Si el jugador escribe «Mara entrega la llave a Aldric», la validación de evidencia no prueba por sí sola que el modelo haya entendido el sentido de entregar, que Mara sea el agente, que la llave sea el tema transferido y Aldric el receptor.

### 3.2 Qué miden los corpora actuales

| Corpus | Casos | Cobertura observada del predicado |
|---|---:|---|
| `semantic_frame_corpus_holdout_v1.json` | 20 | Los `expected_action_frame` incluyen familia y argumentos; no tienen un campo gold de predicado para puntuar el frame de acción |
| `language_understanding_corpus_holdout_v1.json` | 26 | Evalúa categoría, paso activo, modalidad/actor y atributos de Intent; no puntúa el predicado del frame |
| `discourse_pipeline_corpus_holdout_v1.json` | 28 | Evalúa discurso, categoría, referencias, familia del frame y argumentos; no incluye exactitud general del predicado de acción |

El evaluador `tests/test_real_llm_semantic_holdout.py::_score_semantic_scenario()` sí itera los campos suministrados en `expected_relation`. Por tanto, los predicados de relación se contrastan **solo en fixtures que incluyen explícitamente `expected_relation.predicate`**. Otros casos verifican dirección, familia, polaridad u otros atributos disponibles sin comprobar el predicado.

El evaluador de discourse holdout compara familia y argumentos de los frames; no compara `action_frame.predicate`.

Hay tests puntuales que contienen un predicado esperado (por ejemplo, en un flujo de corrección), pero no sustituyen a un benchmark de predicados con positivos, negativos, homónimos, construcciones y diversidad de formas verbales.

**Consecuencia:** el 94,74 % de F1 semántico observado es una señal positiva para las dimensiones que el ledger cuenta, pero no debe describirse como «94,74 % de comprensión de predicados». Esa métrica no evalúa esa capacidad de forma directa.

## 4. Predicados de habla: mejora real, cobertura acotada

`services/discourse_context.py` contiene una lista explícita de formas verbales españolas e inglesas y una señal `SpeechPredicateSignal`. La señal extrae spans y exige una estructura superficial muy concreta: pronombre de tercera persona seguido directamente por una forma verbal reconocida, fuera de citas.

La normalización de #248 está deliberadamente limitada: un reporte positivo, de un solo paso, con actor NPC, modalidad observada/reportada y una señal de habla inequívoca puede pasar a diálogo/comunicación. No modifica la evidencia literal.

Es un diseño conservador y útil, pero no es un analizador general de predicados. Las limitaciones actuales incluyen:

- La lista de formas es manual y no cubre de forma sistemática conjugaciones, perífrasis, tiempos compuestos, variantes ortográficas o construcciones con auxiliares.
- La señal directa `pronombre + verbo` no cubre de forma general sujeto con nombre propio, sujeto pospuesto, adverbios interpuestos o construcciones con más de un verbo.
- No resuelve por sí sola negación, ironía, cita, discurso indirecto, verbos polisémicos o distinción entre uso literal y metalingüístico.
- El test positivo más representativo de esta señal es estrecho (por ejemplo, «Ellas contestan en voz alta»), aunque existen negativos para negación y citas.
- La señal superficial informa y permite una normalización muy limitada; no sustituye al análisis global de Intent.

No conviene ampliar indiscriminadamente la regex ni convertir cualquier verbo de habla en diálogo. Deben añadirse pares positivos/negativos y medir falsos positivos.

## 5. Resultados live disponibles y discrepancias

### 5.1 Último log compartido localizado

Se localizó en los archivos compartidos de conversaciones un log creado el 2026-11-16 a las 21:15 UTC. El holdout de discourse terminó con **1 fallo, 3 tests deseleccionados y 243,26 segundos**. El extracto no incluye digest del modelo ni versión/parametrización completa de Ollama, por lo que es una observación útil pero no un baseline plenamente reproducible.

| Métrica/familia | Resultado observado |
|---|---:|
| Context recall | 100 % |
| Intent — elipsis / acción pendiente | 50 % |
| Intent — callback explícito | 0 % |
| Intent — concordancia gramatical local | 75 % |
| Intent — referencia a larga distancia | 100 % |
| Intent — atribución de habla NPC | 100 % |
| Intent — cambio de tema | 25 % |
| Resolución — concordancia local | 75 % |
| Resolución — referencia a larga distancia | 100 % |
| F1 de semantic slots | 94,74 % |
| Precisión de enlace de entidades | 100 % |
| Recall de enlace de entidades | 71,43 % |
| Abstenciones correctas / incorrectas | 15 / 0 |
| Cambios persistentes críticos falsos | 0 |
| Filtraciones de secretos | 0 |

Fallos concretos registrados:
- Dos repeticiones de `dp-grammar-explicit-local-17`: el resolver no devolvió la entidad esperada y tampoco pidió aclaración.
- `dp-grammar-plural-abstention-20`: dos repeticiones clasificaron diálogo esperado como reporte; otra fue rechazada porque un argumento no estaba anclado a la evidencia del jugador. El rechazo del validador es el comportamiento seguro, aunque deja sin completar el caso semántico.

El 100 % de precisión con 71,43 % de recall significa que el modelo/resolver fue conservador en los enlaces emitidos, pero dejó algunos enlaces esperados sin resolver. No debe sacrificarse esa precisión para subir recall mediante enlaces especulativos.

### 5.2 Discrepancia con el documento anterior

`docs/quality/pr-246-discourse-continuity-intent-reliability.md` recoge un baseline con precision y recall de enlaces de entidades al 100 %. El log compartido más reciente muestra precisión 100 % y recall 71,43 %.

No es correcto escoger silenciosamente el número más favorable. Hasta repetir el holdout con la misma versión de código, digest, servidor, modelo por rol y parámetros, deben conservarse ambos registros como ejecuciones distintas y usarse el log 71,43 % como evidencia de que el recall no está cerrado.

### 5.3 Qué sí podemos concluir

- El grounding de contexto ha sido fuerte en los runs observados.
- La extracción de argumentos/familias semánticas ha llegado a un F1 alto.
- La atribución de habla NPC ha mejorado mucho en el último extracto.
- Callbacks y topic boundaries siguen siendo déficits claros.
- Hay fallos puntuales de resolución y de clasificación plural.
- No hay evidencia de un fallo de transporte Ollama en el último run: la ejecución completó las llamadas y falló por assertions semánticas.

No podemos inferir que la PR #248 haya mejorado el modelo en live: su descripción deja la aceptación Ollama y SillyTavern como gates separados.

## 6. Qué mantener intacto

Las siguientes decisiones son correctas y no deben relajarse para aumentar artificialmente las métricas:

- Predicados, menciones, argumentos, relaciones y `source_excerpt` actuales deben seguir anclados al texto actual.
- El historial orienta significado, pero no se convierte en evidencia del jugador.
- No canonicalizar pronombres ni insertar nombres históricos en el payload literal.
- Los grupos plurales no son un NPC único ni un objetivo mecánico singular.
- Una ambigüedad real debe producir abstención/aclaración.
- Un reporte, diálogo o referencia resuelta no autoriza por sí mismo cambios persistentes.
- Se mantienen los gates de visibilidad, validación de dominio, transacciones y workflow durable.
- No añadir otra llamada LLM al camino normal, vector DB o embeddings sin evidencia experimental de que la recuperación existente sea el cuello de botella.

## 7. Plan recomendado

### P0 — Hacer medible la comprensión del predicado (4–6 h)

Ampliar el corpus semántico con gold explícito para cada `action_frame.predicate` y los predicados de relaciones:

- `predicate_surface_exact`: forma escrita exacta esperada.
- `predicate_lemma` o clase morfológica: señal diagnóstica para distinguir error de forma y error de interpretación. No debe convertirse en una normalización que reescriba el output.
- `predicate_semantic_class`: significado operacional esperado, separado del string.
- `actor/agent`, roles/valencia y dirección: medir quién hace qué a quién y qué participantes faltan/sobran.

El evaluador debe reportar por separado exact match, semántica del predicado, family accuracy y role precision/recall/F1. Añadir negativos con verbos cercanos o polisémicos y construcciones donde el mismo verbo cambia de sentido. Mantener el holdout congelado: los ejemplos de evaluación no se copian al prompt.

### P0 — Reproducibilidad y diagnóstico por campo (2–3 h)

Cada ejecución live debe registrar, en un reporte JSON seguro:

- commit SHA, digest y nombre de modelo por rol, versión Ollama;
- parámetros de generación, `think`, timeout, contexto y hardware disponible;
- número de escenarios/repeticiones/llamadas y latencia;
- métricas por familia y por campo;
- códigos de validación y campo rechazado, sin guardar prompts, completions, texto de campaña ni secretos.

Comprobar también que los metadatos llegan realmente al artefacto producido; no confiar únicamente en propiedades JUnit si la configuración de `record_property` genera warnings de compatibilidad.

### P1 — Mejorar la cobertura de señales de superficie (4–6 h)

Ampliar pruebas controladas para formas verbales españolas, variaciones de sujeto/orden, adverbios, negación, perífrasis, tiempos, citas, discurso indirecto y frases multi-step. Cada positivo debe tener controles negativos que eviten normalizar por mera presencia de una palabra.

Mantener las señales tipadas y spans como evidencia auxiliar. Solo aplicar normalizaciones deterministas cuando la gramática superficial sea inequívoca y la transformación preserve actor, polaridad, modalidad y contenido.

No introducir una dependencia NLP grande hasta que los casos etiquetados demuestren que una solución pequeña no alcanza.

### P1 — Iteración semántica orientada por errores (4–6 h)

Una vez exista el score de predicados, agrupar fallos por:
- verbo/predicado mal copiado o ausente;
- predicado literal correcto pero sentido equivocado;
- actor equivocado;
- rol/argumento ausente o intercambiado;
- dirección/polaridad de relación incorrecta;
- validación por evidencia;
- historial/contexto seleccionado incorrectamente.

Cambiar una causa a la vez. Comparar contra el mismo conjunto y configuración; no aceptar un aumento de recall que cree falsos positivos.

### P1/P2 — Cerrar discurso y aceptación de integración (4–7 h)

Resolver los déficits de callback y topic boundary (actualmente 0 % y 25 % en el último log disponible), revisar los dos fallos de concordancia/resolución y comprobar los grupos plurales. Repetir el holdout completo con el SHA posterior a #248 y la misma configuración fijada. Después ejecutar al menos dos conversaciones aisladas en SillyTavern: una con callbacks/cambio de tema y otra con NPCs, plural, diálogo/report y aclaración.

**Orden recomendado:** corpus y métricas primero; después intervención de código/prompt focalizada; finalmente evaluación Ollama y SillyTavern. No invertir ese orden.

## 8. Criterios de salida

La fase no se considera terminada hasta cumplir todos estos gates:

1. Existe una métrica explícita para predicados de acción y de relación, con gold congelado y positivos/negativos.
2. El predicado emitido sigue siendo literal de la evidencia actual y no aparece canonicalizado desde el historial.
3. Mejora el score de predicado en held-out sin degradar family accuracy, roles, dirección, precision de entidades ni abstenciones.
4. Las familias callback y topic boundary dejan de ser fallos silenciosos; tienen thresholds de aceptación explícitos y superados.
5. Cero cambios persistentes críticos falsos y cero filtraciones de secretos.
6. Rerun reproducible con modelo/digest y configuración registrados.
7. Dos smoke tests satisfactorios en SillyTavern y sin contaminación entre chats.

El valor exacto de cada threshold numérico debe fijarse tras obtener el primer baseline de predicados. No se debe inventar retrospectivamente un objetivo para hacer que el run actual pase.

## 9. Estimación de progreso y esfuerzo restante

Estimación de ingeniería al 2026-11-17; no es una métrica generada por CI:

| Dimensión | Estimación de avance |
|---|---:|
| Arquitectura de Intent, semantic frames y fronteras de autoridad | 85–90 % |
| Evidencia literal y señales discursivas tipadas | 80–85 % |
| Comprensión de predicados medida con un benchmark suficiente | 35–45 % |
| Aceptación live de esta fase (Ollama + SillyTavern) | 45–55 % |
| **Avance global estimado de esta fase de calidad lingüística** | **~65 %** |

**Restante estimado: 20–28 horas de trabajo efectivo**, suponiendo que la configuración Ollama actual y el entorno SillyTavern siguen disponibles.

| Trabajo restante | Horas |
|---|---:|
| Gold de predicados y evaluator/ledger | 4–6 h |
| Reporte reproducible y diagnósticos de campo | 2–3 h |
| Ampliación focalizada de señales/contratos y tests | 4–6 h |
| Iteración de calidad por los fallos medidos | 4–6 h |
| Repeticiones Ollama, CI y aceptación SillyTavern | 6–7 h |
| **Total** | **20–28 h** |

La incertidumbre principal está en cuántas iteraciones requerirá el modelo para mejorar callback/topic boundary y en si aparecen regresiones al añadir el gold de predicados. El tiempo real de inferencia local depende del hardware/modelo y no está incluido como trabajo activo separado.

## 10. Archivos fuente examinados

- `services/turns/intent_interpreter.py`
- `services/turns/intent_response_schema.py`
- `services/discourse_context.py`
- `models/semantic_frames.py`
- `models/player_intent_analysis.py`
- `tests/test_real_llm_semantic_holdout.py`
- `tests/test_real_llm_discourse_pipeline.py`
- `tests/test_intent_speech_act_contract.py`
- `tests/test_discourse_context_builder.py`
- `tests/fixtures/semantic_frame_corpus_holdout_v1.json`
- `tests/fixtures/language_understanding_corpus_holdout_v1.json`
- `tests/fixtures/discourse_pipeline_corpus_holdout_v1.json`
- PRs #235, #236, #237, #246, #247 y #248.

**Estado final de auditoría:** la base arquitectónica es buena y el score semántico reciente es prometedor, pero aún no existe evidencia suficiente para declarar cerrada la comprensión de predicados. El próximo incremento de calidad debe ser una PR de evaluación de predicados y corrección guiada por métricas, no otra reescritura general del prompt.


## 12. Implementación P0 — PR #250

La PR #250 conserva intacto el fixture original de 20 casos y añade un sidecar `semantic_frame_predicate_gold_v1.json` enlazado por los IDs existentes, sin duplicar frases. Incorpora evaluación separada de predicados de acción y relación, comprobación de integridad que exige que cada gold aparezca literalmente en el input original y exportación JSON opcional con metadata reproducible y telemetría allowlisted. No modifica prompts, validadores de producción ni autorización. La evaluación mide exactitud superficial (case-sensitive); no debe confundirse con un benchmark completo de desambiguación de sentidos léxicos.

Ejecución live recomendada:

```powershell
$env:CAMPAIGN_MANAGER_REAL_LLM_REPORT_PATH = ".\\artifacts\\predicate-holdout.json"
python -m pytest tests/test_real_llm_semantic_holdout.py -m real_llm -k "semantic_frame_corpus_v1" -v -s
```

Para un diagnóstico de un solo caso, establecer `CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID` con un ID del corpus. El filtro es estricto y no sustituye la evaluación completa.


## 13. Primer baseline de predicados Ollama — 2026-11-17

Ejecución local reportada desde la rama `feat/live-holdout-think-toggle`, con Gemma 4 12B Q4_K_M, digest `6114515d63c17436a7c0417d82820ac65ad643e2806c5a3c89cb62846436ed0b`, Ollama 0.40.16, `think=false`, timeout 300 s. Se procesaron los 20 escenarios del holdout en 36 llamadas y 671,547 s.

| Métrica | Resultado |
|---|---:|
| Action predicate surface F1 | 0,9714 |
| Relation predicate surface F1 | 0,2143 |
| Semantic slot F1 global | 0,6349 |
| Action predicate TP/FP/FN | 17 / 0 / 1 |
| Relation predicate TP/FP/FN | 3 / 7 / 15 |

Esta ejecución **no pasa los gates críticos**. El valor más sólido es la copia de predicados de acción; los fallos dominantes son clasificación de familias/roles de action frame, extracción y clasificación de relation claims, spans de predicado relacional, polaridad/modality, atribución y referencias temporales.

Diagnóstico concreto:
- `Entrego`, `entrega` y `Guardo` se copian bien, pero en varios casos el frame se clasifica como `interaction` en lugar de `transfer`; en combate ocurre lo mismo frente a `combat`. Los roles `theme`, `recipient`, `patient` e `instrument` tampoco se preservan de forma consistente.
- Los predicados relacionales incluyen preposiciones o negación (`pertenece a`, `jura lealtad a`, `no pertenece`) aunque el gold anota el núcleo léxico (`pertenece`, `jura lealtad`) y expresa negación en polarity/modality.
- Hay confusión entre `ownership`, `possession` y `membership`; fallos de dirección/mentions; y omisiones de atribución y temporal_expression.
- La métrica de relation predicate estaba condicionada a extremos textuales prácticamente exactos: una diferencia de artículo (`El anillo de plata` frente a `anillo de plata`) impedía siquiera comparar el predicado. Ese acoplamiento se corrige normalizando solo artículos iniciales para la identidad del extremo; la dirección y el predicado continúan puntuándose por separado.

No se cambia el gold para acomodar esta ejecución. El scorer previo también condicionaba los argumentos de action frame a que la familia coincidiera, y los campos de relation claim a que la dirección coincidiera. Por tanto, algunos falsos negativos agregados podían estar acoplados a otro fallo. Los resultados anteriores quedan archivados como baseline histórico de la versión previa del scorer; no deben compararse directamente con los resultados posteriores.

El incremento #252 (dependiente del toggle live #251) refuerza taxonomías y límites de span en prompt/schema, y separa la puntuación de argumentos/familia y de dirección/campos de relación. Debe volver a ejecutarse el mismo modelo/digest/think sobre el holdout completo para obtener un baseline comparable con el scorer corregido y comprobar si mejora sin sacrificar los límites de evidencia.
