"""Persistent entity creation and update instructions."""

ENTITY_RULES = r"""9. CREAR ENTIDADES
============================================================

Una entidad representa un elemento persistente identificable del mundo.

Puede ser:

- persona;
- criatura;
- NPC;
- organización;
- facción;
- localización;
- u otro elemento representable mediante entity_type.

Usa:

create_entity

solo cuando la narrativa introduce una entidad nueva con identidad propia y
relevancia persistente.

Ejemplo:

"El tabernero deja el vaso y se presenta como Aldric."

Puede justificar:

{
  "type": "create_entity",
  "name": "Aldric",
  "entity_type": "npc",
  "description": "Tabernero.",
  "notes": "",
  "active": true
}

No crees automáticamente una entidad solo porque aparezca un nombre propio.

Un nombre propio es una señal de identidad, no una obligación de persistencia.

Ejemplo:

"Entran en El Barril Agrietado."

-> NO es obligatorio crear una entidad para la taberna.

Pero:

"El grupo descubre que El Barril Agrietado es la base de la Guardia de Hierro."

-> Puede justificar una entidad de tipo location si la localización tiene
relevancia persistente para la campaña.

No crees entidades genéricas como:

- un hombre;
- una mujer;
- un guardia;
- unos soldados;
- una criatura;
- una sombra;

salvo que la narrativa los convierta explícitamente en una entidad identificable
y persistente.


============================================================
10. ACTUALIZAR ENTIDADES
============================================================

Usa:

update_entity

cuando una entidad EXISTENTE recibe información persistente nueva que puede
representarse mediante los campos disponibles.

Utiliza únicamente el entity_id real.

Incluye únicamente los campos que realmente cambian.

NO reemplaces innecesariamente información existente.

NO inventes valores para campos que no aparecen en la narrativa.

Ejemplo:

{
  "type": "update_entity",
  "entity_id": 2,
  "notes": "Ahora sabemos que pertenece a la Guardia de Hierro."
}


============================================================
"""
