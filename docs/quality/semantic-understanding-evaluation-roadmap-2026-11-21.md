# Roadmap de evaluación de comprensión semántica — 2026-11-21

**Prioridad:** P0, bloquea la promoción de v3.  
**Estado:** plan activo; los nuevos gates todavía no están implementados.  
**Roadmap de ejecución:** [roadmap maestro](../architecture/player-understanding-roadmap-2026-11-21.md).

## 1. Objetivo

Pasar de evaluaciones que puntúan principalmente campos aislados a una evaluación que mida si el sistema reconstruye el significado completo de un mensaje, preserva la evidencia, enlaza correctamente los nodos semánticos y evita cambios no autorizados en el mundo.

La evaluación debe responder por separado:
- ¿Ha detectado todos los actos?
- ¿Ha identificado todos los eventos/proposiciones?
- ¿Ha asignado argumentos y roles correctos?
- ¿Ha atribuido hablantes y fuentes correctamente?
- ¿Ha interpretado modalidad, polaridad, fase y temporalidad?
- ¿Ha enlazado las cláusulas correctas?
- ¿Ha resuelto las referencias de contexto correctas?
- ¿Ha seleccionado solo la acción ejecutable?
- ¿Ha conservado los hechos explícitos elegibles?
- ¿Ha evitado persistir información no autorizada?

No producir una sola cifra de «comprensión general».

## 2. Baseline del run 21/11

| Familia | Escenarios | Calls | Resultado |
|---|---:|---:|---|
| Language intent holdout | 35 | 75 | semantic slot F1 0,9710; precision 0,9657; recall 0,9764 |
| Semantic-frame predicate holdout | 20 | 36 | F1 0,9424; precision 0,9170; recall 0,9693 |
| Discourse holdout | 24 | 60 | 1 critical failure; 2 observational mismatches; callback exact accuracy 56/56 |
| Compound intent | 14 | 32 | 9 critical failures; 3 observational mismatches; slot F1 0,9453 |
| V3 shadow | 12 | 24 | precision 0,8684; recall 0,1924; F1 0,3150 |
| Ollama real_llm suite | 23 tests | — | 16 passed, 7 failed, 0 errors, 0 skipped |

Los corpus tienen contratos y denominadores distintos. La media de F1 de diferentes informes no es una métrica global. El scorer shadow inicial mide recuentos y secuencias de etiquetas, pero todavía no demuestra conectividad semántica completa del grafo.

## 2.1 Scorer graph-aware y corpus complementario (PR #293 + primera fase #294)

La PR #293 añade un scorer dedicado al grafo semántico completo y un corpus
graph-gold v1 de 20 escenarios adicionales. Se conserva sin cambios el
corpus shadow v1 de 12 escenarios; ambos son holdouts complementarios con
contratos y métricas distintos y no se deben sumar como si compartieran gold.

El nuevo scorer:
- Alinea nodos por firma semántica y spans exactos, no por local IDs del LLM.
- Puntúa actos, eventos, hechos, enlaces y aclaraciones por separado.
- Puntúa edges de evento→acto, hecho→acto, discourse-link con endpoints y
  clarification→affected-records después de alinear los nodos.
- Detecta argumento/rol ligado al evento incorrecto y links con endpoints
  invertidos aunque las etiquetas de nodo coincidan.
- Devuelve IDs de escenario, contadores y nombres de componentes discrepantes,
  nunca el texto de entrada, menciones, predicados ni prompts.

La primera entrega de #294 queda **parcialmente incluida en #293**: 20 nuevos
escenarios graph-gold cubren acciones, citas, condicionales, callback,
relaciones, atributos, transferencia, incertidumbre, reportes y aclaraciones.
No se afirma que el objetivo de 100–300 escenarios esté completado; la
ampliación se hará tras estudiar la distribución real de errores y revisar
el gold. El nuevo holdout live es opt-in para no alargar por defecto cada
ejecución de la suite real.

Detalles, esquema de anotación y comandos: [Scorer y corpus v3 graph-aware
— 2026-11-21](v3-graph-evaluation-and-corpus-2026-11-21.md).

