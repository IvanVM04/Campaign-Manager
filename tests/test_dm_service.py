from __future__ import annotations

import pytest

from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.entity import Entity
from models.session_state import SessionState
from models.turn_context import TurnContext
from models.turn_record import TurnRecord
from models.world_state import WorldState
from services.context import ContextBuilder
from services.providers import FakeLLMProvider, LLMProvider
from services.turns import DMService, DMServiceError

# ============================================================
# HELPERS
# ============================================================


class RecordingContextBuilder(ContextBuilder):
    """
    ContextBuilder mínimo para comprobar que DMService
    realmente utiliza el servicio de contexto.
    """

    def __init__(
        self,
        context: str = "[ENTIDADES]\n- Fungoso",
    ) -> None:
        super().__init__()
        self.context = context
        self.calls: list[tuple[WorldState, str]] = []
        self.perspectives: list[int | None] = []

    def build(
        self,
        world: WorldState,
        query: str,
        recent_turns=None,
        *,
        supplemental_queries=(),
        character_entity_id: int | None = None,
    ) -> dict:
        self.perspectives.append(character_entity_id)
        self.calls.append(
            (
                world,
                query,
            )
        )

        return {
            "query": query,
            "entities": [],
            "items": [],
            "item_instances": [],
            "resources": [],
            "resource_balances": [],
            "relations": [],
            "events": [],
            "context": self.context,
        }

def make_turn_context():
    return TurnContext(
        campaign=CampaignState(
            campaign_id=1,
            name="Campaña de prueba",
            system="D&D 5e 2014",
            tone="serio",
            summary="Campaña de pruebas.",
        ),
        current_session=SessionState(
            session_id=10,
            number=1,
            title="La llegada",
            summary="Primera sesión.",
        ),
        active_character=CharacterState(
            entity_id=20,
        ),
        world=WorldState(),
        active_character_entity=Entity(
            id=20,
            name="Aldric",
            entity_type="player_character",
            description="Un aventurero.",
            notes="Conoce Vorder's Hold.",
        ),
    )


class NonStringProvider(LLMProvider):
    def generate(
        self,
        prompt: str,
    ):
        return 123


class EmptyProvider(LLMProvider):
    def generate(
        self,
        prompt: str,
    ) -> str:
        return "   "


class FailingProvider(LLMProvider):
    def generate(
        self,
        prompt: str,
    ) -> str:
        raise RuntimeError(
            "boom"
        )


# ============================================================
# BASIC GENERATION
# ============================================================


def test_generate_returns_provider_response():
    provider = FakeLLMProvider(
        response="El viento golpea las ventanas."
    )

    service = DMService(
        provider
    )

    turn_context = make_turn_context()

    result = service.generate(
        turn_context,
        "Miro por la ventana.",
    )

    assert result == (
        "El viento golpea las ventanas."
    )


def test_generate_strips_provider_response():
    provider = FakeLLMProvider(
        response="  Hay una figura en la niebla.  "
    )

    service = DMService(
        provider
    )

    result = service.generate(
        make_turn_context(),
        "Observo la niebla.",
    )

    assert result == (
        "Hay una figura en la niebla."
    )


def test_service_is_callable():
    provider = FakeLLMProvider(
        response="La puerta se abre lentamente."
    )

    service = DMService(
        provider
    )

    result = service(
        make_turn_context(),
        "Abro la puerta.",
    )

    assert result == (
        "La puerta se abre lentamente."
    )


# ============================================================
# CONTEXT BUILDER
# ============================================================


def test_generate_uses_context_builder():
    provider = FakeLLMProvider(
        response="Respuesta narrativa."
    )

    context_builder = RecordingContextBuilder(
        context=(
            "[ENTIDADES]\n"
            "- Aldric (npc): viejo mercader"
        )
    )

    service = DMService(
        provider,
        context_builder,
    )

    turn_context = make_turn_context()

    service.generate(
        turn_context,
        "Busco a Aldric.",
    )

    assert len(
        context_builder.calls
    ) == 1

    called_world, called_query = (
        context_builder.calls[0]
    )

    assert called_world is turn_context.world
    assert called_query == (
        "Busco a Aldric."
    )


def test_context_is_included_in_prompt():
    provider = FakeLLMProvider(
        response="Respuesta."
    )

    context_builder = RecordingContextBuilder(
        context=(
            "[ENTIDADES]\n"
            "- Aldric (npc): mercader y viejo amigo"
        )
    )

    service = DMService(
        provider,
        context_builder,
    )

    service.generate(
        make_turn_context(),
        "Busco a Aldric.",
    )

    prompt = provider.last_prompt

    assert prompt is not None

    assert (
        "[ENTIDADES]\n"
        "- Aldric (npc): mercader y viejo amigo"
        in prompt
    )


