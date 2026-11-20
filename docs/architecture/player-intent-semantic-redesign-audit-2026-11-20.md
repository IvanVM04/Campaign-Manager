# Auditoría y rediseño de la comprensión de intención y semántica del jugador

**Fecha:** 2026-11-20  
**Repositorio:** IvanVM04/Campaign-Manager  
**Base revisada:** main después de PR #281 y de las PR #272–#280  
**Evidencia principal:** informe de evaluación live de Ollama documentado en PR #281 y ejecución local 30-ollama.log  
**Estado de este documento:** auditoría y arquitectura objetivo propuestas. Las estructuras v3 y la secuencia de PR descritas aquí **no están implementadas**. El runtime continúa usando PlayerIntentAnalysis v2.

---

## 1. Decisión ejecutiva

La recomendación es **no reescribir Campaign-Manager, no sustituir el monolito modular y no convertir la interpretación en una cadena de llamadas independientes al LLM**. La arquitectura actual tiene buenas fronteras de seguridad, una separación útil entre intención, mecánicas y propuestas de mundo, y una base de evaluación bastante más madura que hace unas semanas. Conviene conservar esas inversiones.

Lo que sí debe cambiar es el **modelo conceptual que representa lo que ha dicho el jugador y la transición entre interpretación y acción de juego**.

El sistema actual intenta representar con una colección de pasos de intención fenómenos que pertenecen a planos diferentes:

- el acto comunicativo: preguntar, decir algo en personaje, citar, advertir, rechazar, corregir o afirmar;
- el contenido semántico: el evento o estado del que se habla, con sus participantes y relaciones;
- el estatus de ese contenido: observado, afirmado, referido por otra persona, hipotético, condicional, negado o incierto;
- la secuencia del discurso: qué cláusula continúa, explica, corrige, condiciona o retoma otra;
- la intención jugable: qué quiere intentar el jugador ahora;
- la autoridad del juego: qué acción puede adjudicar el motor y qué consecuencia puede pasar a ser un hecho persistente.

Esos planos están relacionados, pero **no son intercambiables**. La modalidad actual intenta absorber demasiadas distinciones; el índice del paso activo mezcla interpretación con selección de acción; y las relaciones del mundo aparecen demasiado cerca de los argumentos de una acción. El resultado es una representación que puede acertar palabras, actores y predicados de manera aislada, pero reconstruir mal el significado completo.

La dirección recomendada es una **interpretación semántica conjunta, expresada mediante actos comunicativos, marcos de evento, enlaces discursivos y afirmaciones de hecho diferenciados**. A partir de esa interpretación, el backend generará candidatos de acción y decidirá cuál puede ejecutarse. No se trata de pedir al modelo que haga más cosas ni de multiplicar las llamadas: se trata de darle un contrato que no obligue a codificar conceptos distintos con los mismos campos.

### Decisiones principales

1. Mantener un único turno de interpretación LLM que analice el mensaje completo con su contexto acotado. No separar actor, verbos, argumentos, discurso y relaciones en llamadas independientes.
2. Diseñar una versión nueva del contrato semántico que separe acto comunicativo, evento/proposición, enlace discursivo y candidato de acción jugable.
3. Retirar progresivamente al modelo la autoridad para elegir el paso activo. El modelo aporta la estructura semántica; el backend calcula la elegibilidad y el foco de acción.
4. Separar argumentos de acciones de relaciones persistentes del mundo. Un destinatario de una transferencia no prueba por sí solo propiedad, pertenencia ni una relación duradera.
5. Hacer explícita la procedencia de cada afirmación: quién habla, quién realiza el evento, quién lo cuenta, a quién se dirige y qué parte es una cita.
6. Tratar el callback como un enlace al contexto anterior, no como un evento nuevo. La frase «retomando lo de...» no es una acción del jugador ni un hecho del mundo.
7. Construir los hechos persistentes mediante una política propia, con procedencia y estabilidad. La extracción de operaciones no debe convertir automáticamente toda frase semánticamente plausible en memoria de campaña.
8. Mantener los contratos v1/v2 para leer datos históricos. La nueva representación se introduce con versionado y migración gradual, nunca reinterpretando silenciosamente resoluciones duraderas antiguas.
9. No promover Stanza ni otro parser a producción hasta demostrar una mejora incremental medible sobre los corpora españoles del proyecto.
10. Mantener CI determinista como gate de cada PR; reservar Ollama live y SillyTavern para evaluaciones diagnósticas y gates de aceptación definidos.

---

## 2. Alcance, fuentes y límites de la auditoría

Se revisaron:

- el informe de evaluación live añadido por PR #281;
- el log completo entregado para la ejecución local;
- el diseño NLU fechado el 2026-11-19;
- los módulos de contrato PlayerIntentAnalysis y semantic frames;
- IntentInterpreter y su IntentNormalizationPipeline;
- las normalizaciones de superficie y los hints semánticos;
- las colaboraciones de discurso y resolución de referencias;
- el flujo de propuesta de mundo y su validador;
- las guías de los paquetes turns, discourse y context;
- las PR #272–#280 y su alcance documentado.

La auditoría distingue tres tipos de afirmación:

- **Hecho observado:** aparece directamente en el código, el informe o el log.
- **Diagnóstico arquitectónico:** interpretación razonada de varios hechos observados.
- **Propuesta:** cambio recomendado que requiere una PR y validación posterior.

No se ha ejecutado Ollama desde este entorno ni se ha realizado una sesión manual con SillyTavern. Esta auditoría no afirma haber corregido los errores live. La PR de auditoría es documental y establece el diseño y las condiciones de implementación; no cambia todavía el prompt, los modelos ni el comportamiento de producción.

La PR #281 también documenta una discrepancia de procedencia: el resumen exterior indica el commit a4a29f3c807dcd062b7261754cd90a86250f0b67, mientras que los cuatro informes JSON interiores indican 98d8759e9ed8648c481141b92a040c761b041287. La causa probable es una variable de entorno heredada por el runner, pero el log por sí solo no prueba esa causa. Por ello, los resultados son una señal diagnóstica muy útil, aunque el próximo benchmark debe corregir y verificar esa trazabilidad antes de utilizarse como comparación oficial.

---

## 3. Qué dicen realmente los resultados

### 3.1 La media del 93 % no describe la comprensión global

La ejecución seleccionó 22 pruebas live: 11 pasaron y 11 fallaron. No hubo errores de pytest ni pruebas omitidas. El tiempo de ejecución reportado fue aproximadamente 42 minutos y 33 segundos.

Los cuatro informes publican F1 de dominio entre 85,24 % y 98,67 %, con una media aritmética simple del 93,00 %. Esa media **no es un score general de comprensión**: los informes miden conjuntos, denominadores y contratos distintos. No se debe utilizar para afirmar que la aplicación entiende correctamente el 93 % de los mensajes.

| Dominio | F1 reportado | Lectura correcta |
|---|---:|---|
| Intención y lenguaje | 98,67 % | Los slots generales están muy bien puntuados en ese corpus; no garantiza los casos compuestos o integrados |
| Discurso y resolución | 95,86 % | Buen resultado en varias referencias y atribuciones; callback y elipsis siguen siendo débiles |
| Semantic frames y predicados | 92,24 % | Los predicados aislados puntúan mucho mejor que los escenarios completos de relaciones |
| Intención compuesta | 85,24 % | La modalidad por paso degrada notablemente el contrato completo |

