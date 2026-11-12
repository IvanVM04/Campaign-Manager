"""Persistent resource and quantity-change instructions."""

RESOURCE_RULES = r"""21. RECURSOS
============================================================

Los recursos representan cantidades cuantificables.

Ejemplos:

- oro;
- reputación;
- suministros;
- influencia;
- cualquier otro recurso cuantificable.

Solo registra un recurso cuando la narrativa confirme un cambio cuantitativo
persistente.


============================================================
22. CREAR RECURSOS
============================================================

Usa:

create_resource

cuando la narrativa introduce un tipo de recurso persistente que todavía no
existe.

Ejemplo:

{
  "type": "create_resource",
  "name": "Oro",
  "resource_type": "currency",
  "unit": "gp",
  "notes": "",
  "ref": "oro"
}

El backend genera el resource_id.

Si posteriormente necesitas utilizarlo en la misma tanda:

"resource_id": "$oro"


============================================================
23. GANAR, GASTAR Y TRANSFERIR RECURSOS
============================================================

Ganar:

{
  "type": "gain_resource",
  "resource_id": 10,
  "owner_id": 2,
  "amount": 50
}

Gastar:

{
  "type": "spend_resource",
  "resource_id": 10,
  "owner_id": 2,
  "amount": 20
}

Transferir:

{
  "type": "transfer_resource",
  "resource_id": 10,
  "subject_id": 2,
  "target_id": 7,
  "amount": 15
}

Solo utiliza estas operaciones cuando la narrativa confirme:

- el recurso;
- la cantidad;
- quién gana;
- quién pierde;
- quién paga;
- quién entrega;
- quién recibe.

NO inventes cantidades.

NO calcules cantidades.

NO conviertas una negociación en una compra.

NO conviertas una petición en un pago.

NO conviertas una amenaza en una transferencia.

Ejemplo:

"El mercader pide 50 monedas por la espada."

-> NO gastar 50.

"El personaje paga las 50 monedas al mercader."

-> SÍ registrar el cambio correspondiente.


============================================================
"""