def test_player_input_is_included_in_prompt():
    provider = FakeLLMProvider(
        response="Respuesta."
    )

    service = DMService(
        provider
    )

    service.generate(
        make_turn_context(),
        "Saco mi espada y avanzo hacia la puerta.",
    )

    prompt = provider.last_prompt

    assert prompt is not None

    assert (
        "Saco mi espada y avanzo hacia la puerta."
        in prompt
    )


# ============================================================
# PROMPT STRUCTURE
# ============================================================


def test_prompt_contains_system_instructions():
    provider = FakeLLMProvider(
        response="Respuesta."
    )

    service = DMService(
        provider
    )

    service.generate(
        make_turn_context(),
        "Observo la habitación.",
    )

    prompt = provider.last_prompt

    assert prompt is not None

    assert (
        "Dungeon Master experto"
        in prompt
    )

    assert (
        "D&D 5e"
        in prompt
    )

    assert (
        "No controles las decisiones del jugador."
        in prompt
    )


def test_prompt_contains_expected_sections():
    provider = FakeLLMProvider(
        response="Respuesta."
    )

    service = DMService(
        provider
    )

    service.generate(
        make_turn_context(),
        "Abro el cofre.",
    )

    prompt = provider.last_prompt

    assert prompt is not None

    assert (
        "=== CONTEXTO DEL MUNDO ==="
        in prompt
    )

    assert (
        "=== ACCIÓN DEL JUGADOR ==="
        in prompt
    )

    assert (
        "=== RESPUESTA DEL DUNGEON MASTER ==="
        in prompt
    )


def test_custom_system_prompt_is_used():
    provider = FakeLLMProvider(
        response="Respuesta."
    )

    service = DMService(
        provider,
        system_prompt=(
            "Eres un DM personalizado."
        ),
    )

    service.generate(
        make_turn_context(),
        "Hago algo.",
    )

    prompt = provider.last_prompt

    assert prompt is not None

    assert (
        "Eres un DM personalizado."
        in prompt
    )

    assert (
        "Dungeon Master experto"
        not in prompt
    )


# ============================================================
# EMPTY INPUT
# ============================================================


def test_empty_player_input_returns_empty_response():
    provider = FakeLLMProvider(
        response="No debería llamarse."
    )

    service = DMService(
        provider
    )

    result = service.generate(
        make_turn_context(),
        "   ",
    )

    assert result == ""

    assert provider.call_count == 0


def test_empty_player_input_does_not_call_context_builder():
    provider = FakeLLMProvider(
        response="No debería llamarse."
    )

    context_builder = RecordingContextBuilder()

    service = DMService(
        provider,
        context_builder,
    )

    result = service.generate(
        make_turn_context(),
        "",
    )

    assert result == ""

    assert (
        context_builder.calls == []
    )


# ============================================================
# VALIDATION
# ============================================================


def test_turn_context_must_be_turn_context():
    provider = FakeLLMProvider(
        response="Respuesta."
    )

    service = DMService(
        provider
    )

    with pytest.raises(
        TypeError,
        match="turn_context must be a TurnContext",
    ):
        service.generate(
            None,
            "Hola.",
        )


def test_player_input_must_be_string():
    provider = FakeLLMProvider(
        response="Respuesta."
    )

    service = DMService(
        provider
    )

    with pytest.raises(
        TypeError,
        match="player_input must be a string",
    ):
        service.generate(
            make_turn_context(),
            None,
        )


def test_provider_must_be_llm_provider():
    with pytest.raises(
        TypeError,
        match="provider must be an LLMProvider",
    ):
        DMService(
            lambda prompt: "respuesta"
        )


def test_context_builder_must_be_context_builder():
    provider = FakeLLMProvider(
        response="Respuesta."
    )

    with pytest.raises(
        TypeError,
        match="context_builder must be a ContextBuilder",
    ):
        DMService(
            provider,
            object(),
        )


def test_system_prompt_must_be_string():
    provider = FakeLLMProvider(
        response="Respuesta."
    )

    with pytest.raises(
        TypeError,
        match="system_prompt must be a string",
    ):
        DMService(
            provider,
            system_prompt=123,
        )


def test_system_prompt_must_not_be_empty():
    provider = FakeLLMProvider(
        response="Respuesta."
    )

    with pytest.raises(
        ValueError,
        match="system_prompt must not be empty",
    ):
        DMService(
            provider,
            system_prompt="   ",
        )


# ============================================================
# PROVIDER ERRORS
# ============================================================


