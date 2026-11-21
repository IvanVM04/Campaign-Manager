# Arquitectura objetivo de comprensión de turnos — 2026-11-21

**Estado:** diseño objetivo para orientar el programa #292–#301; no describe el runtime actual.  
**Fuente de verdad de implementación:** código de main y guías de paquetes.  
**Roadmap:** [roadmap maestro](player-understanding-roadmap-2026-11-21.md).

## 1. Propósito

Definir una representación del mensaje del jugador que preserve el significado completo de un turno, sin mezclar actos comunicativos, eventos, hechos del mundo y acciones que el motor puede ejecutar.

La arquitectura debe soportar varios actos por mensaje, varios hablantes y actores, diálogo/citas/reportes/rumores, observaciones y acciones intentadas, negación/incertidumbre/hipótesis/condicionales, callback y elipsis, hechos explícitos sobre NPC, acciones con dependencias de éxito, hechos independientes de resultados mecánicos y aclaraciones parciales.

La solución no consiste en pedir al LLM que controle la campaña. El LLM interpreta; el backend resuelve identidad, elegibilidad, mecánicas, hechos autorizados y persistencia.

## 2. Principios de arquitectura

1. **Una interpretación semántica holística.** Los campos que describen una misma lectura salen de una única respuesta coherente. No separar actor, predicado, argumentos, discurso y relaciones en llamadas independientes.
2. **Autoridad por capas.** La salida LLM es evidencia no confiable. No contiene IDs canónicos, permisos, visibilidad, éxito mecánico ni autorización de escritura.
3. **Ejes ortogonales.** Fuerza comunicativa, speaker, agente, polaridad, estatus epistémico, fase de acción, tiempo y enlace discursivo no compiten dentro de un único enum.
4. **Evidencia local verificable.** Los campos literales se alinean con el texto actual del jugador; historial y narración solo ayudan a resolver contexto.
5. **Acciones y hechos separados.** Los argumentos de un evento no implican una relación persistente.
6. **Selección backend.** El LLM describe eventos; el backend decide qué acciones pueden pasar a mecánicas.
7. **Hechos independientes.** Un hecho explícito no relacionado con un intento fallido no se descarta por el fallo de ese intento.
8. **Fail closed en autoridad, no en toda la comprensión.** Una referencia o acción ambigua se aclara o se abstiene. La ambigüedad de una parte no debe borrar silenciosamente hechos independientes bien fundamentados.
9. **Durabilidad sin reinterpretación histórica.** Nuevos checkpoints y esquemas se versionan; payloads históricos v1/v2 se siguen decodificando.
10. **Monolito modular.** No añadir microservicios, bus, vector DB o framework genérico sin necesidad demostrada.

## 3. Modelo semántico objetivo

El contrato v3 ya aporta los tipos base. Las siguientes responsabilidades deben mantenerse explícitas.

### 3.1 UtteranceAct — acto comunicativo

Responde a quién habla, qué fuerza comunicativa expresa, si hay destinatario explícito, qué span contiene una cita y qué texto respalda el acto.

Fuerzas relevantes: assertion, question, in-character dialogue, warning, request, refusal, correction, hypothesis, report y other/unknown.

El speaker no es automáticamente el actor de un evento. El jugador puede hablar acerca de una acción de un NPC, citar a un viajero o preguntar al DM.

### 3.2 EventFrame — evento o proposición

Representa predicado de superficie, familia de evento, argumentos etiquetados por rol, polaridad, estado epistémico, fase de acción, fuente atribuida, expresión temporal, acto de origen y evidencia.

Ejemplos:
- «Intento abrir la puerta»: acción de jugador, fase attempted.
- «Aldric me muestra una cicatriz»: evento observado, actor Aldric, tema cicatriz.
- «El viajero dice que vio un dragón»: evento de comunicación y proposición reportada; no prueba la existencia del dragón.
- «Si llego a la cornisa, entro en la torre»: evento condicionado, no acción inmediatamente elegible.

Un paso gramatical no es necesariamente un evento independiente. Los marcadores de callback y las operaciones discursivas no se convierten en predicados de acción.

### 3.3 DiscourseLink — enlace discursivo

Representa orden temporal, continuación, condición de éxito, respuesta, corrección, elaboración, contraste, reporte/cita y callback.

Un callback enlaza el turno actual con un candidato de ancla literal. El modelo no elige un ID de turno ni una referencia canónica. El backend recupera antecedentes posibles dentro del mismo chat y decide si existe un candidato único o si debe abstenerse.

Para una dependencia condicional, el evento dependiente se enlaza explícitamente con su prerrequisito. El backend valida semántica, orden y ausencia de ciclos.

