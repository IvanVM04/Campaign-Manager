# Auditoría actual y hoja de ruta de calidad

**Fecha:** 2026-11-18  
**Baseline de código:** `main` — `f4fb3914ebab4579118863796e6f6d4b7183d0cf` (última PR con cambios de producción: #255).  
**Baseline documental:** `main` — `4a3a2549bb0bb1bc38ec0e6f456ac6d5ccef24d1` (PR #257 fusionada).  
**Tipo:** auditoría documental y priorización; no sustituye la prueba local con Ollama/SillyTavern. La expansión de requisitos v0.2 de esta rama no implica que esas capacidades estén implementadas.

## 1. Resumen ejecutivo

La recomendación es **no abrir otra fase de refactorización arquitectónica amplia**. La aplicación ya tiene un monolito modular razonablemente separado: campañas, personajes, combate, contexto, proveedores, interpretación/propuesta LLM, turnos durables y aplicación del mundo. Hay una composición central y límites explícitos para reglas, persistencia y autoridad.

El principal riesgo de producto ahora no es la forma de los paquetes: es la diferencia entre:

- que el backend acepte/valide correctamente una estructura;
- que el modelo interprete correctamente un mensaje real;
- que el flujo completo funcione en una conversación real de SillyTavern.

La estrategia debe ser **medir → localizar errores → corregir una familia → volver a medir**, sin introducir complejidad antes de tener evidencia.

### Decisiones

1. Mantener la arquitectura modular actual.
2. No hacer tuning amplio de prompts sin un baseline live comparable.
3. Mantener las fronteras de evidencia, visibilidad, reglas y escritura.
4. Priorizar la evaluación reproducible de modelo y la aceptación integral.
5. Cerrar los riesgos de fiabilidad de los caminos críticos y completar un vertical slice jugable.
6. Diseñar la interfaz propia cuando los contratos y workflows de backend sean sólidos; SillyTavern seguirá siendo un cliente de integración, pero no el único camino de aceptación del producto.
7. Tratar el control multi-PJ, la delegación de NPC, las aclaraciones recuperables, la visibilidad configurable y los módulos de reglas como capacidades de dominio que requieren contratos propios antes de construir la UX.

## 2. Baseline verificado

### 2.1 GitHub y CI

PR [#255](https://github.com/IvanVM04/Campaign-Manager/pull/255) está fusionada en `main` desde el 2026-11-18.

| Check | Resultado observado |
|---|---|
| Python determinista | **2042 passed, 22 deselected** |
| Cobertura combinada | **85,14 %** (gate configurado: 85 %) |
| Ruff | Correcto |
| Tests JavaScript | Correctos |
| Pyright obligatorio (models/rules_engine/bootstrap/operations) | Correcto |
| Pyright de repositorio | Correcto |
| CI summary | Correcto |
| CodeQL Python + JavaScript | Correcto |

Evidencia más reciente: [Tests run #44270598043](https://github.com/IvanVM04/Campaign-Manager/actions/runs/44270598043) y [CodeQL run #44270598070](https://github.com/IvanVM04/Campaign-Manager/actions/runs/44270598070), ambos sobre el commit documental `4a3a2549...` posterior a PR #257. El job de tests informa 2.042 passed, 22 deselected y 85,14 % combinado; Ruff, ambos Pyright, JavaScript y CI summary pasan. CodeQL completa correctamente. Los 22 tests deseleccionados son `real_llm`: CI no inicia Ollama ni certifica la calidad del modelo. Tampoco certifica una sesión real de SillyTavern.

La cobertura combinada está apenas por encima del mínimo. La línea de cobertura es alta, pero la cobertura de ramas global es menor; no se recomienda perseguir un porcentaje arbitrario. Se deben priorizar ramas de riesgo: rollback/commit, fencing y recuperación, revisión de campaña, errores de proveedor, clarificaciones, tiradas manuales, visibilidad y conflictos de identidad.

### 2.2 Inventario de evaluación de lenguaje

El repositorio dispone de:

- 138 escenarios en los corpora base de lenguaje, semantic frames, referencias y pipeline/discurso (50 de desarrollo y 88 held-out, según el inventario existente).
- 14 escenarios adicionales de intención compuesta, en un holdout separado y con gold independiente por paso.
- Un sidecar independiente para medir predicados de acción/relación sobre los IDs del corpus semántico, sin copiar los textos originales.
- Evaluadores live separados para interpretación semántica, discurso, mecánicas, operaciones, pipeline compuesto y uso del proveedor.

El tamaño del corpus es una buena base de ingeniería, pero no equivale a una certificación general del español ni a comprensión humana. Los casos críticos, las métricas por familia y los falsos positivos deben mantenerse visibles.

## 3. Hallazgos priorizados

### QF-01 — Falta un baseline live posterior a las últimas mejoras (P0)

**Evidencia:** PRs #250 y #253 ampliaron la evaluación de predicados y añadieron normalización superficial basada en patrones claros. PR #255 amplió señales discursivas y evaluación de mensajes compuestos. El último baseline de predicados documentado es anterior a la intervención semántica #253 y no se puede usar como resultado de la versión actual.

Un run de referencia del 2026-11-17, con Gemma 4 12B Q4_K_M, digest registrado, Ollama 0.40.16 y `think=false`, obtuvo:

- Action predicate surface F1: 0,9714.
- Relation predicate surface F1: 0,2143.
- Semantic slot F1 global: 0,6349.

El informe atribuye la mayor parte del déficit a predicados/claims relacionales, familias y roles de acciones, dirección, polaridad/modalidad, atribución y temporalidad. Esa ejecución es un **baseline histórico de la versión anterior del scorer/intervención**, no una medición de la calidad actual de `main`.

**Acción:** ejecutar el mismo conjunto y configuración sobre el SHA actual y guardar un reporte reproducible. No cambiar el gold para acomodar resultados ni comparar métricas de scorers distintos como si fueran la misma medición.

### QF-02 — Callback, cambio de tema y referencias deben volver a medirse (P0)

Un log compartido del 2026-11-16 registró callback 0 %, topic boundary 25 %, precisión de enlace de entidades 100 % y recall 71,43 %. Es un resultado histórico de una versión anterior. No demuestra que #255 falle ni que lo haya corregido; obliga a repetir los escenarios sobre el código actual.

**Acción:** evaluar separadamente cambio de tema, callback explícito, elipsis, referencia distante, acuerdo local, atribución de NPC, plural y abstención. No aumentar recall a costa de enlaces especulativos.

### QF-03 — Los mensajes de varios pasos tienen contratos deterministas, pero falta evidencia con el modelo (P0)

PR #255 incorporó 14 ejemplos de dos o tres pasos, con gold por actor, modalidad y polaridad. Esto permite detectar omisiones y pasos extra, no solo acertar el primer evento.

**Acción:** ejecutar el holdout completo con repeticiones de los casos críticos y medir categoría global, número de pasos, índice activo, actor, modalidad y polaridad por paso. Revisar también que una negación explícita no se convierta en intento positivo ni en propuesta persistente.

### QF-04 — La integración durable está bien definida, pero necesita aceptación real (P0/P1)

El flujo durable tiene contratos para idempotencia, versiones, clarificaciones, tiradas manuales, commit previo a narración y recuperación. Los tests automatizados protegen muchos casos; la lista manual de SillyTavern sigue siendo un gate separado.

**Acción:** completar el checklist de dos chats, entrega duplicada, regeneración, aclaraciones múltiples, tiradas, recarga/reinicio y recuperación tras fallo de proveedor. Registrar revisiones y configuración exactas.

### QF-05 — La amplitud de D&D está por detrás de la infraestructura (P1)

El backend tiene un subconjunto determinista de 5e 2014, no un rules engine completo. La creación avanzada de personajes, progresión, recursos de clase y hechizos todavía no forman un ciclo jugable completo.

**Acción:** tras cerrar los gates M0, implementar un vertical slice que conecte personaje, equipo, prueba, combate, descanso, recompensa y persistencia. No ampliar reglas de forma aislada sin una aventura concreta que las ejercite.

### QF-06 — La cobertura debe dirigirse por riesgo, no por porcentaje (P1)

El gate de 85 % combinado ya está activo y el último run lo ha superado por poco (85,14 %). Añadir tests indiscriminadamente para elevar el número puede generar ruido.

**Acción:** usar el XML de cobertura por paquete/ramas y el mapa de impacto para proteger especialmente estados transaccionales, reintentos, fencing, revisión de campaña, visibilidad, manual rolls y errores del proveedor. No eliminar asserts ni excluir módulos productivos.

### QF-07 — El límite de seguridad local debe seguir explícito (P1)

La aplicación se diseña para uso local y el servidor documentado escucha en loopback. La selección de campaña no es autenticación. No existe un API GM autenticado que pueda revelar secretos a una persona verificada.

**Acción:** no habilitar binding remoto, túneles ni reverse proxy sin diseñar autenticación, autorización por campaña, protección de secretos y revisión de despliegue. Mantener fail-closed en vistas player-safe.

### QF-08 — Control de personajes y delegación NPC configurables (P1)

La especificación v0.2 exige que una persona pueda controlar uno o varios PJ y cambiar ese conjunto durante la partida. También exige que jugador y DM puedan solicitar control de NPC, pero que la transferencia sea aprobada por la autoridad vigente y registrada.

**Riesgo:** una implementación que modele únicamente un personaje activo o que infiera permisos por el texto de la conversación no podrá soportar estas opciones de forma segura.

**Acción:** definir un contrato explícito de control/delegación por entidad, capacidades, duración, solicitante, aprobador, expiración y revocación. Separar personaje en foco de contexto de conjunto de personajes bajo control. Probar peticiones aceptadas, rechazadas, expiradas, revocadas y reiniciadas.

### QF-09 — Las aclaraciones necesitan progreso durable y señales de incertidumbre (P1)

El requisito v0.2 pide un umbral configurable para preguntar ante dudas y conservar lo ya resuelto en turnos con varias partes.

**Riesgo:** tomar la puntuación de confianza declarada por un LLM como una probabilidad fiable o guardar consecuencias del mundo antes de resolver sus dependencias puede generar errores persistentes.

**Acción:** modelar un checkpoint de interpretación con pasos/slots resueltos, evidencia, dependencias y dudas abiertas. Validar/calibrar la señal con holdouts y combinarla con grounding y validaciones deterministas. Los presets de usuario solo ajustan cuándo preguntar; nunca relajan permisos ni validaciones. Al reanudar se recalculan únicamente los pasos dependientes y se conserva el trabajo válido.

### QF-10 — La extensibilidad de reglas exige un formato de módulo seguro (P1/P2)

D&D 5e 2014 sigue siendo el paquete incluido por defecto; la especificación pide importar módulos personalizados. La revisión 2024 y el acceso remoto no son prioritarios.

**Acción:** definir primero el manifiesto y esquema de módulos: IDs y versión, compatibilidad, dependencias, reglas/datos aportados, conflictos y política de activación por campaña. Empezar declarativo y sin ejecución de código arbitrario. Probar importación inválida, dependencia ausente, conflicto y actualización/rollback antes de una biblioteca de módulos.

### QF-11 — La consulta del mundo debe respetar conocimiento y visibilidad a todos los niveles (P1)

La persona usuaria quiere consultar la información que el jugador conoce, abrir fichas de entidades y explorar relaciones/acciones; también desea ajustar por NPC qué datos como HP o CA son visibles.

**Acción:** definir proyecciones de conocimiento por jugador y por personaje, visibilidad por campo/NPC y referencia canónica de entidad en narración. El mismo filtro debe aplicarse a API, búsqueda, paneles, tooltips, compendio y exportaciones player-safe. Una vista previa no debe usar una búsqueda libre que pueda resolver a una entidad oculta o ambigua.

### QF-12 — La interfaz propia necesita comenzar por investigación y contratos, no por pantallas aisladas (P1/P2)

La interfaz deseada es altamente configurable y debe ofrecer los modos Simplificado y Avanzado sin perder opciones. Las explicaciones de configuración deben ser comprensibles y accesibles; no todo debe depender de tooltips.

**Acción:** una vez estables los contratos de lectura/escritura y workflows del backend, comenzar prototipos de navegación, paneles, ayuda contextual y visor del mundo. Probar tareas con ambos modos, ratón, teclado y táctil. Construir la interfaz como cliente de la API, sin duplicar reglas de dominio o acceso a SQLite.

## 4. Fases recomendadas

Las fases están ordenadas por dependencia. Una fase no se cierra porque el código exista: se cierra con evidencia registrada.

### Fase 0 — Baseline de repositorio y CI

**Estado: completada en el baseline.**

- [x] PR #255 integrada en `main`.
- [x] 2042 tests deterministas correctos.
- [x] Ruff, JavaScript y ambos alcances Pyright correctos.
- [x] CodeQL correcto.
- [x] Cobertura combinada 85,14 %.

**Salida:** baseline de código estable para planificar la siguiente medición. Esta fase no certifica Ollama/SillyTavern.

### Fase 1 — Reproducibilidad y baseline de IA

**Prioridad: P0 — siguiente trabajo técnico.**

1. Ejecutar semantic/predicate holdout, discourse pipeline, compound intent, mechanics y operation quality contra la misma revisión.
2. Registrar commit, modelo/digest por rol, versión de Ollama, parámetros, `think`, timeout, contexto, hardware, repeticiones, número de llamadas y latencias.
3. Guardar JSON allowlisted y logs técnicos sin mensajes, prompts, completions, narrativas ni secretos.
4. Mantener el gold held-out fuera de prompts y ejemplos de tuning.
5. Reportar resultados por familia y campo, no solo un promedio global.

**Salida:** baseline comparable de la versión actual y una lista ordenada de errores reproducibles.

**Gate:** fallos de parseo/validación cuentan como fallos; los casos críticos no se pueden omitir. Cero cambios persistentes críticos falsos y cero filtraciones de secretos.

### Fase 2 — Correcciones guiadas por evidencia

**Prioridad: P0 — después de Fase 1.**

Orden de intervención:

1. Claims/predicados relacionales: núcleo predicativo, familia, extremos, dirección, modalidad y polaridad.
2. Action frames: familia y valencia/roles (agente, tema, receptor, instrumento, paciente, origen/destino).
3. Discurso: callback, cambio de tema, elipsis y referencias distantes.
4. Actor/NPC: sujeto de cada paso, habla citada, plural y perspectiva.
5. Mensajes compuestos: orden de pasos, transición entre actores y selección del paso activo.
6. Correcciones pendientes y continuación durable solo donde los datos muestren fallos.

Regla de trabajo: **un grupo de errores por cambio**. Mantener comparables los corpora, no relajar grounding ni abstenciones para subir recall y no introducir nuevas llamadas al modelo sin demostrar que hacen falta.

**Salida:** mejora por familia/campo sin regresión de precisión, seguridad, mecánicas o escritura persistente.

### Fase 3 — Auditoría de fiabilidad de workflows

**Prioridad: P1.**

Revisar sistemáticamente los invariantes de:

- commit atómico y rollback de escrituras parciales;
- checkpoint y reanudación de aclaraciones con varios pasos, umbrales configurables y respuestas parciales;
- control de varios PJ, foco de contexto y delegación aprobada/revocada de NPC;
- herencia y excepciones de configuración global/campaña/personaje/NPC;
- revision conflict/stale state y lease fencing;
- entrega duplicada y secuenciación de versiones;
- clarificación simple y multi-ronda;
- tiradas automáticas/manuales;
- fallo de proveedor, fallo de narración y recuperación;
- cambio de chat, reinicio del backend y reconstrucción del runtime;
- aislamiento multi-campaña;
- migraciones de bases históricas;
- visibilidad de hechos y protección de secretos.

Cada hallazgo debe contener escenario reproducible, frontera responsable, test más estrecho posible y test de integración cuando el contrato atraviese varios paquetes. No duplicar baterías que ya cubren el mismo contrato.

**Salida:** matriz de riesgos con evidencia de tests, defectos y gaps reales.

### Fase 4 — Aceptación end-to-end en SillyTavern

**Prioridad: P1 como integración soportada; no es el único gate de aceptación del producto.**

Ejecutar y registrar `docs/sillytavern-smoke-test.md` en una instalación real:

- dos chats/campañas aislados;
- acciones, diálogo, NPC y referencias cruzadas;
- cambio de tema y callback;
- pregunta/clarificación con varias rondas;
- tiradas automáticas y manuales;
- regeneración/swipes;
- duplicados y reintentos;
- recarga/reinicio con resolución pendiente;
- persistencia de descubrimientos;
- fallo y recuperación de backend/proveedor.

**Salida:** checklist con backend SHA, extensión SHA, modelo/digest, versión/configuración de Ollama, fecha y resultado por caso. Lo que no se ejecute queda explícitamente pendiente. La compatibilidad de SillyTavern se conserva y se prueba cuando se cambie su adaptador, pero la experiencia de producto se validará también desde la futura interfaz propia.

### Fase 5 — Primer vertical slice jugable

**Prioridad: P1 una vez cerrada la base de calidad.**

Entregar un recorrido completo y pequeño:

1. Crear/seleccionar un personaje válido.
2. Equipar y utilizar equipo básico.
3. Explorar y conversar con NPC.
4. Resolver pruebas de característica/habilidad.
5. Completar un encuentro de combate dentro del ruleset implementado.
6. Descansar, recuperar recursos soportados y recibir una recompensa.
7. Conservar estado, eventos y consecuencias entre turnos/sesiones.

No hace falta implementar toda la 5e 2014 para validar este hito. Sí hace falta que las reglas utilizadas estén correctas, documentadas y probadas. El recorrido deberá incluir la elección/cambio de varios PJ, al menos un cambio de delegación NPC y una aclaración que se pause y reanude sin perder los pasos ya resueltos.

### Fase 6 — Ampliación selectiva

**Prioridad: P2.**

Solo después del vertical slice:

- progresión de personaje y clases;
- recursos específicos de clase;
- hechizos y condiciones adicionales;
- más familias de objetos/equipo;
- misiones, pistas y progresión de aventuras;
- mejoras de recuperación/contexto cuando se demuestre un cuello de botella.

### Fase 7 — Diseño y entrega progresiva de la interfaz propia

**Prioridad: P1/P2 — iniciar discovery cuando el backend sea sólido; no esperar a que SillyTavern sea la única UX validada.**

Criterios mínimos para empezar el diseño funcional:

- Contratos de API para campañas, personajes, turnos, configuración, mundo y entidades definidos y versionados.
- Ciclo durable de turnos probado en happy path, aclaración, tirada manual, reintento, regeneración y reinicio.
- Política de permisos para PJ/NPC definida y aplicada en backend.
- Proyecciones de conocimiento/visibilidad documentadas y cubiertas con tests.
- Errores, loading, conflictos y estados pendientes representables mediante contratos API.

Trabajo de UX/entrega:

1. Prototipar el modelo de navegación y personalización de paneles.
2. Probar los modos Simplificado/Avanzado y jerarquía de ayuda (texto visible, tooltip breve, popover/panel para detalle).
3. Diseñar visor de mundo, fichas, relaciones, referencias inline en narración y acceso rápido.
4. Diseñar la configuración de tiradas, visibilidad NPC, idiomas, control PJ/NPC y umbral de aclaración.
5. Implementar el cliente propio en verticales que consuman la API, sin replicar reglas o autoridad de dominio.
6. Ejecutar pruebas de tareas y accesibilidad con teclado y pantallas táctiles antes de considerar cerrada cada vista.

**Gate:** el cliente propio no podrá leer secretos por vías distintas al backend ni modificar estado saltándose los contratos. El modo Simplificado no puede eliminar una capacidad ni degradar los límites de seguridad.

## 5. Qué no priorizar ahora

- Otra reescritura general del prompt.
- Nueva llamada LLM por cada campo semántico.
- Vector DB, embeddings o recuperación semántica nueva sin un benchmark que demuestre el límite del ranker actual.
- Microservicios, colas, múltiples workers o locks distribuidos.
- Implementar una interfaz propia completa antes de tener contratos y workflows de backend sólidos; el diseño/prototipado sí debe comenzar en cuanto se alcancen esos criterios.
- Hacer que SillyTavern sea la única vía de probar o aceptar el producto.
- Multijugador, autenticación remota o acceso público como cambio incidental.
- Importar módulos de reglas con ejecución arbitraria de plugins/código; primero un formato declarativo, validable y versionado.
- Implementar reglas de D&D 2024 dentro del módulo 2014.
- Añadir cobertura solo para aumentar un porcentaje global.
- Declarar que el modelo funciona porque los tests deterministas pasan.

## 6. Evidencia y documentación de referencia

- [Requisitos de producto v0.2](../product/product-requirements-2026-11-18.md) — control configurable, incertidumbre, UI propia, conocimiento del mundo, selección explícita de entidades para el contexto, internacionalización y módulos personalizados.
- [Visión y estado actual](../../README.md).
- [Auditoría de comprensión de predicados](predicate-understanding-audit-2026-11-17.md).
- [Hardening semántico](semantic-understanding-hardening-2026-11-17.md).
- [Evaluación de discurso](discourse-understanding-evaluation-2026-11-17.md).
- [Fase de comprensión de mensajes compuestos](player-message-comprehension-phase-2026-11-18.md).
- [Evaluación de prompts y protocolo live](prompt-evaluation-2026-11-12.md).
- [Observabilidad y diagnósticos](../architecture/observability-and-diagnostics.md).
- [Smoke test de SillyTavern](../sillytavern-smoke-test.md).
- [Guía CI](ci-quality-roadmap.md).

## 7. Regla de actualización

Este archivo es la hoja de ruta vigente. Al cerrar una fase, actualizar su estado y evidencia en este documento. Los informes con fecha anterior permanecen como snapshots históricos: no reescribirlos para que parezca que las correcciones posteriores ya existían cuando se hicieron aquellos análisis.