def test_provider_error_is_wrapped():
    provider = FailingProvider()

    service = DMService(
        provider
    )

    with pytest.raises(
        DMServiceError,
        match="LLM provider failed",
    ):
        service.generate(
            make_turn_context(),
            "Intento algo.",
        )


def test_non_string_provider_response_is_rejected():
    provider = NonStringProvider()

    service = DMService(
        provider
    )

    with pytest.raises(
        DMServiceError,
        match="non-string response",
    ):
        service.generate(
            make_turn_context(),
            "Intento algo.",
        )


def test_empty_provider_response_is_rejected():
    provider = EmptyProvider()

    service = DMService(
        provider
    )

    with pytest.raises(
        DMServiceError,
        match="empty response",
    ):
        service.generate(
            make_turn_context(),
            "Intento algo.",
        )


# ============================================================
# CONTEXT ERRORS
# ============================================================


def test_invalid_context_from_context_builder_is_rejected():
    class InvalidContextBuilder(
        ContextBuilder
    ):
        def build(
            self,
            world,
            query,
            recent_turns=None,
            *,
            supplemental_queries=(),
            character_entity_id=None,
        ):
            return {
                "context": None,
            }

    provider = FakeLLMProvider(
        response="Respuesta."
    )

    service = DMService(
        provider,
        InvalidContextBuilder(),
    )

    with pytest.raises(
        DMServiceError,
        match="invalid context",
    ):
        service.generate(
            make_turn_context(),
            "Algo.",
        )


# ============================================================
# WORLD IMMUTABILITY
# ============================================================


def test_generate_does_not_modify_world():
    provider = FakeLLMProvider(
        response="La puerta se abre."
    )

    context_builder = RecordingContextBuilder()

    service = DMService(
        provider,
        context_builder,
    )

    turn_context = make_turn_context()

    world = turn_context.world

    entities_before = dict(
        world.entities
    )

    items_before = dict(
        world.items
    )

    relations_before = dict(
        world.relations
    )

    events_before = dict(
        world.events
    )

    service.generate(
        turn_context,
        "Abro la puerta.",
    )

    assert world.entities == (
        entities_before
    )

    assert world.items == (
        items_before
    )

    assert world.relations == (
        relations_before
    )

    assert world.events == (
        events_before
    )


# ============================================================
# CALL COUNT / PROVIDER CONTRACT
# ============================================================


def test_generate_calls_provider_exactly_once():
    provider = FakeLLMProvider(
        response="Respuesta."
    )

    service = DMService(
        provider
    )

    service.generate(
        make_turn_context(),
        "Exploro.",
    )

    assert provider.call_count == 1


def test_each_generation_creates_one_provider_call():
    provider = FakeLLMProvider(
        response="Respuesta."
    )

    service = DMService(
        provider
    )

    turn_context = make_turn_context()

    service.generate(
        turn_context,
        "Primera acción.",
    )

    service.generate(
        turn_context,
        "Segunda acción.",
    )

    assert provider.call_count == 2


# ============================================================
# END-TO-END WITH FAKE PROVIDER
# ============================================================


def test_end_to_end_fake_provider():
    provider = FakeLLMProvider(
        response=(
            "La lluvia golpea el tejado mientras "
            "una silueta aparece al otro lado de la calle."
        )
    )

    context_builder = RecordingContextBuilder(
        context=(
            "[ENTIDADES]\n"
            "- Vorder's Hold (location): "
            "puesto minero bajo la lluvia"
        )
    )

    service = DMService(
        provider,
        context_builder,
    )

    result = service.generate(
        make_turn_context(),
        "Salgo a la calle.",
    )

    assert result == (
        "La lluvia golpea el tejado mientras "
        "una silueta aparece al otro lado de la calle."
    )

    assert provider.call_count == 1

    assert (
        "Vorder's Hold"
        in provider.last_prompt
    )

    assert (
        "Salgo a la calle."
        in provider.last_prompt
    )

def test_generate_uses_world_from_turn_context():
    provider = FakeLLMProvider(
        response="Respuesta narrativa."
    )

    context_builder = RecordingContextBuilder()

    service = DMService(
        provider,
        context_builder,
    )

    turn_context = make_turn_context()

    service.generate(
        turn_context,
        "Exploro.",
    )

    assert len(
        context_builder.calls
    ) == 1

    called_world, called_query = (
        context_builder.calls[0]
    )

    assert called_world is (
        turn_context.world
    )

    assert called_query == "Exploro."