La disparidad importante no es la media, sino la diferencia entre acertar campos sueltos y reconstruir correctamente el escenario completo.

### 3.2 Los indicadores que marcan la dirección

| Dimensión | Resultado observado |
|---|---:|
| Pruebas live | 11/22 correctas |
| F1 de modalidad por paso compuesto | 54,0 % |
| F1 de actor por paso compuesto | 97,8 % |
| F1 de polaridad por paso compuesto | 97,8 % |
| Exactitud del número de pasos compuestos | 96,9 % |
| Exactitud del índice activo | 93,8 % |
| Contratos completos de escenarios compuestos | 8/32 (25 %) |
| Callback en el holdout de discurso | 3/12 (25 %) |
| Elipsis de acción pendiente | 1/4 (25 %) |
| Transferencias completas | 1/6 (16,7 %) |
| Dirección relacional completa | 0/9 |
| Modalidad epistémica de relaciones completas | 0/6 |
| Temporalidad de relaciones completas | 0/3 |
| Controles negativos de operaciones, en su batería específica | 6/6 |

Actor, polaridad, recuento de pasos e índice activo no están al mismo nivel de degradación que modalidad. Es un indicio concreto de que el problema dominante no es simplemente detectar quién aparece o separar frases: el contrato no expresa de forma suficientemente ortogonal **qué acto se está realizando, qué evento se describe y con qué estatus se presenta**.

Los semantic frames muestran otra divergencia: los predicados de acción alcanzan 18/18 y los de relación 16/18, pero las transferencias completas solo pasan 1/6. En esas transferencias se observaron relaciones adicionales no expresadas. Acertar un predicado y varios argumentos no equivale a acertar el significado relacional completo.

### 3.3 Fallos live que deben tratarse como contratos distintos

| Familia de fallo | Síntoma observado | Riesgo de producto |
|---|---|---|
| NPC nuevo | Se propuso Aldric con entity_type vacío | Operación estructuralmente parseable, pero inválida para el dominio |
| Instrucción dentro de una cita | El payload de intención llegó con forma inválida en steps[] | El turno falla en el límite de interpretación; debe fallar de forma segura y quedar diagnosticado |
| Acción compuesta con resultado fallido | No se conservó el único hecho confirmado de la cicatriz de Aldric | Se pierde un hecho explícito mientras se procesa otra acción no confirmada |
| Diálogo NPC | «Aldric me advierte: ...» se clasificó como reported en vez de dialogue | Confusión entre el acto de habla y el reporte de un hecho |
| Relación de parentesco | Predicado de gold distinto entre fixture y test determinista | El contrato de evaluación/normalización no está totalmente alineado |
| Modalidad compuesta | Varios casos fallan al distinguir diálogo, reporte, intento, plan y condición | Se selecciona o interpreta mal qué parte del turno es accionable |
| Callback integrado | El pipeline emitió una operación persistente cuando se esperaba ninguna | Una referencia al pasado puede provocar una mutación no autorizada |
| Hecho de NPC existente | El detalle explícito «cicatriz» no acabó en description ni notes | Se pierde evidencia persistente relevante |
| Callback / resolución discursiva | Mismatches de categoría, callback y argumentos | La continuidad conversacional no se reconstruye de forma fiable |
| Relaciones held-out | Falsos positivos y fallos de dirección, modalidad y tiempo | Riesgo de inventar parentescos, propiedad o relaciones |

El log contiene un ejemplo especialmente revelador de callback: «Retomando lo de la pared lisa de piedra, intento escalarla usando Atletismo. Si alcanzo la cornisa, entro en la torre». El modelo produjo un primer paso cuyo predicado era Retomando y cuya familia era OTHER, con una interpretación aproximada de percepción de la pared; el intento real de escalar quedó en el paso siguiente y el objetivo llegó a ser Atletismo en vez de la pared. Además se generó una relación a partir de ese fragmento discursivo. No es una mera falta de vocabulario: **una operación del discurso se representó como si fuera un evento**.

Otro ejemplo útil es el turno que mezcla el detalle visible de la cicatriz de Aldric con un intento fallido de abrir una puerta. La arquitectura necesita representar por separado el hecho observado sobre Aldric, la acción intentada sobre la puerta y el resultado narrado de esa acción. La pérdida del primer hecho no debe depender de cómo se resuelve la segunda acción.

### 3.4 Lo que sí está funcionando y debe preservarse

Los resultados también muestran capacidades aprovechables:

- incertidumbre epistémica y varios casos de habla citada puntúan bien en el corpus general;
- referencias de larga distancia y ciertos casos de atribución de NPC obtienen resultados completos;
- los controles específicos de calidad de operaciones obtuvieron precisión/recall del 100 % en sus ocho escenarios;
- el backend ya separa interpretación, adjudicación de mecánicas, propuesta, validación de operaciones y commit durable;
- la resolución de referencias conserva procedencia y abstiene ante ambigüedad en vez de convertir cualquier mención en ID canónico;
- las colaboraciones de discurso ya tienen salidas tipadas y una fachada estable.

La batería de operaciones y el pipeline integrado miden ámbitos distintos. Que una batería de ocho operaciones pase sus controles negativos no invalida el fallo integrado que produjo una operación inesperada tras un callback.

---

## 4. Diagnóstico de raíz: no es un único problema de prompt

### 4.1 La modalidad actual contiene varias dimensiones distintas

El contrato v2 contiene IntentModality con valores como attempted, completed, observed, planned, conditional, question, dialogue, reported, negated, correction y unknown.

La lista mezcla al menos cuatro ejes:

1. **Fuerza comunicativa:** preguntar, dialogar, afirmar, corregir.
2. **Procedencia/estatus epistémico:** observado, reportado, incierto.
3. **Fase temporal o de acción:** planeado, intentado, completado.
4. **Polaridad o negación:** negado.

La polaridad ya existe como campo separado, pero negated también figura como modalidad. Dialogue describe un tipo de acto comunicativo, mientras que attempted describe una fase de acción; reported describe procedencia de la información, y conditional describe una relación de dependencia/modalidad. Al competir por un mismo campo, el modelo tiene que elegir una etiqueta que puede ser parcialmente correcta y parcialmente incorrecta.

La discrepancia de modalidad del 54 % F1 compuesta es coherente con este diseño. Añadir más ejemplos a la misma taxonomía puede mejorar algunos patrones, pero no elimina la ambigüedad estructural.

**Decisión:** en la siguiente versión, no debe existir un único enum que mezcle acto comunicativo, estatus factual, fase del evento y elegibilidad jugable. Cada eje debe tener su propio campo y reglas de consistencia.

### 4.2 El paso de intención está siendo usado para representar cosas que no son pasos de acción

Una lista ordenada de steps presupone que cada fragmento relevante del mensaje se puede representar como un paso similar a una acción. Eso no se cumple:

