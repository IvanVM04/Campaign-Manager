# Estado actual y mapa de arquitectura — 2026-11-18

**Baseline de código auditado:** main — ae52afcf9c172514a5d119fe301de11255f08091 (PR #261 fusionada; baseline previo a esta actualización).  
**Última implementación integrada:** PR #261, que endurece los contratos de allowlist del LLM y aísla snapshots de turno mientras reduce el alcance de los locks.  
**Método:** inspección estática del árbol, contratos, routers, migraciones, guías de paquetes, índices y evidencias de CI. No es una certificación de una sesión local de Ollama/SillyTavern.

> **Actualización de fuente de verdad — 2026-11-19:** el `main` vigente ya incluye PR #266 en `5988ed161a9023d9a2bf86912c82f74092a53e96`. La ejecución de CI asociada al SHA final de #266 registró 2.148 tests deterministas pasados, 22 `real_llm` excluidos y 85,31 % de cobertura combinada ([workflow run #44417534718](https://github.com/IvanVM04/Campaign-Manager/actions/runs/44417534718)). Esto reemplaza los conteos históricos de #255/#261 cuando se hable del estado actual; no certifica calidad live de Ollama ni una sesión SillyTavern. La nueva arquitectura NLU y el gate de pruebas live se describen en [player-language-understanding-architecture-2026-11-19.md](player-language-understanding-architecture-2026-11-19.md). PR #267 está en desarrollo y aún no forma parte de `main`.

> **Reconciliación verificada — 2026-11-19:** `main` está en `8276450babba6611a172e601d0c76b83ae8e449e`, con PRs #267, #268 y #269 integradas. En ese SHA: 2.188 tests Python pasaron, 22 `real_llm` se excluyeron deliberadamente, cobertura combinada 85,23 % (88,8 % líneas; 75,9 % ramas); Ruff, Pyright, JavaScript y CodeQL pasaron. Esto no certifica Ollama live ni la aceptación manual de SillyTavern. Véase [auditoría global del 19-11](project-audit-2026-11-19.md).

## 1. Resumen ejecutivo

Campaign Manager es actualmente un **backend local de gestión de campañas con un pipeline durable de turnos, propuestas estructuradas al mundo, persistencia y una integración con SillyTavern**. Está evolucionando hacia una aplicación de Dungeon Master de IA para D&D 5e.

La arquitectura de producción es un monolito modular Python con FastAPI, SQLite, Ollama y ocho paquetes de capacidad: `campaign`, `characters`, `combat`, `context`, `llm_world`, `providers`, `turns` y `world`. La raíz de composición es `bootstrap/campaign_runtime.py`. Las rutas API son adaptadores de transporte y no deben convertirse en propietarios de workflows.

**No es todavía** un motor completo de D&D 5e, un constructor completo de personajes, una interfaz gráfica propia, una plataforma internacionalizada ni un sistema de módulos de reglas importables. Esas capacidades están en la definición de producto, no deben inferirse como implementadas por aparecer en los requisitos.

## 2. Qué está implementado y qué es objetivo de producto

| Área | Estado observado en el código/documentación | Objetivo de producto |
|---|---|---|
| Instalación y ejecución | Local, un solo proceso/worker, SQLite y Ollama. | Se mantiene como alcance inicial; acceso remoto no prioritario. |
| Campañas | Varias campañas aisladas; cada request de campaña requiere selección explícita. | Mantener aislamiento y mejorar gestión desde interfaz propia. |
| Personajes jugadores | Ficha/estado parcial, personaje activo usado como foco de contexto y varias operaciones de estado. | Poder controlar uno o varios PJ y cambiar ese conjunto durante la partida. No implementado aún como política multi-PJ completa. |
| NPC | El DM controla el mundo y los NPC no delegados; hay datos mecánicos tipados para combate. | Delegación de NPC solicitada por jugador o DM, con aprobación, alcance, duración y revocación. No tratarla como implementada. |
| Reglas | Subconjunto determinista de D&D 5e 2014: checks/saves d20, iniciativa, ataques, daño, condiciones, movimiento y equipo/encuentros seleccionados. | 2014 como paquete incluido por defecto; sistema seguro de módulos personalizados importables. 2024 no prioritario. |
| Interpretación | `PlayerIntentAnalysis` versionado, v2 con action frames y relation claims, evidencia literal, discurso y evaluación held-out. | Mejorar precisión, incertidumbre y UX de aclaraciones; no confiar en confianza autodeclarada sin calibración. |
| Aclaraciones | Clarificaciones durables, multi-ronda y correcciones por slots; reutilizan el análisis pendiente y preservan campos no modificados. | Umbral configurable de duda y checkpoint visible que conserva pasos resueltos/pendientes. No hay todavía un umbral de producto calibrado configurable. |
| Tiradas | Existen resolución automática determinista, desafíos manuales y un dice tray API; SillyTavern tiene modo manual/automático para los flujos soportados. | Permitir elegir quién aporta cada tirada por campaña/actor/tipo, desde una interfaz unificada. |
| Conocimiento y visibilidad | Visibilidad player-safe, event provenance/epistemic metadata, filtros de eventos y lecturas públicas. No todos los campos libres tienen proveniencia por afirmación. | Compendio interactivo del conocimiento del jugador, fichas/relaciones/eventos y visibilidad configurable de datos de NPC por campo. |
| Contexto elegido por jugador | El backend recupera contexto por intent, menciones y dependencias; no hay selector visual de contexto. | Permitir fijar y adjuntar entidades visibles al siguiente turno sin convertirlas en evidencia nueva de intención. |
| Interfaz | SillyTavern es la interfaz conversacional operativa; FastAPI expone API y Swagger/OpenAPI. No hay UI propia de campaña. | Interfaz propia posterior a la consolidación del backend, con modos Simplificado y Avanzado y personalización alta. |
| Ayuda de configuración | No existe aún un sistema UI de ayuda por campo. | Etiquetas, ayuda visible, tooltips complementarios y paneles explicativos accesibles. |
| Idiomas | No se ha identificado un sistema de internacionalización de interfaz/campaña/interacción completo. | Español e inglés inicialmente; permitir otros idiomas y separar los tres ámbitos lingüísticos. |
| Importación/exportación | Existe `GET /export` player-safe. No se ha identificado una importación/restauración completa de campaña. | Import/export de campañas versionado, validado y seguro. |
| Acceso remoto/multijugador | No incluido; loopback y autoridad local. | Remoto y D&D 2024 se mantienen como futuro/no prioritario; multijugador fuera del alcance inicial. |

## 3. Flujo durable de turnos

El contrato activo es único para clientes nativos y externos:

1. Recibir el mensaje y establecer identidad/alcance de campaña y, cuando aplique, identidad de conversación.
2. Construir contexto acotado y filtrado con el personaje activo, localización, dependencias, referencias resueltas y señales pertinentes.
3. Interpretar el texto con el `IntentInterpreter` y el contrato compartido `PlayerIntentAnalysis` (v1 compatible y v2 semántico).
4. Validar evidencia literal, actor, modalidad, polaridad, referencias canónicas y permisos mediante código de aplicación.
5. Ejecutar adjudicación mecánica solo cuando el análisis autoriza un intento actionable y la decisión requiere mecánica.
6. Calcular dados/reglas soportadas en código determinista.
7. Pedir una propuesta estructurada de consecuencias al modelo cuando está permitida.
8. Validar operaciones y autoridad de dominio; aplicar consecuencias y guardar la resolución de forma atómica.
9. Generar/persistir narración después del commit.

Las clarificaciones y tiradas manuales continúan la misma resolución durable. Regenerar una narración no repite mecánicas ni consecuencias. Los errores de proveedor/narración deben reanudarse sin doble escritura.

### Rutas principales verificadas en los contratos

| Entrada | Propósito |
|---|---|
| `POST /turn` | Turno nativo durable. |
| `POST /integration/turn/resolve` | Prepara/resuelve consecuencias para un cliente externo como SillyTavern. |
| `POST /integration/turn/complete` | Persiste narración/versiones después del commit. |
| `POST /integration/turn/clarification` y `/roll` | Continúa desafíos pendientes. |
| `GET /integration/turn/{external_turn_id}` | Consulta estado de turno externo. |
| `POST /integration/context` | Contexto e historial filtrados para el adaptador. |

`POST /integration/turn` — la antigua ruta narrativa-first — está retirada y debe responder 404. No reintroducirla.

## 4. Interpretación de lenguaje y límites de confianza

- La interpretación semántica compartida tiene v1 decodificable por compatibilidad y v2 con marcos de acción y claims de relación dirigidos.
- El texto, menciones, predicados y excerpts deben estar anclados literalmente al mensaje actual. La historia puede ayudar a resolver discurso, no sustituir la evidencia del turno actual.
- Hay resolución de referencias explícitas, alias, señales de discurso, topic changes/callbacks, pistas de elipsis, señales de habla atribuida y soporte de mensajes compuestos.
- El backend valida permisos, IDs canónicos, visibilidad, esquema y operaciones. El modelo no recibe capacidad de escritura directa ni autoridad sobre resultados de dados.
- Las correcciones pendientes editan slots de una interpretación persistida con evidencia literal de la última respuesta y preservan campos no modificados.
- Los 14 escenarios adicionales de intención compuesta introducidos alrededor de PR #255 permiten evaluar orden/actor/modalidad/polaridad por paso; la evaluación live del holdout actual debe ejecutarse y registrarse. Los contratos deterministas no certifican la calidad general del modelo.

Referencias de comportamiento: [guía de turn services](../../services/turns/README.md), [guía de context services](../../services/context/README.md), [modelos compartidos](../../models/README.md), [fase de comprensión de mensajes de jugador — PR #255](../quality/player-message-comprehension-phase-2026-11-18.md) y la nueva [arquitectura de comprensión del lenguaje](player-language-understanding-architecture-2026-11-19.md).

## 5. Paquetes y propiedad

| Paquete | Responsabilidad principal |
|---|---|
| `services/campaign` | Campaña, sesión, reloj y lifecycle del runtime. |
| `services/characters` | Creación/estado/ficha y operaciones de personaje. |
| `services/combat` | Casos de uso de combate; deriva mecánicas numéricas desde el rules engine. |
| `services/context` | Búsqueda, expansión, ranking, selección y resolución de referencias/contexto. |
| `services/llm_world` | Construcción de prompt de propuesta, parser, registry y validación de operaciones propuestas. |
| `services/providers` | Puertos/adaptadores de proveedores y observabilidad allowlisted. |
| `services/turns` | Coordinación de análisis, adjudicación, persistencia, clarificación, tiradas y narración durable. |
| `services/world` | Validación y aplicación de operaciones sobre el mundo, repositorios y proyecciones. |

Dirección de dependencias: routers API → runtime/application services → capabilities/domain/repositories/providers según contratos permitidos. El root de composición sigue siendo `bootstrap/campaign_runtime.py`. Mantener monolito modular, una sola instancia de proceso y una sola fuente de autoridad de turnos.

## 6. Persistencia, migraciones y concurrencia

- SQLite es la persistencia canónica.
- `database.py` configura claves foráneas y espera de ocupación en cada conexión; el modo WAL persistente se establece durante la inicialización del esquema, no se vuelve a negociar en cada lectura/escritura.
- `scripts/db_maintenance.py` proporciona comprobación de integridad, backup online mediante `sqlite3.Connection.backup` y restauración offline de backups con versión de esquema compatible. La restauración exige detener el backend, valida integridad y claves foráneas, conserva automáticamente un backup pre-restauración y reemplaza el archivo mediante staging en el mismo directorio.
- `migrations.py` declara `CURRENT_VERSION = 34`; la migración 034 añade `conversation_id` a turnos y resoluciones y los índices de historial por chat.
- Las migraciones son forward-only y el registry `MIGRATIONS` es la lista de ejecución.
- `CampaignRuntime` mantiene `WorldState` en memoria por campaña y la ejecución usa locks de proceso/campaña. Ejecutar con un solo worker; procesos separados tendrían caches y locks independientes.
- El commit de las consecuencias es corto y atómico. Llamadas a proveedor y narración no deben mantener una transacción de escritura abierta.
- `turn_snapshot_archive` conserva JSON histórico del antiguo snapshot, pero no participa en el runtime y no debe volver a usarse para regenerar estado.

La guía de migraciones es [migration-catalog-2026-11-12.md](migration-catalog-2026-11-12.md). A fecha del audit, su versión 34 coincide con `migrations.CURRENT_VERSION`.

## 7. Visibilidad, privacidad y despliegue

- `X-Campaign-Id` selecciona campaña; no es autenticación.
- El servidor documentado escucha en `127.0.0.1`; no cambiar a `0.0.0.0`, túneles o proxy remoto sin autenticación, autorización de campaña y revisión de seguridad.
- Las lecturas player-safe omiten eventos secretos/GM-only. No existe un GM read API autenticado.
- La visibilidad de hechos/eventos no debe confundirse con una capacidad configurada por campo para todas las estadísticas de NPC; esta última es requisito futuro.
- Los logs usan campos allowlisted y no deben persistir prompts, completions, mensajes, narración, notas secretas ni credenciales.

## 8. CI y verificación observada

Como referencia histórica, en el commit documental `4a3a2549...` (PR #257 fusionada) se observaron:

| Ejecución | Resultado |
|---|---|
| [Tests #44330385868](https://github.com/IvanVM04/Campaign-Manager/actions/runs/44330385868) | Success: 2.050 passed, 22 deselected, 85,18 % de cobertura combinada. Ruff, ambos alcances Pyright, JavaScript y CI summary correctos. |
| [CodeQL #44330385883](https://github.com/IvanVM04/Campaign-Manager/actions/runs/44330385883) | Success. |

Este resultado pertenece al baseline histórico del 18-11. Para el resultado vigente sobre #269, usa la reconciliación del inicio de este documento y la [auditoría global del 19-11](project-audit-2026-11-19.md). Los tests `real_llm` y la aceptación manual de SillyTavern siguen siendo gates separados.

## 9. Límites de arquitectura que deben preservarse

1. LLM output es input no confiable: nunca escribe directamente en SQLite.
2. Una mención o entidad añadida al contexto no es, por sí sola, una acción ni una declaración factual actual.
3. Historia y narrativa son pistas de interpretación, no evidencia nueva del mensaje actual ni autoridad canónica.
4. El jugador no puede controlar el mundo/NPC salvo delegación explícita aprobada y limitada.
5. El DM no puede invalidar resultados mecánicos confirmados.
6. Ningún umbral de incertidumbre puede rebajar autorización, validación o grounding.
7. Los filtros player-safe deben aplicarse a búsqueda, paneles, previews, export y API; no solo a la narración.
8. Los módulos de reglas futuros deben ser versionados, declarativos y validados; no ejecutar código arbitrario ni mezclar reglas 2014/2024.
9. La UI propia y SillyTavern deben ser clientes de la API, no dueños de estado o reglas.
10. Mantener un único pipeline durable; regeneración narrativa nunca repite consecuencias.

## 10. Fuentes actuales de verdad

- [Requisitos de producto v0.2](../product/product-requirements-2026-11-18.md) — alcance y requisitos deseados, con estados de implementación.
- [Hoja de ruta de calidad 2026-11-18](../quality/quality-roadmap-2026-11-18.md) — prioridades de calidad, gates live y fases de entrega.
- [Mapa de paquetes y ejecución](current-state-2026-11-18.md) — ownership y rutas de ejecución de alto nivel.
- [Contrato del pipeline de turnos](turn-pipeline-compatibility.md) — rutas activas y lifecycle.
- [Lifecycle durable](turn-resolution-lifecycle.md) es un documento de diseño antiguo; usar el contrato activo anterior y el código actual.
- [Matriz de dependencias](package-dependency-matrix.md), [catálogo de migraciones](migration-catalog-2026-11-12.md) y [observabilidad](observability-and-diagnostics.md).
- [Hub documental](../README.md), [README de proyecto](../../README.md) y [guías de paquetes](../../services/).



## 11. Mantenimiento y ciclo de vida de la aplicación

- FastAPI libera los runtimes de campaña mediante el contrato lifespan, evitando el hook de apagado obsoleto.
- Los helpers de construcción no utilizados que estaban exportados accidentalmente desde app.py se han retirado. El serializador de mecánicas sigue perteneciendo al router de turnos y ya no se reexporta desde el módulo de composición.
- Las operaciones de backup/restore son herramientas offline, no endpoints HTTP. No se debe restaurar una base mientras el servidor está activo.
- La guía operativa se encuentra en [SQLite maintenance and recovery](sqlite-maintenance-and-recovery.md).