## 3. Fallos a conservar como escenarios de regresión

1. Hecho nuevo explícito de NPC existente: preservar una cicatriz visible sin duplicar NPC ni perder notas anteriores.
2. NPC nuevo: entidad creada una sola vez y con entity_type no vacío y correcto.
3. Acción compuesta: persistir el hecho independiente confirmado aunque un intento mecánico posterior falle.
4. Citas no confiables: contenido citado no se convierte en orden del jugador ni en hecho.
5. Diálogo atribuido: distinguir «Aldric me advierte: ...» de un reporte genérico.
6. Callback: «Retomando lo de la pared...» es un link discursivo, no un evento/acción.
7. Condición: una consecuencia futura solo se desbloquea tras éxito autoritativo.
8. Transferencia: recipient no implica ownership o possession.
9. Relación de parentesco: dirección, predicado, familia y evidencia deben ser exactos.
10. Negación y rechazo: no querer actuar no equivale a intentar y fallar.
11. Incertidumbre: no convertir «no sé si...» en un hecho afirmado.
12. Varios hablantes: speaker, agent, addressee y attributed_source deben ser independientes.
13. Referente ambiguo: abstención/clarificación antes de adjudicar o persistir.
14. Secuencias independientes: no descartar automáticamente una acción independiente posterior por el fallo de otra.
15. Recuperación: retry técnico conserva idempotencia; no se confunde con resultado mecánico FAILURE.

Los fixtures actuales deben seguir siendo históricos e inmutables cuando documentan una evaluación anterior. Los nuevos escenarios se agregan a versiones nuevas del corpus.

## 4. Corpus v3 objetivo

Construir un corpus inicial de 100–300 escenarios anotados y ampliar progresivamente a partir de fallos reales anonimizados o reescritos. El tamaño no es un objetivo de vanity: cada caso debe cubrir un fenómeno, contar con gold consistente y tener una razón explícita para estar en el conjunto.

### Familias mínimas

| Familia | Variaciones obligatorias |
|---|---|
| Speech acts | Afirmar, preguntar, hablar en personaje, advertir, solicitar, rechazar, corregir, hipotetizar, reportar |
| Multi-actor | Jugador, NPC visible, NPC no resuelto, terceros, varios hablantes |
| Event frames | Movimiento, percepción, interacción, combate, comunicación, transferencia, creación, cambio de estado |
| Argument roles | Agent, patient/theme, recipient, source, destination, instrument, location/path, beneficiary, experiencer, cause/result |
| Discourse | Before/after, continuation, condition_on_success, response_to, correction_of, elaboration, contrast, reports, quotes, callback |
| Epistemic | Asserted, observed, reported, rumour, hypothetical, uncertain, not_established |
| Action phase | Planned, attempted, ongoing, completed, state, not_applicable, unknown |
| Negation | Scope sobre predicado, actor, deseo, evento completo y condición |
| Temporalidad | Permanente, temporal, previa, futura, simultánea, indefinida |
| Relaciones | Kinship, ownership, membership, friendship, hostility, location, dirección y simetría |
| Hechos de entidad | Marcas visibles, rasgos, ocupación explícita, atributos persistentes y no persistentes |
| Correcciones | Pronombre, destinatario, objeto, relación, referencia, paso pendiente |
| Referencias | Nombre, alias, pronombre, demostrativo, grupo, larga distancia, colisión/ambigüedad |
| Contexto | Topic shift, callback, elipsis, mismo chat, chat diferente, contexto ausente |
| Adversariales | Instrucción citada, contenido malicioso reportado, narración con nombres, negación dentro de cita |

### Variación lingüística

Los escenarios no deben ser simples sustituciones de nombres. Incluir orden de constituyentes variable, tiempos y conjugaciones, pronombres/clíticos, sujetos omitidos, sinónimos y paráfrasis, frases coloquiales y elípticas, puntuación y comillas distintas, y variación del orden de cláusulas cuando la semántica lo permita.

