# Requisitos de producto — Campaign Manager

**Versión:** 0.2 — requisitos ampliados y dirección de UX  
**Fecha:** 2026-11-18  
**Baseline de código:** `main` — `f4fb3914ebab4579118863796e6f6d4b7183d0cf` (PR #255). **Baseline documental:** `main` — `4a3a2549bb0bb1bc38ec0e6f456ac6d5ccef24d1` (PR #257 fusionada).  
**Estado:** decisiones de producto ampliadas a partir de feedback explícito; las capacidades siguen pendientes salvo donde se indique lo contrario.

> Este documento define qué producto queremos construir y separa los requisitos de las capacidades que el repositorio implementa hoy. Que un requisito aparezca aquí no significa que esté terminado ni que haya superado una prueba con Ollama/SillyTavern.

## 1. Visión y propósito

Campaign Manager aspira a ser un **Dungeon Master de IA configurable para campañas de rol**, comenzando con D&D 5e 2014. La experiencia inicial es local y para una persona, pero esa persona podrá controlar uno o varios personajes jugadores y configurar delegaciones sobre NPC. La aplicación interpreta mensajes en lenguaje natural, recupera contexto, adjudica reglas, valida consecuencias, conserva el estado y genera narración. El producto deberá ofrecer una interfaz propia muy configurable, sin depender de ella hasta que los contratos y workflows del backend sean sólidos; SillyTavern seguirá siendo una integración compatible, no la única interfaz posible.

El producto debe combinar libertad narrativa con un núcleo de juego fiable. La IA no debe poder inventar resultados mecánicos, hechos persistentes ni conocimientos de personajes que no estén respaldados por la campaña.

### Objetivos

1. Mantener una o varias campañas independientes y persistentes en una instalación local.
2. Permitir jugar mediante lenguaje natural, sin exigir al jugador que conozca comandos internos o estructuras JSON.
3. Mantener continuidad entre turnos, sesiones y conversaciones, sin mezclar campañas o chats.
4. Aplicar de forma determinista las reglas que estén implementadas.
5. Permitir que la IA interprete y narre, pero mantener bajo control del backend los permisos, la validación y la persistencia.
6. Hacer que los fallos, reintentos, aclaraciones y regeneraciones no dupliquen consecuencias.
7. Poder evaluar objetivamente la calidad de interpretación del modelo y detectar regresiones.
8. Permitir que la persona usuaria configure profundidad, presentación y controles de la experiencia sin perder acceso a las capacidades avanzadas.
9. Hacer consultable la información del mundo que el jugador ha descubierto, respetando los límites de conocimiento y visibilidad de cada personaje.
10. Extender el conjunto de reglas y los idiomas mediante formatos y contratos versionados, sin acoplar la aplicación a un único ruleset o idioma.

### Principios de producto

- **La ficción puede ser flexible; el estado persistente no.**
- **La IA propone; la aplicación valida y decide qué se guarda.**
- **El historial aporta contexto, no evidencia nueva del mensaje actual.**
- **La incertidumbre se expresa o se pregunta; no se rellena con invenciones.**
- **Las reglas no implementadas se reconocen como tales.**
- **Una narración generada nunca puede contradecir silenciosamente un resultado mecánico ya confirmado.**

## 2. Usuarios, roles y autoridad

El alcance inicial es de una persona usuaria que gestiona sus propias campañas. Esa persona podrá controlar uno o varios personajes jugadores y cambiar el conjunto de personajes bajo su control durante la partida. La IA actúa como Dungeon Master. SillyTavern seguirá siendo un cliente compatible; la futura interfaz propia será otro cliente de primera clase sobre los mismos contratos del backend.

| Actor | Responsabilidad | Límites |
|---|---|---|
| Jugador | Decide intenciones, acciones, diálogo y elecciones de los personajes jugadores que tenga asignados. Puede solicitar control de NPC. | No declara unilateralmente resultados mecánicos ni adquiere autoridad sobre otros personajes o el mundo por mera mención. |
| Dungeon Master de IA | Interpreta la ficción, controla el mundo y los NPC que no estén delegados, decide cuándo pedir pruebas y produce narración. Puede solicitar cambios de delegación. | No puede sobreescribir reglas resueltas, inventar datos persistentes, conceder permisos en nombre del jugador ni saltarse validaciones. |
| Motor de reglas | Calcula las mecánicas soportadas del ruleset activo y realiza las tiradas automáticas autorizadas. | Solo resuelve reglas implementadas y explícitamente soportadas; el LLM no elige resultados aleatorios. |
| Backend | Aplica permisos, valida operaciones, controla transacciones, revisiones, configuraciones y persistencia. | No delega autoridad de escritura al modelo. |
| Cliente (interfaz propia, SillyTavern/API) | Presenta estado y narración, recoge elecciones, preferencias, tiradas y aclaraciones. | No es autoridad sobre el estado canónico de campaña ni puede ampliar permisos por sí mismo. |

El control de NPC será una delegación explícita, auditable y revocable. El DM y el jugador podrán solicitarla; quien tenga la autoridad vigente sobre ese NPC deberá aprobarla. La delegación se limitará al NPC y a las capacidades concedidas, y podrá ser temporal, permanente hasta revocación o condicionada. Delegar un NPC no concede conocimiento del resto del mundo ni hechos que ese NPC desconozca.

## 3. Alcance del producto

### Incluido en el alcance inicial

- Aplicación local, de una persona usuaria y un solo proceso; no implica limitar la campaña a un único personaje jugador.
- Varias campañas separadas en la misma instalación.
- Persistencia local mediante SQLite y migraciones versionadas.
- Backend HTTP/API y flujo de conversación integrado con SillyTavern.
- Proveedor LLM local mediante Ollama.
- Estado de campaña, sesiones, personajes, mundo, entidades, NPC, objetos, eventos, relaciones, recursos y políticas de visibilidad.
- Control configurable de uno o varios personajes jugadores y delegación explícita de NPC.
- Interpretación estructurada de intenciones, aclaraciones recuperables y consecuencias validadas.
- D&D 5e 2014 como configuración de reglas incluida por defecto, con una arquitectura preparada para módulos personalizados importables.
- Español e inglés como primeros idiomas, con internacionalización preparada para incorporar otros.
- Importación y exportación de campañas completas mediante paquetes versionados y validados.
- Diseño y posterior desarrollo de una interfaz propia cuando el backend alcance criterios de solidez; SillyTavern seguirá siendo un cliente de integración.
- Historial, recuperación de contexto, continuidad y flujo durable de turnos.

### Fuera del alcance inicial o no prioritario

- Multijugador, cuentas de usuario, membresías y campañas compartidas.
- Exposición remota, hosting público, túneles o acceso desde redes no confiables; se reconsiderará en una fase posterior con autenticación y revisión de seguridad.
- VTT, mapas tácticos, tokens, niebla de guerra o movimiento en tiempo real.
- Implementación completa de todas las reglas de D&D 5e.
- D&D 5e 2024; no se mezcla con el conjunto 2014 y se evaluará en el futuro.
- Una interfaz propia completa antes de estabilizar los contratos del backend; su investigación y diseño podrán comenzar en cuanto esos contratos y workflows sean sólidos.
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
| FR-CAM-04 | La persona usuaria podrá consultar el estado de campaña y establecer qué uno o varios personajes jugadores controla en cada momento. | Parcial |
| FR-CAM-05 | La aplicación conservará los datos al reiniciarse y evolucionará el esquema mediante migraciones controladas. | Implementado |

### 4.2 Personajes, mundo e inventario

| ID | Requisito | Estado |
|---|---|---|
| FR-WLD-01 | La campaña conservará entidades del mundo, incluidos NPC, localizaciones, objetos, eventos, relaciones y recursos. | Parcial |
| FR-WLD-02 | Los objetos y recursos mantendrán identidad y propiedad suficientes para distinguir definiciones, instancias y cantidades. | Parcial |
| FR-WLD-03 | Los hechos podrán tener alcance/visibilidad; los secretos y hechos no conocidos por el personaje no se filtrarán a sus proyecciones. | Implementado en las proyecciones player-safe existentes |
| FR-WLD-04 | La aplicación conservará el historial de hechos y distinguirá hechos actuales de hechos reemplazados o superados. | Parcial |
| FR-WLD-05 | La persona usuaria podrá consultar un compendio del mundo con la información descubierta por el jugador, distinguiendo el conocimiento global del jugador como persona del conocimiento individual de cada personaje. | Pendiente |
| FR-WLD-06 | El compendio permitirá buscar, filtrar y abrir fichas de entidades con datos conocidos, acciones/eventos relevantes, relaciones, localizaciones y procedencia de los hechos, sin exponer información oculta. | Pendiente |
| FR-WLD-07 | Las menciones de entidades en la narración podrán enlazarse a referencias canónicas y conocidas; la interfaz mostrará una vista previa al pasar el ratón, recibir foco de teclado o activar el elemento en pantallas táctiles. | Pendiente |
| FR-WLD-08 | El jugador podrá fijar entidades, relaciones, localizaciones o acciones a paneles/listas de acceso rápido para preparar sus siguientes turnos. | Pendiente |
| FR-WLD-09 | La visibilidad de datos de NPC (por ejemplo, puntos de golpe, CA, condiciones, recursos y estadísticas) será configurable por NPC y por campo, con opciones como visible, oculto, descriptivo o reservado. La política afectará a las proyecciones, no al estado mecánico real. | Pendiente |
| FR-WLD-10 | El jugador podrá seleccionar y adjuntar al contexto de un turno las entidades visibles que considere relevantes (personajes, NPC, lugares, objetos, relaciones o eventos), sin tener que repetir manualmente su información. Esa selección aporta contexto factual, no evidencia nueva de la intención actual ni autorización para ejecutar acciones. | Pendiente |
| FR-CHR-01 | El personaje tendrá estado canónico y una proyección legible de su ficha. | Parcial |
| FR-CHR-02 | Se podrá crear un personaje completo mediante opciones tipadas de especie/raza, clase, trasfondo, características y competencias. | Pendiente |
| FR-CHR-03 | La progresión de nivel, rasgos de clase y recursos se reflejará en el estado y en las reglas. | Pendiente |
| FR-CHR-04 | La persona usuaria podrá controlar uno o varios personajes jugadores en una misma campaña y cambiar ese conjunto durante la partida sin perder el estado de los demás personajes. | Pendiente |
| FR-CHR-05 | El control de cada personaje jugador tendrá un propietario/actor autorizado explícito, distinguible del personaje activo usado como foco de contexto. | Pendiente |
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
| FR-AI-11 | Detectar incertidumbre en la interpretación o adjudicación y comparar una puntuación/señal de confianza con un umbral configurable por campaña; al superar el nivel de duda permitido, solicitar una aclaración al jugador en vez de inventar datos. | Pendiente |
| FR-AI-12 | Guardar un checkpoint durable de cada turno parcialmente resuelto: pasos y campos ya interpretados, evidencias, dependencias, decisiones validadas y cuestiones aún abiertas. | Pendiente |
| FR-AI-13 | Una aclaración continuará la resolución original y actualizará únicamente los campos pendientes; no volverá a preguntar lo ya resuelto ni repetirá interpretaciones o efectos. | Pendiente |
| FR-AI-14 | El jugador podrá resolver, corregir o indicar que no sabe una cuestión pendiente; si una respuesta afecta a pasos dependientes, la aplicación recalculará solo esos pasos y conservará el resto del trabajo válido. | Pendiente |

**Regla de seguridad para la incertidumbre:** la confianza del modelo solo decide cuándo pedir ayuda o abstenerse; nunca concede permiso para escribir estado. La puntuación no deberá tratarse como una probabilidad calibrada por defecto: se validará con holdouts y señales de evidencia. Los pasos ya resueltos se almacenan como progreso de resolución, pero las consecuencias del turno se confirman mediante el límite transaccional normal cuando todos los datos obligatorios y dependencias estén resueltos. No se aplican cambios especulativos o parciales al mundo.

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
| FR-RUL-08 | La persona usuaria podrá configurar quién realiza cada tirada: jugador mediante entrada manual/dado externo o resolución automática gestionada por la aplicación en nombre del jugador o del DM. La política podrá variar por campaña, actor o tipo de tirada. | Pendiente |
| FR-RUL-09 | Cuando una tirada sea automática, el resultado aleatorio lo generará el servicio/motor de dados del backend y quedará registrado; el LLM podrá solicitar la tirada y narrarla, pero no inventar ni escoger el resultado. | Pendiente |
| FR-RUL-10 | D&D 5e 2014 será el paquete de reglas incluido y predeterminado. La aplicación permitirá importar módulos personalizados declarativos, versionados y validados, y activarlos de forma explícita por campaña. | Pendiente |
| FR-RUL-11 | Los módulos personalizados declararán identificador, versión, dependencias, compatibilidad y reglas/datos aportados; el backend detectará conflictos y rechazará paquetes inválidos. La importación no ejecutará código arbitrario ni permitirá saltarse validaciones. | Pendiente |

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
| FR-INT-04 | La persona usuaria podrá consultar memoria/contexto recuperado y datos player-safe. | Parcial |
| FR-INT-05 | La aplicación dispondrá de una interfaz propia que consuma la misma API/contratos del backend que SillyTavern; su implementación comenzará cuando el backend cumpla los criterios de solidez definidos en la hoja de ruta. | Pendiente |
| FR-INT-06 | La interfaz ofrecerá modos Simplificado y Avanzado. Simplificado priorizará flujos guiados y ajustes habituales; Avanzado expondrá el conjunto completo de opciones. Ambos modos conservarán acceso a las mismas capacidades y a cambiar de modo sin perder configuración. | Pendiente |
| FR-INT-07 | Cada campo de configuración tendrá etiqueta clara y explicación adecuada a su complejidad, incluyendo valores permitidos, unidades, valor por defecto y efectos importantes. La ayuda esencial estará visible; tooltips serán complementarios, no la única fuente de información. | Pendiente |
| FR-INT-08 | La persona usuaria podrá personalizar paneles, orden, tamaño/visibilidad de secciones, densidad y vistas de campaña/personajes, con configuraciones guardables y restablecimiento a valores por defecto. | Pendiente |
| FR-INT-09 | La aplicación separará idioma de interfaz, idioma de la campaña/narración e idioma de interacción del jugador. Español e inglés serán los primeros idiomas y la arquitectura permitirá añadir otros sin cambiar identificadores internos o datos canónicos. | Pendiente |
| FR-INT-10 | La persona usuaria podrá exportar e importar campañas completas mediante paquetes versionados que incluyan configuración, personajes, mundo, historial y módulos personalizados referenciados, con validación previa y restauración segura. | Pendiente |
| FR-INT-11 | La interfaz permitirá consultar el compendio y las fichas de entidades exclusivamente dentro del alcance de conocimiento/visibilidad permitido; las vistas previas desde la narración respetarán exactamente el mismo filtro. | Pendiente |
| FR-INT-12 | La configuración de visibilidad de NPC y la política de tiradas se podrán administrar desde la interfaz, con valores heredados por defecto y excepciones por NPC/campaña donde corresponda. | Pendiente |
| FR-INT-13 | La interfaz ofrecerá interacción accesible con ratón, teclado y pantallas táctiles; las vistas previas de entidades no dependerán exclusivamente del hover. | Pendiente |
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
| NFR-REL-04 | Recuperación de aclaraciones. | Un reinicio o reintento conserva los pasos resueltos y pendientes; el mismo turno continúa sin duplicar trabajo ni efectos. |
| NFR-SEC-04 | Aislamiento de conocimiento y visibilidad. | Búsquedas, paneles, tooltips, exportaciones player-safe y narración no revelan campos o hechos que la política de visibilidad prohíbe. |
| NFR-DAT-02 | Portabilidad de campañas. | Importaciones se validan antes de mutar datos, comprueban versión/integridad/dependencias y se aplican de forma atómica o se revierten por completo. |
| NFR-MNT-02 | Extensibilidad de reglas. | Los módulos declaran esquema/versiones y se procesan sin ejecutar código arbitrario; los módulos incompatibles o conflictivos fallan de forma explícita. |
| NFR-UX-01 | Configuración comprensible y reversible. | Los modos Simplificado/Avanzado no duplican ni pierden opciones; se puede encontrar, entender, cambiar y restablecer cualquier ajuste relevante. |
| NFR-UX-02 | Accesibilidad de ayuda e interacción. | Ayudas y previews funcionan con teclado y táctil, tienen nombres/relaciones accesibles, contraste suficiente y no ocultan información obligatoria. |
| NFR-I18N-01 | Internacionalización. | No hay textos de interfaz críticos codificados en un único idioma; los formatos localizados no alteran IDs, valores numéricos canónicos ni reglas. |
| NFR-OBS-02 | Evaluación de incertidumbre. | Los umbrales y señales de duda se pueden reproducir en pruebas; los reportes guardan métricas allowlisted, no contenido sensible del turno. |

## 6. Reglas de aceptación global

Una capacidad no se considera terminada por tener un prompt, una clase o un test unitario. Debe cumplir los gates aplicables:

1. **Contrato:** entradas, salidas, errores y autoridad están tipados y documentados.
2. **Validación:** datos no confiables son validados en el backend; los casos ambiguos fallan de forma segura.
3. **Prueba determinista:** hay tests positivos, negativos, límites y casos de recuperación.
4. **Evaluación de modelo:** cuando interviene un LLM, hay casos held-out independientes y métricas por familia/campo.
5. **Persistencia:** las operaciones stateful prueban rollback, reintento, duplicados y recuperación.
6. **Seguridad:** no hay falsos cambios persistentes críticos ni filtraciones de secretos.
7. **Integración:** el flujo real de cada cliente soportado se prueba cuando el cambio le afecta. SillyTavern sigue teniendo su suite de aceptación, pero no es el único cliente ni debe bloquear la validación del cliente propio.
8. **UX:** las configuraciones complejas se prueban con tareas reales en ambos modos; la ayuda no depende solo de hover.
9. **Portabilidad:** import/export prueba paquetes válidos, incompatibles, incompletos y duplicados, sin mutación parcial.
10. **Documentación:** el estado implementado/parcial/pendiente queda actualizado sin reescribir auditorías históricas.

### Gates de aceptación de la primera versión jugable

- Campaña y personaje seleccionados correctamente.
- Exploración, diálogo y acciones básicas sobre el mundo.
- Tiradas y mecánicas soportadas coherentes con la ficha.
- Un encuentro de combate completo dentro del subconjunto implementado.
- Inventario/recompensas y descanso básico.
- Clarificaciones y tiradas manuales continuables.
- Persistencia entre turnos, sesiones y reinicios.
- Regeneración y reintentos sin duplicar consecuencias.
- Uno o varios personajes jugadores controlables, con cambio de control durante la campaña.
- Una delegación de NPC que pueda solicitarse, aprobarse, limitarse y revocarse.
- Un turno con varios pasos y una ambigüedad que se pausa, persiste su progreso y continúa sin repetir los pasos resueltos.
- Política verificable de tiradas manuales y automáticas.
- Consulta de los hechos conocidos y fichas de entidades sin filtrar secretos; al menos una política de visibilidad configurable para NPC.
- Selección explícita de entidades visibles para enriquecer el contexto del siguiente turno, sin convertir ese contexto en una nueva declaración de intención.
- Dos chats aislados sin contaminación.
- Cero cambios persistentes críticos falsos y cero filtraciones de secretos en los held-out críticos y las pruebas de operación.

## 7. Hitos de producto propuestos

| Hito | Resultado observable | Dependencias principales |
|---|---|---|
| M0 — Backend fiable | CI verde, contratos API estables, workflows durables, recuperación, permisos y evaluación live reproducible. La aceptación SillyTavern se mantiene como prueba de integración, no como único gate de producto. | Calidad del modelo, consistencia de estado, validación y recuperación. |
| M1 — Primer ciclo jugable | Crear/usar uno o varios personajes, explorar, hablar, realizar pruebas, combatir en el alcance soportado, descansar y conservar progreso. | FR-CHR, FR-RUL, FR-TUR y FR-WLD. |
| M2 — Primera aventura completa | Objetivos, pistas, NPC, recompensas y consecuencias persistentes de principio a fin. | Continuidad, memoria, objetos, recursos y narrativa. |
| M3 — Interfaz propia | Cliente de primera parte con modos Simplificado/Avanzado, ayuda contextual accesible, personalización, visor del mundo, fichas enlazadas y controles de campaña. El diseño comienza cuando los contratos del backend sean estables. | M0, API de lectura/escritura definida y recorrido jugable probado mediante API/cliente de integración. |
| M4 — Portabilidad y reglas extensibles | Importar/exportar campañas completas y activar módulos personalizados versionados, con validación e integridad. | Contratos de datos, esquema de módulos y compatibilidad. |
| Futuro — Producto ampliado | D&D 2024, acceso remoto, multiusuario o VTT solo mediante decisión de alcance y diseño/auditoría independientes. | Evidencia de necesidad y revisión de seguridad/arquitectura. |

## 8. Referencias de implementación

Este documento se ha contrastado con el estado del repositorio y sus contratos actuales. Los puntos de entrada recomendados son:

- [README del proyecto](../../README.md) — visión, límites y flujos principales.
- [Estado actual y mapa de arquitectura](../architecture/current-state-2026-11-18.md).
- [Contrato activo del pipeline de turnos](../architecture/turn-pipeline-compatibility.md).
- [Auditoría documental y clasificación de snapshots](../architecture/documentation-audit-2026-11-18.md).
- [Ciclo durable de resolución](../architecture/turn-resolution-lifecycle.md) — propuesta PR #28 conservada como referencia histórica, no contrato activo.
- [Guía de modelos y contratos compartidos](../../models/README.md).
- [Servicios de turnos](../../services/turns/README.md).
- [Servicios de contexto](../../services/context/README.md).
- [Servicios de propuestas al mundo](../../services/llm_world/README.md).
- [Smoke test manual de SillyTavern](../sillytavern-smoke-test.md).
- [Hoja de ruta de calidad](../quality/quality-roadmap-2026-11-18.md).

## 9. Dirección de diseño de la interfaz

### 9.1 Modos Simplificado y Avanzado

La aplicación ofrecerá dos modos de presentación de la configuración:

- **Simplificado:** organiza la experiencia alrededor de tareas habituales, valores recomendados, presets y explicaciones cortas. No debe eliminar capacidades ni impedir acceder a una opción avanzada cuando se necesite.
- **Avanzado:** expone el catálogo completo, excepciones por campaña/personaje/NPC, umbrales, políticas y parámetros técnicos, con valores por defecto y límites visibles.

Los modos son dos vistas de un mismo modelo de configuración. Cambiar de modo no crea dos configuraciones incompatibles, no reinicia opciones y no debe ocultar silenciosamente valores activos.

### 9.2 Ayuda contextual por campo

Cada ajuste debe tener un nombre descriptivo y, cuando su efecto no sea obvio, una explicación visible junto al control. Como mínimo, una explicación deberá aclarar qué cambia, a quién afecta, su alcance (global/campaña/personaje/NPC), el valor por defecto y las consecuencias relevantes.

La presentación seguirá una jerarquía:

1. Etiqueta clara y ejemplo/unidad cuando proceda.
2. Texto de ayuda breve visible para la información que se necesita al tomar la decisión.
3. Tooltip o icono de ayuda para aclaraciones secundarias y breves.
4. Popover, panel lateral o documentación enlazada para explicaciones largas, ejemplos y conceptos relacionados.

No se usará un tooltip como único lugar para instrucciones obligatorias, advertencias críticas o reglas necesarias para completar una configuración. Cualquier ayuda debe funcionar con ratón, foco/teclado y toque; los elementos esenciales no dependerán del hover. Se investigará y probará la solución concreta con prototipos, en lugar de asumir que todos los campos necesitan el mismo patrón.

**Referencias iniciales de investigación UX (consultadas el 2026-11-18):** [DWP Design System — Hint text](https://design-system.dwp.gov.uk/guidance/hint-text), [GOV.UK Design System — Text input](https://design-system.service.gov.uk/components/text-input/), [Nielsen Norman Group — Tooltip Guidelines](https://www.nngroup.com/articles/tooltip-guidelines/) y [European Commission — Tooltip usage](https://ec.europa.eu/component-library/ec/components/tooltip/usage/). Estas guías coinciden en mantener visible la información esencial, reservar tooltips para ayuda breve complementaria y ofrecer alternativas a hover. Son referencias de partida, no sustituyen pruebas de usabilidad con prototipos del producto.

### 9.3 Explorador de mundo y entidades

La interfaz dispondrá de una zona de consulta del conocimiento disponible para el jugador. Deberá distinguir, al menos, el conocimiento del jugador como persona del conocimiento individual de cada personaje, y permitir filtrar por campaña, personaje, tipo de entidad y estado de conocimiento.

Las fichas de entidad podrán crecer por pestañas o secciones —descripción, datos visibles, relaciones, eventos, localizaciones, acciones y procedencia— sin presentar campos ocultos. La narración generada podrá incluir referencias estructuradas a entidades conocidas. En escritorio, pasar el ratón o recibir foco de teclado mostrará una vista previa; en táctil, un toque/activación abrirá esa vista o la ficha completa. El jugador podrá fijar entidades, relaciones o lugares a un panel de acceso rápido. También podrá seleccionar desde ese panel qué entidades quiere incluir expresamente en el contexto del siguiente turno.

Las referencias inline deben estar ligadas a IDs canónicos que el backend ya haya autorizado para esa proyección. No se resolverán enlaces mediante una búsqueda libre del nombre en la interfaz, porque podría producir coincidencias incorrectas o filtrar entidades no visibles.

### 9.4 Incertidumbre, aclaraciones y continuidad

El jugador podrá configurar cuánto debe preguntar el DM ante ambigüedades. El modo simplificado podrá ofrecer presets como «preguntar ante dudas importantes», «equilibrado» y «priorizar fluidez»; el modo avanzado podrá exponer umbrales y excepciones por familia de decisión.

El umbral no convierte la confianza autodeclarada por el LLM en una probabilidad verdadera. La aplicación deberá combinar señales de evidencia, validación y evaluación del modelo; calibrará el comportamiento con conjuntos de prueba. Los límites de autoridad y las validaciones deterministas no se rebajan nunca por elegir un preset más fluido.

Cuando un mensaje contenga varios pasos y solo algunos estén claros, el sistema conservará un checkpoint estructurado de los pasos resueltos, las dependencias y las dudas pendientes. Formulará una pregunta enfocada al jugador. La respuesta actualizará solo los huecos afectados y reanudará el mismo turno. El checkpoint puede guardar progreso de interpretación, pero no adelantará efectos del mundo que dependan de una resolución todavía incompleta.

### 9.5 Dados y visibilidad de NPC

La política de dados deberá expresar con claridad quién aporta el resultado: el jugador (entrada manual o dado externo) o la aplicación (tirada automática en nombre del jugador/DM). Puede existir una política general por campaña con excepciones por actor y tipo de tirada. En cualquier caso, el resultado automático será generado y registrado por el backend; el texto del LLM no es una fuente aleatoria ni una autoridad para elegir números.

La visibilidad de NPC podrá definirse por campo y entidad. Por ejemplo, la CA o los puntos de golpe pueden estar completamente visibles, ocultos o traducidos a descripciones cualitativas. Los controles de visibilidad filtran las proyecciones y las vistas previas; no modifican la ficha real ni la mecánica subyacente.

## 10. Ideas adicionales para valorar (no aprobadas como requisitos)

Estas ideas pueden mejorar la experiencia, pero se mantienen como propuestas para validar contigo y, cuando corresponda, mediante prototipos:

- **Diario/códice del jugador:** hechos confirmados, rumores, hipótesis y datos contradichos, con quién descubrió cada cosa y cuándo. Evitaría que un rumor aparezca en la ficha como verdad confirmada.
- **Cronología y registro de sesión:** eventos importantes, escenas, decisiones y consecuencias, con búsqueda, filtros, marcadores y opción de volver a una escena anterior solo como consulta.
- **Panel de grupo:** resumen de personajes controlados, salud, recursos, condiciones, equipo y quién tiene el control de cada uno.
- **Grafo de relaciones:** navegar por relaciones conocidas entre NPC, facciones, lugares y objetos, diferenciando relaciones confirmadas de sospechas.
- **Perfiles de estilo del DM:** longitud de respuestas, cantidad de detalle, ritmo, descripción frente a diálogo y tono narrativo. Deben afectar a la presentación, nunca permitir que la narración contradiga las reglas o el estado confirmado.
- **Límites de contenido y preferencias de mesa:** configurar temas que se quieren evitar, tratar con cuidado o permitir, respetando siempre las reglas de seguridad y las preferencias por campaña.
- **Backups y puntos de restauración:** crear/exportar snapshots antes de cambios importantes, restaurar en una copia o confirmar explícitamente una recuperación. No ofrecería un «deshacer» que reescriba consecuencias sin auditar dependencias.
- **Plantillas de campaña y presets:** guardar configuración de interfaz, reglas, visibilidad, dados, idiomas y estilo para reutilizarlas al crear otra campaña.
- **Accesibilidad y presentación:** tamaños de fuente, contraste, temas, reducción de animación, densidad visual y atajos de teclado.
- **Vista de localizaciones o mapa de relaciones espaciales:** una vista opcional de lugares descubiertos podría ser útil, pero un VTT/mapa táctico permanece fuera del alcance actual.

## 11. Mantenimiento del documento

- Cada requisito funcional debe conservar un ID estable.
- Las decisiones indicadas como confirmadas reflejan instrucciones explícitas del propietario del producto; las ideas de la sección 10 son propuestas y no se convierten en requisitos sin aprobación.
- Un cambio de alcance requiere actualizar objetivos, estados y criterios de aceptación en el mismo PR que apruebe ese cambio.
- Los estados reflejan evidencia observada; no se marcan como implementados por existir únicamente una especificación.
- La aceptación live/manual se registra con revisión del backend, revisión de la extensión, modelo/digest, configuración, fecha y resultados.
- Las auditorías históricas se mantienen fechadas; este documento y el roadmap son las referencias actuales de producto/calidad hasta que sean reemplazados explícitamente.
