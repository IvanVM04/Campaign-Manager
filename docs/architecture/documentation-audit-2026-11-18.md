# Auditoría documental integral — 2026-11-18

**Repositorio:** IvanVM04/Campaign-Manager  
**Rama auditada:** main en 4a3a2549bb0bb1bc38ec0e6f456ac6d5ccef24d1 (PR #257 fusionada).  
**Baseline de código de producción:** f4fb3914ebab4579118863796e6f6d4b7183d0cf (PR #255; PR #256 y #257 fueron documentales).  
**Alcance:** 508 rutas del árbol Git, de las cuales 118 son archivos documentales/textuales: 4 en raíz, 12 en docs/, 49 en docs/architecture/, 43 en docs/quality/, 1 en docs/product/, 1 en models/ y 8 guías en services/.  
**Tipo:** auditoría documental/estática. No modifica código de producción ni afirma que se hayan repetido pruebas live con Ollama o una sesión manual de SillyTavern.

## 1. Resumen ejecutivo

La documentación había crecido de forma incremental junto con las PRs, pero la jerarquía de fuentes de verdad no había evolucionado al mismo ritmo. El problema principal no era que todos los documentos estuvieran equivocados, sino que índices, READMEs de entrada y algunos contratos antiguos presentaban snapshots de noviembre 3–12 como si fueran el estado vigente.

Se encontraron cinco clases de desactualización:

1. **Punteros de estado actual obsoletos.** Los índices dirigían a mapas y auditorías cuyo baseline era PR #205, #208 o #218, aunque el código de producción había llegado a PR #255.
2. **Contratos históricos presentados como activos.** El diseño inicial de lifecycle PR #28 describía como futuro un pipeline ya implementado; una frontera de contexto aún mencionaba el prompt/extractor legacy; una auditoría de locks listaba la ruta /integration/turn como writer activo aunque ya fue retirada.
3. **Visión del producto desfasada.** Algunos textos reducían single-player a un único personaje o aplazaban indefinidamente la UI propia. El objetivo actual es una persona humana que puede controlar varios PJ y una interfaz propia que se diseñará al consolidarse el backend.
4. **Estado de calidad antiguo.** Inventarios de tests, porcentajes y siguientes P0 de informes anteriores no reflejaban PRs #250, #253 y #255.
5. **Requisitos futuros confundidos con capacidades actuales.** La definición de producto debe distinguir de forma consistente objetivo aprobado frente a código implementado.

La jerarquía documental recomendada queda así:

- **Producto:** [requisitos v0.2](../product/product-requirements-2026-11-18.md).
- **Implementación:** [estado actual del sistema](current-state-2026-11-18.md).
- **Calidad/prioridades:** [hoja de ruta de calidad](../quality/quality-roadmap-2026-11-18.md).
- **Navegación:** [hub documental](../README.md) e [índice de arquitectura](README.md).
- **Historial:** documentos fechados y registros de PR, preservados pero etiquetados como snapshots.

## 2. Evidencia y método

### 2.1 Inventario y validación

Se obtuvo el árbol Git recursivo de main con truncated=false y se identificaron 118 archivos documentales/textuales. Se contrastaron las afirmaciones de mayor impacto con:

- migrations.py: CURRENT_VERSION = 34.
- Routers actuales: campaign, character, clock, combat, dice, effects, integration, memory, system, turns, world y world collections.
- Servicios y guías de ocho paquetes de capacidad más el adapter externo de SillyTavern.
- Contratos activos del pipeline durable, clarificaciones, tiradas manuales, commit, narración, contexto y persistencia.
- README, AGENTS.md, índices documentales, quickstart, guías de paquetes y auditorías fechadas.
- Ejecuciones GitHub Actions sobre el commit documental actual de main, posterior a PR #257.

Se revisaron encabezados, estados, navegación y afirmaciones de especial riesgo: rutas retiradas, propuesta frente a implementación, versión de esquema, conteos de tests, cobertura, número de personajes, futuro de la UI y tareas P0. El inventario de abajo cubre los 118 archivos. No se ha reescrito línea por línea cada antiguo informe de PR: esos informes se conservan como evidencia de su propio baseline y quedan clasificados como históricos. Las correcciones se concentran en los índices de entrada y en contratos donde el texto podía inducir a implementar comportamiento retirado.

### 2.2 Baseline CI verificado

Para main en 4a3a2549bb0bb1bc38ec0e6f456ac6d5ccef24d1:

| Evidencia | Resultado |
|---|---|
| [Tests run #44270598043](https://github.com/IvanVM04/Campaign-Manager/actions/runs/44270598043) | Success |
| Pytest determinista | 2.042 passed, 22 deselected |
| Cobertura combinada | 85,14 %, gate mínimo 85 % |
| Ruff | Success |
| Pyright requerido (models, rules_engine, bootstrap, operations) | Success |
| Pyright repository-wide | Success |
| JavaScript | Success |
| CI summary | Success |
| [CodeQL run #44270598070](https://github.com/IvanVM04/Campaign-Manager/actions/runs/44270598070) | Success |

Los 22 tests excluidos son de tipo real_llm. CI no certifica la calidad actual del modelo con Ollama ni una sesión manual end-to-end de SillyTavern. La auditoría no marca esos gates como completados.

## 3. Hallazgos de desactualización

| ID | Hallazgo | Riesgo documental | Corrección aplicada |
|---|---|---|---|
| DOC-01 | El hub indexaba el mapa y auditoría de arquitectura 11/12 como current. | Seguir tareas ya completadas o utilizar estados #205/#218 como presentes. | Hub reconstruido con fuente actual, contratos activos, operación, históricos y registros PR separados. |
| DOC-02 | El índice de arquitectura mezclaba snapshots con contratos activos. | Tratar el PR #28 lifecycle como contrato de producción. | Índice reconstruido y lifecycle PR #28 clasificado como histórico. |
| DOC-03 | Lifecycle PR #28 afirmaba que no existía tabla de resoluciones ni continuación manual. | Diseñar sobre una arquitectura que ya no existe. | Aviso explícito de supersesión; texto original preservado por historia. |
| DOC-04 | La frontera de contexto mencionaba legacy prompt builder y full-world legacy path como activos. | Crear un segundo pipeline o depender del extractor retirado. | Frontera reescrita con el flujo estructurado y límites actuales. |
| DOC-05 | La auditoría de locks mantenía POST /integration/turn como writer. | Reintroducir la ruta narrativa-first retirada. | Fila sustituida por estado Removed / 404. |
| DOC-06 | README/quickstart describían SillyTavern como interfaz definitiva y única. | Contradicción con la decisión de UI propia tras consolidar el backend. | Separado cliente operativo actual del objetivo de interfaz propia. |
| DOC-07 | Single-player aparecía sin distinguir número de personas y PJ controlados. | Restringir el diseño a un único personaje. | README y mapa actual aclaran una persona humana y objetivo de uno o varios PJ. |
| DOC-08 | Guías turns/context llegaban solo hasta PR #223/#226. | Perder mejoras de discurso y compound intent de PR #255. | Guías actualizadas con cambios #246–#255 y sus límites. |
| DOC-09 | Auditorías CI/tests y language quality estaban indexadas como prioridades actuales. | Confundir conteos, coberturas y tareas P0 antiguas con estado actual. | Avisos de snapshot y fuentes actuales de referencia. |
| DOC-10 | Requisitos/roadmap no apuntaban al merge documental PR #257. | Baselines inconsistentes. | Baselines alineados con commit 4a3 y run CI posterior. |

## 4. Cambios aplicados en esta rama

### 4.1 Documentos nuevos

- [current-state-2026-11-18.md](current-state-2026-11-18.md): mapa de implementación, flujo durable, paquetes, persistencia/migraciones, seguridad, CI y gaps de producto. (Creado durante esta auditoría; fuera del inventario base de main.)
- [documentation-audit-2026-11-18.md](documentation-audit-2026-11-18.md): este inventario y registro de frescura. (Creado durante esta auditoría; fuera del inventario base de main.)

### 4.2 Documentos activos actualizados

- README.md: visión, autoridad del jugador, varios PJ como objetivo, nuevo índice, estado real y roadmap; corregido un code fence faltante en las rutas SillyTavern.
- AGENTS.md: punto de entrada actualizado, documentos actuales y distinción active-character actual frente a multi-PJ futuro.
- docs/README.md: reestructurado como hub con fuente actual, contratos activos, guías, operación y snapshots históricos.
- docs/architecture/README.md: reestructurado; lifecycle PR #28 pasa a histórico.
- docs/architecture/package-dependency-matrix.md: referencia al mapa actual en lugar del snapshot 11/12.
- docs/architecture/writer-lock-cache-audit.md: retirada la fila de writer legacy.
- docs/architecture/llm-world-context-rendering-boundaries.md: describe el único proposal path actual, límites de contexto y brecha multi-PJ.
- docs/architecture/turn-resolution-lifecycle.md: banner de propuesta histórica/supersedida.
- docs/architecture/context-rendering-boundaries.md: clasificado como snapshot del renderer genérico antiguo.
- docs/mvp-quickstart.md: SillyTavern descrito como walkthrough operativo actual, no como UI final.
- services/turns/README.md: actualizado a PR #255; aclara límite active-character.
- services/context/README.md: actualizado con señales de discurso y holdout compuesto PR #255.

### 4.3 Requisitos, calidad y snapshots

- docs/product/product-requirements-2026-11-18.md: baseline documental alineado a PR #257.
- docs/quality/quality-roadmap-2026-11-18.md: código baseline #255, baseline documental #257 y CI #44270598043/#44270598070.
- Se añadieron avisos de snapshot/supersesión a architecture-map-2026-11-12, architecture-audit-2026-11-12, phase-0-closeout-2026-11-12, engineering-readiness-and-gameplay-roadmap-2026-11-12, ai-world-understanding-roadmap-2026-11-12, ci-audit-2026-11-11, test-suite-navigation-2026-11-12, language-understanding-priority-2026-11-13, predicate-understanding-audit-2026-11-17, discourse-understanding-evaluation-2026-11-17, semantic-understanding-hardening-2026-11-17, semantic-understanding-evaluation-corpus-2026-11-13 y prompt-evaluation-2026-11-12.

No se han eliminado auditorías ni alterado métricas históricas para simular que fueron medidas con código posterior.

## 5. Inventario completo de archivos documentales

La clasificación distingue **actual** (fuente vigente), **apoyo** (contrato/guía puntual que sigue vigente), **histórico** (snapshot, PR record o métrica fechada) y **operativo/reglas** (procedimiento o referencia de reglas). Un documento histórico puede seguir siendo correcto para su fecha; simplemente no describe el estado global actual.

### 5.1 Raíz del repositorio (4)

| Archivo | Clasificación y decisión |
|---|---|
| AGENTS.md | Actual. Punto de entrada actualizado en esta rama. |
| README.md | Actual. Actualizado en esta rama. |
| SRD-ATTRIBUTION.md | Legal/operativo. Conservar asociado al material SRD; no es fuente de estado arquitectónico. |
| requirements.txt | Configuración de dependencias runtime; revisar junto con pyproject.toml al cambiar dependencias. |

### 5.2 docs/ (12)

| Archivo | Clasificación y decisión |
|---|---|
| docs/README.md | Actual. Hub reconstruido. |
| docs/armor-rules.md | Operativo/reglas. Referencia de armadura soportada. |
| docs/campaign-clock.md | Apoyo. Contrato de reloj de campaña. |
| docs/combat-attack.md | Operativo/reglas. Referencia acotada de ataques implementados. |
| docs/combat-consistency-audit.md | Histórico/técnico. Auditoría focalizada, no inventario total del combate. |
| docs/combat-movement.md | Operativo/reglas. Referencia de movimiento soportado. |
| docs/combat-opportunity-attacks.md | Operativo/reglas. Referencia de ataques de oportunidad soportados. |
| docs/death-saving-throws.md | Operativo/reglas. Referencia del subconjunto de death saves. |
| docs/mvp-quickstart.md | Operativo. Actualizado; walkthrough actual mediante SillyTavern. |
| docs/persistent-effects.md | Apoyo. Contrato de efectos persistentes/expiración. |
| docs/sillytavern-smoke-test.md | Operativo. Checklist manual; solo se marca pasado tras ejecución real. |
| docs/weapon-domain.md | Operativo/reglas. Dominio de equipo/armas, no catálogo completo de reglas 5e. |

### 5.3 docs/architecture/ (49)

| Archivo | Clasificación y decisión |
|---|---|
| README.md | Actual. Índice reconstruido. |
| current-state-2026-11-18.md | Actual. Nuevo mapa fuente-verificado. |
| documentation-audit-2026-11-18.md | Actual. Esta auditoría y registro de frescura. |
| api-error-contract.md | Apoyo vigente. Contrato de errores HTTP. |
| campaign-state-revisions.md | Apoyo vigente. Revisión de campaña/fencing. |
| combat-attack-profile-boundary.md | Apoyo vigente. Selección de perfil de ataque. |
| combat-character-state-audit-2026-11-12.md | Apoyo/snapshot focalizado; ownership del vertical slice, no estado total del combate. |
| change-impact-map-2026-11-12.md | Apoyo. Checklist transversal de revisión; verificar contra routers/tests actuales antes de cada cambio, no es mapa de imports. |
| context-rendering-boundaries.md | Histórico. Renderer genérico previo al proposal-context actual; banner añadido. |
| dnd5e-2014-rules-engine.md | Apoyo vigente. Subconjunto determinista 2014, no reglas completas. |
| durable-challenge-state-boundary.md | Contrato activo de lectura de challenge. |
| durable-clarification-submission.md | Contrato activo de continuación. |
| durable-manual-roll-submission.md | Contrato activo de tiradas manuales. |
| durable-narration-lifecycle.md | Contrato activo de narración post-commit. |
| durable-prepared-challenge-commit.md | Contrato activo de commit transaccional. |
| durable-turn-execution-boundary.md | Contrato activo de ejecución durable. |
| durable-turn-resolution-persistence.md | Apoyo histórico/implementación: migración 022 y persistencia durable. |
| llm-world-context-rendering-boundaries.md | Contrato activo reescrito en esta rama. |
| llm-world-proposal-prompt-boundary.md | Contrato activo del proposal path. |
| migration-catalog-2026-11-12.md | Catálogo activo; versión 34 coincide con código. Fecha original conservada. |
| module-catalog-2026-11-12.md | Snapshot de inventario de capas compartidas contra PR #205; banner añadido y navegación a la fuente actual. Verificar nombres/rutas contra el source antes de cambios. |
| observability-and-diagnostics.md | Contrato activo de logs/telemetría. |
| package-dependency-matrix.md | Contrato activo; referencia al mapa actual actualizada. |
| sillytavern-adapter-boundary-2026-11-12.md | Contrato activo del adapter. La fecha indica su introducción. |
| sillytavern-durable-turn-adapter.md | Contrato activo de workflow externo durable. |
| sqlite-transaction-ownership.md | Contrato activo de transacciones. |
| turn-pipeline-compatibility.md | Contrato activo y fuente principal del mapa de rutas. |
| world-applier-boundaries.md | Contrato activo de aplicación de operaciones. |
| writer-lock-cache-audit.md | Auditoría focalizada actualizada; ruta legacy retirada. |
| turn-resolution-lifecycle.md | Histórico: propuesta PR #28; banner añadido. |
| architecture-map-2026-11-12.md | Snapshot PR #218; banner añadido. |
| architecture-audit-2026-11-12.md | Snapshot PR #205; banner añadido. |
| phase-0-closeout-2026-11-12.md | Snapshot de decisión; banner aclara la decisión posterior de UI. |
| engineering-readiness-and-gameplay-roadmap-2026-11-12.md | Snapshot PR #214/estimaciones; banner añadido. |
| architecture-audit-2026-11-11.md | Snapshot histórico. |
| architecture-audit-2026-11-06.md | Snapshot histórico. |
| architecture-decisions-2026-11-03.md | ADRs históricos; consultar junto al mapa actual. |
| audit-and-refactor-plan-2026-11-05.md | Snapshot histórico. |
| comprehensive-architecture-audit-2026-11-05.md | Snapshot histórico. |
| current-architecture-2026-11-03.md | Snapshot histórico. |
| current-architecture-2026-11-05.md | Snapshot histórico. |
| domain-boundaries-2026-11-03.md | Snapshot histórico de ownership. |
| engineering-audit-2026-11-03.md | Snapshot histórico. |
| functional-audit-2026-11-03.md | Snapshot histórico funcional. |
| legacy-cleanup-2026-11-06.md | Historial de disposición de legacy; conservar. |
| legacy-extraction-boundary-audit-2026-11-12.md | Historial legacy con aviso de supersesión. |
| legacy-prompt-decomposition-2026-11-12.md | Historial legacy con aviso de supersesión. |
| legacy-retirement-2026-11-12.md | Registro de retirada; conservar como evidencia histórica. |
| legacy-sillytavern-retirement-audit-2026-11-11.md | Historial con aviso de supersesión. |
| legacy-sillytavern-turn-boundary.md | Historial con aviso de supersesión. |
| roadmap-2026-11-03.md | Snapshot histórico de roadmap. |

### 5.4 docs/quality/ (43)

| Archivo | Clasificación y decisión |
|---|---|
| quality-roadmap-2026-11-18.md | Actual. Fuente de verdad de prioridades, baseline CI y gates live. |
| player-message-comprehension-phase-2026-11-18.md | Registro de PR #255 y holdout de mensajes compuestos. |
| predicate-understanding-audit-2026-11-17.md | Snapshot pre/post parcial de #250/#253; banner añadido, necesita baseline live nuevo. |
| discourse-understanding-evaluation-2026-11-17.md | Snapshot anterior a #255; banner añadido. |
| semantic-understanding-hardening-2026-11-17.md | Registro de PR #253; banner añadido. |
| ai-world-understanding-roadmap-2026-11-12.md | Roadmap histórico multi-PR; banner añadido. |
| ci-audit-2026-11-11.md | Snapshot workflow/ruleset; banner añadido. |
| test-suite-audit-2026-11-11.md | Auditoría histórica que ya identifica su inventario como point-in-time. |
| test-suite-navigation-2026-11-12.md | Snapshot tras PR #208; banner añadido. |
| prompt-evaluation-2026-11-12.md | Protocolo snapshot; banner añadido, principios CI/live siguen válidos. |
| semantic-understanding-evaluation-corpus-2026-11-13.md | Snapshot de 110 escenarios; banner añadido. |
| language-understanding-priority-2026-11-13.md | Prioridad P0 histórica; banner añadido. |
| language-understanding-architecture-audit-2026-11-16.md | Auditoría previa a #255; conservar como snapshot. |
| language-understanding-audit-2026-11-14.md | Auditoría pre-#226/#227; histórica. |
| modular-language-understanding-pipeline-2026-11-14.md | Decisión de arquitectura implementada en #225/#226; conservar como rationale. |
| advanced-discourse-understanding-2026-11-14.md | Snapshot de discourse; histórico. |
| semantic-understanding-next-phase-2026-11-13.md | Plan de fase previo; histórico. |
| entity-reference-resolution-2026-11-12.md | Registro técnico de resolución; consultar junto a la guía de context actual. |
| typed-world-reference-resolution-2026-11-13.md | Registro de implementación de referencias tipadas. |
| context-scale-probes-2026-11-12.md | Evidencia de scale probes fechada. |
| pyright-baseline-2026-11-11.md | Registro del baseline antiguo; workflow actual reporta cero diagnósticos. |
| ci-quality-roadmap.md | Guía general de calidad estática; contrastar detalles con workflows actuales. |
| pr-226-integrated-llm-pipeline-hardening.md | Registro PR #226, no backlog actual. |
| pr-227-held-out-discourse-pipeline-evaluation.md | Registro PR #227. |
| pr-228-configurable-ollama-thinking.md | Registro PR #228. |
| pr-229-intent-validation-diagnostics.md | Registro PR #229. |
| pr-230-field-level-intent-validation-diagnostics.md | Registro PR #230. |
| pr-231-intent-category-active-step-consistency.md | Registro PR #231. |
| pr-232-intent-step-position-canonicalization.md | Registro PR #232. |
| pr-233-intent-attribution-current-evidence.md | Registro PR #233. |
| pr-234-discourse-holdout-fixture-integrity.md | Registro PR #234. |
| pr-235-intent-surface-evidence-prompting.md | Registro PR #235. |
| pr-236-intent-speech-act-categories.md | Registro PR #236. |
| pr-237-reference-correction-evidence-reliability.md | Registro PR #237. |
| pr-238-read-only-negative-references-and-coverage-gate.md | Registro PR #238. |
| pr-240-atomic-pending-correction-selectors.md | Registro PR #240. |
| pr-241-pending-correction-endpoint-diagnostics.md | Registro PR #241. |
| pr-242-backend-pending-correction-slot-catalogue.md | Registro PR #242. |
| pr-243-canonical-pending-correction-candidates.md | Registro PR #243. |
| pr-244-durable-llm-workflow-hardening.md | Registro PR #244. |
| pr-245-correction-holdout-assertion-contract.md | Registro PR #245. |
| pr-246-discourse-continuity-intent-reliability.md | Registro PR #246. |
| pr-250-predicate-evaluation-and-telemetry.md | Registro PR #250. |

### 5.5 Producto, modelos y guías de servicio (10)

| Archivo | Clasificación y decisión |
|---|---|
| docs/product/product-requirements-2026-11-18.md | Actual. Requisitos v0.2; separa requisitos de implementación. |
| models/README.md | Apoyo vigente. Contratos semánticos/durables y límites de confianza. |
| services/campaign/README.md | Apoyo vigente. Ownership de campaña/runtime/sesiones. |
| services/characters/README.md | Apoyo vigente. Estado y descansos; no implica constructor completo. |
| services/combat/README.md | Apoyo vigente. Boundaries de combate y reglas pendientes. |
| services/context/README.md | Actualizado en esta rama hasta PR #255; aclara límites actuales. |
| services/llm_world/README.md | Apoyo vigente. Pipeline de propuesta estructurada. |
| services/providers/README.md | Apoyo vigente. Provider/Ollama, schemas y telemetría segura. |
| services/turns/README.md | Actualizado en esta rama hasta PR #255; aclara active-character frente a objetivo multi-PJ. |
| services/world/README.md | Apoyo vigente. Proyecciones player-safe y autoridad de aplicación. |

### 5.6 Recuento de clasificación

| Grupo | Cantidad |
|---|---:|
| Raíz | 4 |
| docs/ | 12 |
| Arquitectura | 49 |
| Calidad | 43 |
| Producto | 1 |
| Modelos | 1 |
| Guías de servicio | 8 |
| **Total inventariado** | **118** |

## 6. Reglas para futuros cambios documentales

1. **No usar nombres con fecha como sinónimo de actual.** Un documento fechado puede seguir vigente como contrato, pero el estado se verifica desde el contenido y el código.
2. **Un requisito no es una implementación.** Todo documento de producto debe diferenciar Implemented, Partial, Pending y Out.
3. **Una PR record no es un backlog.** Sus siguientes pasos describen el momento en que se redactó; el work order vive en la hoja de ruta vigente.
4. **No reescribir historia.** Cuando un estado histórico queda superado, añadir banner y apuntar a la fuente actual; no alterar métricas originales.
5. **Actualizar índices en el mismo cambio.** Todo nuevo mapa/auditoría requiere links en hub e índice propietario.
6. **Validar endpoints contra routers y contratos.** No mantener listas copiadas que puedan perder rutas o conservar rutas retiradas.
7. **Diferenciar evidencia.** CI determinista, evaluación live de Ollama y aceptación manual SillyTavern son gates distintos.
8. **No declarar una capacidad en README como existente** hasta que código y tests indiquen ese estado.

## 7. Limitaciones y trabajo documental restante

- Los registros de PR #226–#250 conservan el detalle de su propio cambio; no se uniformaron todos sus encabezados porque son registros numerados de entrega y no fuentes actuales.
- Las guías de reglas describen áreas acotadas. Al ampliar el rules engine habrá que añadir fuente normativa, alcance exacto y tests por subsistema.
- Importación de módulos personalizados, importación/restauración completa de campañas, localización, UI propia, panel de conocimiento, selección de entidades y permisos multi-PJ/NPC siguen pendientes. No se documentan formatos/API ficticios antes de que exista un contrato aprobado e implementación.
- El quickstart sigue siendo un walkthrough SillyTavern porque esa es la interfaz operativa actual de prueba; se mantendrá hasta que el primer cliente propio sea funcional.
- Se recomienda una auditoría de frescura tras cambios importantes de routers, migraciones o contratos y antes de una release; no crear informes amplios redundantes por cada PR.
