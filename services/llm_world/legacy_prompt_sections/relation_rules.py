"""Persistent relationship creation, update and removal instructions."""

RELATION_RULES = r"""24. RELACIONES
============================================================

Una relación representa una conexión PERSISTENTE entre dos entidades.

Ejemplos:

- pertenece a una organización;
- miembro de una facción;
- familiar de;
- padre de;
- hijo de;
- aliado de;
- enemigo de;
- trabaja para;
- debe dinero a;
- está casado con;
- relación política persistente;
- relación comercial persistente;
- relación social persistente.

Una interacción momentánea NO es automáticamente una relación.


============================================================
25. NO CREAR RELACIONES POR INTERACCIONES MOMENTÁNEAS
============================================================

NO crees relaciones simplemente porque dos entidades:

- hablen;
- se conozcan;
- se saluden;
- estén juntas;
- se ataquen una vez;
- se ayuden una vez;
- discutan una vez;
- sospechen;
- sean amables;
- sean antipáticas;
- se miren;
- se amenacen;
- se persigan;
- luchen.

Ejemplo:

"El guardia ataca a Fungoso."

-> NO crear automáticamente "enemigo".

Ejemplo:

"El guardia declara que considera a Fungoso su enemigo y que lo perseguirá."

-> Puede justificar una relación persistente si la narrativa establece realmente
esa relación.


============================================================
26. CREAR RELACIONES
============================================================

Usa:

create_relation

cuando la narrativa establece una relación persistente nueva.

Ejemplo:

{
  "type": "create_relation",
  "relation_id": "aldric_miembro_guardia_hierro",
  "subject_id": 2,
  "relation_type": "miembro_de",
  "target_id": 7,
  "metadata": {}
}

subject_id y target_id deben ser:

- IDs existentes del contexto;
- o referencias "$..." creadas anteriormente.

Si una entidad nueva necesita una relación:

crea primero la entidad y después la relación.

Ejemplo:

{
  "operations": [
    {
      "type": "create_entity",
      "name": "Aldric",
      "entity_type": "npc",
      "description": "Tabernero.",
      "notes": "",
      "active": true,
      "ref": "aldric"
    },
    {
      "type": "create_relation",
      "relation_id": "aldric_miembro_guardia_hierro",
      "subject_id": "$aldric",
      "relation_type": "miembro_de",
      "target_id": 7,
      "metadata": {}
    }
  ]
}


============================================================
27. NO DUPLICAR RELACIONES
============================================================

Antes de crear una relación:

comprueba RELACIONES CONOCIDAS.

Si ya existe una relación equivalente:

-> NO crear otra.

Si la narrativa repite la relación:

-> NO hacer nada.

Si la relación existente cambia realmente:

-> utilizar update_relation con su relation_id real.

Si deja de existir:

-> utilizar remove_relation con su relation_id real.

Nunca inventes un relation_id para modificar una relación existente.


============================================================
28. ACTUALIZAR RELACIONES
============================================================

Usa:

update_relation

solo para una relación existente.

Ejemplo:

{
  "type": "update_relation",
  "relation_id": "aldric_guardia_hierro",
  "relation_type": "aliado_de",
  "target_id": 7,
  "metadata": {},
  "active": true
}

El relation_id debe existir en RELACIONES CONOCIDAS.

NO inventes uno.


============================================================
29. ELIMINAR RELACIONES
============================================================

Usa:

remove_relation

solo cuando la narrativa confirme que una relación persistente existente
ha dejado de existir.

Ejemplo:

{
  "type": "remove_relation",
  "relation_id": "aldric_guardia_hierro"
}

El relation_id debe existir realmente.


"""
