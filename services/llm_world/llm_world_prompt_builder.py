"""Prompt construction for extracting structured world operations."""

from models.turn_context import TurnContext

from .legacy_prompt_sections import STATIC_INSTRUCTIONS
from .llm_world_context_renderer import LLMWorldContextRenderer


class LLMWorldPromptBuilder:
    """Build the legacy world-extraction prompt from a turn context."""

    @staticmethod
    def build_prompt(
        text: str,
        context: TurnContext,
    ) -> str:
        """
        Construye el prompt para extraer cambios persistentes
        del turno a partir de hechos explícitos de la narrativa.
        """

        context_blocks = LLMWorldContextRenderer.build_context(context)

        prompt = STATIC_INSTRUCTIONS

        # ------------------------------------------------------------
        # CONTEXTO DINÁMICO
        # ------------------------------------------------------------

        dynamic_context = f"""

============================================================
CONTEXTO ACTUAL DEL MUNDO
============================================================

PERSONAJE ACTIVO:

{context_blocks['character_block']}


ENTIDADES CONOCIDAS:

{context_blocks['known_entities']}


ITEMS CONOCIDOS:

{context_blocks['known_items']}


INSTANCIAS DE OBJETOS CONOCIDAS:

{context_blocks['known_item_instances']}


RECURSOS CONOCIDOS:

{context_blocks['known_resources']}


RELACIONES CONOCIDAS:

{context_blocks['known_relations']}


EVENTOS CONOCIDOS:

{context_blocks['known_events']}


============================================================
NARRATIVA A ANALIZAR
============================================================

{text}


============================================================
FIN DE LOS DATOS DE ENTRADA
============================================================

Ahora analiza únicamente la NARRATIVA A ANALIZAR utilizando el contexto
proporcionado.

Devuelve EXCLUSIVAMENTE el JSON final.
"""

        return prompt + dynamic_context
