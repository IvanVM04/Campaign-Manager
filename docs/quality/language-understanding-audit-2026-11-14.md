# Auditoría independiente — comprensión del lenguaje natural y acciones de IA

**Fecha:** 2026-11-14  
**Baseline auditado:** merge de PR #223, `7f4f8b10a072665471370fab4493a338835b875c`  
**Repositorio:** [IvanVM04/Campaign-Manager](https://github.com/IvanVM04/Campaign-Manager)  
**Alcance:** PRs #210–#223, flujo de interpretación/adjudicación/propuestas, recuperación de referencias, continuidad, evaluación y documentación relacionada.

> Esta auditoría distingue código integrado, pruebas deterministas, evaluación con modelo real y aceptación en SillyTavern. No considera una descripción de PR ni un documento anterior como evidencia suficiente de que una capacidad funciona.

## 1. Dictamen ejecutivo

La base técnica es sólida y ha evolucionado más allá de un sistema de prompts: hay una interpretación compartida y tipada, evidencia literal, referencias resueltas por código, separación de fuentes, control de visibilidad, operaciones no confiables, persistencia durable y un corpus de evaluación separado.

**No hay evidencia suficiente para declarar que el modelo ya entiende de forma fiable todas las acciones expresadas en lenguaje natural.** A fecha de esta auditoría, el principal déficit no es la ausencia de otra capa de prompts: es la falta de resultados reproducibles de calidad con el modelo real y la falta de pruebas de extremo a extremo con SillyTavern que demuestren que las señales lingüísticas llegan completas al modelo y producen las consecuencias correctas.

La PR #223 está fusionada. Sus workflows finales de Tests y CodeQL concluyeron correctamente. El job de tests ejecutó 1.774 tests deterministas, excluyó 15 tests `real_llm` y alcanzó 85,31% de cobertura combinada (88,8% de líneas y 75,8% de ramas). Es evidencia de calidad de software y contratos, no de precisión semántica del modelo.

### Evaluación de madurez — estimación de auditoría, no métrica observada

| Dimensión | Madurez estimada | Interpretación |
|---|---:|---|
| Autoridad, validación y seguridad de operaciones | 90% | Límites fuertes; todavía requieren validación de escenarios adversariales end-to-end |
| Representación de intención y acciones | 80% | Contratos v1/v2 ricos; la extracción del modelo no está medida en ejecución real |
| Recuperación de entidades y objetos tipados | 80% | Resolutores deterministas, evidencia y abstención; cobertura lingüística limitada |
| Continuidad y discurso | 65% | PR #223 amplía el alcance, pero usa reglas explícitas y ventana acotada |
| Evaluación automatizada | 75% | Corpus/ledger/harness existentes; falta un baseline live completo y reproducible |
| Calidad real del modelo demostrada | 10% | No se ha acreditado aquí una ejecución live completa con resultados por familia |
| Aceptación real SillyTavern | 0% acreditado | No se ha aportado una ejecución manual reproducible en esta auditoría |

No debe calcularse un promedio de estas cifras ni presentarlo como «el modelo entiende el X%». Son estimaciones de madurez de ingeniería para priorizar trabajo. **La precisión real del modelo sigue siendo desconocida hasta ejecutar y publicar el protocolo live.**

## 2. Evidencia y método

Se revisaron los metadatos y descripciones de las PR #210–#223, los cambios de código de #215–#223, los contratos actuales de interpretación, los resolutores, el constructor discursivo, los prompts, los fixtures de evaluación, las guías de aceptación y los workflows de #223.

Se verificó expresamente:

- #210–#223 constan como fusionadas; #223 se integró el 2026-11-14.
- El merge commit de #223 es `7f4f8b10a072665471370fab4493a338835b875c`.
- Los workflows finales de Tests y CodeQL asociados al head de #223 terminaron con `success`.
- El job de tests registró 1.774 pasados, 15 excluidos y 85,31% de cobertura combinada.
- Los 15 excluidos corresponden a la separación de pruebas live; no se interpretan como 15 éxitos.
- El código de #223 incluye pruebas deterministas para el índice discursivo, resolutores y prompt. No añade una nueva batería live que mida específicamente las nuevas capacidades discursivas.

**Limitación:** esta auditoría de GitHub no ejecutó el repositorio en un entorno local, no llamó a Ollama y no operó una sesión real de SillyTavern. No se ha inferido el contenido de ejecuciones live a partir de tests verdes ni de afirmaciones de documentación.

## 3. Evolución auditada de las PR

| PR | Aportación real | Evaluación independiente |
|---|---|---|
| #210 | Más evidencia del mundo en el contexto, reglas de propuesta y controles positivos/negativos | Cambio importante de información disponible. Los probes live son opt-in, no una aceptación automática |
| #211 | Alias persistentes y resolución determinista de entidades | Reduce duplicados y ambigüedad; no resuelve por sí sola paráfrasis libre ni correferencia |
| #212 | Consultas separadas, recuperación multi-señal y endurecimiento del adaptador | Mejora recuperación; no prueba que los candidatos recuperados sean siempre los correctos |
| #213 | Reglas explícitas de modalidad, negación, hipótesis, preguntas y acciones compuestas | Mejora el contrato; las pruebas de prompt no equivalen a comprensión del modelo |
| #214 | Procedencia, perspectiva del personaje, privacidad y grounding narrativo | Base de seguridad esencial; necesita pruebas de integración sobre cada camino de lectura |
| #215 | Interpretación compartida `PlayerIntentAnalysis`, evidencia y persistencia durable | Elimina interpretaciones independientes entre adjudicación y consecuencias |
| #216 | Aislamiento por chat, referencias conversacionales limitadas y schema estructurado de Ollama | Correcto como arquitectura; no es coreferencia general |
| #217 | Sincronización documental y roadmap de marcos semánticos | No aporta capacidad runtime |
| #218 | Marcos de acción v2 y relaciones dirigidas con roles tipados | Mejora la representación; no demuestra que el LLM rellene bien todos los roles |
| #219 | Evidencia discursiva, ranking de candidatos, abstención y primitiva de corrección | Mejora el resolvedor; la corrección automática todavía necesitaba integración |
| #220 | 110 escenarios, 60 held-out y métricas por familia | Excelente base de evaluación; corpus y ledger no son resultados de modelo |
| #221 | Corrección emitida por el modelo durante aclaraciones pendientes, validación literal y auditoría durable | Cierra el enlace de corrección, con límites de slot y estado |
| #222 | Referencias tipadas a definición/instancia de objeto, recursos y eventos; métricas que penalizan extras | Cierra namespaces importantes; aún debe medirse con Ollama |
| #223 | Índice discursivo, doce turnos, cambios/callbacks explícitos, elipsis, concordancia local y hablantes NPC etiquetados | Integrada y con CI verde; sin evidencia live específica que cierre su calidad |

La secuencia ha sido coherente. El riesgo sería seguir encadenando mejoras semánticas sin detenerse a medir el sistema integrado contra una referencia estable.

## 4. Arquitectura existente y recorrido efectivo

El recorrido previsto y conectado es:

1. Se conserva la entrada literal del jugador, la identidad durable y el ámbito de conversación.
2. Se obtiene historial reciente del chat y contexto de mundo visible para el personaje.
3. `MechanicsAdjudicator.understand()` genera una interpretación estructurada y una decisión mecánica en una llamada normal.
4. Los resolutores deterministas contrastan menciones con entidades y registros tipados visibles; la ambigüedad puede provocar aclaración.
5. La misma interpretación se entrega a la propuesta de consecuencias. El modelo no debería reinterpretar la acción de manera independiente.
6. El parser y el dominio validan las operaciones propuestas; la autoridad mecánica sigue en el motor determinista.
7. Las consecuencias se confirman por el flujo durable y la narración se genera desde el resultado comprometido.
8. Aclaraciones y correcciones se limitan a resoluciones pendientes; las tiradas manuales reutilizan la interpretación persistida.

Esta separación es un punto fuerte. Debe preservarse: no añadir otra llamada LLM normal, una memoria paralela o una base vectorial sin demostrar que el baseline actual no alcanza los objetivos.

## 5. Hallazgos técnicos: qué funciona y qué no está demostrado

### F-01 — Interpretación compartida y evidencia tipada

**Estado: implementado; calidad live no demostrada.**

V1 conserva modalidad, polaridad, orden, actor, resultado reportado y menciones literales. V2 añade predicados, familias de acción, roles (agente, paciente, destinatario, origen, destino, instrumento, etc.) y claims de relación dirigidos con modalidad, polaridad, atribución y evidencia.

La validación rechaza campos desconocidos, IDs canónicos del modelo, referencias no literales y estructuras inválidas. El codec conserva compatibilidad con registros v1.

**Riesgo residual:** una salida puede ser estructuralmente válida y semánticamente incorrecta. Hay que medir argumentos omitidos, argumentos extra, roles intercambiados, relaciones invertidas y afirmaciones no justificadas, no solo parseabilidad.

### F-02 — Recuperación tipada y namespaces

**Estado: implementado; cobertura real parcial.**

La resolución diferencia entidades, definiciones de objetos, instancias físicas, recursos y eventos. Las instancias inactivas y eventos no visibles se excluyen; varias copias físicas pueden producir abstención. La resolución no entrega al modelo autoridad de escritura.

**Riesgo residual:** alias y coincidencia léxica no equivalen a comprensión de paráfrasis. Deben medirse falsos enlaces, referencias nuevas confundidas con existentes, y abstenciones incorrectas por categoría y tipo de objeto.

### F-03 — Continuidad discursiva de PR #223

**Estado: implementado con reglas acotadas; no es comprensión discursiva general.**

`DiscourseContextBuilder` limita el historial a doce turnos, detecta marcadores explícitos de cambio de tema y reactivación, marca frases elípticas, extrae algunas citas NPC con etiqueta explícita y usa concordancia gramatical local cuando existe artículo/aposición literal.

Límites deliberados y correctos:
- No deduce género a partir de nombres propios.
- No convierte pronombres plurales en una persona individual.
- No atribuye diálogo a un NPC sin una etiqueta inequívoca y visible.
- No trata las citas como instrucciones del jugador.
- Un callback permite consultar el historial acotado, pero no debe saltarse el umbral de ambigüedad.

**Riesgos residuales observados en el diseño:**
- El cambio de tema depende de una lista de marcadores explícitos; los cambios implícitos no quedan resueltos.
- La ventana de doce turnos es un límite de recencia, no una memoria semántica de toda la campaña. Un antecedente relevante puede quedar fuera.
- La señal discursiva renderizada tiene un máximo de 650 caracteres. En adjudicación se compacta a una fracción del presupuesto de contexto; en propuestas se elimina antes que otras secciones cuando falta presupuesto. Por diseño, el índice puede no llegar al modelo en prompts ajustados.
- El índice de elipsis marca una posibilidad y da una instrucción; no es un parser completo de elipsis ni demuestra que la acción antecedente siga pendiente.
- La atribución NPC cubre formatos de cita explícitos reconocidos por patrones. No representa turnos de diálogo arbitrarios, diálogos sin etiqueta ni una estructura completa de conversación.
- La concordancia cubre formas locales incluidas en listas y patrones; no es análisis morfosintáctico general, ni resuelve grupos.
- La segmentación depende de texto de jugador y narrador. Hay que comprobar que un marcador citado o incidental no produzca un cambio de tema falso.

**Acción requerida:** añadir pruebas held-out y live que midan tanto el acierto como el falso positivo de cada regla, además de verificar si la señal discursiva sobrevivió al presupuesto del prompt.

### F-04 — Evaluación de modelo: corpus no equivale a benchmark ejecutado

**Estado: infraestructura implementada; baseline live pendiente de acreditación.**

El corpus #220 declara 110 casos: 50 de desarrollo y 60 held-out. Incluye familias de intención, marcos/relaciones y referencias. El ledger contempla precisión/recall/F1 de slots, abstenciones, contexto, operaciones, cambios persistentes falsos, secretos y latencia.

Sin embargo:
- No hay en la evidencia revisada un informe live completo con todos los casos, repeticiones, resultados por familia y digest del modelo.
- Los casos held-out no miden todas las capacidades añadidas por #223.
- El documento de evaluación todavía describe algunos límites anteriores (por ejemplo, seis turnos) y no está sincronizado con la nueva ventana de doce.
- El test de operaciones tiene controles útiles, pero un conjunto pequeño de escenarios no representa todas las acciones del juego.
- La métrica de interpretación debe complementarse con evaluación de la consecuencia final y del estado persistido.

### F-05 — Presupuesto y pérdida de señales

**Estado: riesgo concreto del diseño; requiere medición.**

El adjudicador limita el bloque discursivo a `max_context_tokens // 24`. El constructor de propuestas elimina expresamente el índice discursivo si el prompt excede el presupuesto. Esto protege la longitud del prompt, pero puede eliminar justo la señal que #223 pretende aportar.

No debe asumirse que «ventana de 12 turnos» significa «12 turnos entendidos por el modelo». Hay que registrar, sin almacenar contenido sensible, cuántos turnos y qué tipos de señales se seleccionaron, compactaron o descartaron. La prioridad de truncado debe conservar evidencia crítica de la acción actual y antecedentes resueltos, no solo los últimos caracteres.

### F-06 — SillyTavern y recorrido de extremo a extremo

**Estado: contratos automatizados; aceptación manual no acreditada.**

Los tests API/adaptador/JavaScript protegen contratos y aislamiento. No sustituyen una sesión real con dos chats, diálogos NPC, cambios de tema, aclaraciones y reinicios.

La aceptación debe comprobar la cadena completa: historial real → adaptador → interpretación → resolutores → propuesta → operación validada → persistencia → narración/swipes/reintento. Una prueba unitaria del resolutor no demuestra que la extensión envíe el historial correcto ni que el backend lo limite al chat correcto.

### F-07 — Documentación desincronizada

**Estado: defecto documental confirmado.**

Se encontraron documentos que todavía:
- identificaban #222 como trabajo activo aunque está fusionada;
- describían seis turnos después de que #223 ampliara el límite a doce;
- presentaban #223 como trabajo futuro o activo aunque ya se fusionó;
- mantenían descripciones de gramática y NPC previas a #223.

La documentación histórica debe conservar su contexto temporal. Los índices y documentos activos deben describir el estado actual y enlazar este informe como fuente de auditoría.

## 6. Matriz de capacidades y trabajo pendiente

| Capacidad | Situación actual | Trabajo para un nivel robusto |
|---|---|---|
| Abrir/cerrar, coger/dejar, mover, transferir, equipar, usar | Roles tipados y operaciones existentes | Matriz por acción, objeto y estado; origen/destino y éxito/fallo |
| Ataques, checks, daño y estados | Autoridad mecánica determinista | Evaluar intención de acción, objetivo, condiciones y no duplicar mecánicas |
| Hablar, preguntar, persuadir, informar | Categorías y relaciones atribuidas | Diálogo multi-turno, hablante, destinatario, citas, discurso indirecto |
| Observar, descubrir, investigar | Eventos/procedencia y contexto | Distinguir observación, inferencia, descubrimiento y verdad canónica |
| Negar, cancelar, fallar, cambiar de idea | Modalidad/polaridad y reglas de prompt | Negación en subordinadas, autocorrecciones y cancelación de pasos compuestos |
| Acciones compuestas | Pasos ordenados y paso activo | Dependencias, interrupciones, fallo parcial, reanudación y acciones futuras |
| Pronombres y deixis | Resolución determinista limitada | Grupos, referencias ambiguas, objetos repetidos y referentes fuera de ventana |
| Elipsis e instrucciones persistentes | Señales de #223 | «hazlo», «igual que antes», «continúa» con estado de tarea pendiente verificable |
| Cambios de tema | Marcadores explícitos | Cambios implícitos, temas paralelos y callbacks con antecedente único |
| Tiempo y causalidad | Expresiones temporales literales | Intervalos, antes/después, duración, caducidad y causa/efecto |
| Idiomas | Corpus Spanish-first con controles en inglés | Variantes naturales, morfología, errores, sinónimos y evaluación multilingüe |
| Seguridad de operaciones | Parser/dominio y autoridad separada | Ataques de prompt injection, citas, texto importado, contradicciones y falsos positivos |

La tabla no afirma que todas las acciones del juego estén ya cubiertas por una misma API. Cada operación soportada debe vincularse con una familia de lenguaje y con su contrato de dominio.

## 7. Plan priorizado y estimación de esfuerzo

Las horas son estimaciones de ingeniería para una persona que conoce el repositorio, no compromisos ni tiempo ya invertido. Incluyen implementación, pruebas y revisión; no incluyen tiempos de espera del proveedor ni hardware.

| Fase | Entrega | Horas estimadas | Prioridad |
|---|---|---:|---|
| A | Ejecutar baseline live de los 110 casos y guardar informe reproducible | 8–14 h | P0 |
| B | Diagnosticar fallos por familia y corregir regresiones críticas | 12–24 h | P0 |
| C | Ampliar held-out para capacidades #223: elipsis, temas, NPC, gramática y referencias lejanas | 12–20 h | P0 |
| D | Medir pérdida por presupuesto/truncado y mejorar diagnósticos de contexto | 8–14 h | P0 |
| E | Aceptación real SillyTavern de dos chats, aclaraciones, reintentos y reinicios | 8–14 h | P0 |
| F | Matriz de acciones completa con controles positivos, negativos y compuestos | 20–32 h | P1 |
| G | Diálogo, temporalidad, causalidad, grupos y cambios implícitos de tema | 24–44 h | P1 |
| H | Robustez lingüística y adversarial en español natural y controles en inglés | 16–28 h | P1 |
| I | Revisión final, documentación de resultados y gates de release | 6–10 h | P0/P1 |

**Totales orientativos:**
- Cierre de P0 y aceptación de la base actual (A–E, I): **54–96 horas**.
- Robustez funcional ampliada (F–H): **60–104 horas adicionales**.
- Programa total estimado: **114–200 horas**.

Si el baseline live revela fallos críticos, la fase B puede crecer. No conviene fijar un número cerrado antes de observar el modelo real.

## 8. Criterios de aceptación propuestos

No fijar un «90% de comprensión» agregado. Un promedio puede esconder una familia rota y confundir omisiones con escrituras falsas.

### Hard gates
- Cero cambios persistentes falsos en los negativos críticos ejecutados.
- Cero filtraciones de eventos o datos no visibles.
- Cero transferencias, ataques, cambios de propiedad o creación de entidades por inferencia no respaldada.
- Cero cruces de historial entre chats.
- Cero aplicación de correcciones sobre resoluciones comprometidas o evidencia no literal.
- Toda abstención/clarificación debe ser recuperable y no dejar leases bloqueados.

### Métricas por familia
- Intent category y modalidad.
- Actor, paciente, destinatario, origen, destino e instrumento.
- Precisión, recall y F1 de argumentos y relaciones.
- Resolución de identidad y precisión de abstención.
- Recuperación de contexto obligatorio y contexto irrelevante.
- Operaciones correctas, omitidas, duplicadas y falsas.
- Exactitud de referencia a turnos anteriores y cambios de tema.
- Latencia, tokens estimados, llamadas, retries y compactación.

### Protocolo live
- Fijar modelo, digest, versión de Ollama, parámetros, timeout, hardware y SHA.
- Ejecutar el corpus held-out intacto; nunca convertir fallos en ejemplos de prompt antes de cerrar la medición.
- Repetir al menos tres veces los negativos y casos críticos.
- Guardar por escenario resultado, métrica, latencia y error clasificado.
- Comparar baseline y candidato con el mismo corpus y configuración.
- Ejecutar después el checklist real de SillyTavern, no antes de tener controlados los falsos positivos críticos.

## 9. Secuencia recomendada

1. No abrir otra gran PR semántica todavía.
2. Completar el baseline Ollama actual con los fixtures #220, pruebas de corrección y operaciones.
3. Crear un informe de resultados por familia, conservando todos los fallos.
4. Añadir un hold-out específico de #223 y comprobar pérdida por presupuesto.
5. Corregir primero falsos positivos críticos; después recall y fluidez.
6. Ejecutar aceptación SillyTavern con dos chats y continuidad real.
7. Solo entonces decidir si hacen falta nuevas reglas, cambios en retrieval, otra representación o modelos distintos.

## 10. Conclusión

Campaign Manager ya tiene una arquitectura seria para interpretar lenguaje natural con límites de autoridad y evidencia. Lo que todavía no tiene demostrado es que esa arquitectura, con el modelo y configuración reales, comprenda de forma consistente la variedad de acciones y conversaciones que se esperan en una campaña.

La prioridad ya no debería ser añadir complejidad por intuición. Debe ser medir el comportamiento, identificar los fallos reales y corregirlos con pruebas que no se puedan aprobar simplemente repitiendo el prompt esperado.

**La fase P0 no se considera cerrada hasta que existan resultados live reproducibles y una aceptación real de SillyTavern.**
