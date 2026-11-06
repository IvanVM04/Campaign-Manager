import pytest

from models.campaign_state import CampaignState
from models.turn_context import TurnContext
from models.world_state import WorldState
from operations.character_operations import ChangeCharacterHpOperation
from services.llm_world import LLMWorldExtractor
from services.operation_parser import OperationParser
from services.providers import OllamaProvider
from services.turns import (
    TurnExecutionLock,
)

pytestmark = pytest.mark.real_llm


def make_context() -> TurnContext:
    return TurnContext(
        campaign=CampaignState(),
        current_session=None,
        active_character=None,
        world=WorldState(),
    )

def test_real_ollama_extractor_returns_valid_operations():
    provider = OllamaProvider()

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=OperationParser(),
    )

    context = make_context()

    narrative = (
        "El aventurero entra en una pequeña taberna de piedra. "
        "El tabernero se presenta como Aldric y le entrega "
        "una llave de hierro oxidada."
    )

    operations = extractor.extract(
        narrative,
        context,
    )

    assert isinstance(operations, list)

    print("\n=== OPERACIONES EXTRAÍDAS POR OLLAMA ===")

    for index, operation in enumerate(operations, start=1):
        print(f"{index}. {operation!r}")

    print("=== FIN DE OPERACIONES ===")

    operation_types = [
        type(operation).__name__
        for operation in operations
    ]

    print("\n=== TIPOS DE OPERACIÓN ===")
    print(operation_types)
    print("=== FIN DE TIPOS ===\n")

    for operation in operations:
        assert operation is not None

def test_real_ollama_full_turn_persists_world_change():
    from database import get_conn
    from repositories.campaign_repository import CampaignRepository
    from repositories.character_repository import CharacterRepository
    from repositories.entity_repository import EntityRepository
    from repositories.turn_repository import TurnRepository
    from services.campaign import CampaignStateService
    from services.context import ContextBuilder
    from services.llm_world import LLMWorldExtractor
    from services.operation_parser import OperationParser
    from services.providers import OllamaProvider
    from services.silly_tavern_integration_service import (
        SillyTavernIntegrationService,
    )
    from services.world import WorldService

    world_service = WorldService()
    world_service.load()

    campaign_state_service = CampaignStateService(
        campaign_repository=CampaignRepository(),
        character_repository=CharacterRepository(),
        entity_repository=EntityRepository(),
        world_service=world_service,
    )

    context_builder = ContextBuilder()

    extractor = LLMWorldExtractor(
        provider=OllamaProvider(),
        operation_parser=OperationParser(),
    )

    turn_repository = TurnRepository()

    service = SillyTavernIntegrationService(
        campaign_state_service=campaign_state_service,
        context_builder=context_builder,
        extractor=extractor,
        world_service=world_service,
        turn_repository=turn_repository,
        turn_execution_lock=TurnExecutionLock(),
    )

    narrative = (
        "El aventurero llega a una pequeña taberna de piedra. "
        "El tabernero se presenta como Aldric y le entrega "
        "una llave de hierro oxidada."
    )

    result = service.process_turn(
        external_turn_id="real-ollama-e2e-001",
        turn_version=1,
        player_input="Entro en la taberna y hablo con el tabernero.",
        narrative=narrative,
    )

    assert result is not None
    assert result.narrative

    with get_conn() as conn:
        aldric = conn.execute(
            """
            SELECT id, name, entity_type
            FROM entities
            WHERE name = ?
            """,
            ("Aldric",),
        ).fetchone()

        key = conn.execute(
            """
            SELECT id, name
            FROM items
            WHERE name = ?
            """,
            ("Llave de hierro",),
        ).fetchone()

        turn = conn.execute(
            """
            SELECT id, external_turn_id, version
            FROM turns
            WHERE external_turn_id = ?
            """,
            ("real-ollama-e2e-001",),
        ).fetchone()

    assert aldric is not None
    assert aldric["entity_type"] == "npc"

    assert key is not None

    assert turn is not None
    assert turn["external_turn_id"] == "real-ollama-e2e-001"
    assert turn["version"] == 1

