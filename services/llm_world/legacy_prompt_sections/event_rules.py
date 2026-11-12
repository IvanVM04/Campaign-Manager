"""Persistent event classification and duplication rules."""

EVENT_RULES = r"""============================================================
30. EVENTOS
============================================================

Un evento representa un acontecimiento histórico o causal relevante para
el mundo.

NO registres cada acción narrativa como evento.

Un evento debe tener relevancia suficiente para justificar su persistencia.

Puede ser relevante por:

- historia;
- causalidad;
- política;
- consecuencias futuras;
- estado del mundo;
- decisiones futuras;
- continuidad de campaña.

Ejemplos:

- una localización importante es destruida;
- una figura importante muere;
- se descubre un secreto importante;
- comienza una guerra;
- termina una guerra;
- ocurre una traición significativa;
- aparece una amenaza importante;
- cambia el poder político;
- ocurre un acontecimiento con consecuencias futuras.


============================================================
31. NO CREAR EVENTOS PARA ACCIONES COTIDIANAS
============================================================

NO crees eventos para:

- caminar;
- sentarse;
- hablar normalmente;
- saludar;
- abrir una puerta normal;
- sacar un arma;
- mirar alrededor;
- comer;
- beber;
- acciones cotidianas;
- conversaciones sin consecuencia persistente.

Ejemplo:

"El personaje abre la puerta de la taberna."

-> normalmente NO crear evento.

Ejemplo:

"La puerta sellada de la cripta se abre por primera vez en quinientos años."

-> Puede justificar un evento si el hecho es históricamente relevante.


============================================================
32. EVENTOS EXISTENTES
============================================================

Si el mismo acontecimiento ya aparece en EVENTOS CONOCIDOS:

-> NO duplicarlo.

No existe una operación de actualización de eventos.

Si la narrativa añade información a un evento existente pero no existe una
operación disponible para actualizarlo:

-> NO inventes una operación.

Registra únicamente otros cambios representables.


============================================================
"""
