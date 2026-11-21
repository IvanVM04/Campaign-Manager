# Roadmap de prompts, runtime LLM y reproducibilidad Ollama — 2026-11-21

**Prioridad:** P0 para la evaluación v3; P1 para la optimización general del runtime.  
**Estado:** diseño y backlog; no afirma que las mejoras estén implementadas.  
**Roadmap maestro:** [comprensión semántica](../architecture/player-understanding-roadmap-2026-11-21.md).

## 1. Objetivo

Hacer comparables y diagnosticables las evaluaciones de intención, mecánicas, extracción y narrativa; mejorar el comportamiento del prompt sin sobreajustarlo a un pequeño holdout; y registrar el coste real de cada generación sin exponer contenido privado de campaña.

El sistema ya separa roles de proveedor, presupuestos de prompt y schemas estructurados. Esta hoja de ruta completa la reproducibilidad y experimentación.

## 2. Observación del proveedor actual

La implementación de Ollama inspeccionada utiliza una solicitud estructurada con:
- Modelo.
- Prompt.
- stream=false.
- JSON Schema en format para generación estructurada.
- think cuando está configurado.

El proveedor recoge telemetría de prompt bytes, duración, modelo devuelto, done reason, prompt_eval_count, eval_count y duraciones de Ollama cuando están disponibles.

La configuración por rol ya permite modelos, timeouts, presupuestos y think separados.

En la solicitud inspeccionada no se pasan explícitamente opciones generales de sampling como temperature, seed, top_p, top_k, num_predict o num_ctx. Antes de afirmar que el entorno usa valores por defecto concretos, consultar y registrar la configuración efectiva de Ollama/Modelfile y añadir una capa tipada de opciones si corresponde.

## 3. Contrato de configuración por rol

Crear un objeto inmutable y validado por rol para la configuración efectiva. Campos propuestos, sujetos al soporte de la versión de Ollama:

| Parámetro | Propósito |
|---|---|
| model | Modelo configurado |
| model digest | Artefacto inmutable observado en Ollama |
| temperature | Variabilidad de generación |
| seed | Reproducibilidad cuando el proveedor lo soporte |
| top_p / top_k | Muestreo, cuando proceda |
| num_predict | Límite de tokens generados |
| num_ctx | Contexto efectivo del modelo |
| think | Estado explícito de reasoning/thinking si el modelo lo soporta |
| timeout | Límite de espera de cada rol |
| format/schema | Contrato estructurado del rol |
| prompt version | Versión estática del prompt |
| schema version | Versión del DTO esperado |

No asumir que una opción tiene el mismo significado o soporte en todas las versiones/modelos. La configuración efectiva se valida contra el proveedor y se incluye en el manifiesto. No pasar nombres de opciones desconocidos silenciosamente.

La configuración debe permitir overrides por rol: intent, mechanics, extraction y narrative. La evaluación de intención no debe cambiar parámetros por accidente al modificar configuración narrativa.

## 4. Manifiesto reproducible de cada evaluación

Cada run debe registrar:
- Git commit exacto y clean/dirty state si puede conocerse.
- Modelo pedido y modelo devuelto.
- Model digest.
- Versión Ollama.
- Rol del proveedor.
- Generation options efectivas.
- Prompt template version.
- Schema contract version y fingerprint.
- Identificador del corpus/version/split.
- Configuración de thinking.
- Context budget y prompt bytes.
- Tokens reales de entrada/salida si el proveedor los devuelve.
- Latencia total y duraciones internas disponibles.
- Repetición/seed/selector de escenario.
- Resultado de procedencia SHA.

La versión del prompt y el fingerprint deben identificar la plantilla estática y schema, no obligar a copiar el prompt dinámico completo en los informes. Los datos específicos de un turno permanecen privados.

## 5. Versionado y experimentación de prompts

Cada rol debe tener un identificador versionado explícito. Un cambio semántico sustancial incrementa versión y genera comparación con la anterior.

Para intent:
- Mantener un único prompt holístico que cubra todos los planos interdependientes.
- Distinguir instrucciones de confianza, contrato semántico, reglas de evidencia y ejemplos.
- Usar ejemplos contrastivos mínimos: un par correcto/incorrecto que muestre la distinción concreta.
- Evitar listas largas duplicadas de prohibiciones.
- Evitar ejemplos literales del holdout.
- Explicar cuándo devolver arrays vacíos y cuándo una aclaración es material.
- No premiar la omisión excesiva: precision y recall se miden juntos.

