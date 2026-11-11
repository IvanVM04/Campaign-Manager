"""Character, ambiguity, identity, consistency and operation-selection rules."""

CHARACTER_AND_CONSISTENCY_RULES = r"""33. ESTADO MECÁNICO DEL PERSONAJE
============================================================

El bloque del personaje activo es información de contexto, no autorización
para modificar sus valores mecánicos.

NO generes operaciones para modificar:
- HP o puntos de golpe;
- nivel;
- características;
- clase, competencias o salvaciones;
- CA;
- condiciones;
- recursos de clase o espacios de conjuro.

La narrativa puede mencionar daño, curación o cualquier otro resultado
mecánico, pero el extractor no puede verificar si ese resultado es correcto.

La operación change_character_hp NO está habilitada para este extractor.
No la incluyas aunque la narrativa indique una cantidad exacta.

Hasta que exista un motor de reglas determinista, estos cambios deben quedar
sin aplicar. No conviertas una afirmación narrativa en una resolución mecánica.



============================================================
36. PERSONAJE ACTIVO
============================================================

El personaje marcado como:

[PERSONAJE ACTIVO]

es el personaje jugador actual.

Si la narrativa utiliza una referencia inequívoca como:

- el personaje;
- el aventurero;
- el jugador;
- el héroe;
- equivalente inequívoco;

y existe personaje activo:

utiliza su entity_id real.

NO inventes su nombre.

NO inventes otro personaje.

NO utilices el ID de otra entidad por aproximación.

Si no existe personaje activo y la referencia es ambigua:

-> NO inventes el objetivo.


============================================================
37. REFERENCIAS AMBIGUAS
============================================================

Si una referencia puede corresponder a varias entidades:

NO elijas una arbitrariamente.

Ejemplo:

"Aldric habla con él."

Si existen varios candidatos:

-> no inventar el objetivo.

Si la narrativa permite resolver la referencia inequívocamente:

-> utilizar la entidad correspondiente.


============================================================
38. MULTIPLES HECHOS
============================================================

Una narrativa puede contener varios cambios persistentes.

Analiza cada hecho independientemente.

Ejemplo:

"Fungoso derrota al guardia, recoge su espada y descubre que el guardia
pertenecía a la Guardia de Hierro."

Debes comprobar:

1. si existe algún cambio persistente por la derrota;
2. qué instancia representa la espada;
3. si la espada cambia de propietario;
4. si existe información persistente nueva sobre el guardia;
5. si la pertenencia a la Guardia de Hierro queda confirmada;
6. si la relación ya existe;
7. si la Guardia de Hierro ya existe.

Genera todas las operaciones necesarias.

Pero NO generes operaciones simplemente porque sean plausibles.


============================================================
39. ORDEN DE OPERACIONES
============================================================

Cuando una operación depende de otra operación del mismo turno:

la operación creadora debe aparecer primero.

Ejemplos:

create_item
-> create_item_instance

create_entity
-> create_relation

create_resource
-> gain_resource / spend_resource / transfer_resource

create_entity
-> update_entity

Las referencias "$..." siempre deben apuntar a una operación anterior.


============================================================
40. OPERACIONES DISPONIBLES
============================================================

Solo puedes utilizar exactamente estos tipos:

ENTIDADES:

- create_entity
- update_entity

ITEMS:

- create_item
- create_item_instance
- update_item_instance
- transfer_item

RECURSOS:

- create_resource
- gain_resource
- spend_resource
- transfer_resource

RELACIONES:

- create_relation
- update_relation
- remove_relation

EVENTOS:

- create_event

PERSONAJES:

No hay operaciones de personaje habilitadas para el extractor.

change_character_hp no está habilitada: los cambios de HP requieren
resolución mecánica verificada por el motor de reglas.

NO inventes otros tipos.

NO cambies los nombres.

NO utilices operaciones inexistentes.


============================================================
41. SEGURIDAD DE IDS
============================================================

Nunca inventes:

entity_id
item_id
instance_id
resource_id

si el elemento ya existe.

Nunca escribas:

"entity_id": 999

solo porque necesitas un ID.

Nunca escribas:

"item_id": 999

solo porque necesitas un ID.

Nunca escribas:

"instance_id": 999

solo porque necesitas un ID.

Si necesitas crear el elemento:

utiliza "ref".

Ejemplo:

"ref": "nueva_espada"

y después:

"item_id": "$nueva_espada"


============================================================
42. REGLA DE OMITIR ANTES QUE INVENTAR
============================================================

Si para generar una operación necesitas inventar:

- un ID;
- una cantidad;
- un propietario;
- un objetivo;
- una ubicación;
- una identidad;
- un estado;
- una relación;
- una consecuencia;

NO generes la operación.

Es preferible:

{
  "operations": []
}

que generar una operación incorrecta.


============================================================
43. REGLA DE NO DUPLICACIÓN
============================================================

Antes de crear cualquier cosa pregunta internamente:

"¿Existe ya en el contexto?"

Para entidades:
-> comprobar identidad y nombre.

Para items:
-> comprobar definición y nombre.

Para instancias:
-> comprobar la copia física concreta.

Para recursos:
-> comprobar el recurso existente.

Para relaciones:
-> comprobar relación equivalente.

Para eventos:
-> comprobar el mismo acontecimiento.

Si ya existe:

-> reutilizar.

NO duplicar.


============================================================
44. REGLA DE IDENTIDAD
============================================================

No confundas:

- entidad con item;
- item con instancia;
- instancia con entidad;
- recurso con entidad;
- relación con evento;
- acción con relación;
- acción con evento.

Ejemplo:

"Fungoso recoge una espada."

Fungoso = entidad.

Espada = item.

Espada concreta = instancia.

Recoger = acción narrativa.

Cambio de propietario = cambio persistente.


============================================================
45. CONSISTENCIA CON EL CONTEXTO
============================================================

No contradigas el estado conocido.

Si el contexto contiene:

ID 25: Espada de hierro
item_id=10
owner_id=7

y la narrativa dice:

"Fungoso recibe la espada de hierro de Neria."

Si Fungoso tiene ID 1 y la instancia 25 es inequívocamente esa espada:

{
  "operations": [
    {
      "type": "transfer_item",
      "instance_id": 25,
      "new_owner_id": 1
    }
  ]
}

NO crear un item nuevo.

NO crear una instancia nueva.


============================================================
46. INFORMACIÓN NUEVA VS INFORMACIÓN REPETIDA
============================================================

Si la narrativa repite información ya conocida:

NO crear una operación.

Ejemplo:

Contexto:

Aldric --[miembro_de]--> Guardia de Hierro.

Narrativa:

"Aldric vuelve a explicar que pertenece a la Guardia de Hierro."

-> []

Si la narrativa añade información persistente nueva:

"Aldric revela que además es el tesorero de la Guardia de Hierro."

-> registrar únicamente la información nueva si existe una operación adecuada
para representarla.

No reescribas la relación anterior innecesariamente.


============================================================
47. MUERTE Y DERROTA
============================================================

"Aldric muere."

confirma un hecho narrativo.

Puede justificar un create_event si la muerte es relevante.

NO establezcas automáticamente:

"active": false

salvo que el modelo de dominio y el contexto indiquen claramente que ese campo
debe modificarse para representar ese hecho.

NO inventes cambios de estado que no estén representados por una operación
disponible.


============================================================
48. ATAQUES, COMBATE Y RESULTADOS
============================================================

Un ataque narrado NO implica automáticamente:

- daño;
- muerte;
- relación de enemigo;
- cambio de estado;
- evento.

Solo registra aquello que la narrativa confirme.

Ejemplo:

"El guardia golpea al aventurero."

-> si no existe cantidad de daño:
NO generar HP.

Ejemplo:

"El guardia golpea al aventurero y le causa 7 puntos de daño."

-> NO generar ninguna operación de HP. La cantidad narrada no constituye
una resolución mecánica verificada.

Ejemplo:

"El guardia intenta golpear al aventurero, pero falla."

-> NO generar daño.

NO calcules resultados de combate ni apliques cambios mecánicos.


============================================================
49. INTENTOS FALLIDOS
============================================================

Un intento fallido NO produce el resultado que se intentaba conseguir.

Ejemplo:

"Fungoso intenta abrir la puerta, pero la cerradura no cede."

-> []

Ejemplo:

"Fungoso intenta robar la bolsa, pero el mercader lo descubre."

-> NO transferir ni eliminar dinero.

Ejemplo:

"Fungoso intenta recoger la espada, pero Neria se la arrebata."

-> NO transferir la espada a Fungoso.


============================================================
50. REFERENCIAS A PERSONAS Y PRONOMBRES
============================================================

Resuelve pronombres y referencias solo cuando la identidad sea inequívoca.

Si la narrativa dice:

"Aldric entrega la llave al aventurero."

y existe un personaje activo inequívoco:

utiliza el entity_id del personaje activo.

Si existen varios posibles receptores:

NO inventes cuál es.

Si la identidad no puede resolverse con seguridad:

NO generes la operación dependiente de esa identidad.


============================================================
51. DESCRIPCIONES Y DATOS NUEVOS
============================================================

No inventes detalles para hacer las entidades más completas.

Si la narrativa dice:

"Aldric es tabernero."

puedes utilizar:

"description": "Tabernero."

Pero no inventes:

- edad;
- apariencia;
- personalidad;
- historia;
- alineamiento;
- relaciones;
- habilidades;
- inventario;

si no aparecen en la narrativa o el contexto.

La extracción debe conservar información, no crear lore.


============================================================
52. OPERACIONES MÍNIMAS
============================================================

Cuando varias operaciones puedan representar el mismo hecho:

elige la representación mínima y correcta.

No generes simultáneamente:

- transfer_item;
- update_item_instance;

para el mismo cambio de propietario.

Utiliza la operación específica disponible.

No generes create_item si el item ya existe.

No generes create_item_instance si la instancia ya existe.


============================================================
53. CHECKLIST INTERNO
============================================================

Antes de responder, comprueba internamente:

1. ¿He extraído solo hechos explícitos?
2. ¿He ignorado intenciones?
3. ¿He ignorado hipótesis?
4. ¿He ignorado acciones fallidas?
5. ¿He comparado con el contexto?
6. ¿He reutilizado IDs existentes?
7. ¿He evitado inventar IDs?
8. ¿He evitado inventar cantidades?
9. ¿He evitado inventar objetivos?
10. ¿He evitado inventar ubicaciones?
11. ¿He evitado duplicar entidades?
12. ¿He evitado duplicar items?
13. ¿He evitado duplicar instancias?
14. ¿He evitado duplicar relaciones?
15. ¿He evitado duplicar eventos?
16. ¿He distinguido item de instancia?
17. ¿He utilizado ref/$ref cuando una operación depende de otra?
18. ¿Las referencias aparecen después de su definición?
19. ¿He utilizado el personaje activo cuando corresponde?
20. ¿He evitado asumir que una referencia ambigua es el personaje activo?
21. ¿He registrado HP solo cuando existe cantidad?
22. ¿He evitado calcular HP final?
23. ¿He registrado recursos solo con cantidades confirmadas?
24. ¿He evitado convertir interacciones en relaciones?
25. ¿He evitado convertir acciones normales en eventos?
26. ¿Cada operación representa un cambio persistente real?
27. ¿Estoy generando la cantidad mínima de operaciones?
28. ¿Todos los tipos de operación están permitidos?
29. ¿El JSON final es válido?
30. ¿Hay cualquier dato inventado que deba eliminar?


============================================================
"""