def test_real_ollama_regeneration_restores_previous_snapshot():
    from database import get_conn
    from repositories.campaign_repository import CampaignRepository
    from repositories.character_repository import CharacterRepository
    from repositories.entity_repository import EntityRepository
    from repositories.turn_repository import TurnRepository
    from services.campaign import CampaignStateService
    from services.context import ContextBuilder
    from services.llm_world import LLMWorldExtractor
    from services.operation_parser import OperationParser
    from services.providers import OllamaProvider
    from services.silly_tavern_integration_service import (
        SillyTavernIntegrationService,
    )
    from services.world import WorldService

    world_service = WorldService()

    campaign_state_service = CampaignStateService(
        campaign_repository=CampaignRepository(),
        character_repository=CharacterRepository(),
        entity_repository=EntityRepository(),
        world_service=world_service,
    )

    context_builder = ContextBuilder()

    extractor = LLMWorldExtractor(
        provider=OllamaProvider(),
        operation_parser=OperationParser(),
    )

    turn_repository = TurnRepository()

    service = SillyTavernIntegrationService(
        campaign_state_service=campaign_state_service,
        context_builder=context_builder,
        extractor=extractor,
        world_service=world_service,
        turn_repository=turn_repository,
        turn_execution_lock=TurnExecutionLock(),
    )

    # --------------------------------------------------------
    # V1
    # --------------------------------------------------------

    v1_narrative = (
        "El aventurero entra en una pequeña taberna de piedra. "
        "El tabernero se presenta como Aldric y le entrega "
        "una llave de hierro oxidada."
    )

    v1 = service.process_turn(
        player_input=(
            "Entro en la taberna y hablo con el tabernero."
        ),
        narrative=v1_narrative,
        external_turn_id="real-ollama-regeneration-001",
        turn_version=1,
    )

    assert v1 is not None
    assert v1.narrative == v1_narrative

    # --------------------------------------------------------
    # Comprobar que V1 realmente modificó el mundo.
    # --------------------------------------------------------

    with get_conn() as conn:
        aldric_v1 = conn.execute(
            """
            SELECT id
            FROM entities
            WHERE name = ?
            """,
            ("Aldric",),
        ).fetchone()

        key_v1 = conn.execute(
            """
            SELECT id
            FROM items
            WHERE name = ?
            """,
            ("Llave de hierro",),
        ).fetchone()

    assert aldric_v1 is not None
    assert key_v1 is not None

    # --------------------------------------------------------
    # Regeneración V2.
    #
    # Esta narrativa NO menciona a Aldric ni la llave.
    # El snapshot de V1 debe restaurarse antes de aplicar V2.
    # --------------------------------------------------------

    v2_narrative = (
        "El aventurero decide ignorar al tabernero "
        "y continúa hacia una habitación lateral. "
        "Allí encuentra a una mujer llamada Mira "
        "que vigila una puerta cerrada."
    )

    v2 = service.process_turn(
        player_input=(
            "Ignoro al tabernero y exploro la habitación lateral."
        ),
        narrative=v2_narrative,
        external_turn_id="real-ollama-regeneration-001",
        turn_version=2,
    )

    assert v2 is not None
    assert v2.narrative == v2_narrative

    # --------------------------------------------------------
    # Estado final.
    #
    # Aldric y la llave pertenecen al estado de V1.
    # Mira pertenece al estado de V2.
    #
    # Lo importante es que el mundo final no haya acumulado
    # modificaciones de V1 + V2 de forma incorrecta.
    # --------------------------------------------------------

    with get_conn() as conn:
        aldric_final = conn.execute(
            """
            SELECT id
            FROM entities
            WHERE name = ?
            """,
            ("Aldric",),
        ).fetchone()

        key_final = conn.execute(
            """
            SELECT id
            FROM items
            WHERE name = ?
            """,
            ("Llave de hierro",),
        ).fetchone()

        mira_final = conn.execute(
            """
            SELECT id
            FROM entities
            WHERE name = ?
            """,
            ("Mira",),
        ).fetchone()

        turns = conn.execute(
            """
            SELECT external_turn_id, version, status
            FROM turns
            WHERE external_turn_id = ?
            ORDER BY version
            """,
            ("real-ollama-regeneration-001",),
        ).fetchall()

    # --------------------------------------------------------
    # V1 debe haber sido completamente sustituido por V2.
    #
    # El snapshot almacenado en V1 representa el estado
    # anterior a V1. Al regenerar V2 se restaura ese estado
    # y después se aplican únicamente las operaciones de V2.
    # --------------------------------------------------------

    assert aldric_final is None
    assert key_final is None

    # Mira pertenece exclusivamente a V2.
    assert mira_final is not None

    assert len(turns) == 2

    assert turns[0]["version"] == 1
    assert turns[1]["version"] == 2