El primer corpus debe ser español-first por el uso actual. El trabajo multilingüe se evalúa en fase posterior y no debe mezclarse para ocultar una regresión española.

## 5. Diseño del gold y control de leakage

Cada escenario debe tener ID/familia, texto de entrada y contexto mínimo reproducible, actos esperados, eventos esperados con argumentos/roles/estatus/fase/temporalidad, enlaces con extremos, candidatos de hechos y elegibilidad, spans de evidencia, referencias históricas y candidatas visibles, acción elegible o abstención, operaciones esperadas/prohibidas, severidad critical/observational y notas de anotación.

Reglas:
1. Mantener train/development/held-out separados.
2. No copiar frases held-out literalmente al prompt.
3. La inclusión de una familia en el prompt debe ser general y contrastiva; el texto exacto del escenario no.
4. Mantener origen y fecha de cada fixture.
5. Resolver discrepancias de gold con revisión independiente antes de cambiar aserciones.
6. No cambiar gold para coincidir con la salida observada.
7. Comprobar discrepancias predicado de superficie vs. predicado normalizado; no mezclar ambas convenciones.
8. Mantener pruebas deterministas y live separadas.

## 6. Métricas necesarias

### 6.1 Métricas de nodos

- Act detection precision/recall/F1.
- Event detection precision/recall/F1.
- Predicate exact accuracy y canonical-family accuracy.
- Argument mention F1.
- Argument-role pair F1.
- Speaker/addressee/source attribution accuracy.
- Polarity, epistemic status, action phase y temporal-scope accuracy.
- Clarification kind/missing-slot accuracy.

### 6.2 Métricas de aristas y grafos

- Discourse-link precision/recall/F1.
- Link endpoint exact accuracy.
- Conditional dependency exact accuracy.
- Relation endpoint/direction accuracy.
- Source-act/event linkage accuracy.
- Cycle/forward-link invalidity rate.
- Exact semantic graph match por escenario.
- Partial graph match por escenario y dimensión.

El scorer debe alinear nodos de manera reproducible antes de puntuar aristas. La alineación no puede depender de IDs locales generados por el modelo, porque son arbitrarios. Utilizar evidencia, orden, tipos de nodo y predicados como señales de correspondencia; publicar el algoritmo y probarlo con casos simétricos/ambiguos. Los extremos de relaciones y enlaces se puntúan después de establecer el mapeo de nodos.

No contar etiquetas como multiset y asumir que eso prueba que están unidas al nodo correcto. El multiset puede seguir publicándose como métrica secundaria.

### 6.3 Evidencia y autoridad

- Evidence span alignment accuracy.
- Evidence coverage por campo.
- Ungrounded field rate.
- Quote-span containment.
- History-to-current-evidence leakage rate.
- Canonical reference exact resolution accuracy.
- Correct abstention rate.
- False authorization rate para acciones.

### 6.4 Métricas de acciones y mundo

- Action candidate precision/recall.
- Action selection exact accuracy.
- Dependency-unlock correctness.
- Confirmed-step preservation.
- Fact eligibility precision/recall.
- False persistent changes por familia.
- Fact independence/preservation.
- Idempotency/recovery correctness.
- Exact operations match y world-state delta match.

### 6.5 Métricas de operación

- Schema validity.
- Provider/decoder error rate.
- Repetition stability en casos críticos.
- Prompt bytes y tokens reales.
- Completion tokens.
- Duration y provider eval duration.
- Calls por escenario.
- Timeout rate.
- Context section reduction y sección eliminada.
- Model digest, Ollama version y generation options.

## 7. Evaluación de grafo exacto

El evaluador compara significado estructurado, no solo arrays de etiquetas.

Un escenario pasa exactamente solo cuando los actos esperados están presentes sin extras críticos; cada evento corresponde a la cláusula/fuente correcta; los argumentos y roles están asociados al evento correcto; speaker, agent, addressee y attributed source están diferenciados; cada enlace apunta a los nodos esperados; las condiciones tienen el antecedente correcto; las relaciones tienen sujeto, objeto y dirección correctos; los spans sustentan cada elemento; y no hay hechos o acciones extras que alteren autoridad.