- «Retomando lo de la pared...» reactiva un tema anterior; no es un evento.
- «Aldric me advierte: ...» contiene un acto comunicativo de NPC y una proposición citada; no es una acción del jugador.
- «Si llego a la cornisa, entro en la torre» expresa una condición y una consecuencia futura; no son dos acciones actuales e independientes.
- «No sé si el viajero dice la verdad» expresa incertidumbre sobre una proposición; no es necesariamente otro evento narrativo.
- «Mara es hermana de Aldric» expresa una relación de estado; no es una acción de interacción que deba recibir un índice activo.

En el ejemplo del callback, el predicado Retomando acaba ocupando un step. Esto demuestra que el paso actual no es una unidad semántica universal.

**Decisión:** utilizar nodos tipados para actos, eventos/estados y enlaces. La secuencia seguirá existiendo, pero solo entre elementos que realmente tengan una relación temporal o discursiva.

### 4.3 El modelo elige el paso activo demasiado pronto

PlayerIntentAnalysis contiene active_step_index y propiedades derivadas como is_actionable y allows_world_proposal. En v2, ese índice es parte del payload interpretado por el modelo y participa en el gate de mecánicas. Las normalizaciones posteriores pueden eliminar un puntero contradictorio, pero el diseño sigue haciendo que la interpretación LLM sugiera directamente el foco de ejecución.

El índice activo mezcla al menos estas preguntas:

- ¿Qué acción está expresando el jugador?
- ¿Se refiere a una acción actual o a una condición futura?
- ¿Es una acción propia o una frase atribuida a un NPC?
- ¿Hay una acción anterior pendiente?
- ¿El paso posterior depende de que el anterior tenga éxito?
- ¿El jugador ya comunicó un resultado o el motor debe adjudicarlo?

Un puntero escalar no representa bien esas dependencias. Tampoco debe ser el mecanismo que autoriza la adjudicación.

**Decisión:** el modelo describe la semántica; el backend calcula los candidatos de acción, sus dependencias y cuál está habilitado. El concepto de active step puede conservarse temporalmente para v1/v2 y para adaptadores, pero no será la autoridad del contrato nuevo.

### 4.4 Argumentos de una acción no son relaciones permanentes del mundo

SemanticActionFrame contiene roles como recipient, source, destination, owner o holder. SemanticRelationClaim contiene sujeto, predicado, objeto, familia, polaridad, modalidad y tiempo. Son tipos distintos, pero siguen compartiendo un mismo análisis y una referencia a step_index.

La diferencia de dominio es importante:

- «Entrego la llave a Mara» describe una acción y sus participantes.
- «La llave pertenece a Mara» describe una relación de propiedad.
- «Mara guarda la llave» puede describir ubicación/posesión temporal, no necesariamente propiedad.
- «La llave pasa a ser de Mara» puede justificar una relación de propiedad si se afirma explícitamente y el dominio lo permite.

No es válido inferir cualquier relación persistente a partir de los argumentos de una transferencia. El patrón de falsos positivos del corpus de transferencias sugiere que la separación actual todavía no es suficientemente fuerte para el modelo, el normalizador o ambos.

**Decisión:** los argumentos de acción, las relaciones declaradas y los hechos persistentes deben tener contratos separados. Una transferencia puede producir una consecuencia de propiedad únicamente cuando la semántica explícita y las reglas del dominio lo justifiquen.

### 4.5 Speaker, agent, addressee y attributed_to no son el mismo papel

Los mensajes de rol contienen varias personas y fuentes:

- el **speaker** es quien pronuncia el mensaje;
- el **agent** es quien realiza el evento descrito;
- el **addressee** es a quien se dirige el acto comunicativo;
- el **source/reporter** es quien transmite una afirmación;
- el **experiencer** es quien percibe o conoce algo;
- el **attributed source** puede ser quien dijo las palabras citadas.

«Le pregunto a Mara por la llave» tiene al jugador como speaker y agent del acto de preguntar; Mara es addressee. «Mara me advierte: ...» tiene a Mara como speaker y el jugador como posible addressee. «Un viajero dice que vio un dragón» tiene al viajero como source del reporte, pero el jugador no está afirmando necesariamente que el dragón exista.

La propiedad actual attributed_to no modela por sí sola todo ese reparto. Si se usa como prueba suficiente de speaker o de identidad canónica, se mezclan evidencia lingüística y resolución de entidad.

**Decisión:** preservar estos roles de forma independiente y mantener toda mención como texto y procedencia no confiables hasta resolverla contra entidades visibles y únicas.

### 4.6 Los callbacks necesitan enlaces, no verbos de acción

El sistema ya tiene un selector de historial temático, límites de conversación, señales superficiales y un resolver de referencias. No se necesita otro almacén de memoria para resolver «retomando lo de la pared».

La debilidad está en que la reactivación del tema se acaba expresando en el mismo objeto que contiene los eventos actuales. Un marcador de callback debe generar un enlace de discurso con un ancla candidata del historial, no un nuevo evento con predicado Retomando.

La referencia resuelta continúa siendo una salida del backend: el modelo puede proponer una mención o un ancla textual; el selector puede escoger un segmento y el resolver solo puede emitir IDs visibles y no ambiguos.

**Decisión:** representar callbacks, elipsis y correcciones como enlaces discursivos tipados. No producir eventos o hechos por el mero hecho de mencionar un tema anterior.

### 4.7 Las normalizaciones están acumulando conocimiento lingüístico duplicado

IntentNormalizationPipeline ya ofrece un límite determinista, ordenado, comprobable y con diagnósticos sin contenido narrativo. Esa decisión es buena y debe conservarse.

Pero PR #279 y #280 añadieron nuevas reparaciones específicas para intentos divididos, incertidumbre reportada, relaciones fragmentadas, investigación, diálogo con hablante nombrado y diálogo seguido de acción. La existencia de estas reparaciones es comprensible: corrigen fallos observados y mantienen los controles de evidencia. Sin embargo, cada patrón nuevo puede crear otra interpretación parcial, duplicar vocabulario y competir con un patrón parecido en otra etapa.

El vocabulario de predicados de habla ya es una señal del problema: el informe identifica que advierte/advirtió no se reconocía en la extracción de señales de habla aunque sí aparecía en otra normalización. La misma noción lingüística vive en más de un lugar.

**Decisión:** no prohibir las reglas superficiales, sino cambiar su papel. Deben aportar señales de alta precisión y conservar offsets/procedencia; la representación semántica conjunta debe determinar el significado. Las reparaciones destructivas se reservarán a invariantes de seguridad o patrones estrechos con contrato positivo, negativos cercanos y corpus held-out.

### 4.8 La validez de la operación no garantiza la validez del hecho

PR #280 añadió campos exactos al prompt de reparación para las operaciones afectadas. El log posterior muestra un NPC creado con entity_type vacío. Por tanto, el reparador puede producir una estructura que supera la validación actual sin que el dominio tenga toda la información necesaria.

Algo parecido ocurre con la cicatriz: una instrucción de prompt para crear o actualizar NPC no garantiza que el hecho estable se conserve en la operación final.

**Decisión:** la validación semántica del dominio debe ser estricta y posterior a cualquier reparación de formato. Los campos obligatorios de entidad deben ser no vacíos y pertenecientes a un conjunto permitido. Una reparación puede corregir el JSON, no inventar el tipo, la identidad ni un hecho ausente.

---

