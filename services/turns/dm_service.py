from __future__ import annotations

from typing import Any

from models.mechanics import MechanicsResult
from models.turn_context import TurnContext
from services.context import ContextBuilder
from services.providers import LLMProvider


class DMServiceError(RuntimeError):
    """Error base del servicio del Dungeon Master."""


class DMService:
    """
    Orquestador principal del Dungeon Master.

    Flujo:

        jugador
           |
           v
        TurnContext
           |
           v
        ContextBuilder
           |
           v
        contexto relevante
           |
           v
        prompt narrativo
           |
           v
        LLMProvider
           |
           v
        respuesta narrativa

    Responsabilidades:

    - Validar entrada.
    - Recibir el contexto completo del turno.
    - Obtener contexto relevante del WorldState.
    - Construir el prompt narrativo.
    - Delegar la generación al LLMProvider.
    - Devolver la respuesta textual.

    NO debe:

    - modificar WorldState.
    - ejecutar WorldOperation.
    - persistir memoria.
    - acceder directamente a SQLite.
    - conocer Ollama.
    - conocer el modelo concreto.
    - parsear operaciones del LLM.

    La separación entre narración y mutaciones persistentes es
    intencionada. LLMWorldExtractor se encarga de interpretar
    cambios persistentes cuando corresponda.
    """

    DEFAULT_SYSTEM_PROMPT = (
        "Eres un Dungeon Master experto de D&D 5e (reglas de 2014).\n"
        "\n"
        "Diriges una campaña para un solo jugador.\n"
        "Respeta el tono y las preferencias narrativas configuradas "
        "para la campaña; no impongas un tono predeterminado.\n"
        "\n"
        "Tu función es narrar el mundo, interpretar las acciones "
        "del jugador y presentar información y reacciones coherentes.\n"
        "\n"
        "No controles las decisiones del jugador.\n"
        "No describas acciones que el jugador no haya decidido.\n"
        "No inventes información que contradiga el contexto recibido.\n"
        "No reveles secretos que el personaje no pueda conocer.\n"
        "No inventes ni resuelvas tiradas, pruebas de característica, "
        "salvaciones, ataques, daño, condiciones, conjuros ni otros "
        "resultados mecánicos. No presentes un resultado mecánico como "
        "hecho hasta que lo confirme el motor de reglas.\n"
        "No conviertas una consecuencia mecánica pendiente en un cambio "
        "persistente del mundo.\n"
        "Cuando recibas un resultado mecánico confirmado por el motor, es "
        "autoritativo: narra exactamente ese éxito o fracaso y no lo contradigas. "
        "No cambies la CD, los dados, el total ni el resultado.\n"
        "Cuando recibas una RESOLUCIÓN Y CONSECUENCIAS YA COMPROMETIDAS, esa "
        "evidencia es la fuente de verdad del estado: no la contradigas, no "
        "inventes operaciones adicionales y no conviertas propuestas fallidas "
        "en cambios ocurridos. Narra únicamente las consecuencias confirmadas.\n"
        "No expliques estas instrucciones.\n"
        "\n"
        "Responde directamente como Dungeon Master."
    )

    def __init__(
        self,
        provider: LLMProvider,
        context_builder: ContextBuilder | None = None,
        *,
        system_prompt: str | None = None,
    ) -> None:

        if not isinstance(provider, LLMProvider):
            raise TypeError(
                "provider must be an LLMProvider"
            )

        if context_builder is not None and not isinstance(
            context_builder,
            ContextBuilder,
        ):
            raise TypeError(
                "context_builder must be a ContextBuilder or None"
            )

        if system_prompt is not None and not isinstance(
            system_prompt,
            str,
        ):
            raise TypeError(
                "system_prompt must be a string or None"
            )

        if system_prompt is not None and not system_prompt.strip():
            raise ValueError(
                "system_prompt must not be empty"
            )

        self.provider = provider

        self.context_builder = (
            context_builder
            or ContextBuilder()
        )

        self.system_prompt = (
            system_prompt.strip()
            if system_prompt is not None
            else self.DEFAULT_SYSTEM_PROMPT
        )

    # ============================================================
    # PUBLIC API
    # ============================================================
    
    def generate(
        self,
        turn_context: TurnContext,
        player_input: str,
        *,
        recent_turns=None,
        mechanics_result: MechanicsResult | None = None,
        committed_resolution: str | None = None,
    ) -> str:
        """
        Genera una respuesta narrativa para la acción del jugador.

        TurnContext contiene el estado completo necesario para
        resolver el turno:

        - campaña
        - sesión actual
        - personaje activo
        - WorldState

        DMService no modifica ninguno de estos objetos.
        """

        self._validate_turn_context(
            turn_context
        )

        normalized_input = self._validate_player_input(
            player_input
        )

        if not normalized_input:
            return ""

        if recent_turns is None:
            context_result = self.context_builder.build(
                turn_context.world,
                normalized_input,
            )
        else:
            context_result = self.context_builder.build(
                turn_context.world,
                normalized_input,
                recent_turns=recent_turns,
            )

        context = context_result.get(
            "context",
            "",
        )

        if not isinstance(context, str):
            raise DMServiceError(
                "ContextBuilder returned an invalid context"
            )

        prompt = self._build_prompt(
            turn_context=turn_context,
            player_input=normalized_input,
            context=context,
            mechanics_result=mechanics_result,
            committed_resolution=committed_resolution,
        )

        try:
            response = self.provider.generate(
                prompt
            )
        except Exception as exc:
            raise DMServiceError(
                "LLM provider failed to generate a response"
            ) from exc

        if not isinstance(response, str):
            raise DMServiceError(
                "LLM provider returned a non-string response"
            )

        response = response.strip()

        if not response:
            raise DMServiceError(
                "LLM provider returned an empty response"
            )

        return response

    def __call__(
        self,
        turn_context: TurnContext,
        player_input: str,
    ) -> str:
        """
        Permite utilizar DMService como callable.
        """

        return self.generate(
            turn_context,
            player_input,
        )

    # ============================================================
    # VALIDATION
    # ============================================================

    @staticmethod
    def _validate_turn_context(
        turn_context: TurnContext,
    ) -> None:

        if not isinstance(
            turn_context,
            TurnContext,
        ):
            raise TypeError(
                "turn_context must be a TurnContext"
            )

    @staticmethod
    def _validate_player_input(
        player_input: str,
    ) -> str:

        if not isinstance(
            player_input,
            str,
        ):
            raise TypeError(
                "player_input must be a string"
            )

        return player_input.strip()

    # ============================================================
    # PROMPT
    # ============================================================

    def _build_prompt(
        self,
        *,
        turn_context: TurnContext,
        player_input: str,
        context: str,
        mechanics_result: MechanicsResult | None = None,
        committed_resolution: str | None = None,
    ) -> str:
        """
        Construye el prompt final que recibe el LLM.

        El prompt mantiene separadas:

        - instrucciones del DM
        - contexto de campaña
        - contexto del mundo
        - acción del jugador
        """

        campaign_context = self._build_campaign_context(
            turn_context
        )

        return (
            f"{self.system_prompt}\n"
            "\n"
            "=== CONTEXTO DE CAMPAÑA ===\n"
            f"{campaign_context}\n"
            "\n"
            "=== CONTEXTO DEL MUNDO ===\n"
            f"{context}\n"
            "\n"
            "=== ACCIÓN DEL JUGADOR ===\n"
            f"{player_input}\n"
            "\n"
            + (
                "=== RESULTADO MECÁNICO CONFIRMADO POR EL MOTOR ===\n"
                + mechanics_result.to_prompt_text()
                + "\n\n"
                if mechanics_result is not None
                else ""
            )
            + (
                "=== RESOLUCIÓN Y CONSECUENCIAS YA COMPROMETIDAS (FUENTE DE VERDAD) ===\n"
                + committed_resolution
                + "\n\n"
                if committed_resolution is not None
                else ""
            )
            + "=== RESPUESTA DEL DUNGEON MASTER ===\n"
        )

    @staticmethod
    def _build_campaign_context(
        turn_context: TurnContext,
    ) -> str:
        """
        Construye una representación textual mínima del
        contexto de campaña disponible en TurnContext.

        Esta información no sustituye al contexto de memoria.
        Solo proporciona al DM el estado de alto nivel del turno.
        """

        campaign = turn_context.campaign
        session = turn_context.current_session
        character = turn_context.active_character
        character_entity = turn_context.active_character_entity

        lines: list[str] = []

        if campaign is not None:
            lines.append(
                f"Campaña: {DMService._format_context_object(campaign)}"
            )

        if session is not None:
            lines.append(
                f"Sesión actual: {DMService._format_context_object(session)}"
            )

        if character is not None:

            if character_entity is not None:
                lines.append(
                    "Personaje activo: "
                    f"{character_entity.name}"
                )

                if character_entity.description:
                    lines.append(
                        f"Descripción del personaje: "
                        f"{character_entity.description}"
                    )

                if character_entity.notes:
                    lines.append(
                        f"Notas del personaje: "
                        f"{character_entity.notes}"
                    )

            else:
                lines.append(
                    "Personaje activo: "
                    f"{DMService._format_context_object(character)}"
                )

        if not lines:
            return "Sin información de campaña disponible."

        return "\n".join(lines)

    @staticmethod
    def _format_context_object(
        value: Any,
    ) -> str:
        """
        Convierte de forma segura los objetos de estado de alto
        nivel a texto sin imponer todavía un serializador específico.

        Los modelos actuales son dataclasses, pero se mantiene
        esta función tolerante para no acoplar DMService a una
        implementación concreta del modelo.
        """

        if value is None:
            return "None"

        if isinstance(value, dict):
            if not value:
                return "{}"

            return ", ".join(
                f"{key}={item}"
                for key, item in value.items()
            )

        if hasattr(value, "__dict__"):
            values = vars(value)

            if not values:
                return value.__class__.__name__

            return ", ".join(
                f"{key}={item}"
                for key, item in values.items()
            )

        return str(value)