def test_campaign_context_is_included_in_prompt():
    provider = FakeLLMProvider(
        response="Respuesta narrativa."
    )

    service = DMService(
        provider
    )

    turn_context = make_turn_context()

    service.generate(
        turn_context,
        "Observo la zona.",
    )

    prompt = provider.last_prompt

    assert prompt is not None

    assert (
        "=== CONTEXTO DE CAMPAÑA ==="
        in prompt
    )

    assert (
        "Campaña de prueba"
        in prompt
    )

    assert (
        "La llegada"
        in prompt
    )

    assert (
        "Aldric"
        in prompt
    )


def test_world_context_and_campaign_context_are_both_in_prompt():
    provider = FakeLLMProvider(
        response="Respuesta narrativa."
    )

    context_builder = RecordingContextBuilder(
        context=(
            "[ENTIDADES]\n"
            "- Vorder's Hold (location): "
            "puesto minero"
        )
    )

    service = DMService(
        provider,
        context_builder,
    )

    turn_context = make_turn_context()

    service.generate(
        turn_context,
        "Salgo a la calle.",
    )

    prompt = provider.last_prompt

    assert prompt is not None

    assert (
        "Campaña de prueba"
        in prompt
    )

    assert (
        "La llegada"
        in prompt
    )

    assert (
        "Aldric"
        in prompt
    )

    assert (
        "Vorder's Hold"
        in prompt
    )

    assert (
        "Salgo a la calle."
        in prompt
    )

# ============================================================
# RECENT TURN HISTORY
# ============================================================


def test_generate_passes_recent_turns_to_context_builder():
    provider = FakeLLMProvider(
        response="Respuesta narrativa."
    )

    class RecentTurnsContextBuilder(ContextBuilder):
        def __init__(self):
            super().__init__()
            self.received_recent_turns = None

        def build(
            self,
            world,
            query,
            recent_turns=None,
            *,
            supplemental_queries=(),
            character_entity_id=None,
        ):
            self.received_recent_turns = recent_turns
            self.received_character_entity_id = character_entity_id

            return {
                "query": query,
                "entities": [],
                "items": [],
                "item_instances": [],
                "resources": [],
                "resource_balances": [],
                "relations": [],
                "events": [],
                "recent_turns": recent_turns or [],
                "context": "[HISTORIAL]",
            }

    context_builder = RecentTurnsContextBuilder()

    service = DMService(
        provider,
        context_builder,
    )

    recent_turns = [
        TurnRecord(
            id=1,
            session_id=10,
            player_input="Entré en la taberna.",
            narrative="El tabernero levantó la mirada.",
        ),
        TurnRecord(
            id=2,
            session_id=10,
            player_input="Pregunté por el camino norte.",
            narrative="El tabernero señaló hacia las montañas.",
        ),
    ]

    service.generate(
        make_turn_context(),
        "Pregunto de nuevo por las montañas.",
        recent_turns=recent_turns,
    )

    assert (
        context_builder.received_recent_turns
        == recent_turns
    )
    assert context_builder.received_character_entity_id == 20


def test_default_prompt_respects_campaign_tone_and_defers_mechanics():
    provider = FakeLLMProvider(
        response="Respuesta narrativa."
    )
    service = DMService(provider)

    service.generate(
        make_turn_context(),
        "Ataco al guardia.",
    )

    prompt = provider.last_prompt
    assert prompt is not None

    # The configured campaign tone is included as context, but the
    # default system prompt must not replace it with a fixed style.
    assert "tone=serio" in prompt
    assert "no impongas un tono predeterminado" in prompt
    assert "oscuro y épico" not in prompt

    # Until deterministic rule resolution exists, the narrator must
    # not invent mechanical outcomes and present them as facts.
    assert "No inventes ni resuelvas tiradas" in prompt
    assert "motor de reglas" in prompt
    assert "No conviertas una consecuencia mecánica pendiente" in prompt


def test_committed_resolution_is_included_as_authoritative_narration_context():
    provider = FakeLLMProvider(response="La acción se resuelve.")
    service = DMService(provider)

    service.generate(
        make_turn_context(),
        "Abro la puerta.",
        committed_resolution='{"operations":[{"type":"open_door"}],"operation_results":[{"success":true}]}',
    )

    prompt = provider.last_prompt
    assert prompt is not None
    assert "RESOLUCIÓN Y CONSECUENCIAS YA COMPROMETIDAS" in prompt
    assert "open_door" in prompt


def test_generate_retrieves_events_for_the_active_character_perspective():
    provider = FakeLLMProvider(response="Respuesta narrativa.")
    context_builder = RecordingContextBuilder()
    service = DMService(provider, context_builder)
    context = make_turn_context()

    service.generate(context, "Busco una pista.")

    assert context_builder.perspectives == [20]
    assert "rumores atribuyendo" in service.DEFAULT_SYSTEM_PROMPT
    assert "históricos/sustituidos" in service.DEFAULT_SYSTEM_PROMPT