## 5. Arquitectura objetivo: interpretar el turno como una estructura semántica

La arquitectura objetivo sigue siendo un monolito modular y conserva una única interpretación conjunta por turno. El cambio principal reside en el contrato de salida y en los pasos deterministas posteriores.

### 5.1 Los cuatro objetos semánticos que deben distinguirse

#### A. Acto comunicativo (UtteranceAct)

Describe qué está haciendo comunicativamente el hablante.

Campos conceptuales:

- identificador local del acto dentro del turno;
- speaker mention/role;
- addressee mention/role, cuando exista;
- fuerza ilocutiva: afirmar, preguntar, hablar en personaje, advertir, pedir, rechazar, corregir, hipotetizar u otra categoría controlada;
- span literal de la expresión;
- span de cita y límites de contenido citado;
- acto al que responde o al que corrige, si se trata de una continuación;
- evidencia y procedencia.

El acto no demuestra que el contenido citado sea verdadero ni que deba ejecutarse. Una instrucción dentro de una cita es contenido citado, no una instrucción al sistema.

#### B. Evento o proposición (EventFrame / Proposition)

Describe qué ocurrió, qué se intenta, qué se observa o qué estado se afirma.

Campos conceptuales:

- predicado literal;
- familia semántica;
- participantes y roles: agent, patient/theme, recipient, source, destination, instrument, location, experiencer, beneficiary, etc.;
- polaridad;
- estatus epistémico: afirmado, observado, reportado, rumor, hipotético, incierto o no establecido;
- fase temporal/de acción: planeado, intentado o completado según lo expresado;
- tiempo o expresión temporal literal;
- evidencia literal asociada;
- atribución de fuente separada del actor del evento.

El resultado de una tirada no se infiere de un EventFrame. El modelo puede representar que el jugador dice que tuvo éxito o fracasó; la adjudicación autoritativa procede del motor o de una fuente del dominio aprobada.

#### C. Enlace discursivo (DiscourseLink)

Expresa cómo se relacionan actos y eventos, o cómo el mensaje actual se conecta con el historial.

Tipos iniciales:

- antes/después;
- continuación;
- condición sobre el éxito de otro evento;
- respuesta a un acto anterior;
- corrección de una afirmación anterior;
- explicación/elaboración;
- contraste;
- reporte de una fuente;
- cita de un acto;
- callback a un tema/turno anterior.

Los enlaces entre elementos del mensaje pueden usar IDs locales generados dentro de la respuesta. Un callback al historial debe incluir evidencia superficial y un ancla candidata; nunca un ID de entidad canónica ni un identificador de turno inventado por el modelo. La selección final del turno y el referente corresponde a los colaboradores deterministas.

#### D. Afirmación de relación/hecho (WorldFactCandidate)

Describe un posible hecho duradero del mundo, no un argumento de una acción.

Campos conceptuales:

- sujeto y objeto como menciones sin ID;
- predicado literal de superficie;
- relación semántica normalizada, si la construcción lo permite;
- dirección explícita;
- polaridad, estatus epistémico y temporalidad;
- fuente de la afirmación;
- span de evidencia;
- estabilidad: permanente, temporal, desconocida o no aplicable;
- política de elegibilidad de persistencia, calculada por backend y no por el modelo.

El hecho solo pasa a una propuesta persistente si supera la política de procedencia, estabilidad, visibilidad, identidad y dominio. Las relaciones inferidas a partir de roles de una acción no se convierten automáticamente en WorldFactCandidate.

### 5.2 Candidato de acción jugable: salida derivada por backend

GameplayActionCandidate no debe ser otro campo de autorización decidido por el LLM. Es un objeto derivado a partir de EventFrames y DiscourseLinks ya validados.

Debe registrar:

- evento de origen;
- actor y mención de objetivo;
- tipo de acción de juego soportado;
- motivo de elegibilidad o abstención;
- dependencias previas;
- condición de desbloqueo;
- si requiere resolución mecánica, diálogo, aclaración o ninguna resolución;
- referencias canónicas resueltas por el backend;
- estado de procesamiento durable.

La selección del candidato activo debe ser determinista. No se utiliza un score de confianza declarado por el modelo para conceder permisos. La elegibilidad exige evidencia literal, actor compatible con el jugador bajo el conjunto de control vigente, acción soportada, estado no negado/condicional/no ejecutado sin resolver, referencias visibles y ausencia de dependencias pendientes.

Una comunicación dirigida a un NPC puede ser un acto de juego relevante, pero no debe convertirse en una tirada física ni en un hecho sobre el contenido de la cita. El backend determina qué workflow corresponde: diálogo, mecánicas o aclaración.

### 5.3 Ejemplo de contrato conceptual

El siguiente esquema es ilustrativo, no un JSON Schema aprobado ni código de producción:

~~~
TurnInterpretationV3
  utterance_acts[]
    local_id
    illocution
    speaker_mention
    addressee_mention
    quote_spans[]
    evidence_spans[]

  events[]
    local_id
    predicate_surface
    event_family
    arguments[]
    polarity
    epistemic_status
    action_phase
    temporal_expression
    evidence_spans[]
    source_act_id

  discourse_links[]
    source_local_id
    target_local_id_or_anchor_candidate
    link_type
    evidence_span

  relation_assertions[]
    subject_mention
    predicate_surface
    normalized_relation_type
    object_mention
    direction
    polarity
    epistemic_status
    temporal_scope
    evidence_span

  clarification_candidates[]
    affected_local_ids
    ambiguity_kind
    missing_slot
    question_intent
~~~

No se incluyen IDs canónicos, permisos, tiradas, resultados de mecánicas, operaciones ni una autoridad model-supplied de active_step_index. El payload es una hipótesis estructurada sobre el texto, sujeta a validación.

### 5.4 No mezclar predicado literal y tipo semántico normalizado

El caso de parentesco muestra que el corpus y los tests pueden comparar superficies distintas: «hermana» frente a «es hermana». La representación debe guardar dos datos cuando ambos sean relevantes:

- **predicate_surface:** la forma literal extraída del mensaje, por ejemplo «es hermana»;
- **normalized_relation_type:** el concepto controlado, por ejemplo kinship.sibling.

El scorer debe poder puntuar la coincidencia literal y la normalización semántica por separado. No se debe cambiar el gold solo para acomodar la salida del modelo. Antes de migrar el corpus, hay que reconciliar el contrato esperado con una anotación explícita y revisar qué prueban los tests deterministas.

---

## 6. Cómo debe funcionar el pipeline nuevo

~~~
Mensaje actual + historial acotado del mismo chat + contexto visible
                              |
                              v
       Señales deterministas de discurso / spans lingüísticos opcionales
                              |
                              v
             UNA interpretación LLM conjunta (v3)
      actos comunicativos + eventos + enlaces + afirmaciones
                              |
                              v
     Validación estructural, spans, procedencia y consistencia
                              |
                              v
       Resolución de referencias y callbacks determinista
                              |
                              v
     Selector de candidatos de acción y dependencias (backend)
                              |
                 +------------+------------+
                 |                         |
                 v                         v
        Adjudicación de reglas       Hechos candidatos
        y mecánicas determinista     y propuesta de mundo
                 |                         |
                 +------------+------------+
                              |
                              v
             Validación de dominio y autorización
                              |
                              v
                  Commit atómico durable
                              |
                              v
                    Narración post-commit
