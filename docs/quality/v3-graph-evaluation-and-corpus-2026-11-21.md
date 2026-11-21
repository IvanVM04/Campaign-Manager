# Scorer graph-aware y corpus v3 — 2026-11-21

**Implementación:** PR #293.  
**Primera fase de corpus #294:** incluida en #293; 20 escenarios adicionales.  
**Estado:** scorer y corpus añadidos; live baseline pendiente de ejecutar.  
**Roadmap:** [master](../architecture/player-understanding-roadmap-2026-11-21.md).

## 1. Por qué hacía falta

El scorer shadow v1 compara cantidades y multiconjuntos de etiquetas. Eso detecta
omisiones y extras de campos, pero puede dar crédito a una interpretación que
contiene los predicados, roles y tipos correctos enlazados a los nodos
equivocados. Tampoco comprueba de forma explícita los extremos de enlaces y
dependencias.

Ejemplos del error que ahora se detecta:
- Un evento conserva el predicado correcto, pero el argumento recipient termina
  en otro evento.
- Un evento tiene el actor/acto de origen incorrecto.
- Un enlace condition_on_success invierte el evento dependiente y su
  prerrequisito.
- Un fact candidate usa el tipo, predicado y nombres correctos, pero invierte
  sujeto/objeto o la dirección.
- Una aclaración afecta a un evento distinto del que contiene la referencia
  ambigua.

## 2. Alineación de nodos sin local IDs del modelo

Los IDs locales (act_*, event_*, etc.) solo sirven para enlazar nodos
dentro de una respuesta. No son identidades semánticas estables y no se
comparan con los gold.

El scorer alinea cada tipo de nodo usando una firma intrínseca que incluye:
- Sus atributos semánticos tipados.
- Argumentos y roles exactos, ordenados canónicamente cuando el orden no es
  semánticamente significativo.
- Menciones literales y kind hints.
- Atribución, polaridad, estatus epistémico, fase y tiempo.
- Spans de evidencia exactos (offset start/end y texto literal).

El alineador conserva multiplicidad. Duplicados no desaparecen mediante un set.
Cuando dos nodos son idénticos según su firma, el emparejamiento conserva el
orden de aparición del corpus/modelo. Los local IDs observados se usan solo
para construir el mapa temporal después de emparejar nodos.

Los spans forman parte de la firma porque un campo semántico correcto sin la
evidencia correcta no satisface el contrato.

## 3. Métricas de grafo

El scorer registra por familia:
- Exactitud/precision/recall para actos, eventos, facts, links y aclaraciones.
- Relaciones evento→acto de origen.
- Relaciones fact→acto de origen.
- Links discursivos con tipo y endpoints tipados (act/event/fact).
- Referencias afectadas por cada clarification.
- Exact semantic graph match por escenario.

Un escenario exacto debe tener los nodos y aristas esperados, sin omisiones,
duplicados ni extras. La precisión/recall parcial permanece visible para
diagnóstico; una etiqueta correcta enlazada al extremo incorrecto no recibe
crédito de arista.

El scorer no decide elegibilidad de acciones ni escritura de hechos. La
evaluación del grafo no sustituye al selector backend ni a world_fact_policy.

## 4. Contrato del gold

Nuevo fixture: tests/fixtures/player_turn_v3_graph_corpus_v1.json.

- Schema v1; split held_out.
- 20 escenarios adicionales español-first.
- Cada caso define actos, eventos, links, facts y aclaraciones esperadas.
- Los references se guardan como tipo de nodo + índice gold; nunca como
  local IDs del modelo.
- Los evidence spans son offsets Unicode de Python y se validan exactamente
  contra el texto del caso.
- El loader rechaza IDs duplicados, spans fuera de rango, spans que no sean
  literales, enlaces no resueltos y referencias gold inválidas.

Cobertura incluida: acción simple, percepción, movimiento, negación/rechazo,
diálogo citado de NPC, instrucción citada reportada, condicional/dependencia,
parentesco, atributo de NPC, transferencia sin propiedad inferida,
incertidumbre, atribución de reporte, callback, hostilidad, referencia
ambigua, hecho independiente de acción, relación negativa, pregunta sin hecho,
múltiples relaciones y propiedad reportada.

El corpus legacy v1 de 12 escenarios se conserva sin modificar. Los dos
corpus no comparten un mismo gold schema y no se deben combinar en una métrica
única ni afirmar que forman una misma muestra homogénea de 32 casos.

**Límite declarado:** 20 casos adicionales son una primera ampliación, no el
objetivo final de 100–300 escenarios anotados del roadmap. El siguiente
crecimiento se basará en errores observados, diversidad de construcciones y
revisión del gold; no en generar simples permutaciones de nombres.

## 5. Diagnóstico y privacidad

Los resultados por escenario incluyen únicamente:
- ID del fixture y familia.
- Severidad.
- Estado de validez.
- Componentes de grafo discrepantes.
- Cantidades gold/predichas/matched/FP/FN.
- Métricas agregadas de precision y recall.

No se incluyen utterance text, prompts, completions, menciones, predicados,
quote spans ni nombres de entidad. El matching usa esos datos solo en memoria.

## 6. Pruebas deterministas

Ejecutar:

    python -m pytest tests/test_player_turn_v3_graph_evaluation.py tests/test_player_turn_v3_shadow_evaluation.py -q

Los tests cubren:
- Loader held-out y unicidad del corpus.
- Match exacto sin depender del valor de local IDs.
- Rol argumental incorrecto.
- Endpoint invertido de una dependencia condicional, manteniendo los nodos.
- Nodos extra contados como falsos positivos.
- Interpretación inválida contada como nodos esperados omitidos.
- Rechazo de evidence spans no literales.
- Ausencia de texto de campaña en diagnósticos/reportes.

## 7. Evaluación real Ollama opt-in

Por coste, el nuevo holdout graph live no se añade por defecto a cada
ejecución general de real_llm. Se habilita explícitamente:

PowerShell:

    $env:CAMPAIGN_MANAGER_REAL_LLM_V3_GRAPH_ENABLE = "1"
    python -m pytest -m real_llm tests/test_real_llm_player_turn_v3_graph.py -v -s

Filtrar un solo escenario:

    $env:CAMPAIGN_MANAGER_REAL_LLM_V3_GRAPH_SCENARIO_ID = "conditional_open_then_enter"

Generar reporte local seguro:

    $env:CAMPAIGN_MANAGER_REAL_LLM_V3_GRAPH_REPORT_PATH = "ollama/reports/player-turn-v3-graph.json"

El informe se mantiene en modo diagnostic_baseline:
- La ruta de producción continúa en v2.
- V3 no tiene autoridad.
- No se aplican umbrales de rollout.
- No se afirma aceptación de SillyTavern.

El número de llamadas es dos por escenario cuando la construcción del prompt
v3 puede ejecutarse: v2 y v3 secuenciales con contexto/evidencia pareados.