def test_real_ollama_extractor_does_not_create_changes_without_persistent_facts():
    provider = OllamaProvider()

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=OperationParser(),
    )

    context = make_context()

    narrative = (
        "El aventurero entra en una taberna de piedra. "
        "Observa varias mesas ocupadas, escucha conversaciones "
        "y ve una chimenea encendida al fondo. "
        "Después se sienta y espera tranquilamente."
    )

    operations = extractor.extract(
        narrative,
        context,
    )

    print("\n=== TEST: SIN CAMBIOS PERSISTENTES ===")
    for operation in operations:
        print(operation)
    print("=== FIN TEST ===\n")

    assert operations == []


def test_real_ollama_extractor_detects_named_npc_without_inventing_more_entities():
    provider = OllamaProvider()

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=OperationParser(),
    )

    context = make_context()

    narrative = (
        "El tabernero deja el vaso sobre la barra y se presenta "
        "como Aldric. Explica que lleva veinte años regentando "
        "El Barril Agrietado."
    )

    operations = extractor.extract(
        narrative,
        context,
    )

    print("\n=== TEST: NPC ===")
    for operation in operations:
        print(operation)
    print("=== FIN TEST ===\n")

    entity_operations = [
        operation
        for operation in operations
        if type(operation).__name__ == "CreateEntityOperation"
    ]

    assert len(entity_operations) == 1

    aldric = entity_operations[0]

    assert aldric.name == "Aldric"
    assert aldric.entity_type == "npc"

    # No debería inventar personajes, lugares u otras entidades.
    assert len(operations) == 1


def test_real_ollama_extractor_does_not_turn_failed_attempt_into_success():
    provider = OllamaProvider()

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=OperationParser(),
    )

    context = make_context()

    narrative = (
        "El aventurero encuentra una antigua puerta de piedra "
        "cerrada con llave. Intenta abrirla varias veces, "
        "pero la cerradura no cede y la puerta permanece cerrada."
    )

    operations = extractor.extract(
        narrative,
        context,
    )

    print("\n=== TEST: ACCIÓN FALLIDA ===")
    for operation in operations:
        print(operation)
    print("=== FIN TEST ===\n")

    assert operations == []


def test_real_ollama_extractor_detects_explicit_damage():
    provider = OllamaProvider()

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=OperationParser(),
    )

    context = make_context()

    narrative = (
        "El guardia golpea al aventurero con su espada "
        "y el impacto le causa 7 puntos de daño."
    )

    operations = extractor.extract(
        narrative,
        context,
    )

    print("\n=== TEST: DAÑO ===")
    for operation in operations:
        print(operation)
    print("=== FIN TEST ===\n")

    hp_operations = [
        operation
        for operation in operations
        if isinstance(operation, ChangeCharacterHpOperation)
    ]

    assert len(hp_operations) == 1
    assert hp_operations[0].amount == -7