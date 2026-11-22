# Orquestación de acciones compuestas v3 — diseño de PR #299

**Fecha:** 2026-11-22  
**Estado:** implementación parcial; todavía no habilitada en el runtime  
**Dependencias:** PR #297 (preview/checkpoint v3) y PR #298 (hechos v3 durables)

## Objetivo

Convertir el grafo semántico de una intervención del jugador en una secuencia backend de acciones independientes, sin volver a interpretar cada fragmento con el LLM ni permitir que el modelo decida identidades, resultados mecánicos o escrituras.

El selector/checkpoint de PR #287 ya expresa el orden, las dependencias, las aclaraciones y la identidad de cada intento. PR #299 añade el contrato de orquestación para consumirlo: como máximo una acción se entrega al ejecutor cada vez; cada transición del grafo debe guardarse; el resultado de reglas y el error de infraestructura nunca se confunden.

## Núcleo implementado en esta rama

`V3CompoundActionOrchestrator` recibe tres piezas:

- Un `PlayerActionCheckpoint` versionado.
- Un ejecutor backend inyectado que recibe candidato, clave idempotente estable y si está reanudando un intento; debe devolver `ActionOutcome` producido por reglas/backend.
- Un callback de persistencia que guarda el checkpoint bajo el lease y CAS que controle el llamador.

El ciclo hace lo siguiente:

1. Selecciona una acción; si la evaluación de dependencias marca nodos como SKIPPED, persiste también esa transición.
2. Marca el nodo como IN_PROGRESS y lo persiste **antes** de invocar al ejecutor.
3. Registra SUCCESS/FAILURE solo a partir del resultado autoritativo del ejecutor.
4. Ante una excepción del ejecutor, registra EXECUTION_FAILED sin asignar un resultado de juego. El siguiente intento reutiliza la misma clave y aumenta el contador de intentos.
5. Continúa con la siguiente acción independiente o dependiente ya desbloqueada, o devuelve una pausa por aclaración/dependencia.
6. La ruta de reanudación de aclaración usa `resume_after_clarification`, conserva identidad/dependencias y expone los descendientes que deben reevaluarse.

La persistencia del inicio y del resultado son dos transiciones separadas. Si la llamada al ejecutor termina pero no se puede persistir el resultado, el nodo durable queda IN_PROGRESS y se reintenta con la misma clave. Por tanto, el ejecutor final debe ser idempotente y poder recuperar/reproducir el resultado de esa clave; no basta con que el callback de persistencia sea CAS.

## Integridad de la persistencia

`TurnResolutionRepository.save_action_checkpoint` permite ahora guardar cambios de progreso JSON junto al checkpoint en el mismo UPDATE con lease/CAS. Los campos auxiliares están limitados a `proposal_json`, `intent_json`, `adjudication_json` y `mechanics_json`; sus valores se validan como JSON antes de escribir. Se añadió una prueba de que el checkpoint y esos campos comparten la misma operación transaccional.

Esto no cambia el límite normal de commit: la propuesta preparada sigue aplicándose mediante el servicio de commit atómico existente. No se introducen commits parciales del mundo ni se relaja la revisión de campaña.

## Lo que aún impide activar ejecución real

El núcleo anterior es un state machine probado por contrato, no un adaptador de gameplay. Antes de conectar un flujo de usuario se deben completar y probar todos estos puntos:

1. **Adaptador de evento a acción:** convertir cada `EventFrame` almacenado a una única `PlayerIntentAnalysis` de un paso, conservando literalmente los spans y argumentos ya interpretados. No debe volver a llamar al intérprete para extraer la misma intención ni reinterpretar el mensaje completo.
2. **Adjudicación por acción:** invocar el adjudicador y las reglas con la proyección de mundo correcta, mapear el resultado de reglas a `ActionOutcome` y mantener separados diálogo, acciones sin tirada, tiradas automáticas y tiradas manuales.
3. **Operaciones y recuperación:** guardar el plan tipado de cada acción junto con cada transición. Si el proceso cae después de completar una acción, la recuperación debe reconstruir ese plan y su resultado sin reejecutar el LLM ni volver a aplicar sus efectos.
4. **Dependencias con contexto actualizado:** una acción sucesora condicionada por éxito debe ver los resultados relevantes de la anterior. Debe diseñarse una proyección virtual de los cambios staged o una frontera transaccional de subacción explícita; no se debe usar silenciosamente un snapshot inicial obsoleto.
5. **Aclaraciones y tiradas manuales:** reanudar el mismo checkpoint y el mismo nodo, validando la respuesta solo para los slots pendientes. Una respuesta manual o una aclaración no puede crear una interpretación nueva que reemplace el grafo original.
6. **Finalización atómica:** agregar las operaciones válidas, preservar recibos de hechos independientes y entregar una única propuesta completa al commit durable existente, salvo que una revisión arquitectónica separada autorice explícitamente una transacción por acción.
7. **Recuperación end-to-end:** probar reintentos con mismo idempotency key, leases caducados/reclamados, revisión stale, crash en cada transición, callback/antecedente, ramas condicionales y registros históricos v1/v2.

Los servicios existentes ofrecen parte de los puntos de extensión: `TurnResolutionService.prepare_turn` acepta un análisis y una proyección/resolución de referencias suministradas por backend; `V3ActionPreviewService.restore` reconstruye el grafo desde la interpretación persistida sin llamar al LLM. Aún falta conectarlos al ciclo durable de preparación, aclaración y tirada manual, y persistir los resultados staged con un codec versionado.

## Política de activación

No se añade una flag de ejecución en esta fase. Una flag antes de conectar el ejecutor y la recuperación haría parecer que existe una ruta de producción que no está implementada. El único comportamiento runtime autorizado por las PR anteriores sigue siendo:

- preview/selección v3 bajo `CAMPAIGN_MANAGER_PLAYER_TURN_V3_ACTION_SHADOW_ENABLED`;
- hechos v3 independientes bajo `CAMPAIGN_MANAGER_PLAYER_TURN_V3_WORLD_FACTS_ENABLED`;
- interpretación/mecánicas v2 y commit durable existentes como autoridad.

La ejecución compuesta seguirá inactiva hasta que los siete puntos anteriores tengan pruebas de integración y CI verde. La aceptación real con Ollama/SillyTavern pertenece al gate #300, no se presume por pasar pruebas deterministas.