~~~

Este flujo conserva las responsabilidades actuales:

- IntentInterpreter sigue coordinando la petición y validación de la respuesta semántica.
- El paquete discourse selecciona temas, spans, hablantes y señales de referencia sin adjudicar identidad ni escribir.
- El paquete context resuelve menciones a IDs visibles, únicos y permitidos.
- El selector de acciones es backend y no llama al modelo.
- MechanicsAdjudicator recibe solo el candidato validado que realmente necesita adjudicación.
- LLMWorldExtractor puede ayudar a formular propuestas de consecuencias/hechos, pero no decide si una afirmación es verdadera ni si se puede persistir.
- OperationParser, servicios de dominio, WorldService/WorldApplier y el ciclo durable siguen siendo autoridad de escritura y commit.
- Narration continúa después del commit y no crea efectos por sí misma.

### 6.1 Validación en capas, con errores distintos

No conviene tratar toda discrepancia como «JSON inválido». El pipeline debe reportar, mediante códigos tipados y sin contenido del jugador, al menos:

1. error de transporte/proveedor;
2. JSON no parseable;
3. contrato estructural inválido;
4. span que no existe en la evidencia;
5. referencias o roles inconsistentes;
6. contradicción entre acto y evento;
7. secuencia imposible o enlace sin extremos;
8. ambigüedad de resolución;
9. falta de elegibilidad de acción;
10. operación de dominio inválida.

Una cita mal formada debe fallar de forma segura: no debe repararse convirtiendo su contenido en una acción del jugador. Se puede evaluar una reparación de formato acotada, pero debe ser consciente de su finalidad: corregir la estructura del payload sin cambiar speaker, quote scope, factualidad ni semántica. Si no se puede demostrar preservación, se abstiene.

### 6.2 Separar reparación de formato y reparación semántica

La reparación JSON del proposal validator y cualquier reparación de respuesta de intención deben estar sujetas a reglas distintas.

- Reparación de formato: completar la forma obligatoria, corregir tipos JSON, eliminar campos prohibidos; no inventa contenido semántico.
- Normalización determinista: aplica un contrato lingüístico estrecho que ya está probado con positivos y negativos.
- Interpretación semántica: pertenece a la salida conjunta del modelo y a su validación de evidencia.
- Resolución/autoridad: solo backend.

La reparación no debe asignar entity_type, identidad, relación, éxito ni propiedad cuando el payload no contiene evidencia suficiente.

---

## 7. Política de autoridad: qué puede y qué no puede hacer el modelo

| Salida | El modelo puede proponer | El backend debe decidir |
|---|---|---|
| Acto comunicativo | Fuerza, speaker/addressee textual, spans de cita | Si el speaker se puede vincular a NPC visible y único |
| Evento | Predicado, participantes, roles, polaridad, estatus, temporalidad | Si es relevante, soportado y resoluble en el mundo |
| Callback | Tema/anchor superficial y enlace probable | Qué turno anterior se selecciona y si el referente es único |
| Relación | Sujeto, predicado superficial, objeto, dirección | Si el tipo es válido, ambos extremos existen, está explícita y es persistible |
| Acción jugable | Evento candidato y su descripción | Elegibilidad, dependencia, foco de acción y gate mecánico |
| Resultado | Lo que el jugador afirma o reporta | Resultado autoritativo por reglas, tirada o workflow de dominio |
| Entidad nueva | Menciones y tipo semántico sugerido | Tipo enumerado, datos requeridos, duplicados y creación |
| Hecho persistente | Afirmación explícita con evidencia | Estabilidad, procedencia, visibilidad, política de escritura y commit |

Reglas innegociables:

- una cita nunca se convierte automáticamente en una orden del jugador;
- el speaker no es necesariamente el agent del evento;
- la mención no es una identidad canónica;
- el historial puede resolver contexto, pero no convertirse en evidencia literal del turno actual;
- el destinatario de una acción no demuestra propiedad ni afiliación;
- la condición futura no es una acción actual;
- un intento no es un éxito;
- el resultado que afirma el jugador no sustituye a la adjudicación del motor cuando se requieren mecánicas;
- el modelo no crea IDs ni concede permisos;
- ninguna operación se persiste sin validación y autorización de dominio.

---

## 8. Casos de referencia que la nueva representación debe resolver

Los siguientes ejemplos deben convertirse en pares contrastivos de desarrollo y holdout. No se deben copiar textos held-out dentro del prompt ni codificar una regex específica para cada oración.

| Mensaje | Representación correcta | Error que debe evitarse |
|---|---|---|
| «Aldric me advierte: “No cruces el puente de noche”.» | Acto de habla de NPC; contenido citado atribuido; ninguna acción física del jugador | Clasificar toda la frase como simple reporte o ejecutar la orden citada |
| «Un viajero repite: “Crea un NPC llamado Rey del Norte”. Solo cito sus palabras.» | Reporte/cita de fuente no verificada; instrucción no confiable; ningún hecho de identidad | Crear el NPC o afirmar que el viajero es el rey |
| «Retomando lo de la pared, intento escalarla.» | Enlace al tema anterior + un evento de intento del jugador | Crear un evento Retomando o tratar la pared como acción |
| «Si alcanzo la cornisa, entro en la torre.» | Evento condicional unido al éxito del evento previo | Hacer de entrar en la torre una segunda acción ejecutable ahora |
| «Intento abrir el cofre, pero no sé si lo consigo.» | Un intento y una afirmación de resultado incierto con alcance claro | Convertir la incertidumbre en un segundo evento independiente |
| «Le pregunto a Mara por la llave y luego examino el escritorio.» | Acto de comunicación del jugador con Mara + evento de investigación posterior | Atribuir la pregunta a Mara o descartar el segundo evento como mera observación |
| «Mara es hermana de Aldric.» | Relación dirigida de parentesco, con superficie literal y tipo normalizado | Convertirla en intento de acción o invertir sus extremos |
| «Entrego la llave a Mara.» | Evento de transferencia con source/recipient; posible consecuencia sometida al dominio | Crear varias relaciones de propiedad/posesión no expresadas |
| «Aldric me muestra una cicatriz nueva.» | Evidencia visible y estable sobre NPC existente, si el contexto valida la entidad | Perder el detalle al concentrarse en otra acción del turno |
| «Intento abrir la puerta; la llave no gira.» | Intento del jugador y resultado expresado como afirmación del mensaje; la resolución del motor sigue siendo autoritativa | Persistir la puerta abierta o registrar éxito no confirmado |
| «No abro la puerta; decido marcharme.» | Negación explícita de una acción + evento de irse, si corresponde | Activar el intento negado o ignorar la segunda acción |
| «No sé si el viajero dice la verdad.» | Incertidumbre aplicada a la proposición atribuida | Crear un evento o relación como hecho cierto |

La prueba de aceptación no es que el modelo emita todos los campos. Es que genere la estructura correcta, sin eventos, enlaces o relaciones extra y sin activar ningún paso que el jugador no haya intentado.

---

## 9. Estrategia de transición desde v2 a v3

