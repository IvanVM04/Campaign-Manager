"""Item definitions, instances, inventory and transfer instructions."""

ITEM_RULES = r"""11. ITEMS Y INSTANCIAS
============================================================

Hay una diferencia fundamental:

ITEM = definición o tipo de objeto.

ITEM INSTANCE = copia física concreta de ese objeto.

Ejemplo:

"Espada de hierro"

puede representar el ITEM.

"La espada de hierro que Neria lleva en la mano"

puede representar una INSTANCE concreta.


============================================================
12. CREAR ITEMS
============================================================

Usa:

create_item

cuando aparece un tipo de objeto persistente que todavía no existe en
ITEMS CONOCIDOS.

El backend genera el item_id.

NO inventes el item_id.

Ejemplo:

{
  "type": "create_item",
  "name": "Llave de hierro oxidada",
  "description": "Una llave de hierro oxidada.",
  "significance": "",
  "unique": false,
  "notes": "",
  "ref": "llave_hierro"
}

Para armaduras y escudos SRD 5e 2014, añade `armor_key` a la definición
del objeto cuando corresponda. Valores permitidos:
`padded`, `leather`, `studded_leather`, `hide`, `chain_shirt`,
`scale_mail`, `breastplate`, `half_plate`, `ring_mail`,
`chain_mail`, `splint`, `plate`, `shield`.
La armadura corporal usa `equipment_slot: "body"`; el escudo usa
`equipment_slot: "off_hand"`. No asignes `weapon_key` a una armadura
ni combines `weapon_key` y `armor_key`.


============================================================
13. ITEM NUEVO + INSTANCIA NUEVA
============================================================

Este es un caso especialmente importante.

Si la narrativa introduce una copia física concreta de un tipo de objeto que
todavía NO existe en ITEMS CONOCIDOS:

1. crea primero el ITEM;
2. asigna una referencia al ITEM;
3. crea después la INSTANCE;
4. utiliza "$referencia" como item_id.

Ejemplo:

Narrativa:

"Aldric entrega al aventurero una llave de hierro oxidada."

Si no existe la llave en el contexto y el objeto debe persistir:

{
  "operations": [
    {
      "type": "create_item",
      "name": "Llave de hierro oxidada",
      "description": "Una llave de hierro oxidada.",
      "significance": "",
      "unique": false,
      "notes": "",
      "ref": "llave_hierro"
    },
    {
      "type": "create_item_instance",
      "item_id": "$llave_hierro",
      "instance_number": 1,
      "owner_id": ID_REAL_DEL_RECEPTOR,
      "location_id": null,
      "condition": "oxidada",
      "notes": "",
      "active": true
    }
  ]
}

Si el receptor es el personaje activo y este tiene entity_id 1:

"owner_id": 1

NO escribas un número inventado.

Si no puedes determinar el propietario con seguridad:

NO inventes el owner_id.


============================================================
14. CUÁNDO CREAR UNA INSTANCE
============================================================

Una INSTANCE representa una copia física concreta.

Créala cuando la narrativa confirme suficientemente que esa copia física existe
y debe poder rastrearse.

Ejemplos:

- una llave concreta encontrada;
- una espada concreta entregada;
- un objeto único descubierto;
- una copia concreta que cambia de propietario;
- un objeto físico relevante recogido por el personaje.

NO crees instancias automáticamente para objetos genéricos.

Ejemplo:

"Hay veinte espadas en la armería."

-> NO crear veinte instancias.

"El personaje toma la espada de plata que estaba sobre el altar."

-> Puede requerir una instancia si esa espada concreta es persistente y no
existe todavía en el contexto.


============================================================
15. INSTANCIAS EXISTENTES
============================================================

Si una instancia física ya existe en:

INSTANCIAS DE OBJETOS CONOCIDAS

NO crees otra instancia porque vuelva a aparecer.

Debes reutilizar la instancia existente.

Ejemplo:

ID 25: Espada de hierro
(item_id=10, instance_number=1, owner_id=1)

Narrativa:

"Fungoso vuelve a empuñar la espada de hierro."

-> NO crear otra instancia.

La instancia 25 continúa siendo la misma espada.


============================================================
16. IDENTIFICAR UNA INSTANCE EXISTENTE
============================================================

Cuando la narrativa se refiere a un objeto concreto:

1. busca primero una instancia conocida compatible;
2. considera nombre del item;
3. considera propietario;
4. considera ubicación;
5. considera condición;
6. considera la continuidad narrativa;
7. utiliza la instancia existente si la identidad es inequívoca.

Si existen varias instancias compatibles y no puedes determinar cuál es:

NO inventes cuál es.

En ese caso es preferible no generar la operación.


============================================================
17. RECOGER OBJETOS
============================================================

Cuando la narrativa confirma que un personaje recoge un objeto:

1. identifica la instancia física;
2. si existe, reutilízala;
3. si cambia el propietario, representa ese cambio;
4. si la instancia no tiene propietario, puedes actualizar su propietario;
5. si pertenece a otra entidad y pasa al personaje, utiliza transfer_item;
6. solo crea una instancia nueva si la narrativa confirma una copia física nueva;
7. nunca inventes instance_id;
8. nunca inventes item_id;
9. nunca inventes owner_id;
10. nunca inventes location_id.

Ejemplo:

Contexto:

ID 25 = espada concreta
owner_id = 7

Narrativa:

"Fungoso recibe la espada de Neria."

Si Fungoso = ID 1:

{
  "operations": [
    {
      "type": "transfer_item",
      "instance_id": 25,
      "new_owner_id": 1
    }
  ]
}

NO crear otra espada.


============================================================
18. TRANSFERIR OBJETOS
============================================================

Usa:

transfer_item

cuando una instancia física EXISTENTE cambia explícitamente de propietario.

Ejemplo:

{
  "type": "transfer_item",
  "instance_id": 25,
  "new_owner_id": 1
}

instance_id debe ser:

- un ID de una instancia conocida;
- o una referencia "$..." creada anteriormente en este mismo turno si la
instancia fue creada previamente.

new_owner_id debe ser:

- un ID de entidad conocida;
- o una referencia "$..." creada anteriormente.

No utilices transfer_item si no puedes identificar la instancia.


============================================================
19. ACTUALIZAR INSTANCIAS
============================================================

Usa:

update_item_instance

cuando cambia una propiedad de una instancia existente.

Ejemplo:

{
  "type": "update_item_instance",
  "instance_id": 25,
  "condition": "dañada"
}

Solo incluye los campos que cambian.

Reglas:

- campo omitido = no modificar;
- null = borrar explícitamente el valor;
- NO uses null porque simplemente desconozcas el valor.

Ejemplo:

"El personaje deja la espada en el suelo."

Si la espada era propiedad del personaje:

{
  "type": "update_item_instance",
  "instance_id": 25,
  "owner_id": null
}

NO inventes location_id.


============================================================
20. INSTANCE_NUMBER
============================================================

instance_number NO es el ID interno de la instancia.

Es el número de copia dentro del mismo ITEM.

La primera instancia de un ITEM normalmente utiliza:

"instance_number": 1

Si ya existen instancias del mismo ITEM:

- utiliza un número que no entre en conflicto;
- NO inventes instance_id.

Si no puedes determinar correctamente el número de copia y no es necesario
para representar el hecho con seguridad:

no inventes información.


============================================================
"""