### 3.4 WorldFactCandidate — candidato de hecho

Un hecho potencial contiene acto de origen, sujeto/objeto, tipo de hecho, predicado, dirección, familia y tipo normalizado de relación, polaridad, estatus epistémico, temporalidad, fuente atribuida y evidencia literal.

Un WorldFactCandidate no es una operación ni concede autorización. Solo representa algo que el backend puede evaluar.

Ejemplos:
- «Mara es hermana de Aldric»: relación explícita y dirigida según el contrato familiar.
- «Entrego la llave a Mara»: evento de transferencia; no prueba ownership.
- «Un viajero dice que Mara es hermana de Aldric»: afirmación reportada, no hecho confirmado.
- «Aldric lleva una cicatriz visible»: candidato de atributo de entidad, independiente de otras acciones si la evidencia y la política permiten persistirlo.

### 3.5 ClarificationCandidate — ambigüedad material

Una aclaración se solicita cuando la ambigüedad impide una decisión correcta o segura: referente, rol, evento, relación, secuencia o temporalidad.

No preguntar por cada detalle desconocido. Separar lo procesable, lo que necesita referencia, lo bloqueado por dependencia y lo que puede abstenerse sin impedir otras partes del turno.

## 4. Evidencia: simplificar generación, no la garantía

El decoder v3 actual vincula spans Unicode de medio intervalo directamente al texto actual. Esa garantía debe conservarse.

Generar offsets exactos en el LLM añade trabajo mecánico y oportunidades de error. El diseño objetivo permite que el modelo emita fragmentos literales breves y que una fase determinista del backend calcule offsets.

Reglas para la alineación:
- La cadena del span debe existir literalmente en el mensaje actual.
- Debe seleccionarse una coincidencia única.
- Si hay múltiples coincidencias, resolver mediante contexto local determinista; si persiste la ambigüedad, rechazar o aclarar.
- Los offsets finales se calculan sobre el string original, como índices Unicode Python.
- La fase de alineación no completa, parafrasea ni sustituye evidencia.
- Los spans de cita quedan dentro de spans del acto correspondiente.
- Argumentos y predicados deben estar respaldados por evidencia del registro al que pertenecen.

No cambiar este contrato en producción hasta que PR #293–#296 comparen validez, recall, precisión de evidencia y escenarios completos.

## 5. Pipeline objetivo

### Etapa 1 — Contexto y evidencia

La frontera de aplicación construye texto original, historial acotado del mismo chat, proyección de mundo visible/compacta, referencias discursivas candidatas y contexto de personaje/campaña necesario. Historial y narración se marcan como contexto no autoritativo; no se copian a spans del turno actual.

### Etapa 2 — Interpretación holística v3

Una llamada del proveedor devuelve actos, eventos, enlaces, candidatos de hechos y aclaraciones con schema estricto.

No decide IDs canónicos, visibilidad, personaje controlado, acción activa, tiradas/resultados, operaciones ni permisos de persistencia.

### Etapa 3 — Validación sintáctica, semántica y de evidencia

Backend:
- Decodifica DTOs versionados.
- Comprueba IDs locales y referencias cruzadas.
- Alinea evidencia literal.
- Comprueba orden de registros.
- Comprueba citas y atribución.
- Comprueba consistencia de speaker/agent, fases, polaridad y links.
- Rechaza campos extra/desconocidos.
- Emite diagnósticos estables y libres de contenido privado.

No «reparar» una contradicción semántica ambigua mediante una transformación arbitraria.

### Etapa 4 — Resolución de referencias

Los mentions se resuelven contra entidades activas y visibles mediante resolvers backend.

La salida distingue resuelta única, no resuelta, ambigua y fuera de alcance/visibilidad. El LLM no suministra IDs. El resolver no cambia la interpretación literal.

### Etapa 5 — Candidate action graph

El selector backend deriva candidatos a partir de eventos validados. Comprueba speaker player/actor correcto, personaje controlado, fase attempted y estatus compatible, polaridad no negativa, evento no cubierto por cita, familia soportada, targets resueltos, dependencias explícitas y ausencia de ciclos.

Solo una acción elegible se entrega a adjudicación por vez. Los nodos posteriores permanecen pendientes hasta que se procese el actual. Un fallo del motor de reglas y un fallo técnico de infraestructura tienen transiciones diferentes.

### Etapa 6 — Candidate fact evaluation

Cada candidato de hecho se evalúa independientemente.

La política exige acto del jugador con fuerza adecuada, evidencia dentro del acto y fuera de citas, ausencia de fuente atribuida cuando se prohíbe, polaridad positiva, estatus epistémico permitido, temporalidad persistente, extremos visibles/activos/únicos/canónicos, familia/dirección soportada y ausencia de inferencia de ownership desde transferencia.