No se debe reemplazar PlayerIntentAnalysis v2 en una sola PR. Los registros duraderos ya guardan versiones y tienen que seguir recuperándose sin reinterpretación.

### Fase 0 — Congelar la semántica existente y reforzar contratos obvios

Antes de cambiar el esquema:

- documentar v2 como contrato actual y no añadir nuevas responsabilidades a IntentModality;
- exigir entity_type en propuestas create_entity: texto no vacío de 1–50 caracteres. No cerrar la taxonomía del dominio en esta fase; el constructor conserva el default para callers de confianza y compatibilidad histórica;
- publicar la obligatoriedad en el prompt manifest/JSON Schema y volver a imponerla en OperationParser;
- centralizar el catálogo de predicados de habla, con formas como advierte/advirtió y construcciones con clíticos, sin convertir señales léxicas en identidad NPC;
- eliminar únicamente una cláusula inicial de callback cuando el modelo la haya separado como step independiente, y reindexar a la vez los pasos, el índice activo y las relation_claims; no inferir una acción que falte;
- mantener pruebas de regresión para callback, citas y entradas no confiables;
- descartar relation_claims de ownership/possession/unknown que sean un reflejo del mismo predicado/cláusula de transferencia o creación, salvo que exista una construcción relacional explícita reconocida;
- unificar el gold de parentesco/propiedad con el núcleo léxico superficial (hermana, dueña), excluyendo la cópula meramente gramatical (es);
- mantener los controles negativos de citas, negaciones, hipótesis y acciones fallidas.

En v2, el campo `relation_claims[].predicate` mantiene el núcleo léxico
superficial («hermana», «dueña»); la cópula «es» no forma parte del predicate
que puntúa el corpus actual. La propuesta v3 puede conservar un span
`predicate_surface` más amplio («es hermana») como evidencia textual. Son dos
campos/contratos distintos: no volver a cambiar el gold v2 para anticipar el
contrato v3 ni perder el span literal cuando v3 se diseñe.

Esta fase reduce defectos actuales sin afirmar que resuelve el diseño semántico.

### Fase 1 — Diseñar y validar contratos v3 sin cambiar la producción

Crear records/DTO tipados para:

- UtteranceAct;
- EventFrame;
- DiscourseLink;
- RelationAssertion/WorldFactCandidate;
- GameplayActionCandidate derivado por backend;
- provenance/evidence spans.

Definir invariantes: límites, offsets, orden, referencias locales, cardinalidad, relaciones dirigidas, atribución y consistencia. Los IDs locales solo enlazan elementos del mismo turno. La identidad canónica sigue fuera del esquema.

Añadir fixtures sintéticos y pruebas deterministas de decodificación. No cambiar aún prompt ni runtime.

### Fase 2 — Nuevo prompt holístico y comparación en sombra

Cambiar el prompt una sola vez para que produzca la estructura v3 completa en una respuesta. No dividir la interpretación en llamadas de actor, evento, argumento, callback y relación.

Durante esta fase:

- mantener v2 como ruta de producción;
- producir v3 en modo sombra sobre una muestra controlada;
- ejecutar ambos contratos sobre la misma evidencia y contexto;
- guardar solo métricas allowlisted y diagnósticos sin texto;
- comparar pasos completos, spans, modalidades/ejes, enlaces, referencias y falsos positivos;
- no usar v3 para mecánicas ni persistencia hasta pasar los gates.

La comparación debe incluir casos donde v2 ya funciona. Una mejora en callback que degrade citas o negaciones no es una mejora neta.

### Fase 3 — Selector de acciones y checkpoint parcial

Introducir un selector determinista que convierta eventos elegibles en candidatos de acción con dependencias.

El primer candidato no resuelto se habilita cuando sus precondiciones se cumplen. Los eventos condicionales esperan al evento del que dependen. Un fallo mecánico resuelve ese nodo como fallo y no habilita un consecuente condicionado al éxito. Las acciones posteriores independientes pueden seguir representadas sin ejecutarse por accidente en el mismo commit.

El checkpoint durable debe registrar qué nodos/eventos están pendientes, cuáles fueron adjudicados, qué slots necesitan aclaración y qué hechos fueron validados. La clarificación debe reanudar el análisis preservando lo que no cambia y recalculando solo las dependencias afectadas.

La aplicación ya tiene continuación durable para clarificaciones y tiradas manuales; no debe confundirse esa capacidad existente con el checkpoint generalizado que se propone aquí.

### Fase 4 — Persistencia de hechos y operaciones del mundo

Separar los hechos candidatos de los eventos y de las acciones. Revisar explícitamente:

- creación de un NPC nuevo;
- actualización de una entidad existente;
- detalles visibles y estables como cicatrices o profesión;
- rumores o afirmaciones atribuidas;
- citas dentro de diálogo;
- acciones efímeras;
- intentos fallidos;
- transferencias y cambios de propiedad;
- relaciones de parentesco, afiliación y conocimiento.

Cada operación debe incluir campos obligatorios, tipo y procedencia. El dominio valida ambos extremos, permisos, visibilidad, duplicados y revisiones antes del commit. Si el extractor no puede emitir una operación válida a partir de la evidencia, debe abstenerse; no completar el significado por intuición.

### Fase 5 — Compatibilidad, despliegue y retirada gradual

- conservar decodificadores v1/v2;
- añadir un adaptador explícito v1/v2 a la vista interna común solo para lectura y comparación;
- persistir v3 únicamente cuando el nuevo contrato haya superado pruebas y paridad;
- no reinterpretar registros históricos usando el prompt nuevo;
- versionar el payload y el checkpoint durable;
- mantener rollback a la ruta v2 hasta que el criterio de aceptación esté satisfecho;
- retirar compatibilidad antigua solo cuando los consumidores reales estén migrados y existan pruebas de recuperación/replay.

No se necesita una migración de base de datos en la fase documental ni en la primera fase de contratos. Cualquier persistencia nueva requiere una decisión específica de schema y replay.

---

## 10. Qué conservar, modificar, reemplazar o evitar

| Área actual | Decisión | Motivo |
|---|---|---|
| Modular monolith | Conservar | Los límites de dominio actuales son razonables y la complejidad no justifica distribuir servicios |
| Una llamada holística de Intent | Conservar | Actos, eventos, argumentos, atribución y discurso dependen entre sí |
| PlayerIntentAnalysis v1/v2 | Conservar para compatibilidad | Hay datos duraderos y consumidores existentes |
| IntentModality como taxonomía universal | Sustituir gradualmente en v3 | Mezcla ejes comunicativos, epistémicos y temporales |
| active_step_index emitido por modelo | Dejar de usar como autoridad | La selección jugable depende de reglas y dependencias de backend |
| IntentNormalizationPipeline | Conservar y adelgazar | El límite determinista es bueno; la proliferación de reparaciones semánticas no debe continuar |
| Regex de superficie | Conservar solo como señales estrechas | Son útiles para negación o formas explícitas; no son una gramática general |
| DiscourseContextBuilder | Conservar como fachada | Los colaboradores tipados ya separan responsabilidades |
| ConversationReferenceResolver | Conservar | La resolución canónica, filtrada y con abstención es responsabilidad de backend |
| SemanticActionFrame | Evolucionar/adaptar a EventFrame | Los roles de acción son útiles, pero deben existir independientemente del acto y del estado |
| SemanticRelationClaim | Evolucionar a afirmación independiente | Debe diferenciarse claramente de los argumentos de transferencias e interacciones |
| LLMWorldExtractor | Conservar con límites más estrictos | Puede proponer, nunca autenticar ni autorizar |
| Stanza piloto | Mantener opt-in | Solo debe aportar hints comprobablemente útiles |
| Nueva llamada por cada cláusula | No introducir | Multiplica latencia, desalineación y pérdida de contexto |
| Microservicios/event bus | No introducir | No resuelve el defecto de representación |
| Vector DB o segunda memoria semántica | No introducir ahora | Los callbacks actuales son bounded y el fallo principal es de representación/selección |
| Ensemble o cambio de modelo como primera medida | No priorizar | Primero hay que corregir el contrato y medir con una configuración fijada |
| Grandes prompts con cientos de ejemplos | Evitar | Aumentan fragilidad y no separan las dimensiones conceptuales |
| Regex nueva para cada fallo | Evitar | Produce sobreajuste, duplicación y regresiones |