Para extraction:
- Tratar la interpretación validada como input de referencia.
- No reinterpretar la frase original como un segundo modelo de intención.
- Mantener operaciones limitadas por schema, allowlist, contexto y evidencia.
- Reparación limitada y validada; nunca aceptar una operación abreviada o incompleta como sustituto.

Para mechanics:
- Recibir solo acción y contexto mecánico validados.
- El motor determinista conserva autoridad sobre dados y consecuencias.
- No pedir al adjudicador que vuelva a decidir la intención del jugador.

Para narrative:
- Consumir solo evidencia y operaciones confirmadas.
- No cambiar estado ni fabricar resultados mecánicos.

## 6. Presupuesto y compresión del contexto

Los budgets expresados en bytes UTF-8 son una cota útil, pero no un tokenizer exacto. El consumo de tokens cambia según idioma, JSON, nombres, puntuación y modelo.

Para cada request registrar prompt bytes antes/después de compresión, tokens reales cuando Ollama los reporte, tokens de completion, secciones incluidas, secciones eliminadas/reducidas y orden de compresión, referencias obligatorias conservadas, y si se rechazó el request por exceder el presupuesto.

Reglas:
- La evidencia del jugador nunca se trunca silenciosamente.
- La evidencia obligatoria no se elimina para mantener el presupuesto.
- El contexto histórico/discurso es degradable, pero se informa qué sección se redujo.
- No borrar entidad obligatoria ni dependencia requerida para una propuesta.
- No compactar la interpretación semántica canónica.
- Fallar explícitamente cuando los datos obligatorios exceden el presupuesto.

El estimador actual basado en bytes debe seguir nombrándose como estimación/cota, no como token count exacto.

## 7. Telemetría y privacidad

Eventos recomendados:
- provider.request.started
- provider.request.completed
- provider.request.failed
- llm.role.validation_failed
- llm.role.normalization_applied
- llm.role.prompt_compacted
- llm.role.output_accepted

Campos seguros: correlation/request ID, provider role, model/digest, options version, prompt/schema version, prompt bytes, token counts, duration, error type/code, validation stage/field, record counts, normalization rule IDs, context section sizes y omitted-section IDs.

No registrar en logs generales prompts, completions, texto de campaña, secretos, narrativa privada, spans literales ni IDs canónicos salvo necesidad justificada y protegida. Los informes agregados deben seguir siendo seguros para compartir.

## 8. Experimentos de modelo

No cambiar de modelo por intuición. PR #296 debe ejecutar un experimento controlado:
- Modelo actual Gemma 4 12B Q4_K_M como baseline.
- Alternativas locales razonables seleccionadas según VRAM/latencia disponible.
- Mismo corpus, split, contexto, prompt, schema y generation options siempre que el modelo lo soporte.
- Registrar diferencias de soporte de JSON Schema, thinking y opciones.
- Repetir casos críticos.
- Comparar graph exact match, precision, recall, validación, false writes, tokens, latencia y estabilidad.

La comparación diferencia mejora semántica, validez JSON, recall, latencia, tokens y tamaño de salida. No asumir que el modelo más grande gana; tampoco que el modelo más rápido es suficiente.

## 9. Latencia y estrategia de evaluación

Los ocho tests live más lentos del run 21/11 acumulan ~2470 s, un 92,7 % de la suite. Language holdout tarda 1000 s y semantic-frame holdout 530,84 s.

Crear tres perfiles:
1. Quick diagnostic con filtro de escenario y pocas repeticiones.
2. Full evaluation secuencial/configurada con corpus completo y repeticiones críticas.
3. Acceptance run congelado con manifiesto y resultados por escenario.

No paralelizar agresivamente solicitudes al mismo Ollama sin experimento explícito. La contención de GPU/CPU y la carga del modelo pueden cambiar latencia y estabilidad.

## 10. PR responsables

- PR #293 incorpora run manifest, telemetry gap analysis y generation options reproducibles.
- PR #294 optimiza prompt v3 y estrategia de evidence alignment.
- PR #296 compara modelos/parámetros y aprueba gates de aceptación.
- PRs posteriores mejoran ranking/retrieval si los informes demuestran que es necesario.

La actualización del roadmap maestro y el estado de cada PR son parte obligatoria de su checklist de merge.