Una decisión rechazada no borra otro candidato válido. Una acción fallida no elimina un hecho independiente.

### Etapa 7 — Mecánicas

MechanicsAdjudicator recibe la acción validada, no el mensaje completo para reinterpretarlo. El motor determinista conserva autoridad sobre tiradas, éxito, fallo, daño y cambios mecánicos.

### Etapa 8 — Operaciones y commit

Las operaciones derivadas de acciones y hechos se mantienen separadas hasta validación y ensamblado de commit. Se preservan allowlist, IDs backend, claves idempotentes, lease/fencing, revisión/CAS, commit transaccional, inmutabilidad post-commit y recuperación.

Un receipt de validación de hecho no es prueba de escritura o commit; documenta que el candidato pasó la política.

### Etapa 9 — Narración

La narración posterior al commit describe la evidencia y operaciones confirmadas. Nunca adjudica ni persiste consecuencias.

## 6. Separación de responsabilidades por paquete

| Paquete / módulo | Responsabilidad objetivo | No debe hacer |
|---|---|---|
| services/context | Recuperar contexto visible y construir proyección acotada | Autorizar acciones o escribir mundo |
| services/discourse | Seleccionar historial, detectar señales y resolver antecedentes con límites | Inventar IDs o tratar callback como evento |
| IntentInterpreter / proveedor de intención | Una respuesta holística v3 | Elegir acción activa o persistir |
| models/player_turn_interpretation_v3 | DTOs, invariantes y decoder | Tomar decisiones de dominio |
| Evidence aligner (si se justifica) | Vincular spans literales al texto original | Corregir/parafrasear contenido |
| Reference resolvers | Vincular menciones a entidades visibles y únicas | Modificar el texto o inferir visibilidad |
| player_action_selector | Derivar grafo/candidatos backend | Llamar al LLM, tirar dados o escribir mundo |
| world_fact_policy | Determinar elegibilidad y construir operaciones tipadas | Resolver IDs por nombre o commit directo |
| mechanics_adjudicator | Adjudicar una acción validada | Reinterpretar el mensaje original |
| TurnResolutionService / durable collaborators | Orquestar checkpoint, aclaraciones, commit y recuperación | Bypassear lease/CAS |
| services/llm_world | Propuesta estructurada permitida por contrato | Reinterpretar libremente como autoridad |
| WorldService / WorldApplier | Validar y aplicar operaciones | Aceptar escritura cruda del modelo |
| Narration | Expresar resultado confirmado | Introducir cambios |

Mantener la dirección de dependencias actual del monolito modular y la composition root. No introducir importaciones inversas desde llm_world hacia context ni convertir routers en propietarios del workflow.

## 7. Errores y degradación segura

Cada fase debe producir un resultado tipado que distinga provider failure/timeout, JSON/schema inválido, fallo de evidencia, grafo inconsistente, referencia ambigua, acción no soportada, dependencia bloqueada, aclaración, hecho rechazado/validado/pendiente, fallo mecánico, conflicto de commit y recuperación.

No convertir todos estos casos en «unknown intent» genérico. Los diagnósticos identifican etapa, código estable, campo cuando sea seguro y número de registros; nunca registran texto privado, prompt completo, completion, secretos ni IDs canónicos innecesarios.

## 8. Migración v2 → v3

1. V1/v2 siguen decodificándose para históricos.
2. V3 se interpreta y evalúa en shadow.
3. El gate de aceptación se aplica fuera de producción.
4. Runtime v3 se habilita tras feature flag y baseline verificada.
5. Se preserva fallback controlado durante rollout, sin mezclar resultados v2 y v3 en un mismo checkpoint.
6. Los nuevos checkpoints incluyen versión, digest de input/interpretación y estado durable.
7. Los turnos iniciados se reanudan con el contrato/snapshot originalmente persistidos.
8. Los datos históricos no se reinterpretan silenciosamente por inferencia LLM.

La decisión de apagar v2 debe ser explícita, basada en aceptación y registrada en roadmap.

## 9. Fuera de alcance

No forman parte de esta fase:
- Reescribir Campaign-Manager como microservicios.
- Añadir vector database antes de medir recuperación actual.
- Añadir una llamada LLM por cada componente semántico.
- Fine-tuning sin corpus/gold fiable.
- Usar confianza autodeclarada como autoridad.
- Dar al LLM IDs, permisos, éxito de tirada o acceso directo a SQLite.
- Reemplazar mecánicas deterministas por razonamiento LLM.
- Diseñar una nueva UI de campaña.