### Sobre el piloto NLP

PR #272 añade el piloto opcional de Stanza, pero eso no justifica convertirlo ya en dependencia de producción. Debe responder a una pregunta limitada: ¿mejoran las señales lingüísticas con suficiente precisión y coste aceptable sobre la baseline actual?

Comparar, en el mismo corpus español:

1. extracción determinista actual;
2. Stanza sin LLM;
3. modelo actual sin hints;
4. modelo con hints del parser.

Medir negación, condicional, límites de cláusula, spans, clíticos, citas, verbos de habla, vocabulario fantástico, CPU, memoria, empaquetado, compatibilidad offline y latencia. El parser solo aporta señales con offsets; no resuelve identidad, permisos, resultado ni persistencia. Promoción a producción requiere mejora incremental demostrada y revisión independiente de licencia y distribución de modelos.

---

## 11. Nuevo diseño de evaluación

La evaluación debe medir el contrato semántico nuevo, no solo si aparecen palabras o slots.

### 11.1 Métricas obligatorias

**Actos comunicativos**
- exactitud del tipo de acto;
- speaker/addressee y atribución separados;
- límites de cita;
- precisión de spans y procedencia.

**Eventos/proposiciones**
- precisión/recall de nodos;
- predicado literal y familia;
- participantes y roles;
- polaridad;
- estatus epistémico;
- fase de acción;
- temporalidad;
- exactitud de escenario completo, contando nodos extra y ausentes.

**Discurso**
- exactitud de enlaces;
- dirección y extremos del enlace;
- callback anchor accuracy;
- precisión/recall de referencia;
- tasa de abstención correcta e incorrecta;
- errores por cambio de tema, corrección y elipsis.

**Acción jugable**
- candidatos correctos y falsos positivos;
- foco de acción correcto;
- dependencias bloqueadas/desbloqueadas correctamente;
- selección de workflow correcto (diálogo, mecánica, aclaración, ninguno);
- falsos avances después de fallo o condición no satisfecha.

**Hechos/operaciones**
- precisión de hechos candidatos;
- exactitud de dirección y tipo de relación;
- campos requeridos completos;
- hechos estables conservados;
- persistencia falsa;
- secretos filtrados;
- operaciones no autorizadas.

Los falsos writes y secretos son gates duros: no pueden compensarse con un F1 alto en otro dominio.

### 11.2 Corpus y anotación

Mantener los corpora de desarrollo y held-out separados. Crear anotaciones por fenómeno y contrastes mínimos:

- cita frente a afirmación propia;
- NPC que habla frente a jugador que habla;
- pregunta frente a intento;
- intención frente a acción ejecutada;
- condición frente a secuencia;
- callback frente a evento;
- reporte frente a hecho observado;
- transferencia frente a propiedad;
- relación positiva, negativa e incierta;
- relación directa e inversa;
- hecho estable frente a detalle efímero;
- acción fallida frente a cambio de mundo;
- referencia única frente a ambigua/oculta/plural;
- corrección dentro del turno y en turnos posteriores.

Cada caso debe tener gold independiente por actos, eventos, enlaces, roles, evidencia, acción candidata y hechos. Las anotaciones no deben derivarse de la salida del modelo ni de las regex que se están probando. Revisar dobles anotaciones en los casos relacionales complejos.

### 11.3 Métricas actuales y umbrales

No retirar ni mezclar los cuatro informes del run #281. Sirven como baseline histórico de v2, con su limitación de procedencia. Los umbrales provisionales que propone el propio informe —por ejemplo, modalidad compuesta al menos 85 %, callback al menos 80 %, transferencia completa al menos 80 %, y 22/22 pruebas live— deben considerarse **propuestas pendientes de aprobación**, no gates ya existentes.

La nueva aceptación debe fijar umbrales por dimensión antes de mirar el resultado de la siguiente ejecución. No se deben cambiar denominadores, gold ni clasificación de casos para lograr un pass. Los escenarios críticos se repiten tres veces para observar inestabilidad. La precisión y el coste de abstención se publican junto al recall: elevar recall con relaciones especulativas no es aceptable.

### 11.4 Separar tipos de prueba

- unit/contract: decodificación, spans, invariantes y normalizadores; rápidos, obligatorios por PR;
- deterministic pipeline: selector, resolución, dependencias, reglas y persistencia con proveedores simulados;
- live smoke: muestra pequeña de casos críticos para detectar degradaciones del proveedor;
- live por familia: benchmark dirigido cuando cambia un área semántica concreta;
- full live acceptance: suite fijada, repetición de críticos y configuración totalmente registrada;
- SillyTavern acceptance: workflow real independiente que comprueba chats, continuidad, aclaraciones, tiradas, reintentos y recuperación.

El run #281 tardó unos 42 minutos y medio; la suite completa no debe ejecutarse como sustituto de los tests deterministas en cada cambio pequeño. Sí debe ejecutarse al completar los hitos de arquitectura y como gate de aceptación de la nueva versión. No hay telemetría GPU/VRAM suficiente en ese informe para concluir cuánto se utilizó la RTX 5070 Ti.

---

## 12. Plan de PR propuesto

La siguiente secuencia es una recomendación de arquitectura después de #281, no una declaración de que estas PR existan ya.

| PR futura | Objetivo | Entrega principal | Criterio de cierre |
|---|---|---|---|
| #282 | Esta auditoría | Fuente de verdad de diagnóstico, diseño y secuencia | Documentos e índices coherentes; alcance y no-alcance explícitos |
| #284 | Contratos críticos inmediatos v2 | entity_type obligatorio y acotado, callback-only step, relation claims que reflejan acciones, vocabulario de habla compartido y gold relacional reconciliado | Parser/normalizadores con regresiones deterministas; v1/v2 durables sin cambios; no se debilitan los controles negativos |
| #285 | Contratos semánticos v3 | DTOs versionados de actos, eventos, enlaces, hechos y spans; decoder y fixtures | Tests exhaustivos; v1/v2 siguen decodificando; ninguna ruta de producción usa v3 |
| #286 | Interpretación holística v3 | Prompt único y benchmark en sombra v2/v3 | Mejora por familia sin aumentar citas/relaciones/eventos falsos; spans y cardinalidad correctos |
| #287 | Foco y dependencias de acciones | Selector backend, grafo de acciones, checkpoint parcial y reanudación | No se adjudican nodos condicionales; fallos no desbloquean sucesores; idempotencia durable |
| #288 | Hechos y persistencia semántica | Fact candidates, preservación de detalles NPC, operaciones con invariantes de dominio | Cero falsos writes críticos; campos obligatorios y procedencia validados |
| #289 | Aceptación v3 | Comparación final, repetición live, SillyTavern y decisión de retirada gradual v2 | Gates aprobados por dimensión; replay histórico y rollback probados |

