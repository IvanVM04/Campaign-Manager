# Auditoría global del proyecto — 2026-11-19

**Repositorio:** `IvanVM04/Campaign-Manager`  
**Baseline verificado:** `main` — `8276450babba6611a172e601d0c76b83ae8e449e` (PR #269 integrada).  
**Alcance:** arquitectura, comprensión de lenguaje, calidad automática, evaluación LLM, integración SillyTavern, documentación y avance respecto a los requisitos de producto v0.2.  
**Método:** inspección del árbol y documentación de `main`, PRs #267–#269, estado de GitHub Actions y resumen de cobertura publicado por CI. No se ha ejecutado una instancia local de Ollama ni una sesión manual de SillyTavern durante esta auditoría.

> Esta auditoría es la fotografía vigente a 2026-11-19. Los informes fechados anteriormente conservan su baseline histórico; no deben reinterpretarse como resultados del commit actual.

## 1. Dictamen ejecutivo

**La dirección técnica es correcta. No se recomienda una reescritura ni un cambio de arquitectura de alto nivel.** El monolito modular, la única interpretación estructurada de Intent y la autoridad determinista del backend siguen siendo una base razonable para el alcance local y de una persona usuaria.

El trabajo del 19 de noviembre ha cerrado tres hitos arquitectónicos consecutivos:

- #267 separa la normalización de Intent del orquestador.
- #268 divide selección discursiva, extracción de menciones, señales de hablante y renderizado detrás de una fachada compatible.
- #269 separa extracción de evidencias y ranking de referencias, formaliza la abstención y añade un runner PowerShell reproducible para pruebas de Ollama.

El resultado es una base más fácil de inspeccionar y probar, pero **no demuestra todavía que el modelo comprenda correctamente una partida real**. La aceptación de calidad del modelo y de SillyTavern continúa pendiente.

La prioridad debe cambiar ahora de extracción estructural a medición fiable: corregir el evaluador antes de comparar NLP, calibrar incertidumbre o retocar prompts.

## 2. Baseline verificado en GitHub

| Elemento | Estado |
|---|---|
| Rama principal | `main` |
| Commit | `8276450babba6611a172e601d0c76b83ae8e449e` |
| PRs #267, #268 y #269 | Integradas |
| CI determinista del commit actual | Correcta |
| CodeQL | Correcto |
| Ruff | Correcto |
| Pyright obligatorio y de repositorio | Correcto |
| Tests JavaScript | Correctos |
| Pruebas live `real_llm` | 22 excluidas de CI; no ejecutadas por este workflow |
| Aceptación manual SillyTavern | Pendiente de evidencia |

### 2.1 Ejecución de CI sobre el SHA actual

- Workflow Tests: [run #44546831896](https://github.com/IvanVM04/Campaign-Manager/actions/runs/44546831896).
- Workflow CodeQL: [run #44546832517](https://github.com/IvanVM04/Campaign-Manager/actions/runs/44546832517).
- Python: **2.188 passed, 22 deselected**, de 2.210 casos recogidos.
- Duración reportada de la suite Python: **290,41 s** (4 min 50 s).
- Cobertura combinada de líneas y ramas: **85,23 %**.
- Cobertura de líneas: **88,8 %**.
- Cobertura de ramas: **75,9 %**.
- Gate configurado: **85 % combinado**; margen actual: **0,23 puntos porcentuales**.

La cobertura combinada no significa que las ramas estén cubiertas al 85 %. El 75,9 % de cobertura de ramas sigue justificando pruebas dirigidas a rutas de error y recuperación. El margen de 0,23 puntos también es estrecho: cualquier cambio puede hacer caer el gate si no añade cobertura proporcional.

Los 22 casos excluidos son pruebas marcadas `real_llm`; no son fallos de CI. La suite verde demuestra consistencia de los contratos deterministas, no exactitud semántica del modelo.

## 3. Avance por áreas

### 3.1 Arquitectura NLU

| Hito | Estado | Evidencia |
|---|---|---|
| #267 — frontera de normalización de Intent | Integrado | Pipeline tipado, orden explícito y diagnósticos sin texto sensible |
| #268 — colaboradores de discurso | Integrado | Selector de topic/history, extractor de menciones, señales de hablante y renderer |
| #269 — evidencia y ranking de referencias | Integrado | Bundle tipado, procedencia, ranking estable, márgenes y abstención |
| #270 — evaluación semántica completa | Pendiente | Debe contar pasos/campos omitidos y extra, con denominadores explícitos |
| #271 — piloto NLP offline | Pendiente / opcional | Solo si el evaluador fiable identifica un hueco que justifique el coste |
| #272 — incertidumbre y checkpoints | Pendiente | Requiere datos fiables para calibrar señales y diseñar reanudación durable |
| #273 — benchmark y aceptación integral | Pendiente | Ollama fijado, holdouts repetidos y smoke test real de SillyTavern |

Por número de hitos, se han completado **3 de 7 (43 %)**. Es una métrica de entregables del roadmap NLU, no un porcentaje de comprensión del lenguaje ni del proyecto completo.

### 3.2 Calidad automática

La base de CI es sólida: tests deterministas, lint, tipos, JavaScript, CodeQL y cobertura combinada obligatoria están verdes en el SHA actual.

La mejora siguiente no es perseguir más cobertura global, sino cubrir rutas de alto riesgo: errores de proveedor, recuperación de turnos, conflictos de revisión, clarificaciones, tiradas manuales, visibilidad, referencias ambiguas y fallos entre validación y commit.

### 3.3 Calidad real del modelo

Estado: **no aceptada todavía**.

La última evidencia compartida de Ollama anterior a esta fase no equivale a una evaluación posterior a #267–#269. El nuevo runner simplifica la repetición y produce resultados agregados sin copiar prompts, completions ni mensajes de error, pero incorporarlo no significa que ya se haya ejecutado.

Falta un baseline live comparable que mida, como mínimo:

- categoría, número exacto y orden de pasos;
- actor, modalidad, polaridad y resultado reportado por paso;
- predicado, familia de acción, argumentos y roles;
- dirección y polaridad de relaciones;
- atribución y grounding de evidencia;
- precisión/recall de referencias y motivos de abstención;
- propuestas persistentes falsas y filtraciones de secretos;
- fallos de parseo, latencia P50/P95 y llamadas por turno.

Los casos críticos deben repetirse al menos tres veces con modelo/digest, versión de Ollama, prompt, parámetros de generación y hardware registrados.

### 3.4 Integración SillyTavern

El adaptador y el checklist de aceptación están documentados; no hay evidencia en esta auditoría de que se haya completado la lista manual sobre el SHA actual.

No marcar como aceptados por CI los casos de regeneración, entrega duplicada, chat aislado, aclaraciones multi-ronda, tiradas manuales, reinicio/recuperación y continuidad del mundo.

### 3.5 Alcance de producto

El inventario v0.2 declara **71 requisitos funcionales y 20 no funcionales**. Al agrupar los estados escritos en las 71 filas funcionales:

| Estado del inventario | Requisitos | Porcentaje |
|---|---:|---:|
| Implementado | 22 | 31,0 % |
| Parcial | 21 | 29,6 % |
| Pendiente | 27 | 38,0 % |
| Estado no binario / objetivo de política | 1 | 1,4 % |
| **Total** | **71** | **100 %** |

Una aproximación ponderada —implementado = 1, parcial = 0,5 y pendiente = 0— da **45,8 %**. Es una referencia orientativa basada en las etiquetas de producto del documento, no una certificación nueva requisito por requisito sobre el SHA #269. Los 20 requisitos no funcionales expresan criterios/condiciones de aceptación y no se convierten en un porcentaje sin una revisión individual.

Las áreas de mayor brecha de producto siguen siendo: compendio consultable del mundo, referencias inline, selección de contexto por el jugador, ficha y progresión completa, control de varios PJ, delegación de NPC, más amplitud de reglas, módulos declarativos, import/export de campañas, internacionalización y UI propia.

## 4. Hallazgos y riesgos priorizados

### P0 — El evaluador no mide todavía todos los errores importantes

La auditoría NLU detecta que el scorer general no exige consistentemente el número exacto de pasos ni contabiliza todos los claims/slots extra. El corpus compuesto tampoco dispone aún de gold completo para predicados, marcos, argumentos, outcomes y atribución.

**Riesgo:** métricas optimistas que oculten pasos inventados o semántica adicional incorrecta.

**Acción:** completar el scorer antes de usarlo para comparar modelos, reglas o un parser externo. Publicar TP/FP/FN y denominadores por familia.

### P0 — No existe aceptación live posterior a la secuencia #267–#269

**Riesgo:** confundir una arquitectura más clara con una mejora demostrada de comprensión.

**Acción:** preparar el corpus, el runner y los criterios; ejecutar el gate completo solamente después de #270–#272.

### P0/P1 — No se ha acreditado el recorrido completo de SillyTavern

**Riesgo:** fallos de protocolo, recuperación o continuidad que los tests unitarios y de integración simulados no detecten.

**Acción:** completar el checklist manual con SHA del backend/extensión y configuración exacta de Ollama. Registrar cada caso como pasado, fallido o no ejecutado.

### P1 — Cobertura de ramas y margen del gate

El 85,23 % combinado supera el mínimo, pero solo por 0,23 puntos; la cobertura de ramas es 75,9 %.

**Acción:** no reducir el gate ni excluir producción. Elegir ramas por riesgo y mantener el reporte por paquete.

### P1 — Amplitud funcional inferior a la base técnica

La infraestructura durable y las barreras de seguridad están más avanzadas que la experiencia jugable completa.

**Acción:** después de aceptar NLU e integración, priorizar un vertical slice de aventura que atraviese personaje, equipo, NPC, prueba, combate, descanso, recompensa y persistencia.

### P1 — Fuentes documentales desincronizadas

El roadmap y algunos mapas aún reflejan el estado de #266/#268 o dicen que #269 está en curso.

**Acción:** declarar un único baseline actual, dejar los informes antiguos como históricos y enlazar desde `docs/README.md` esta auditoría, el mapa actual y la hoja de ruta vigente.

## 5. Decisión arquitectónica

### Mantener

- Monolito modular y composición centralizada.
- Una única interpretación estructurada y coherente de Intent.
- Normalización y validación deterministas con contratos tipados.
- Evidencia de mensaje actual separada de historial y narración.
- Identidad canónica, visibilidad, permisos, mecánicas, mutación y persistencia bajo autoridad del backend.
- Clarificación/abstención ante ambigüedad real.
- Una sola fuente canónica de estado y un commit durable de consecuencias.

### No introducir todavía

- Microservicios, colas, varios workers o locks distribuidos.
- Vector DB, segundo almacén de memoria o embeddings por anticipación.
- Varias llamadas LLM para separar campos que dependen entre sí.
- spaCy/Stanza como dependencia de producción sin resultado medido.
- Reescritura amplia de prompts guiada por ejemplos que se usarán después como holdout.

La extracción de colaboradores debe justificarse por ownership y contratos, no por alcanzar un número arbitrario de líneas por archivo.

## 6. Roadmap actualizado

Se cambia el orden de los dos siguientes hitos: **el evaluador debe preceder al piloto NLP**. La arquitectura establece expresamente que la evaluación debe corregirse antes de tunear; el piloto necesita un scorer fiable para producir una comparación útil.

1. **#270 — Completar evaluación semántica.** Gold independiente por paso/campo, exactitud de número de pasos, extras como falsos positivos, TP/FP/FN, métricas por familia y esquema estable de resultados.
2. **#271 — Piloto NLP offline, opcional.** Comparar baseline, parser, modelo y modelo+señales con el scorer ya corregido. Medir español, elipsis, clíticos, citas, negación, condicionales, nombres, vocabulario fantástico, latencia, CPU, empaquetado y licencia. No adoptar dependencia de producción si el beneficio neto no es claro.
3. **#272 — Incertidumbre y checkpoints.** Calibrar con resultados de evaluación; guardar pasos/slots resueltos, evidencia, dependencias y dudas; reanudar sin repetir consecuencias.
4. **#273 — Aceptación integral.** Benchmark Ollama con configuración fijada, críticos ×3, cero falsos cambios persistentes críticos, cero filtraciones y checklist manual SillyTavern.

Después del gate #273: corregir las familias de error observadas, auditar rutas críticas de workflows y entregar un vertical slice jugable. La UI propia se puede investigar/prototipar cuando los contratos estén suficientemente estables, sin bloquearla hasta que esté implementada toda la 5e.

## 7. Estimación de esfuerzo restante

Estimaciones de ingeniería para una persona, en horas de trabajo efectivo. Son rangos de planificación, no horas registradas ni compromisos; excluyen esperas de inferencia, descargas de modelos y el tiempo que el usuario dedique a ejecutar y validar la partida.

| Trabajo | Estimación | Dependencia |
|---|---:|---|
| #270 — Evaluador completo | 16–28 h | Ya se puede iniciar |
| #271 — Piloto NLP opcional | 8–16 h | Después de #270; se puede omitir |
| #272 — Incertidumbre/checkpoints | 24–40 h | #270; diseño de #271 si aporta evidencia |
| #273 — Preparar/analizar aceptación integral | 10–18 h | #270–#272 |
| **Total con piloto** | **58–102 h** | Más correcciones según resultados live |
| **Total sin piloto** | **50–86 h** | Si no se demuestra necesidad del parser |
| Vertical slice jugable posterior | 60–100 h | Gate NLU/integración cerrado |

El trabajo de producto más amplio (UI propia, reglas completas, import/export, multi-PJ, delegación, compendio e internacionalización) no debe reducirse a una cifra única hasta dividirlo en historias y criterios de aceptación. Es un alcance de varias iteraciones, no una PR final.

## 8. Próximos pasos concretos

1. Integrar esta reconciliación documental sin tocar código productivo.
2. Implementar #270: hacer que el evaluador penalice omisiones y extras con gold independiente.
3. Decidir #271 usando evidencia; cancelarlo o mantenerlo pequeño si no hay una carencia lingüística demostrada.
4. Diseñar #272 a partir de métricas fiables y mantener invariantes de permisos/commit.
5. Preparar #273 con configuración reproducible y aceptación manual.
6. Congelar tuning general de prompts hasta disponer de resultados desglosados.
7. Al cerrar NLU, cambiar el centro de gravedad a workflows de juego completos y producto.

## 9. Enlaces de evidencia

- [PR #267 — frontera de normalización](https://github.com/IvanVM04/Campaign-Manager/pull/267)
- [PR #268 — colaboradores de discurso](https://github.com/IvanVM04/Campaign-Manager/pull/268)
- [PR #269 — evidencia y ranking conversacional](https://github.com/IvanVM04/Campaign-Manager/pull/269)
- [Tests CI — main #8276450](https://github.com/IvanVM04/Campaign-Manager/actions/runs/44546831896)
- [CodeQL — main #8276450](https://github.com/IvanVM04/Campaign-Manager/actions/runs/44546832517)
- [Arquitectura NLU](player-language-understanding-architecture-2026-11-19.md)
- [Requisitos de producto v0.2](../product/product-requirements-2026-11-18.md)
- [Smoke test SillyTavern](../sillytavern-smoke-test.md)
