# Auditoría arquitectónica — comprensión del lenguaje, referencias y continuidad

**Fecha:** 2026-11-16  
**Repositorio:** IvanVM04/Campaign-Manager  
**Baseline revisado:** main en 61f6b279667f96aecf0553e452c8888328df8e4c (merge de PR #246)  
**Alcance:** flujo actual de Intent v2, contexto y selección de historial, discurso, resolución de referencias, validación de evidencia, propuestas de mundo, evaluación live y contratos de SillyTavern.

> Esta auditoría distingue hechos comprobados en el código, resultados de pruebas aportados y explicaciones que todavía requieren instrumentación. No presenta una hipótesis causal como si estuviera demostrada por el log.

## 1. Dictamen ejecutivo

**No recomiendo reescribir Campaign Manager ni sustituir su arquitectura principal.** La decisión de mantener un monolito modular local, una interpretación semántica compartida y etapas deterministas posteriores sigue siendo adecuada para el alcance actual. El proyecto ya dispone de límites importantes: IntentInterpreter, PlayerIntentAnalysis v2, resolución de referencias por código, adjudicación mecánica condicional, planner de consecuencias, validación de operaciones y ejecución durable.

El problema está en las **interfaces entre esas etapas**, en la representación incompleta de algunos fenómenos discursivos y en la forma en que medimos la calidad del modelo.

La PR #246 produjo mejoras medibles en el holdout proporcionado: el acierto de intención de elipsis pasó del 25 % al 50 %, la concordancia gramatical local del 50 % al 75 % y la atribución de diálogos NPC del 90 % al 100 %. Pero los callbacks explícitos siguen en 0 %, los límites entre temas permanecen en 25 % y el recall de enlaces a entidades cayó del 100 % al 71,43 %. Además, dos de las tres repeticiones del caso singular «Ella responde...» no resolvieron a Mara, y el caso plural «Ellas contestan...» alternó entre clasificación report y un argumento histórico que el validador rechazó.

Esto no apunta a que falten más instrucciones en el prompt. Apunta a que el sistema no posee todavía un **contrato discursivo tipado y compartido** que mantenga alineadas la selección del historial, la recuperación de contexto, la interpretación superficial y la resolución de referentes.

### Decisiones que debemos conservar

- Una única interpretación semántica coherente por turno normal. No separar actor, acción, argumentos, relaciones y diálogo en llamadas LLM independientes.
- Canonicalización de IDs, visibilidad, autorización y mutación en código determinista; nunca delegarlas al modelo.
- Evidencia literal estricta. El historial puede ayudar a interpretar, pero no se convierte en texto actual del jugador.
- Resolución conservadora y abstención ante ambigüedad.
- Separación entre Intent, adjudicación mecánica, propuesta de consecuencias y narración.
- Arquitectura de monolito modular y composición centralizada. No introducir microservicios, vector DB ni una nueva capa de memoria sin evidencia experimental.

### Decisiones que sí debemos cambiar

1. Usar exactamente el mismo historial ya seleccionado por tema en todas las etapas de recuperación.
2. Dejar de depender exclusivamente de las menciones que el LLM haya emitido para descubrir referentes presentes en el texto actual.
3. Introducir una representación explícita de grupos discursivos sin convertirlos en un NPC individual.
4. Convertir las señales de discurso en resultados tipados y trazables, no únicamente en texto libre añadido al prompt.
5. Hacer que los casos centrales de callbacks y límites de tema sean puertas de calidad reales, en lugar de métricas observacionales que pueden fallar sin bloquear la aceptación.
6. Mejorar los diagnósticos de salida semántica y resolución sin registrar prompts, secretos ni contenido sensible.

## 2. Evidencia evaluada y límites

### Código y documentación revisados

- services/turns/intent_interpreter.py
- services/turns/turn_resolution_service.py
- services/turns/intent_response_schema.py
- services/turns/mechanics_adjudicator.py
- services/discourse_context.py
- services/context/context_builder.py
- services/context/conversation_reference_resolver.py
- services/context/world_reference_resolver.py
- services/context/entity_reference_resolver.py
- models/player_intent_analysis.py
- models/semantic_frames.py
- models/discourse_evidence.py
- models/resolved_conversation_reference.py
- tests/test_real_llm_discourse_pipeline.py
- tests/semantic_evaluation_metrics.py
- tests/fixtures/discourse_pipeline_corpus_holdout_v1.json
- auditorías y decisiones anteriores en docs/architecture/ y docs/quality/, incluida la decisión de pipeline modular de 2026-11-14 y la auditoría de lenguaje de 2026-11-14.

### Resultados live aportados

La comparación que motiva esta auditoría es:

| Familia / métrica | Baseline anterior | Tras PR #246 | Lectura |
|---|---:|---:|---|
| Elipsis / acción pendiente | 25 % | 50 % | Mejora de 25 puntos |
| Concordancia gramatical local | 50 % | 75 % | Mejora de 25 puntos |
| Atribución de diálogo NPC | 90 % | 100 % | Mejora de 10 puntos |
| Referencia a larga distancia | 100 % | 100 % | Sin cambio |
| Callback explícito | 0 % | 0 % | Sin mejora |
| Límite de tema | 25 % | 25 % | Sin mejora |
| Recall de enlaces a entidades | 100 % | 71,43 % | Regresión de 28,57 puntos |
| Precisión de enlaces a entidades | 100 % | 100 % | Sin falsos enlaces medidos |
| F1 de slots semánticos | 94,74 % | 94,74 % | Sin cambio |
| Recall de contexto | 100 % | 100 % | Sin cambio |
| Abstenciones correctas / incorrectas | 15 / 0 | 15 / 0 | Seguridad conservada |
| Cambios persistentes críticos falsos | 0 | 0 | Seguridad conservada |
| Fugas de secretos | 0 | 0 | Seguridad conservada |

Los errores concretos del log aportado son:
- dp-grammar-explicit-local-17: «Ella responde en voz alta a mi pregunta». En dos de tres repeticiones no se devolvió la entidad esperada y tampoco se pidió aclaración.
- dp-grammar-plural-abstention-20: «Ellas contestan en voz alta desde el balcón». En dos repeticiones la categoría fue report, cuando el objetivo del caso es dialogue. En otra repetición se emitió un argumento no sustentado por el texto actual y el validador rechazó toda la interpretación con evidence_not_in_player_text.

**Límite de la evidencia:** el log no contiene la salida estructurada íntegra de cada repetición ni acredita claramente digest del modelo, parámetros de generación y versión del servidor. Por tanto, podemos demostrar el resultado de las métricas y la clase de fallo de validación, pero no atribuir con certeza cada fallo a una única instrucción o módulo. La comparación debe considerarse orientativa hasta fijar y archivar la configuración exacta del proveedor.

Tampoco he ejecutado Ollama ni una sesión real de SillyTavern desde este entorno. Esta auditoría se basa en el código integrado y en el resultado live que has aportado. Los tests deterministas y CI son evidencia de contratos de software, no sustituyen esa aceptación.

## 3. Mapa del flujo actual

El diseño activo puede resumirse así:

1. IntentInterpreter recibe el mensaje actual, historial limitado, proyección visible y pistas discursivas; devuelve una única PlayerIntentAnalysis v2.
2. PlayerIntentAnalysis y SemanticActionFrame comprueban estructura, roles, modalidad y literalidad de los fragmentos.
3. TurnResolutionService construye una proyección de mundo para la segunda fase, resuelve entidades y referencias tipadas, y decide si procede una adjudicación mecánica.
4. MechanicsAdjudicator.adjudicate_analysis() trabaja sobre el paso activo ya validado, no vuelve a interpretar la conversación.
5. LLMWorldExtractor propone operaciones tipadas sobre la misma interpretación y la proyección del mundo.
6. Parser, validadores de dominio y servicios deterministas autorizan o rechazan las operaciones.
7. La ejecución durable confirma consecuencias antes de generar narración.

El flujo es conceptualmente correcto. Las deficiencias principales se encuentran en cómo se transporta el historial y en cómo se representa la referencia discursiva entre las etapas 1–4.

## 4. Hallazgos arquitectónicos

### A-01 — El historial recuperado vuelve a ampliarse después de haber sido segmentado

**Prioridad: P0 — corrección inmediata.**  
**Evidencia: defecto confirmado en el código.**

IntentInterpreter._build_prompt() ya calcula scoped_turns mediante DiscourseContextBuilder.scope_history() y utiliza esa selección para su recuperación suplementaria, el historial y el índice discursivo.

Sin embargo, en TurnResolutionService.prepare_turn() la lista semantic_queries se construye usando self._recent_context_queries(recent_turns), es decir, el historial completo recibido por el servicio. discourse_history se calcula después y solo se utiliza para los resolutores.

Esto rompe la promesa de que un callback o un cambio de tema limita el contexto de forma consistente: el segundo selector de contexto puede volver a recibir nombres y términos de segmentos que Intent había excluido.

**Corrección iniciada en esta entrega:** calcular el historial discursivo seleccionado antes de construir semantic_queries y usar esa misma lista tanto para las consultas suplementarias como para los resolutores. Se añade cobertura para el caso ordinario (mantener el segmento activo) y para callback explícito (recuperar el segmento anterior seleccionado).

No cambia la autoridad del modelo ni la política de referencias. Alinea dos etapas que ya debían compartir el mismo alcance.

### A-02 — La resolución depende de que el LLM emita primero cada mención

**Prioridad: P0/P1 — siguiente bloque funcional.**  
**Evidencia: dependencia confirmada; causa exacta del caso singular aún no demostrada.**

ConversationReferenceResolver.resolve() construye su lista de menciones a partir de:
- step.target_mentions;
- step.attributed_to;
- argumentos de action_frame;
- extremos de relaciones.

No construye de manera independiente un inventario de menciones superficiales desde current_input o desde source_excerpt. current_input sirve para seleccionar el historial, pero no para descubrir un pronombre que el LLM haya omitido en la interpretación.

Consecuencia: si el modelo clasifica el acto como diálogo pero omite «ella» como target/argument, el resolvedor no tiene una mención que resolver. Esto es compatible con el no_reference_returned del caso singular, pero para confirmar la causa concreta debemos conservar un diagnóstico sintético de qué menciones emitió el modelo en esas repeticiones.

**Dirección recomendada:**
- Extraer spans superficiales de menciones del texto actual como una entrada independiente al resolvedor.
- Mantener por separado surface mention (por ejemplo, «ella») y su candidato canónico (por ejemplo, Mara).
- Permitir que el resolvedor resuelva o solicite aclaración sobre una mención literal aunque el modelo la haya omitido del frame.
- No introducir nunca el nombre canónico en source_excerpt, target_mentions o argumentos literales si no estaba en el texto actual.
- Conservar la abstención si la gramática, visibilidad o evidencia no determinan un referente único.

La recuperación de contexto no debe depender de que la generación semántica haya sido perfecta.

### A-03 — No existe una representación de referente plural o grupo

**Prioridad: P1 — requiere evolución del modelo de referencias.**  
**Evidencia: limitación deliberada confirmada.**

ResolvedConversationReference representa una única entidad canónica con un único entity_id. ConversationReferenceResolver._rank_candidates() descarta expresamente los pronombres con número plural.

Esta decisión evita convertir «ellas» en Mara o Lía arbitrariamente, pero no permite representar el resultado semántico intermedio «grupo formado por Mara y Lía». El prompt pide preservar el grupo, pero el contrato de referencias no tiene un objeto que pueda transportarlo.

**Dirección recomendada:**
- Introducir un ResolvedConversationGroupReference transitorio, con los miembros canónicos, evidencia y señales de resolución.
- Permitir ese resultado solo cuando existe evidencia plural explícita y el conjunto de miembros está demostrado.
- No crear automáticamente una nueva entidad persistente de tipo grupo.
- No permitir que un grupo se convierta en un único objetivo de combate o mutación si la operación necesita un individuo.
- Ante grupos incompletos, ambiguos o con visibilidad desigual, pedir aclaración.

No se debe solucionar el caso plural debilitando la política de abstención.

### A-04 — La clasificación del acto de habla sigue siendo principalmente una decisión del LLM

**Prioridad: P1 — robustez semántica.**  
**Evidencia: diseño confirmado; el log muestra el síntoma.**

DiscourseContextBuilder._current_speech_predicates() reconoce formas de verbos de habla en el mensaje actual y las añade al prompt como texto. No devuelve un objeto tipado que pueda ser contrastado con la categoría y modalidad emitidas por el modelo.

Así, una forma verbal inequívocamente comunicativa como «contestan» puede aparecer en el mensaje y aun así terminar en report. El prompt ya contiene instrucciones para diferenciar diálogo de acciones físicas de NPC; repetirlas con más fuerza no ofrece una garantía estructural.

**Dirección recomendada:**
- Convertir las pistas superficiales de comunicación en señales tipadas con span, forma verbal y sujeto candidato.
- Validar coherencia entre esas señales y la categoría global/action frame del modelo.
- Si la señal es inequívoca y la clasificación la contradice, activar una corrección acotada o una aclaración; no reescribir silenciosamente todos los campos.
- Mantener la distinción: habla de NPC → dialogue; acto físico de NPC → report; jugador dirigiéndose a personaje → dialogue; pregunta al narrador → question.

No debe aplicarse una regla simplista que convierta cualquier aparición de un verbo de habla en diálogo: negación, cita, mención metalingüística y narración de terceros deben formar parte de los controles negativos.

### A-05 — El constructor discursivo concentra responsabilidades heterogéneas y devuelve texto libre

**Prioridad: P1 — refactor interno, no reescritura amplia.**  
**Evidencia: estructura del módulo confirmada.**

DiscourseContextBuilder contiene en una única clase:
- detección de cambios de tema;
- reconocimiento de callbacks;
- extracción de anclas por tokens;
- marcadores de elipsis;
- detección de pronombres y concordancia;
- pistas de actos de habla;
- extracción regex de citas NPC;
- segmentación y selección de historial;
- renderizado final de pistas en lenguaje natural.

Además, la selección de callback y la explicación renderizada se calculan parcialmente por separado. scope_history() devuelve solo turnos; no expone de manera estructurada la razón de selección, las anclas, las puntuaciones, los empates ni los turnos seleccionados.

Esto hace difícil saber si el error viene de seleccionar mal el historial, detectar mal un marcador, renderizar mal la pista, perderla por el presupuesto o que el modelo ignore una pista correcta.

**Dirección recomendada:**

Separar responsabilidades internas con contratos tipados, manteniendo el mismo servicio público inicialmente:
- TopicSegmenter → segmentos y límites detectados.
- DiscourseSelector → selección de segmento, motivo, anclas y empates.
- SurfaceLanguageSignals → spans de pronombre, habla, negación y elipsis.
- NpcUtteranceExtractor → atribución de cita explícita.
- DiscoursePromptRenderer → traducción de resultados tipados a una vista compacta para el LLM.

No convertir cada submódulo en una llamada de modelo. La separación es determinista y de responsabilidad.

### A-06 — La segmentación temática depende de marcadores explícitos y una ventana fija

**Prioridad: P1/P2 — ampliar con datos, no con listas arbitrarias.**  
**Evidencia: diseño confirmado; holdout no mejora aún.**

La segmentación se basa en una lista de expresiones explícitas como «cambiando de tema», «por cierto» o «ahora hablemos de». Los callbacks se extraen con tokens posteriores al marcador y se puntúan por solapamiento léxico con segmentos anteriores.

Limitaciones:
- Cambios de tema implícitos no están modelados.
- Temas paralelos se reducen a segmentos lineales por turno.
- El callback ancla toma todo el sufijo de la frase, por lo que tema y cláusula de acción pueden contaminarse entre sí.
- La selección por solapamiento de palabras no entiende relaciones semánticas ni paráfrasis.
- Si no hay ancla o coincidencia, el historial completo se conserva como ambiguo; eso es seguro, pero puede volver a introducir ruido.
- La ventana de doce turnos es una política de recencia, no una representación de tareas o temas pendientes.

**Dirección recomendada:**
- Identificar el tramo que expresa el tema reabierto, separado de la acción posterior.
- Mantener varias hipótesis de tema cuando hay empate, sin fusionarlas.
- Representar focos/antecedentes con evidencia, recencia, tema y estado de resolución.
- Introducir cambios implícitos solo después de añadir escenarios etiquetados y medir falsos cambios de tema.
- No ampliar la ventana sin datos; más historial también puede introducir distractores y referencias incorrectas.

### A-07 — El validador estricto convierte un campo semántico extra no sustentado en fallo total

**Prioridad: P1 — robustez sin perder seguridad.**  
**Evidencia: fallo exacto observado.**

En el caso plural, el modelo introdujo un action_frame.arguments[].mention que no estaba en el texto actual. PlayerIntentAnalysis.from_payload() rechazó la interpretación entera con evidence_not_in_player_text.

La validación es correcta: un argumento histórico no debe aceptarse como evidencia actual. El déficit es que un elemento incorrecto y potencialmente opcional invalida todo el acto de habla, impidiendo que la parte correcta («Ellas contestan») siga siendo utilizable.

**Dirección recomendada:**
- Mantener el validador de evidencia como autoridad estricta.
- Introducir una fase controlada de reparación/normalización únicamente para campos opcionales cuyo descarte no cambia actor, polaridad, modalidad, predicado, objetivo de una acción o autorización.
- Para campos que afecten a un objetivo o a una operación, no descartar en silencio: fallar de forma tipada y pedir aclaración.
- Registrar qué campo se descartó, por qué, y si el análisis restante sigue siendo semánticamente coherente.
- Añadir pruebas positivas y negativas de cada clase de reparación.

Nunca canonicalizar el alias histórico dentro del texto del jugador para hacer pasar la validación.

### A-08 — Los principales casos discursivos no son puertas reales de aceptación

**Prioridad: P0 — cambiar el criterio de salida.**  
**Evidencia: configuración del test confirmada.**

En tests/test_real_llm_discourse_pipeline.py, los fallos solo hacen que el test falle si el escenario es critical o está ejecutándose con filtro estricto. En el fixture actual, los cuatro escenarios de explicit_callback y los cuatro de topic_boundary son critical=false.

Por tanto, el holdout puede registrar 0 % en callbacks y 25 % en límites temáticos sin bloquear la ejecución completa. La métrica aparece en el informe, pero no es una condición de aceptación.

**Dirección recomendada:**
- Mantener separado el baseline observacional inicial del criterio de aceptación posterior.
- Una vez fijados digest, versión, parámetros y repeticiones, declarar objetivos mínimos por familia para callbacks, topic shift y diálogo NPC.
- Hacer que las familias que representan la misión principal de la PR sean críticas o tengan thresholds explícitos.
- No exigir 100 % de cada caso con un corpus pequeño sin repeticiones; usar métricas por familia, controles negativos y límites de falsa referencia.
- Los casos de desarrollo pueden guiar cambios; el conjunto held-out debe permanecer congelado.

No debe arreglarse este problema cambiando el resultado esperado para que el modelo pase.

### A-09 — Las dos fases de recuperación no comparten una proyección de evidencia completamente trazable

**Prioridad: P1 — diseño de contexto.**  
**Evidencia: dos rutas de contexto confirmadas.**

La primera fase de Intent utiliza ContextBuilder.build() para reunir y renderizar contexto para la interpretación. Después de recibir el análisis semántico, TurnResolutionService llama a build_proposal_context() con señales semánticas y una proyección diferente.

Una segunda recuperación tiene sentido porque los argumentos tipados aparecen después de la interpretación. El riesgo está en que no existe un TurnEvidenceBundle explícito que registre:
- historial seleccionado;
- menciones actuales;
- candidatos recuperados;
- fuentes y visibilidad;
- entidades obligatorias;
- presupuesto y elementos descartados;
- resultado de resolución.

Sin este artefacto, resulta difícil comparar qué vio el intérprete con qué vio el resolver/planner. El primer arreglo de A-01 elimina la reintroducción de temas excluidos; el siguiente paso debe hacer auditable la continuidad entre las dos proyecciones.

**Dirección recomendada:** crear un bundle de evidencia tipado, de vida corta y sin autoridad de mutación, reutilizado por las etapas downstream. No convertirlo en una base de memoria persistente.

### A-10 — La observabilidad no identifica con precisión la etapa responsable

**Prioridad: P1 — diagnóstico y benchmark.**  
**Evidencia: métricas actuales y configuración del test revisadas.**

El ledger recoge exactitud por familia, slots, resolución de entidades, contexto, abstenciones, operaciones falsas y latencia. Es una buena base. Pero para diagnosticar el log actual faltan, por caso:
- spans superficiales detectados en la frase;
- categoría, actor y modalidad emitidos;
- menciones y argumentos literales emitidos;
- selección de historial y motivo;
- candidatos de referencia y scores;
- decisión final y motivo de abstención;
- campos descartados/rechazados por validación.

El test cuenta intent_mentions_present como booleano, no como recall de las menciones esperadas. Una frase puede contener un pronombre resuelto o no resuelto y ambas cosas valen lo mismo en esa observación.

Además, el log muestra la advertencia de que record_property es incompatible con junit_family=xunit2. Esto puede impedir que parte de la metadata se conserve en el XML aun cuando se intente registrar model digest y versión de Ollama.

**Dirección recomendada:**
- Exportar un reporte estructurado JSON/JSONL de métricas, separado del JUnit estándar.
- Incluir digest, versión, modelos por rol, parámetros de generación, timeout, hardware y número de llamadas.
- Añadir diagnósticos sintéticos por caso sin almacenar prompt, completion, texto de campaña ni secretos.
- Distinguir fallos del proveedor, fallos de decodificación, errores de evidencia, omisión de mención, ambigüedad del resolver y falta de contexto.

### A-11 — Los umbrales del resolver son heurísticos y necesitan calibración

**Prioridad: P2 — solo después de mejorar la observabilidad.**  
**Evidencia: scoring fijo en código.**

El resolver usa señales ponderadas de recencia, fuente, repetición y tipo semántico, además de umbrales/márgenes fijos. Es determinista, auditable y no llama al modelo, lo cual es positivo. Pero no hay evidencia de que esos pesos o el margen de resolución estén calibrados contra distribuciones representativas de conversaciones reales.

No ajustar esos pesos para recuperar el caso Mara de forma aislada. Primero hay que capturar candidatos, scores, fuentes y resultados de falsos positivos/negativos. La calibración debe usar desarrollo, nunca el conjunto held-out.

## 5. Qué NO debemos cambiar

Los siguientes componentes no son el origen demostrado de estos fallos y deben protegerse:

- No volver al modelo combinado antiguo de Intent + mecánicas.
- No dividir un acto de habla en múltiples llamadas LLM independientes.
- No relajar la validación literal de source_excerpt, argumentos, relaciones y atribuciones.
- No resolver un plural eligiendo al NPC con mayor score si la referencia es a un grupo.
- No deducir género de un nombre propio.
- No convertir narrativa del DM o diálogo citado en evidencia actual del jugador.
- No permitir que un resultado del resolver autorice operaciones de mundo.
- No alterar visibilidad, idempotencia, lease fencing, commits durables o workflows de corrección de #244/#245.
- No introducir embeddings, vector DB, message bus o microservicios sin un benchmark que demuestre su necesidad.

La arquitectura de seguridad y autoridad es uno de los puntos fuertes del proyecto. La mejora debe estar en la comprensión y el transporte de evidencia, no en dar más poder al modelo.

## 6. Arquitectura objetivo recomendada

Propongo mantener un único PlayerIntentAnalysis y añadir un contrato determinista previo y otro posterior alrededor de él:

1. **Current Utterance Evidence**: texto literal + spans de predicados, menciones, pronombres y conectores discursivos, sin canonical IDs.
2. **Discourse Selection**: segmentos, callback anchor span, temas candidatos, turnos seleccionados, motivo y nivel de ambigüedad.
3. **Shared Intent Interpreter**: una única llamada semántica que produce el análisis v2/v3, manteniendo todas las restricciones de evidencia.
4. **Evidence Validation**: comprobación literal, coherencia entre speech cues y categoría, normalización permitida solo para campos no críticos.
5. **Reference Resolution**: mención literal → candidato(s) visible(s), con resultado entity/group/ambiguous/unresolved y trazabilidad de evidencia.
6. **Mechanics Adjudication**: solo para un intento activo del jugador con objetivo ya resuelto o suficientemente definido.
7. **Consequence Planning**: misma interpretación validada, referencias confiables y proyección visible; operaciones como propuestas no autoritativas.
8. **Domain Validation + Durable Commit**: sin cambios en su autoridad.
9. **Narration**: solo desde consecuencias confirmadas.

El artefacto nuevo más importante no es otro prompt ni otra memoria persistente: es una **representación tipada y trazable de evidencia discursiva y referencias**, compartida entre las etapas.

## 7. Plan de trabajo por fases

| Fase | Entrega | Prioridad | Criterio de salida |
|---|---|---|---|
| 0 | Alinear historial de recuperación entre Intent, propuesta y resolver | P0 | Tests prueban topic activo y callback, sin consultas de segmentos excluidos |
| 0 | Hacer que callbacks/topic shift tengan criterios de aceptación explícitos | P0 | Ninguna familia principal puede quedarse en 0 % y seguir siendo aceptación verde |
| 1 | Inventario/span de menciones actuales independiente del output LLM | P0 | Pronombre superficial puede llegar al resolver sin canonicalizar evidencia |
| 1 | Diagnóstico por etapa y metadata reproducible | P0 | Cada fallo se clasifica como selección, interpretación, grounding, resolución o proveedor |
| 2 | Resultado de referencia plural/grupo transitorio | P1 | Grupos demostrados se preservan; nunca colapsan a un miembro individual |
| 2 | Señales tipadas de habla y concordancia | P1 | Casos de diálogo NPC distinguen actor, destinatario y sujeto plural |
| 2 | Contrato tipado de selección discursiva y separación interna de responsabilidades | P1 | Selection/reason/scores se inspeccionan sin volver a parsear prompt text |
| 3 | Mejor callback y tópicos paralelos/implícitos | P1/P2 | Mejora held-out con negativos que midan falsos cambios de tema |
| 3 | Bundle de evidencia común entre recuperación de Intent y de propuesta | P1 | Se puede reconstruir qué vio cada etapa y qué quedó fuera por presupuesto |
| 4 | Calibración de resolver y benchmark representativo | P2 | Umbrales basados en desarrollo etiquetado; held-out congelado |
| 4 | Aceptación real en dos chats de SillyTavern | Gate de producto | Historial aislado, callbacks, plurales, NPC, aclaraciones, restart/replay |

### Orden consolidado de implementación

- **PR #247 — fusionada:** auditoría versionada y corrección de consistencia de historial entre recuperación de Intent y recuperación de propuesta.
- **PR #248 — consolidación actual:** agrupa las antiguas fases previstas #248–#251 en una sola entrega coherente: superficie de menciones independiente del LLM, referencias de grupo transitorias, señales tipadas de habla, selección discursiva tipada, límites de grupo frente a mecánicas individuales, diagnósticos por etapa y gates live explícitos para callbacks y topic boundaries.
- **Siguiente fase, después de medir #248:** mejoras de callbacks semánticos, tópicos paralelos/implícitos y calibración del resolver. No se empezará una memoria persistente, embeddings o vector DB sin evidencia held-out de que la recuperación léxica tipada ya no es suficiente.

La PR #248 no intenta separar todas las responsabilidades de DiscourseContextBuilder en múltiples clases antes de estabilizar y medir los nuevos contratos. El refactor interno se hará cuando la frontera tipada resultante esté validada.

## 8. Criterios de aceptación no negociables

- Cero cambios persistentes críticos falsos.
- Cero fugas de secretos.
- Cero canonicalizaciones que inserten nombres históricos en evidencia actual.
- Precisión de enlaces sin regresión; mejorar recall no justifica introducir enlaces falsos.
- Los plurales nunca se resuelven a una persona individual por score.
- Ambigüedad real → abstención/pregunta, no selección arbitraria.
- Callbacks y topic boundaries se evalúan como requisitos y no como métricas decorativas.
- El mismo digest, modelo por rol, versión de Ollama y parámetros se usan para comparar antes/después.
- CI determinista valida contratos; Ollama valida comportamiento del modelo; SillyTavern valida el recorrido real. Ninguno sustituye a los otros.

## 9. Trabajo iniciado en esta rama

Esta entrega corrige A-01:
- TurnResolutionService calcula el historial ya seleccionado por tema antes de formar las consultas de la proyección de propuesta.
- Las consultas suplementarias de historial y los resolutores reciben la misma lista seleccionada.
- Se añaden regresiones para el uso del segmento temático activo y para la reactivación explícita de un tema anterior.

La corrección no modifica prompts, esquemas semánticos, política de abstención ni autoridad de escritura. Es el primer paso de la auditoría, no pretende resolver por sí solo los fallos live restantes.

## 10. Limitaciones y siguiente evidencia

No se ejecutó Ollama ni SillyTavern desde esta auditoría. La nueva rama debe pasar CI determinista y el holdout del usuario debe repetirse con configuración fijada y metadata exportada. Los fallos de callbacks seguirán abiertos hasta que se demuestre mejora en los casos held-out y en una sesión real con dos chats.

## 11. Consolidación posterior a PR #247 — PR #248

PR #247 quedó fusionada en main el 2026-11-17, commit 9e91416dff8b0779047c8be68f947cf5aa446196. Su corrección de historial ya forma parte del baseline; no debe duplicarse como trabajo pendiente.

La siguiente entrega reúne en una única PR las antiguas fases #248–#251. Incluye:
- spans pronominales de tercera persona extraídos del fragmento literal actual, con exclusión de citas;
- señales tipadas para pronombre sujeto + predicado de habla;
- corrección determinista y acotada de un reporte positivo NPC a diálogo cuando la señal superficial es inequívoca;
- selección discursiva tipada con razón, anclas, segmentos seleccionados y ambigüedad;
- resultado transitorio de grupo para plural solo ante co-mención y concordancia explícitas;
- separación estricta entre referencias de grupo y objetivos mecánicos singulares;
- paso del grupo al planificador como miembros individuales, nunca como entidad persistente;
- callbacks y topic boundaries como casos críticos del holdout live;
- exportación JSON opcional de metadatos y métricas sintéticas, sin prompt, completion ni texto de campaña.

No se modifica la autoridad de escritura, la persistencia durable, las migraciones ni los contratos de corrección. La validación live con Ollama y la aceptación completa en SillyTavern siguen siendo gates separados de CI.