El escenario también informa fallos parciales para diagnóstico. Las etiquetas sueltas pueden tener F1 alto mientras el grafo completo falla; ambos resultados deben quedar visibles.

## 8. Gates de aceptación

Los umbrales finales serán aprobados en PR #296 después de validar scorer/gold y disponer de resultados de PR #293–#295. Los siguientes son mínimos de diseño, no valores ya aprobados:

| Gate | Criterio |
|---|---|
| V3 schema validity | 100 % en escenarios críticos del set de aceptación |
| Evidence grounding | Sin spans/campos críticos no respaldados |
| Critical persistent false positives | 0 |
| Quoted/untrusted instruction controls | 0 escrituras y 0 selección de acción no autorizada |
| Graph exact match | Métrica publicada por familia; umbral explícito antes de promoción |
| Precision y recall | Threshold independiente por dimensión; recall no puede quedar bajo por precision alta |
| Action selection | Exactitud crítica y dependencias bloqueadas correctamente |
| Fact policy | Hechos válidos no perdidos; hechos no elegibles no escritos |
| Stability | Repeticiones de cada caso crítico y sin divergencia peligrosa |
| SillyTavern | Checklist manual real, con artefacto de aceptación, no inferido desde CI |

No promover un modelo con recall v3 cercano a 0,19. No reducir seguridad para conseguir más recall. Si el modelo no puede recuperar una estructura de forma fiable, mejorar prompt/representación, aclarar una ambigüedad o abstenerse sin ejecutar acciones peligrosas.

## 9. Perfiles de ejecución

### Quick diagnostic
Uno o pocos escenarios filtrados, repeticiones configurables, reporte por campo y grafo. Feedback rápido, no sustituye acceptance.

### Full NLU evaluation
Todos los corpus held-out, configuración/modelo congelados, repeticiones de casos críticos, reportes individuales y consolidados. Ejecutado antes de integrar cambios semánticos.

### Acceptance evaluation
Baseline v2/v3 pareada, modelo/configuración/prompt/schema congelados, controles críticos y grafo completo, operaciones/cambios de mundo en fixtures aislados, live Ollama y manual SillyTavern posterior a gates previos.

No paralelizar calls al mismo daemon de forma que altere latencia, carga de modelo o resultados sin medirlo/documentarlo.

## 10. Artefactos del run

Conservar summary JSON/Markdown, JUnit, identidad de commit, model digest, versión Ollama, generation options, prompt/schema version IDs y fingerprints estáticos, métricas por familia/escenario, duración/tokens, errores de validación con códigos/campos seguros.

No conservar en el aggregate texto íntegro del jugador, prompts/completions, contexto de campaña, secretos ni IDs canónicos innecesarios. Los logs locales de debug tienen controles de acceso y retención separados, pero no son reportes compartibles.

## 11. PR responsables

- PR #293: scorer graph-aware, diagnóstico por caso, métricas exact graph match y evaluación live opt-in. Incluye la primera tanda de 20 escenarios graph-gold que originalmente estaba planificada como una entrega separada de corpus.
- La expansión restante del corpus hasta 100–300 escenarios sigue pendiente. Debe basarse en errores reales y revisión de gold; no se debe fabricar volumen con permutaciones triviales.
- PR #294: rediseño del prompt v3 para aumentar la cobertura de cláusulas/proposiciones, más alineación conservadora de spans exactos y telemetría explícita del proceso.
- PR #295: validación de consistencia semántica en el decoder v3: evidencia contenida en el acto origen, edges `quotes`/`condition_on_success`/`before_after`, duplicados, referencias y grounding de aclaraciones.
- PR #296: gate de aceptación y ablations controladas antes de cualquier promoción.

La numeración anterior era una secuencia propuesta. La primera entrega de corpus se integró en #293 y no consumió un número real de GitHub; por eso el hito de prompt se entrega como la PR real #294. Ver [roadmap maestro](../architecture/player-understanding-roadmap-2026-11-21.md) para estado por PR. Toda PR debe actualizar dicho ledger antes de merge.