### Dependencias y disciplina de alcance

- #284 puede empezar sobre v2 sin esperar al nuevo contrato.
- #285 define los tipos sin cambiar el prompt de producción.
- #286 depende de que el contrato y el scorer estén estables.
- #287 depende de que los eventos y enlaces sean fiables; no debe inferir dependencias a partir de una lista de steps sin tipos.
- #288 consume facts/eventos validados, no el texto crudo ni los argumentos indiscriminadamente.
- #289 requiere todas las fases anteriores y un SHA verificable.

Se recomienda una PR activa cada vez, desde el último main integrado. No se debe forzar el tamaño de las PR por número de líneas. Una PR debe ser grande cuando las dependencias lo exijan, no acumular cambios de prompt, modelo, persistencia, parser y UI sin una frontera verificable.

---

## 13. Criterios de aceptación de la arquitectura nueva

La nueva representación no se considera lista por compilar ni por conseguir JSON válido. Debe demostrar:

1. Cada acto comunicativo se distingue de los eventos que contiene o cita.
2. Speaker, agent, addressee y source/reporter no se confunden.
3. Los spans de cada campo apuntan al texto correcto y no absorben texto del historial.
4. Los callbacks no crean nodos de evento por sí mismos.
5. Los condicionales enlazan el evento consecuente a la condición y no habilitan una acción prematuramente.
6. Negación e incertidumbre tienen alcance sobre la proposición correcta.
7. Roles de transferencia no crean relaciones permanentes sin una afirmación explícita o consecuencia validada.
8. Las relaciones conservan extremos, dirección, predicado de superficie y tipo normalizado.
9. El selector backend no activa citas, reportes de NPC, hipótesis ni acciones futuras.
10. Los eventos que necesitan mecánicas se adjudican una vez, con idempotencia, y los fallos no habilitan consecuencias condicionadas al éxito.
11. Los hechos duraderos explícitos de NPC se conservan sin persistir rumores, citas o detalles efímeros.
12. Toda creación/update tiene campos obligatorios válidos, identidad visible y procedencia.
13. Ninguna prueba histórica de replay depende del prompt vigente.
14. Cero falsos writes críticos y cero filtraciones de secretos en todos los controles, unitarios e integrados.
15. El benchmark v3 mejora por escenario/familia con una configuración fijada y resultados reproducibles.
16. La aceptación manual con SillyTavern queda registrada por separado.

---

## 14. Riesgos, decisiones que se descartan y preguntas abiertas

### Riesgos a gestionar

- **Sobreingeniería del esquema:** una estructura con muchos tipos puede ser más difícil para el modelo. Empezar por los campos imprescindibles y medir, no construir una ontología universal.
- **Pérdida de compatibilidad:** mantener adaptadores y lectores v1/v2; no alterar datos ya persistidos.
- **Parser y LLM en desacuerdo:** el parser produce hints con offsets y versión; nunca reemplaza evidencia o significado por sí solo.
- **Aumento de latencia:** una única llamada semántica reduce la multiplicación de llamadas; el coste del prompt v3 se mide con P50/P95.
- **Falsos positivos al mejorar recall:** publicar precisión, abstención y escenario exacto; no premiar nodos extra.
- **Hechos de NPC incompletos:** endurecer el dominio antes de confiar en instrucciones de prompt.
- **Trazabilidad insuficiente:** fijar el SHA real y hacer que el runner falle si resumen e informes no coinciden.

### Decisiones que no se recomiendan ahora

- reescribir todo el runtime de turnos;
- crear un parser sintáctico completo propio;
- añadir una segunda llamada LLM por paso;
- usar el modelo más grande o un ensemble como sustituto del diseño de contrato;
- promover Stanza a runtime por haber añadido el piloto;
- añadir una base vectorial para resolver los callbacks actuales;
- ampliar indefinidamente regex de español;
- confiar en un campo confidence del modelo como probabilidad calibrada;
- permitir al LLM asignar IDs, outcomes, active action o permiso de escritura;
- relajar la validación estricta para que pasen respuestas malformed.

### Preguntas que se deben cerrar antes de #285

1. ¿Qué tipos de actos comunicativos necesita de verdad el MVP y cuáles pueden quedar como OTHER/UNKNOWN?
2. ¿Qué familias de eventos entran en v3 inicialmente y cuáles se mantienen como OTHER?
3. ¿Qué condiciones convierten un evento explícito en una acción jugable soportada por reglas?
4. ¿Qué hechos de campaña son duraderos y qué tipos son solo estado efímero de escena?
5. ¿Qué relaciones se normalizan a una taxonomía controlada y cómo se anotan sus extremos/dirección?
6. ¿Cómo se representa una conversación NPC sin confundir la frase pronunciada con la verdad del mundo?
7. ¿Qué parte del checkpoint se conserva en la resolución durable y qué parte se recalcula al corregir una intención?

Estas decisiones deben resolverse con requisitos del producto y ejemplos anotados, no por la preferencia de una implementación concreta.

---

## 15. Conclusión

La evaluación de PR #281 no demuestra que el modelo sea incapaz de comprender el lenguaje. Demuestra que el sistema puede puntuar alto en campos aislados y fallar en escenarios completos donde debe combinar modalidad, discurso, roles, dependencia, evidencia y consecuencias. El ejemplo de «Retomando» convertido en evento y los falsos positivos relacionales muestran límites de la representación actual, no meros errores ortográficos.

La aplicación necesita dejar de tratar cada segmento relevante como un step de intención homogéneo. Debe representar por separado lo que el jugador hace al hablar, los eventos/estados de los que habla, cómo se conectan entre sí y qué hechos podrían ser persistentes. Solo después el backend puede determinar qué es una acción jugable y qué consecuencias puede aceptar.

**La ruta óptima es evolución del contrato semántico y de la selección de acción, no reescritura de infraestructura.** Conservamos el monolito modular, una llamada LLM holística, el límite de evidencia, el resolver determinista, las reglas del servidor y el ciclo durable. Cambiamos la ontología intermedia, retiramos la autoridad del índice activo del modelo, formalizamos el grafo de discurso/eventos y hacemos más estricta la frontera entre hechos y operaciones.

La PR #282 establece esa dirección. La siguiente implementación debería empezar por los invariantes v2 que ya han fallado (#284), y después construir los contratos v3 con compatibilidad y evaluación en sombra antes de usarlos para adjudicar o persistir.

**Regla de diseño final:** el LLM interpreta el significado; los resolvers identifican las entidades; el backend decide qué puede hacerse; el motor determina los resultados; y solo el dominio confirma qué pasa a formar parte del mundo persistente.
