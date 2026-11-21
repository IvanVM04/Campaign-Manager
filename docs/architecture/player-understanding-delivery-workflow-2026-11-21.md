# Proceso obligatorio de entrega y mantenimiento del roadmap NLU — 2026-11-21

**Estado:** política de contribución para PRs del programa de comprensión semántica.  
**Aplicación:** desde PR #292 en adelante.  
**Documento canónico de estado:** [roadmap maestro](player-understanding-roadmap-2026-11-21.md).

## 1. Regla fundamental

**Ninguna PR del programa se considera lista para merge si no actualiza el roadmap maestro.**

La documentación de roadmap no es un informe decorativo que se actualiza al final de la fase. Es un artefacto de control de alcance, dependencias, aceptación y trabajo restante.

Cada PR debe dejar visible qué objetivo aborda, qué entregables implementó realmente, qué entregables pospuso, qué criterios pasaron/fallaron, qué pruebas se ejecutaron, qué dependencias se cumplieron, qué bloqueos siguen abiertos y qué siguiente PR puede comenzar.

## 2. Ciclo de estado obligatorio

| Estado | Cuándo se usa |
|---|---|
| PLANNED | Todavía no hay implementación activa |
| IN PROGRESS | Existe rama/PR abierta o trabajo activo |
| BLOCKED | No puede continuar por dependencia o gate |
| IMPLEMENTED — PR OPEN | El contenido está implementado y la PR está en revisión, pero no fusionada |
| MERGED + VERIFIED | La PR está fusionada y todas las evidencias acordadas están disponibles |

No marcar MERGED + VERIFIED por tener checks verdes antes del merge. Tampoco marcar una capacidad como integrada si solo existe como módulo aislado.

## 3. Obligaciones en cada PR

### Antes de solicitar review

- [ ] Abrir rama desde el último main integrado.
- [ ] Identificar fila/hito exacto del roadmap maestro.
- [ ] Actualizar esa fila a IN PROGRESS.
- [ ] Enumerar alcance incluido y no incluido.
- [ ] Identificar building blocks existentes que se reutilizan.
- [ ] Mantener contratos históricos y compatibilidad explícitos.
- [ ] Añadir o actualizar criterios y pruebas del hito.
- [ ] Enlazar documentos técnicos nuevos o modificados.

### Antes de merge

- [ ] Actualizar la fila de la PR a IMPLEMENTED — PR OPEN, sin afirmar que ya está fusionada.
- [ ] Marcar individualmente entregables y criterios satisfechos.
- [ ] Registrar comandos y resultados de determinist CI aplicables.
- [ ] Registrar modelo, digest, Ollama version, options, corpus y reportes si hubo live calls.
- [ ] Registrar manual SillyTavern PASS/FAIL/NOT RUN, nunca inferirlo de CI.
- [ ] Describir fallos conocidos, límites y follow-ups.
- [ ] Actualizar el índice de documentación cuando se cree un documento vigente.
- [ ] Incluir la checklist de roadmap en el cuerpo de la PR.

### Después de merge

La siguiente PR del programa debe reconciliar las filas que quedaron en IMPLEMENTED — PR OPEN desde la última sincronización:
- Cambiar a MERGED + VERIFIED solo después de confirmar el merge.
- Registrar merge commit SHA y fecha.
- Verificar que enlaces y estado siguen correctos.
- No mantener tareas completadas duplicadas en otro roadmap.

Si no hay otra PR inmediata, se debe abrir una actualización documental de sincronización antes de declarar que el programa está reconciliado. No alterar un registro histórico para simular que se hizo esta actualización antes.

## 4. Política de criterios de aceptación

Cada hito debe tener objetivo verificable, condiciones previas/dependencias, cambios de código y paquetes afectados, pruebas deterministas, corpus/benchmark, gates negativos de seguridad, compatibilidad, observabilidad, resultado de integración y condición explícita de no-go.

Un PR puede estar implementado pero bloqueado por live evaluation. En ese caso el estado debe reflejarlo; no promoverlo como terminado.

## 5. Política de pruebas y evidencias

Separar siempre:

### Deterministic CI
Código, schemas, validadores, persistencia, seguridad, migraciones, cobertura y arquitectura.

### Live Ollama
Modelo/digest/version/options, calls, escenarios, métricas, latencia, tokens, output validity y fallos por escenario.

### SillyTavern manual
Ejecución real de conversación, continuidad, callbacks, citas, NPC, acción fallida, hechos, recuperación, regeneración y aislamiento de chats.

Un test real LLM exitoso no demuestra todos los escenarios de producto. Un shadow test no demuestra una ruta productiva. Una prueba unitaria de fact policy no demuestra integración transaccional.

## 6. Seguridad y privacidad

Los reportes adjuntos a PR deben ser agregados y no contener prompts/completions completas, conversaciones de campaña, secretos, contenido privado innecesario ni canonical IDs de campañas reales. Utilizar IDs de fixtures y códigos de error estables.

## 7. Cambios de alcance o numeración

La secuencia #293–#305 es la planificación vigente, no una afirmación de que esas PR ya existan. Antes de crear una PR:
- Comprobar números y ramas existentes.
- Reconciliar PRs abiertas de terceros o trabajo intermedio.
- Mantener dependencias y orden lógico.
- Actualizar enlaces del roadmap si hay renumeración.
- No saltar un gate por mantener el número previsto.

## 8. Plantilla para cada PR del programa

Incluir:
- **Roadmap:** enlace al hito y fila correspondiente.
- **Estado anterior / nuevo:** PLANNED → IN PROGRESS → IMPLEMENTED — PR OPEN.
- **Alcance realizado:** entregables concretos.
- **No realizado:** límites y diferidos explícitos.
- **Acceptance criteria:** tabla PASS / FAIL / NOT RUN.
- **Deterministic CI:** resultados.
- **Ollama:** modelo, digest, version, options, corpus, calls y métricas; o NOT RUN.
- **SillyTavern:** PASS / FAIL / NOT RUN.
- **Privacidad:** confirmación de que artefactos compartidos no incluyen prompts/completions/conversaciones privadas.
- **Siguiente paso:** hito habilitado y bloqueos.

Esta política se incorpora a AGENTS.md y al checklist general del repositorio por PR #292. Cualquier excepción requiere justificación explícita en el PR y actualización del roadmap.
