# Requisitos de producto — Campaign Manager

**Versión:** 0.1 — baseline de requisitos  
**Fecha:** 2026-11-18  
**Baseline de código:** `main` — `f4fb3914ebab4579118863796e6f6d4b7183d0cf` (PR #255)  
**Estado:** documento inicial; debe evolucionar con decisiones explícitas de producto.

> Este documento define qué producto queremos construir y separa los requisitos de las capacidades que el repositorio implementa hoy. Que un requisito aparezca aquí no significa que esté terminado ni que haya superado una prueba con Ollama/SillyTavern.

## 1. Visión y propósito

Campaign Manager aspira a ser un **Dungeon Master de IA para campañas de D&D 5e**, centrado en una experiencia de un solo jugador. La persona describe en lenguaje natural lo que su personaje intenta hacer; la aplicación interpreta esa intención, recupera el contexto relevante de la campaña, adjudica las reglas aplicables, valida las consecuencias, conserva el estado y genera una respuesta narrativa coherente.

El producto debe combinar libertad narrativa con un núcleo de juego fiable. La IA no debe poder inventar resultados mecánicos, hechos persistentes ni conocimientos de personajes que no estén respaldados por la campaña.

### Objetivos

1. Mantener una o varias campañas independientes y persistentes en una instalación local.
2. Permitir jugar mediante lenguaje natural, sin exigir al jugador que conozca comandos internos o estructuras JSON.
3. Mantener continuidad entre turnos, sesiones y conversaciones, sin mezclar campañas o chats.
4. Aplicar de forma determinista las reglas que estén implementadas.
5. Permitir que la IA interprete y narre, pero mantener bajo control del backend los permisos, la validación y la persistencia.
6. Hacer que los fallos, reintentos, aclaraciones y regeneraciones no dupliquen consecuencias.
7. Poder evaluar objetivamente la calidad de interpretación del modelo y detectar regresiones.

### Principios de producto

- **La ficción puede ser flexible; el estado persistente no.**
- **La IA propone; la aplicación valida y decide qué se guarda.**
- **El historial aporta contexto, no evidencia nueva del mensaje actual.**
- **La incertidumbre se expresa o se pregunta; no se rellena con invenciones.**
- **Las reglas no implementadas se reconocen como tales.**
- **Una narración generada nunca puede contradecir silenciosamente un resultado mecánico ya confirmado.**

## 2. Usuarios, roles y autoridad

El alcance inicial es de una persona usuaria que gestiona sus propias campañas. La IA actúa como Dungeon Master. SillyTavern es el cliente de conversación de referencia; la API también permite clientes nativos y pruebas.

| Actor | Responsabilidad | Límites |
|---|---|---|
| Jugador | Decide las intenciones, acciones, diálogo y elecciones de su personaje jugador. | No puede declarar unilateralmente resultados mecánicos ni controlar el resto del mundo. |
| Dungeon Master de IA | Interpreta la ficción, controla el mundo y los NPC no delegados, decide cuándo pedir una prueba y produce narración. | No puede sobreescribir reglas resueltas, inventar datos persistentes ni saltarse validaciones. |
| Motor de reglas | Calcula los resultados de las mecánicas D&D soportadas. | Solo resuelve reglas implementadas y explícitamente soportadas. |
| Backend | Aplica permisos, valida operaciones, controla transacciones, revisiones y persistencia. | No delega autoridad de escritura al modelo. |
| Cliente (SillyTavern/API) | Envía mensajes, presenta narración y devuelve resultados de interacción. | No es autoridad sobre el estado canónico de campaña. |

Un jugador puede recibir permiso explícito para interpretar determinados NPC. Ese permiso no implica control del resto del mundo ni conocimiento de hechos que el NPC no podría conocer.

## 3. Alcance del producto

### Incluido en el alcance inicial

- Aplicación local, de un solo jugador y de un solo proceso.
- Varias campañas separadas en la misma instalación.
- Persistencia local mediante SQLite y migraciones versionadas.
- Backend HTTP/API y flujo de conversación integrado con SillyTavern.
- Proveedor LLM local mediante Ollama.
- Estado de campaña, sesiones, personajes, mundo, entidades, NPC, objetos, eventos, relaciones y recursos.
- Interpretación estructurada de intenciones y consecuencias validadas.
- Un subconjunto determinista y ampliable de D&D 5e de 2014.
- Historial, recuperación de contexto, continuidad y flujo durable de turnos.

### Fuera del alcance inicial

- Multijugador, cuentas de usuario, membresías y campañas compartidas.
- Exposición remota, hosting público, túneles o acceso desde redes no confiables.
- VTT, mapas tácticos, tokens, niebla de guerra o movimiento en tiempo real.
- Implementación completa de todas las reglas de D&D 5e.
- Reglas de la revisión 2024 mezcladas con el conjunto de reglas 2014.
- Una interfaz gráfica independiente completa antes de estabilizar el ciclo de juego.
- Sustituir la arquitectura actual por microservicios, colas distribuidas o infraestructura de varios nodos sin una necesidad demostrada.

## 4. Requisitos funcionales

Los estados de implementación se refieren al código inspeccionado en el baseline de este documento:

- **Implementado:** hay una ruta de producción y contratos/tests que la protegen.
- **Parcial:** existe una base funcional, pero la capacidad o su aceptación no está cerrada.
- **Pendiente:** forma parte del producto deseado, pero todavía requiere implementación.
- **Fuera:** no forma parte del alcance inicial acordado.

### 4.1 Campañas y sesiones

| ID | Requisito | Estado |
|---|---|---|
| FR-CAM-01 | La persona usuaria podrá crear y listar varias campañas independientes. | Implementado |
| FR-CAM-02 | Las operaciones de campaña estarán siempre asociadas a una campaña explícita; no habrá fallback silencioso a una campaña por defecto. | Implementado |
| FR-CAM-03 | Cada campaña conservará su estado, sesión activa, reloj, mundo e historial de forma independiente. | Parcial |
| FR-CAM-04 | La persona usuaria podrá consultar el estado y cambiar el personaje activo dentro de la campaña. | Implementado |
| FR-CAM-05 | La aplicación conservará los datos al reiniciarse y evolucionará el esquema mediante migraciones controladas. | Implementado |

### 4.2 Personajes, mundo e inventario

| ID | Requisito | Estado |
|---|---|---|
| FR-WLD-01 | La campaña conservará entidades del mundo, incluidos NPC, localizaciones, objetos, eventos, relaciones y recursos. | Parcial |
| FR-WLD-02 | Los objetos y recursos mantendrán identidad y propiedad suficientes para distinguir definiciones, instancias y cantidades. | Parcial |
| FR-WLD-03 | Los hechos podrán tener alcance/visibilidad; los secretos y hechos no conocidos por el personaje no se filtrarán a sus proyecciones. | Implementado en las proyecciones player-safe existentes |
| FR-WLD-04 | La aplicación conservará el historial de hechos y distinguirá hechos actuales de hechos reemplazados o superados. | Parcial |
| FR-CHR-01 | El personaje tendrá estado canónico y una proyección legible de su ficha. | Parcial |
| FR-CHR-02 | Se podrá crear un personaje completo mediante opciones tipadas de especie/raza, clase, trasfondo, características y competencias. | Pendiente |
| FR-CHR-03 | La progresión de nivel, rasgos de clase y recursos se reflejará en el estado y en las reglas. | Pendiente |
| FR-INV-01 | Inventario, equipo, propiedad, consumibles y recursos tendrán consecuencias coherentes en el mundo y las mecánicas. | Parcial |

### 4.3 Comprensión del lenguaje y continuidad

| ID | Requisito | Estado |
|---|---|---|
| FR-AI-01 | Interpretar un mensaje en una representación estructurada común que identifique categoría, pasos, actor, modalidad, polaridad y evidencia literal. | Implementado a nivel de contrato; calidad live pendiente |
| FR-AI-02 | Reconocer mensajes con varios pasos y preservar su orden, actor y modalidad de forma independiente por paso. | Parcial; evaluación determinista añadida, evaluación con el modelo pendiente |
| FR-AI-03 | Distinguir acciones, diálogo en ficción, preguntas al DM, observaciones, reportes, planes, condicionales, incertidumbre y negaciones. | Parcial |
| FR-AI-04 | Extraer argumentos de acciones (agente, tema, destinatario, instrumento, origen, destino, etc.) y relaciones dirigidas entre entidades. | Parcial |
| FR-AI-05 | Mantener las menciones, predicados y argumentos del mensaje actual anclados literalmente a la evidencia actual. | Implementado como límite de validación |
| FR-AI-06 | Usar el historial de la conversación para interpretar elipsis, pronombres y callbacks, sin convertirlo en evidencia nueva del jugador. | Parcial |
| FR-AI-07 | Resolver referencias solo contra entidades visibles y activas, con evidencia suficiente; ante ambigüedad real, abstenerse o pedir aclaración. | Implementado de forma acotada; calidad semántica live pendiente |
| FR-AI-08 | Mantener aislados el historial de chats y las campañas, evitando contaminación entre conversaciones. | Parcial; contratos deterministas existentes, aceptación manual pendiente |
| FR-AI-09 | Permitir corregir de forma explícita un dato pendiente sin reescribir campos no corregidos ni modificar resoluciones ya confirmadas. | Implementado en el flujo durable; calidad live pendiente |
| FR-AI-10 | Respetar la perspectiva y el conocimiento de cada personaje/NPC. | Parcial; proveniencia tipada para eventos, no para todos los campos de texto libres |

### 4.4 Reglas y adjudicación

| ID | Requisito | Estado |
|---|---|---|
| FR-RUL-01 | Resolver de forma determinista las mecánicas D&D 5e 2014 que estén implementadas. | Parcial |
| FR-RUL-02 | Soportar pruebas de característica, habilidades y salvaciones dentro del conjunto implementado. | Parcial |
| FR-RUL-03 | Soportar el primer ciclo de combate implementado: iniciativa, ataques, daño, puntos de golpe, condiciones, salvaciones contra muerte y movimiento seleccionado. | Parcial |
| FR-RUL-04 | Diferenciar acciones rutinarias de acciones inciertas con consecuencias significativas; no pedir tiradas innecesarias. | Parcial |
| FR-RUL-05 | Permitir resolución automática o entrada manual de tiradas cuando el flujo lo requiera. | Parcial |
| FR-RUL-06 | No inventar reglas, modificadores, CDs ni resultados para sistemas no implementados; indicar la limitación o pedir intervención. | Objetivo obligatorio para cada nueva familia de reglas |
| FR-RUL-07 | Mantener aislada la implementación 2014 para permitir un ruleset futuro sin mezclar sus reglas. | Parcial |

### 4.5 Consecuencias, turnos y narración

| ID | Requisito | Estado |
|---|---|---|
| FR-TUR-01 | Un mensaje podrá iniciar una resolución durable identificada por un ID externo estable y una versión. | Implementado |
| FR-TUR-02 | El backend preparará una resolución, comprobará la revisión del estado y validará las consecuencias antes de confirmarlas. | Implementado |
| FR-TUR-03 | Las operaciones propuestas por la IA se validarán contra esquemas, permisos, visibilidad, reglas y estado de campaña antes de aplicarse. | Implementado |
| FR-TUR-04 | El commit de consecuencias y el registro durable de resolución se realizarán de forma atómica. | Implementado |
| FR-TUR-05 | Reentregar el mismo turno no duplicará daño, objetos, eventos, recursos ni otras consecuencias. | Implementado a nivel de contrato; aceptación ST pendiente |
| FR-TUR-06 | Una aclaración o tirada manual pendiente podrá continuar la resolución original, incluso tras reinicio. | Implementado a nivel de contrato; aceptación ST pendiente |
| FR-TUR-07 | La narración se generará después de confirmar las consecuencias. | Implementado |
| FR-TUR-08 | Regenerar una narración creará una versión narrativa nueva sin repetir mecánicas ni aplicar las consecuencias otra vez. | Implementado a nivel de contrato; aceptación ST pendiente |
| FR-TUR-09 | Un fallo de proveedor o de narración podrá reintentarse sin dejar una resolución parcialmente aplicada. | Parcial; contratos deterministas existentes, aceptación manual pendiente |
| FR-TUR-10 | Los pasos negativos, hipotéticos, interrogativos o no confirmados no se convertirán en cambios persistentes. | Implementado como límite de autorización; la precisión del modelo sigue en evaluación |

### 4.6 Integración, consulta y operación

| ID | Requisito | Estado |
|---|---|---|
| FR-INT-01 | SillyTavern podrá proporcionar el contexto actual y el transcript filtrado del chat. | Implementado |
| FR-INT-02 | La integración usará el ciclo durable resolve/complete y no una ruta paralela de escritura narrativa. | Implementado |
| FR-INT-03 | El backend expondrá endpoints para campañas, personajes, turnos, tiradas, memoria, mundo e integración. | Implementado con cobertura funcional desigual |
| FR-INT-04 | La persona usuaria podrá consultar memoria/contexto recuperado y exportar datos player-safe. | Parcial |
| FR-OPS-01 | Los fallos técnicos podrán diagnosticarse mediante logs estructurados y correlación de request/campaign/resolution sin almacenar prompts o narraciones privadas. | Implementado |
| FR-OPS-02 | Los cambios de esquema conservarán compatibilidad con las versiones de datos históricas soportadas. | Implementado mediante migraciones; ampliar pruebas con nuevas versiones |

## 5. Requisitos no funcionales

| ID | Requisito | Criterio de aceptación |
|---|---|---|
| NFR-REL-01 | Persistencia coherente ante fallos. | Ningún fallo entre validación y commit deja una aplicación parcial de las consecuencias. |
| NFR-REL-02 | Idempotencia y recuperación. | Reintentos, entregas duplicadas, reinicios y regeneraciones no duplican efectos. |
| NFR-REL-03 | Aislamiento de campañas y chats. | Una conversación nunca lee ni modifica datos de otra campaña/chat por una coincidencia de IDs locales. |
| NFR-SEC-01 | El modelo se considera entrada no confiable. | Ninguna salida LLM puede escribir directamente en SQLite ni saltarse validación de dominio. |
| NFR-SEC-02 | Separación de secretos. | Cero filtraciones de eventos secretos, notas GM o datos no conocidos por el personaje en respuestas/proyecciones player-safe. |
| NFR-SEC-03 | Exposición local segura. | El servidor permanece ligado a loopback por defecto; cualquier acceso remoto requiere autenticación/autorización y revisión de seguridad separadas. |
| NFR-PRV-01 | Privacidad de telemetría. | Los logs y reportes live solo guardan campos allowlisted; no prompts, completions, mensajes, narrativas, secretos ni credenciales. |
| NFR-DAT-01 | Integridad y evolución de datos. | Cambios del esquema se realizan mediante migraciones versionadas y pruebas de upgrade compatibles. |
| NFR-PER-01 | Presupuestos de contexto y proveedor. | Prompts completos y reparaciones están acotados; los timeouts y tamaños se diagnostican. Los objetivos numéricos de latencia se fijarán tras medir hardware/modelos reales. |
| NFR-OBS-01 | Diagnóstico reproducible. | Cada evaluación live identifica commit, modelo/digest, versión Ollama, configuración relevante, llamadas y latencias sin conservar contenido sensible. |
| NFR-TEST-01 | Separación de pruebas. | CI determinista no depende de Ollama ni de la red; los evaluadores live y la aceptación manual son gates separados. |
| NFR-MNT-01 | Mantenibilidad. | Se preserva el monolito modular, la composición en bootstrap y las dependencias permitidas entre paquetes. |
| NFR-CMP-01 | Compatibilidad de reglas. | Cada regla declara su ruleset y alcance; no se mezclan automáticamente reglas 2014 y 2024. |

## 6. Reglas de aceptación global

Una capacidad no se considera terminada por tener un prompt, una clase o un test unitario. Debe cumplir los gates aplicables:

1. **Contrato:** entradas, salidas, errores y autoridad están tipados y documentados.
2. **Validación:** datos no confiables son validados en el backend; los casos ambiguos fallan de forma segura.
3. **Prueba determinista:** hay tests positivos, negativos, límites y casos de recuperación.
4. **Evaluación de modelo:** cuando interviene un LLM, hay casos held-out independientes y métricas por familia/campo.
5. **Persistencia:** las operaciones stateful prueban rollback, reintento, duplicados y recuperación.
6. **Seguridad:** no hay falsos cambios persistentes críticos ni filtraciones de secretos.
7. **Integración:** el flujo real del cliente de referencia se prueba cuando el cambio afecta a SillyTavern.
8. **Documentación:** el estado implementado/parcial/pendiente queda actualizado sin reescribir auditorías históricas.

### Gates de aceptación de la primera versión jugable

- Campaña y personaje seleccionados correctamente.
- Exploración, diálogo y acciones básicas sobre el mundo.
- Tiradas y mecánicas soportadas coherentes con la ficha.
- Un encuentro de combate completo dentro del subconjunto implementado.
- Inventario/recompensas y descanso básico.
- Clarificaciones y tiradas manuales continuables.
- Persistencia entre turnos, sesiones y reinicios.
- Regeneración y reintentos sin duplicar consecuencias.
- Dos chats aislados sin contaminación.
- Cero cambios persistentes críticos falsos y cero filtraciones de secretos en los held-out críticos y las pruebas de operación.

## 7. Hitos de producto propuestos

| Hito | Resultado observable | Dependencias principales |
|---|---|---|
| M0 — Base fiable | CI verde, contratos estables, evaluación live reproducible y aceptación SillyTavern registrada. | Calidad del modelo, recuperación e integración. |
| M1 — Primer ciclo jugable | Crear/usar un personaje, explorar, hablar, realizar pruebas, combatir en el alcance soportado, descansar y conservar progreso. | FR-CHR, FR-RUL, FR-TUR y FR-WLD. |
| M2 — Primera aventura completa | Objetivos, pistas, NPC, recompensas y consecuencias persistentes de principio a fin. | Continuidad, memoria, objetos, recursos y narrativa. |
| M3 — Ampliación de reglas | Progresión y nuevas familias de clase/equipo/magia, cada una con reglas deterministas y tests. | M1/M2 y selección explícita de reglas. |
| Futuro — Producto ampliado | UI propia, remoto, multiusuario o VTT solo si se aprueba un cambio de alcance. | Diseño y auditoría de seguridad/arquitectura independientes. |

## 8. Referencias de implementación

Este documento se ha contrastado con el estado del repositorio y sus contratos actuales. Los puntos de entrada recomendados son:

- [README del proyecto](../../README.md) — visión, límites y flujos principales.
- [Mapa de arquitectura](../architecture/architecture-map-2026-11-12.md).
- [Contrato del pipeline de turnos](../architecture/turn-pipeline-compatibility.md).
- [Ciclo durable de resolución](../architecture/turn-resolution-lifecycle.md).
- [Guía de modelos y contratos compartidos](../../models/README.md).
- [Servicios de turnos](../../services/turns/README.md).
- [Servicios de contexto](../../services/context/README.md).
- [Servicios de propuestas al mundo](../../services/llm_world/README.md).
- [Smoke test manual de SillyTavern](../sillytavern-smoke-test.md).
- [Hoja de ruta de calidad](../quality/quality-roadmap-2026-11-18.md).

## 9. Mantenimiento del documento

- Cada requisito funcional debe conservar un ID estable.
- Un cambio de alcance requiere actualizar objetivos, estados y criterios de aceptación en el mismo PR que apruebe ese cambio.
- Los estados reflejan evidencia observada; no se marcan como implementados por existir únicamente una especificación.
- La aceptación live/manual se registra con revisión del backend, revisión de la extensión, modelo/digest, configuración, fecha y resultados.
- Las auditorías históricas se mantienen fechadas; este documento y el roadmap son las referencias actuales de producto/calidad hasta que sean reemplazados explícitamente.
