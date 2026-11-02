import threading
import time

import pytest

from models.operation_result import OperationResult, OperationStatus
from models.turn_context import TurnContext
from models.turn_record import TurnRecord
from models.turn_resolution_result import (
    TurnResolutionResult,
)
from models.world_state import WorldState
from operations.world_operations import CreateEntityOperation
from repositories.turn_repository import TurnRepository
from services.campaign_state_service import (
    CampaignState,
    CampaignStateService,
    CampaignStateServiceError,
)
from services.campaign_turn_service import (
    CampaignTurnService,
    CampaignTurnServiceError,
)
from services.dm_service import DMService
from services.llm_world_extractor import LLMWorldExtractor
from services.turn_execution_lock import TurnExecutionLock
from services.turn_resolution_service import (
    TurnResolutionService,
    TurnResolutionServiceError,
)
from services.world_service import WorldService

# ============================================================
# FAKES
# ============================================================


class RecordingWorldService(WorldService):

    def __init__(self):
        super().__init__()

        self.world = WorldState()

        self.get_world_calls = 0
        self.save_calls = 0
        self.load_calls = 0

        self.save_error = None
        self.load_error = None

    def get_world(self):
        self.get_world_calls += 1

        return self.world

    def save(self):
        self.save_calls += 1

        if self.save_error is not None:
            raise self.save_error

    def load(self):
        self.load_calls += 1

        if self.load_error is not None:
            raise self.load_error

        return self.world

class RecordingCampaignStateService(
    CampaignStateService
):

    def __init__(
        self,
        world_service,
    ):
        self.world_service = world_service

        self.get_state_calls = 0
        self.get_turn_context_calls = 0
        self.get_world_calls = 0
        self.load_world_calls = 0
        self.save_world_calls = 0

        self.last_conn = None

        self.state_error = None
        self.world_error = None
        self.load_error = None
        self.save_error = None

    def get_state(self):
        self.get_state_calls += 1

        if self.state_error is not None:
            raise self.state_error

        return CampaignState(
            campaign=CampaignState(),
            current_session=None,
            active_character=None,
            world=self.world_service.world,
        )

    def get_turn_context(
        self,
        *,
        conn=None,
    ):

        self.get_turn_context_calls += 1
        self.last_conn = conn

        if self.state_error is not None:
            raise self.state_error

        return TurnContext(
            campaign=CampaignState(),
            current_session=None,
            active_character=None,
            world=self.world_service.world,
        )

    def get_world(self):
        self.get_world_calls += 1

        if self.world_error is not None:
            raise self.world_error

        return self.world_service.world

    def load_world(self):
        self.load_world_calls += 1

        if self.load_error is not None:
            raise self.load_error

        return self.world_service.world

    def save_world(self):
        self.save_world_calls += 1

        if self.save_error is not None:
            raise self.save_error


class RecordingTurnResolutionService(
    TurnResolutionService
):

    def __init__(
        self,
        result,
    ):
        self.result = result

        self.calls = []

        self.error = None

        self.last_conn = None
        self.last_recent_turns = None

    def resolve_turn(
        self,
        turn_context,
        player_input,
        *,
        recent_turns=None,
        conn=None,
    ):
        self.calls.append(
            (
                turn_context,
                player_input,
            )
        )

        self.last_conn = conn
        self.last_recent_turns = recent_turns

        if self.error is not None:
            raise self.error

        return self.result


# ============================================================
# HELPERS
# ============================================================


def make_result(
    *,
    player_input="Exploro.",
    narrative="No ocurre nada.",
    world_changed=False,
):
    """
    Construye un TurnResolutionResult para los tests.

    world_changed no se pasa al constructor porque es una
    propiedad derivada de operation_results.
    """

    operations = ()
    operation_results = ()

    if world_changed:
        operation = CreateEntityOperation(
            name="TestEntity",
            entity_type="test",
            description="Test entity.",
            notes="",
            active=True,
        )

        operations = (operation,)

        # No podemos inventar un OperationResult aquí sin conocer
        # su constructor real. Para estos tests concretos,
        # el resultado debe representar una operación exitosa.
        operation_results = (
            OperationResult(
                status=OperationStatus.SUCCESS,
                operation=operation,
            ),
        )

    return TurnResolutionResult(
        player_input=player_input,
        narrative=narrative,
        operations=operations,
        operation_results=operation_results,
    )


def make_service(
    *,
    result=None,
    world_service=None,
    campaign_state_service=None,
    turn_execution_lock=None,
):
    if result is None:
        result = make_result()

    if world_service is None:
        world_service = RecordingWorldService()

    if turn_execution_lock is None:
        turn_execution_lock = TurnExecutionLock()

    turn_resolution_service = (
        RecordingTurnResolutionService(
            result
        )
    )

    service = CampaignTurnService(
        turn_resolution_service=(
            turn_resolution_service
        ),
        world_service=world_service,
        campaign_state_service=(
            campaign_state_service
        ),
        turn_execution_lock=turn_execution_lock,
    )

    return (
        service,
        turn_resolution_service,
        world_service,
        campaign_state_service,
    )


# ============================================================
# CONSTRUCTOR
# ============================================================


def test_constructor_requires_turn_resolution_service():

    world_service = RecordingWorldService()

    with pytest.raises(TypeError):

        CampaignTurnService(
            turn_resolution_service=object(),
            world_service=world_service,
        )


def test_constructor_requires_world_service():

    result = make_result()

    turn_resolution_service = (
        RecordingTurnResolutionService(
            result
        )
    )

    with pytest.raises(TypeError):

        CampaignTurnService(
            turn_resolution_service=(
                turn_resolution_service
            ),
            world_service=object(),
        )


# ============================================================
# INPUT VALIDATION
# ============================================================


def test_player_input_must_be_string():

    service, _, _, _ = make_service()

    with pytest.raises(TypeError):

        service.play_turn(123)


def test_empty_player_input_is_rejected():

    service, _, _, _ = make_service()

    with pytest.raises(
        CampaignTurnServiceError
    ):

        service.play_turn("   ")


def test_player_input_is_stripped():

    result = make_result(
        player_input="Exploro."
    )

    service, resolver, _, _ = make_service(
        result=result
    )

    returned = service.play_turn(
        "   Exploro.   "
    )

    assert returned is result
    assert len(resolver.calls) == 1
    assert resolver.calls[0][1] == "Exploro."


# ============================================================
# WORLD
# ============================================================


def test_get_world_is_called_before_resolution():

    result = make_result()

    service, resolver, world_service, _campaign_state_service = (
        make_service(
                result=result
            )
        )

    service.play_turn(
        "Exploro."
    )

    assert (
        world_service.get_world_calls
        == 1
    )

    assert len(
        resolver.calls
    ) == 1

    assert isinstance(
        resolver.calls[0][0],
        TurnContext,
    )

    assert (
        resolver.calls[0][0].world
        is world_service.world
    )


def test_invalid_world_returned_by_world_service_is_rejected():

    result = make_result()

    world_service = RecordingWorldService()

    world_service.world = object()

    service, resolver, _, _ = make_service(
        result=result,
        world_service=world_service,
    )

    with pytest.raises(
        CampaignTurnServiceError,
        match="invalid WorldState",
    ):

        service.play_turn(
            "Exploro."
        )

    assert resolver.calls == []


# ============================================================
# RESOLUTION
# ============================================================


def test_resolution_result_is_preserved():

    result = make_result(
        player_input="Abro.",
        narrative="La puerta se abre.",
        world_changed=False,
    )

    service, _, _, _ = make_service(
        result=result
    )

    returned = service.play_turn(
        "Abro."
    )

    assert returned is result

    assert (
        returned.narrative
        == "La puerta se abre."
    )

    assert (
        returned.player_input
        == "Abro."
    )


def test_turn_resolution_service_error_is_wrapped():

    result = make_result()

    service, resolver, _, _ = make_service(
        result=result
    )

    resolver.error = (
        TurnResolutionServiceError(
            "DM failed"
        )
    )

    with pytest.raises(
        CampaignTurnServiceError,
        match="turn resolution failed",
    ) as exc_info:

        service.play_turn(
            "Exploro."
        )

    assert isinstance(
        exc_info.value.__cause__,
        TurnResolutionServiceError,
    )


def test_unexpected_resolution_error_is_wrapped():

    result = make_result()

    service, resolver, _, _ = make_service(
        result=result
    )

    resolver.error = RuntimeError(
        "unexpected"
    )

    with pytest.raises(
        CampaignTurnServiceError,
        match="unexpected error while resolving turn",
    ) as exc_info:

        service.play_turn(
            "Exploro."
        )

    assert isinstance(
        exc_info.value.__cause__,
        RuntimeError,
    )


def test_invalid_resolution_result_is_rejected():

    service, _resolver, _, _ = make_service(
        result=object()
    )

    with pytest.raises(
        CampaignTurnServiceError,
        match="invalid TurnResolutionResult",
    ):

        service.play_turn(
            "Exploro."
        )


# ============================================================
# PERSISTENCE
# ============================================================


def test_world_is_not_saved_when_world_did_not_change():

    result = make_result(
        world_changed=False
    )

    service, _, world_service, _  = (
        make_service(
            result=result
        )
    )

    service.play_turn(
        "Miro alrededor."
    )

    assert (
        world_service.save_calls
        == 0
    )


def test_play_turn_does_not_save_world_directly():

    result = make_result(
        world_changed=True
    )

    service, _, world_service, _  = (
        make_service(
            result=result
        )
    )

    service.play_turn(
        "Creo una entidad."
    )

    assert (
        world_service.save_calls
        == 0
    )


# ============================================================
# LOAD
# ============================================================


def test_load_returns_world():

    service, _, world_service, _  = (
        make_service()
    )

    returned = service.load()

    assert returned is (
        world_service.world
    )

    assert (
        world_service.load_calls
        == 1
    )


def test_load_failure_is_wrapped():

    service, _, world_service, _  = (
        make_service()
    )

    world_service.load_error = RuntimeError(
        "database unavailable"
    )

    with pytest.raises(
        CampaignTurnServiceError,
        match="failed to load campaign world",
    ) as exc_info:

        service.load()

    assert isinstance(
        exc_info.value.__cause__,
        RuntimeError,
    )


def test_load_rejects_invalid_world():

    service, _, world_service, _  = (
        make_service()
    )

    world_service.world = object()

    with pytest.raises(
        CampaignTurnServiceError,
        match="invalid WorldState",
    ):

        service.load()


# ============================================================
# EXPLICIT SAVE
# ============================================================


def test_save_delegates_to_world_service():

    service, _, world_service, _  = (
        make_service()
    )

    service.save()

    assert (
        world_service.save_calls
        == 1
    )


def test_explicit_save_failure_is_wrapped():

    service, _, world_service, _  = (
        make_service()
    )

    world_service.save_error = RuntimeError(
        "database unavailable"
    )

    with pytest.raises(
        CampaignTurnServiceError,
        match="failed to save campaign world",
    ) as exc_info:

        service.save()

    assert isinstance(
        exc_info.value.__cause__,
        RuntimeError,
    )


# ============================================================
# GET WORLD
# ============================================================


def test_get_world_returns_current_world():

    service, _, world_service, _  = (
        make_service()
    )

    returned = service.get_world()

    assert returned is (
        world_service.world
    )

    assert (
        world_service.get_world_calls
        == 1
    )


def test_get_world_rejects_invalid_world():

    service, _, world_service, _  = (
        make_service()
    )

    world_service.world = object()

    with pytest.raises(
        CampaignTurnServiceError,
        match="invalid WorldState",
    ):

        service.get_world()

# ============================================================
# CAMPAIGN STATE INTEGRATION
# ============================================================


def test_play_turn_uses_campaign_state_service():
    result = make_result()

    world_service = RecordingWorldService()

    campaign_state_service = (
        RecordingCampaignStateService(
            world_service
        )
    )

    service, resolver, _, state_service = (
        make_service(
            result=result,
            world_service=world_service,
            campaign_state_service=(
                campaign_state_service
            ),
        )
    )

    returned = service.play_turn(
        "Exploro."
    )

    assert returned is result

    assert (
        state_service.get_turn_context_calls
        == 1
    )

    assert len(
        resolver.calls
    ) == 1

    assert isinstance(
        resolver.calls[0][0],
        TurnContext,
    )

    assert (
        resolver.calls[0][0].world
        is world_service.world
    )


def test_play_turn_does_not_call_world_service_directly():
    result = make_result()

    world_service = RecordingWorldService()

    campaign_state_service = (
        RecordingCampaignStateService(
            world_service
        )
    )

    service, _, _, _ = make_service(
        result=result,
        world_service=world_service,
        campaign_state_service=(
            campaign_state_service
        ),
    )

    service.play_turn(
        "Exploro."
    )

    # CampaignTurnService obtiene el mundo
    # exclusivamente a través de CampaignStateService.
    assert (
        campaign_state_service.get_turn_context_calls
        == 1
    )


def test_campaign_state_service_error_is_wrapped():
    result = make_result()

    world_service = RecordingWorldService()

    campaign_state_service = (
        RecordingCampaignStateService(
            world_service
        )
    )

    campaign_state_service.state_error = (
        CampaignStateServiceError(
            "campaign does not exist"
        )
    )

    service, resolver, _, _ = make_service(
        result=result,
        world_service=world_service,
        campaign_state_service=(
            campaign_state_service
        ),
    )

    with pytest.raises(
        CampaignTurnServiceError,
        match="failed to obtain campaign turn context",
    ) as exc_info:

        service.play_turn(
            "Exploro."
        )

    assert isinstance(
        exc_info.value.__cause__,
        CampaignStateServiceError,
    )

    assert resolver.calls == []


def test_load_delegates_to_campaign_state_service():
    world_service = RecordingWorldService()

    campaign_state_service = (
        RecordingCampaignStateService(
            world_service
        )
    )

    service, _, _, _ = make_service(
        world_service=world_service,
        campaign_state_service=(
            campaign_state_service
        ),
    )

    returned = service.load()

    assert returned is world_service.world

    assert (
        campaign_state_service.load_world_calls
        == 1
    )


def test_save_delegates_to_campaign_state_service():
    world_service = RecordingWorldService()

    campaign_state_service = (
        RecordingCampaignStateService(
            world_service
        )
    )

    service, _, _, _ = make_service(
        world_service=world_service,
        campaign_state_service=(
            campaign_state_service
        ),
    )

    service.save()

    assert (
        campaign_state_service.save_world_calls
        == 1
    )


def test_get_world_delegates_to_campaign_state_service():
    world_service = RecordingWorldService()

    campaign_state_service = (
        RecordingCampaignStateService(
            world_service
        )
    )

    service, _, _, _ = make_service(
        world_service=world_service,
        campaign_state_service=(
            campaign_state_service
        ),
    )

    returned = service.get_world()

    assert (
        returned
        is world_service.world
    )

    assert (
        campaign_state_service.get_turn_context_calls
        == 1
    )

def test_play_turn_loads_recent_turns_before_resolving():

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

    class RecordingTurnRepository(
        TurnRepository
    ):

        def __init__(self):
            self.calls = []
            self.saved_turns = []
            self.connections = []

        def list_recent_turns(
            self,
            *,
            session_id=None,
            limit=10,
            conn=None,
        ):
            self.calls.append(
                (
                    session_id,
                    limit,
                )
            )

            return recent_turns

        def save_turn(
            self,
            turn,
            *,
            conn=None,
        ):
            self.saved_turns.append(
                turn
            )

            self.connections.append(
                conn
            )

            return turn

    world_service = RecordingWorldService()

    turn_repository = RecordingTurnRepository()

    resolver = RecordingTurnResolutionService(
        make_result(
            player_input="Pregunto por el camino.",
        )
    )

    service = CampaignTurnService(
        turn_resolution_service=resolver,
        world_service=world_service,
        turn_repository=turn_repository,
        turn_execution_lock=TurnExecutionLock(),
    )

    result = service.play_turn(
        "  Pregunto por el camino.  "
    )

    assert result.player_input == (
        "Pregunto por el camino."
    )

    assert resolver.last_recent_turns == recent_turns

    assert turn_repository.calls == [
        (None, 10),
    ]

    assert len(resolver.calls) == 1

    assert (
        resolver.calls[0][1]
        == "Pregunto por el camino."
    )

def test_play_turn_passes_shared_connection_to_turn_resolution_service():
    result = make_result()

    service, resolver, _, _ = make_service(
        result=result,
    )

    service.play_turn(
        "Exploro."
    )

    assert resolver.last_conn is not None

def test_play_turn_passes_same_connection_to_turn_repository():
    class RecordingTurnRepository(
        TurnRepository
    ):

        def __init__(self):
            self.connections = []

        def save_turn(
            self,
            turn,
            *,
            conn=None,
        ):
            self.connections.append(
                conn
            )

            return turn

    result = make_result()

    repository = RecordingTurnRepository()

    service = CampaignTurnService(
        turn_resolution_service=(
            RecordingTurnResolutionService(
                result
            )
        ),
        world_service=RecordingWorldService(),
        turn_repository=repository,
        turn_execution_lock=TurnExecutionLock(),
    )

    service.play_turn(
        "Exploro."
    )

    assert len(
        repository.connections
    ) == 1

    assert repository.connections[0] is not None

def test_play_turn_persists_turn_record_when_turn_repository_is_configured():
    result = make_result(
        player_input="Exploro la taberna.",
        narrative="El interior está casi vacío.",
        world_changed=False,
    )

    world_service = RecordingWorldService()

    turn_repository = TurnRepository()

    turn_resolution_service = RecordingTurnResolutionService(
        result
    )

    service = CampaignTurnService(
        turn_resolution_service=turn_resolution_service,
        world_service=world_service,
        turn_repository=turn_repository,
        turn_execution_lock=TurnExecutionLock(),
    )

    returned = service.play_turn(
        "  Exploro la taberna.  "
    )

    assert returned is result

    turns = turn_repository.list_turns()

    assert len(turns) == 1

    saved_turn = turns[0]

    assert saved_turn.player_input == (
        "Exploro la taberna."
    )

    assert saved_turn.narrative == (
        "El interior está casi vacío."
    )

    assert saved_turn.operation_count == (
        result.operation_count
    )

    assert saved_turn.successful_operation_count == (
        result.successful_operation_count
    )

    assert saved_turn.failed_operation_count == (
        result.failed_operation_count
    )

    assert saved_turn.all_operations_succeeded == (
        result.all_operations_succeeded
    )

    assert saved_turn.world_changed == (
        result.world_changed
    )


def test_play_turn_persists_turn_with_same_session_id():
    result = make_result(
        player_input="Pregunto por Aldric.",
        narrative="El tabernero señala una mesa.",
    )

    world_service = RecordingWorldService()

    turn_repository = TurnRepository()

    turn_resolution_service = RecordingTurnResolutionService(
        result
    )

    campaign_state_service = RecordingCampaignStateService(
        world_service
    )

    service = CampaignTurnService(
        turn_resolution_service=turn_resolution_service,
        world_service=world_service,
        campaign_state_service=campaign_state_service,
        turn_repository=turn_repository,
        turn_execution_lock=TurnExecutionLock(),
    )

    returned = service.play_turn(
        "Pregunto por Aldric."
    )

    assert returned is result

    turns = turn_repository.list_turns()

    assert len(turns) == 1

    assert turns[0].session_id is None


def test_play_turn_loads_recent_turns_before_resolution():
    first_result = make_result(
        player_input="Entro en la taberna.",
        narrative="La taberna está llena.",
    )

    repository = TurnRepository()

    repository.save_turn(
        TurnRecord(
            session_id=None,
            player_input="Llego a Vorder's Hold.",
            narrative="La lluvia cae sobre la ciudad.",
        )
    )

    world_service = RecordingWorldService()

    turn_resolution_service = RecordingTurnResolutionService(
        first_result
    )

    service = CampaignTurnService(
        turn_resolution_service=turn_resolution_service,
        world_service=world_service,
        turn_repository=repository,
        turn_execution_lock=TurnExecutionLock(),
    )

    service.play_turn(
        "Entro en la taberna."
    )

    assert (
        turn_resolution_service.last_recent_turns
        is not None
    )

    assert len(
        turn_resolution_service.last_recent_turns
    ) == 1

    recent_turn = (
        turn_resolution_service.last_recent_turns[0]
    )

    assert recent_turn.player_input == (
        "Llego a Vorder's Hold."
    )

    assert recent_turn.narrative == (
        "La lluvia cae sobre la ciudad."
    )


def test_play_turn_persists_current_turn_after_loading_recent_history():
    repository = TurnRepository()

    repository.save_turn(
        TurnRecord(
            session_id=None,
            player_input="Primer turno.",
            narrative="Primera escena.",
        )
    )

    result = make_result(
        player_input="Segundo turno.",
        narrative="Segunda escena.",
    )

    world_service = RecordingWorldService()

    resolver = RecordingTurnResolutionService(
        result
    )

    service = CampaignTurnService(
        turn_resolution_service=resolver,
        world_service=world_service,
        turn_repository=repository,
        turn_execution_lock=TurnExecutionLock(),
    )

    service.play_turn(
        "Segundo turno."
    )

    turns = repository.list_turns()

    assert len(turns) == 2

    assert turns[0].player_input == (
        "Primer turno."
    )

    assert turns[1].player_input == (
        "Segundo turno."
    )

    assert turns[0].narrative == (
        "Primera escena."
    )

    assert turns[1].narrative == (
        "Segunda escena."
    )

def test_play_turn_serializes_concurrent_turns():
    world_service = RecordingWorldService()

    result = make_result(
        player_input="Primer turno.",
    )

    resolution_service = RecordingTurnResolutionService(
        result=result,
    )

    service = CampaignTurnService(
        turn_resolution_service=resolution_service,
        world_service=world_service,
        turn_execution_lock=TurnExecutionLock(),
    )

    first_entered = threading.Event()
    release_first = threading.Event()

    original_resolve_turn = (
        resolution_service.resolve_turn
    )

    calls = []

    def blocking_resolve_turn(
        turn_context,
        player_input,
        *,
        recent_turns=None,
        conn=None,
    ):
        calls.append(player_input)

        if player_input == "Primer turno.":
            first_entered.set()

            if not release_first.wait(
                timeout=5
            ):
                raise RuntimeError(
                    "Timed out waiting for first turn."
                )

        return original_resolve_turn(
            turn_context,
            player_input,
            recent_turns=recent_turns,
            conn=conn,
        )

    resolution_service.resolve_turn = (
        blocking_resolve_turn
    )

    first_thread = threading.Thread(
        target=service.play_turn,
        args=("Primer turno.",),
    )

    second_finished = threading.Event()

    def run_second_turn():
        service.play_turn(
            "Segundo turno."
        )
        second_finished.set()

    second_thread = threading.Thread(
        target=run_second_turn,
    )

    first_thread.start()

    assert first_entered.wait(
        timeout=5
    )

    second_thread.start()

    time.sleep(0.1)

    assert (
        second_finished.is_set()
        is False
    )

    release_first.set()

    first_thread.join(
        timeout=5
    )

    second_thread.join(
        timeout=5
    )

    assert (
        second_finished.is_set()
        is True
    )

    assert calls == [
        "Primer turno.",
        "Segundo turno.",
    ]

def test_play_turn_serializes_concurrent_turns_and_persists_in_order():
    import threading
    import time

    world_service = RecordingWorldService()

    first_result = make_result(
        player_input="Primer turno.",
        narrative="Primera escena.",
    )

    second_result = make_result(
        player_input="Segundo turno.",
        narrative="Segunda escena.",
    )

    resolution_service = RecordingTurnResolutionService(
        result=first_result,
    )

    service = CampaignTurnService(
        turn_resolution_service=resolution_service,
        world_service=world_service,
        turn_execution_lock=TurnExecutionLock(),
    )

    first_started = threading.Event()
    release_first = threading.Event()

    calls = []

    original_resolve_turn = (
        resolution_service.resolve_turn
    )

    def blocking_resolve_turn(
        turn_context,
        player_input,
        *,
        recent_turns=None,
        conn=None,
    ):
        calls.append(player_input)

        if player_input == "Primer turno.":
            first_started.set()

            if not release_first.wait(timeout=5):
                raise RuntimeError(
                    "Timed out waiting for first turn."
                )

        resolution_service.result = (
            first_result
            if player_input == "Primer turno."
            else second_result
        )

        return original_resolve_turn(
            turn_context,
            player_input,
            recent_turns=recent_turns,
            conn=conn,
        )

    resolution_service.resolve_turn = (
        blocking_resolve_turn
    )

    first_exception = []
    second_exception = []

    def run_first():
        try:
            service.play_turn(
                "Primer turno."
            )
        except Exception as exc: # noqa: BLE001
            first_exception.append(exc)

    def run_second():
        try:
            service.play_turn(
                "Segundo turno."
            )
        except Exception as exc: # noqa: BLE001
            second_exception.append(exc)

    first_thread = threading.Thread(
        target=run_first,
    )

    second_thread = threading.Thread(
        target=run_second,
    )

    first_thread.start()

    assert first_started.wait(
        timeout=5
    )

    second_thread.start()

    time.sleep(0.1)

    # El segundo turno no puede entrar en resolución
    # mientras el primero siga ejecutándose.
    assert calls == [
        "Primer turno.",
    ]

    release_first.set()

    first_thread.join(
        timeout=5
    )

    second_thread.join(
        timeout=5
    )

    assert not first_exception
    assert not second_exception

    assert calls == [
        "Primer turno.",
        "Segundo turno.",
    ]

def test_play_turn_restores_world_when_turn_persistence_fails(
    monkeypatch,
):
    from services.campaign_turn_service import (
        CampaignTurnService,
        CampaignTurnServiceError,
    )

    world_service = RecordingWorldService()

    original_world = world_service.world

    original_entity_count = len(
        original_world.entities
    )

    result = make_result(
        player_input="Creo a Aldric.",
        narrative="Aldric aparece.",
    )

    resolution_service = RecordingTurnResolutionService(
        result=result,
    )

    repository = TurnRepository()

    def failing_save_turn(
        *args,
        **kwargs,
    ):
        raise RuntimeError(
            "turn persistence failed"
        )

    monkeypatch.setattr(
        repository,
        "save_turn",
        failing_save_turn,
    )

    service = CampaignTurnService(
        turn_resolution_service=resolution_service,
        world_service=world_service,
        turn_repository=repository,
        turn_execution_lock=TurnExecutionLock(),
    )

    try:
        service.play_turn(
            "Creo a Aldric."
        )
    except CampaignTurnServiceError:
        pass
    else:
        raise AssertionError(
            "Expected CampaignTurnServiceError"
        )

    assert (
        world_service.world
        is original_world
    )

    assert (
        len(
            original_world.entities
        )
        == original_entity_count
    )

def test_invalid_resolution_result_restores_world():
    class MutatingInvalidResultService(
        TurnResolutionService
    ):
        def resolve_turn(
            self,
            turn_context,
            player_input,
            *,
            recent_turns=None,
            conn=None,
        ):
            turn_context.world.entities[1] = "temporary"

            return object()

    world_service = RecordingWorldService()

    world_service.world.entities[1] = (
        "original"
    )

    dm_service = object.__new__(DMService)
    extractor = object.__new__(LLMWorldExtractor)

    resolver = MutatingInvalidResultService(
        dm_service=dm_service,
        extractor=extractor,
        world_service=world_service,
    )

    service = CampaignTurnService(
        turn_resolution_service=resolver,
        world_service=world_service,
        turn_execution_lock=TurnExecutionLock(),
    )

    with pytest.raises(
        CampaignTurnServiceError,
        match="invalid TurnResolutionResult",
    ):
        service.play_turn(
            "Exploro."
        )

    assert (
        world_service.world.entities[1]
        == "original"
    )

def test_failed_turn_rolls_back_database_changes_before_saving_turn(
    isolated_database,
):
    from database import one
    from operations.world_operations import (
        CreateEntityOperation,
    )

    operation = CreateEntityOperation(
        name="Temporal",
        entity_type="npc",
        description="Temporal.",
        notes="",
        active=True,
    )

    result = TurnResolutionResult(
        player_input="Exploro.",
        narrative="La acción falla.",
        operations=(operation,),
        operation_results=(
            OperationResult(
                status=OperationStatus.INVALID,
                message="Forced failure.",
                operation=operation,
            ),
        ),
    )

    class MutatingFailingResolutionService(
        RecordingTurnResolutionService
    ):
        def resolve_turn(
            self,
            turn_context,
            player_input,
            *,
            recent_turns=None,
            conn=None,
        ):
            conn.execute(
                """
                UPDATE campaign
                SET summary=?
                WHERE id=1
                """,
                ("temporary",),
            )

            return super().resolve_turn(
                turn_context,
                player_input,
                recent_turns=recent_turns,
                conn=conn,
            )

    resolver = MutatingFailingResolutionService(
        result
    )

    world_service = RecordingWorldService()

    turn_repository = TurnRepository()

    service = CampaignTurnService(
        turn_resolution_service=resolver,
        world_service=world_service,
        turn_repository=turn_repository,
        turn_execution_lock=TurnExecutionLock(),
    )

    returned = service.play_turn(
        "Exploro."
    )

    assert (
        returned.all_operations_succeeded
        is False
    )

    campaign = one(
        """
        SELECT summary
        FROM campaign
        WHERE id=1
        """
    )

    assert campaign["summary"] == ""

    turns = turn_repository.list_turns()

    assert len(turns) == 1

    assert turns[0].player_input == (
        "Exploro."
    )

    assert (
        turns[0].all_operations_succeeded
        is False
    )

def test_turn_save_failure_rolls_back_resolution_database_changes(
    isolated_database,
    monkeypatch,
):
    from database import one
    from repositories.turn_repository import TurnRepository

    class MutatingResolutionService(
        RecordingTurnResolutionService
    ):
        def resolve_turn(
            self,
            turn_context,
            player_input,
            *,
            recent_turns=None,
            conn=None,
        ):
            conn.execute(
                """
                UPDATE campaign
                SET summary=?
                WHERE id=1
                """,
                ("temporary",),
            )

            return super().resolve_turn(
                turn_context,
                player_input,
                recent_turns=recent_turns,
                conn=conn,
            )

    def failing_save_turn(
        self,
        turn,
        *,
        conn=None,
    ):
        raise RuntimeError(
            "forced turn persistence failure"
        )

    monkeypatch.setattr(
        TurnRepository,
        "save_turn",
        failing_save_turn,
    )

    resolver = MutatingResolutionService(
        TurnResolutionResult(
            player_input="Exploro.",
            narrative="La acción tiene éxito.",
            operations=(),
            operation_results=(),
        )
    )

    world_service = RecordingWorldService()

    service = CampaignTurnService(
        turn_resolution_service=resolver,
        world_service=world_service,
        turn_repository=TurnRepository(),
        turn_execution_lock=TurnExecutionLock(),
    )

    with pytest.raises(
        CampaignTurnServiceError,
        match="unexpected error while resolving turn",
    ):
        service.play_turn(
            "Exploro."
        )

    campaign = one(
        """
        SELECT summary
        FROM campaign
        WHERE id=1
        """
    )

    assert campaign["summary"] == ""

def test_turn_save_failure_restores_in_memory_world(
    isolated_database,
    monkeypatch,
):
    operation = CreateEntityOperation(
        name="Temporal",
        entity_type="npc",
        description="Temporal.",
        notes="",
        active=True,
    )

    result = TurnResolutionResult(
        player_input="Creo a Temporal.",
        narrative="Temporal aparece.",
        operations=(operation,),
        operation_results=(
            OperationResult(
                status=OperationStatus.SUCCESS,
                operation=operation,
            ),
        ),
    )

    class MutatingResolutionService(
        RecordingTurnResolutionService
    ):
        def resolve_turn(
            self,
            turn_context,
            player_input,
            *,
            recent_turns=None,
            conn=None,
        ):
            turn_context.world.entities[1] = "temporary"

            return super().resolve_turn(
                turn_context,
                player_input,
                recent_turns=recent_turns,
                conn=conn,
            )

    def failing_save_turn(
        self,
        turn,
        *,
        conn=None,
    ):
        raise RuntimeError(
            "forced turn persistence failure"
        )

    monkeypatch.setattr(
        TurnRepository,
        "save_turn",
        failing_save_turn,
    )

    world_service = RecordingWorldService()

    world_service.world.entities[1] = "original"

    original_world = world_service.world

    resolver = MutatingResolutionService(
        result
    )

    service = CampaignTurnService(
        turn_resolution_service=resolver,
        world_service=world_service,
        turn_repository=TurnRepository(),
        turn_execution_lock=TurnExecutionLock(),
    )

    with pytest.raises(
        CampaignTurnServiceError,
        match="unexpected error while resolving turn",
    ):
        service.play_turn(
            "Creo a Temporal."
        )

    assert (
        world_service.world
        is original_world
    )

    assert (
        world_service.world.entities[1]
        == "original"
    )

def test_play_turn_serializes_concurrent_calls():
    import threading
    import time

    from models.turn_resolution_result import (
        TurnResolutionResult,
    )

    class ConcurrentResolutionService(
        RecordingTurnResolutionService
    ):
        def __init__(self):
            super().__init__(
                TurnResolutionResult(
                    player_input="",
                    narrative="Narrativa.",
                    operations=(),
                    operation_results=(),
                )
            )

            self.active_calls = 0
            self.max_active_calls = 0
            self.calls = []
            self.lock = threading.Lock()

        def resolve_turn(
            self,
            turn_context,
            player_input,
            *,
            recent_turns=None,
            conn=None,
        ):
            with self.lock:
                self.active_calls += 1
                self.max_active_calls = max(
                    self.max_active_calls,
                    self.active_calls,
                )
                self.calls.append(player_input)

            try:
                time.sleep(0.05)

                return TurnResolutionResult(
                    player_input=player_input,
                    narrative="Narrativa.",
                    operations=(),
                    operation_results=(),
                )

            finally:
                with self.lock:
                    self.active_calls -= 1

    resolution_service = ConcurrentResolutionService()

    world_service = RecordingWorldService()

    service = CampaignTurnService(
        turn_resolution_service=resolution_service,
        world_service=world_service,
        turn_execution_lock=TurnExecutionLock(),
    )

    errors = []

    def run_turn(player_input):
        try:
            service.play_turn(player_input)
        except Exception as exc: # noqa: BLE001
            errors.append(exc)

    thread_a = threading.Thread(
        target=run_turn,
        args=("Turno A",),
    )

    thread_b = threading.Thread(
        target=run_turn,
        args=("Turno B",),
    )

    thread_a.start()
    thread_b.start()

    thread_a.join()
    thread_b.join()

    assert errors == []

    assert resolution_service.max_active_calls == 1

    assert sorted(
        resolution_service.calls
    ) == [
        "Turno A",
        "Turno B",
    ]

def test_play_turn_releases_lock_after_resolution_failure():
    from models.turn_resolution_result import (
        TurnResolutionResult,
    )
    from services.turn_resolution_service import (
        TurnResolutionServiceError,
    )

    class FailingOnceResolutionService(
        RecordingTurnResolutionService
    ):
        def __init__(self):
            super().__init__(
                TurnResolutionResult(
                    player_input="",
                    narrative="Narrativa.",
                    operations=(),
                    operation_results=(),
                )
            )

            self.calls = 0

        def resolve_turn(
            self,
            turn_context,
            player_input,
            *,
            recent_turns=None,
            conn=None,
        ):
            self.calls += 1

            if self.calls == 1:
                raise TurnResolutionServiceError(
                    "forced failure"
                )

            return TurnResolutionResult(
                player_input=player_input,
                narrative="Segundo turno correcto.",
                operations=(),
                operation_results=(),
            )

    resolution_service = FailingOnceResolutionService()

    world_service = RecordingWorldService()

    service = CampaignTurnService(
        turn_resolution_service=resolution_service,
        world_service=world_service,
        turn_execution_lock=TurnExecutionLock(),
    )

    with pytest.raises(
        CampaignTurnServiceError,
        match="turn resolution failed",
    ):
        service.play_turn("Primer turno.")

    result = service.play_turn(
        "Segundo turno."
    )

    assert result.player_input == "Segundo turno."
    assert resolution_service.calls == 2

def test_mixed_turn_operations_are_atomic_when_character_operation_fails(
    isolated_database,
):
    from database import execute, one
    from models.character_state import CharacterState
    from models.operation_result import (
        OperationResult,
        OperationStatus,
    )
    from operations.character_operations import (
        ChangeCharacterHpOperation,
    )
    from operations.world_operations import (
        CreateEntityOperation,
    )
    from repositories.character_repository import (
        CharacterRepository,
    )

    execute(
        """
        INSERT INTO entities (
            name,
            entity_type,
            description,
            notes,
            active
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "Aldric",
            "character",
            "Personaje de prueba.",
            "",
            1,
        ),
    )

    CharacterRepository().save_character(
        CharacterState(
            entity_id=1,
            level=1,
            class_name="Fighter",
            current_hp=10,
            max_hp=10,
            armor_class=16,
            strength=15,
            dexterity=14,
            constitution=14,
            intelligence=10,
            wisdom=10,
            charisma=10,
            proficiency_bonus=2,
            metadata={},
        ),
        campaign_id=1,
    )

    world_service = RecordingWorldService()

    world_operation = CreateEntityOperation(
        name="Temporal",
        entity_type="npc",
        description="NPC temporal.",
        notes="",
        active=True,
    )

    character_operation = ChangeCharacterHpOperation(
        entity_id=1,
        amount=-5,
    )

    class FailingCharacterApplier:
        def apply(
            self,
            operation,
            *,
            campaign_id,
            conn=None,
        ):
            return OperationResult(
                status=OperationStatus.INVALID,
                message="Forced character failure.",
                operation=operation,
            )

    world_service.character_applier = (
        FailingCharacterApplier()
    )

    operations = (
        world_operation,
        character_operation,
    )

    result = world_service.apply_turn_operations(
        (world_operation,),
        (character_operation,),
        campaign_id=1,
        ordered_operations=operations,
    )

    assert len(result) == 2

    assert result[0].success is True
    assert result[1].success is False

    assert world_service.world.entities == {}

    character = one(
        """
        SELECT current_hp
        FROM character_states
        WHERE entity_id=1
        """
    )

    assert character["current_hp"] == 10

    temporal = one(
        """
        SELECT id
        FROM entities
        WHERE name=?
        """,
        ("Temporal",),
    )

    assert temporal is None

def test_play_turn_uses_provided_turn_execution_lock():
    result = make_result()

    turn_execution_lock = TurnExecutionLock()

    service, _, _, _ = make_service(
        result=result,
        turn_execution_lock=turn_execution_lock,
    )

    assert (
        service.turn_execution_lock
        is turn_execution_lock
    )


def test_failed_turn_rolls_back_created_entity_but_persists_turn(
    isolated_database,
):
    from database import one
    from models.entity import Entity
    from models.operation_result import (
        OperationResult,
        OperationStatus,
    )
    from models.turn_resolution_result import (
        TurnResolutionResult,
    )
    from operations.world_operations import (
        CreateEntityOperation,
    )
    from repositories.entity_repository import (
        EntityRepository,
    )

    operation = CreateEntityOperation(
        name="Entidad temporal",
        entity_type="npc",
        description="No debería persistir.",
        notes="",
        active=True,
    )

    result = TurnResolutionResult(
        player_input="Exploro.",
        narrative="Algo sale mal.",
        operations=(operation,),
        operation_results=(
            OperationResult(
                status=OperationStatus.INVALID,
                message="Forced failure.",
                operation=operation,
            ),
        ),
    )

    class MutatingFailingResolutionService(
        RecordingTurnResolutionService
    ):
        def resolve_turn(
            self,
            turn_context,
            player_input,
            *,
            recent_turns=None,
            conn=None,
        ):
            entity = Entity(
                name="Entidad temporal",
                entity_type="npc",
                description="No debería persistir.",
                notes="",
                active=True,
            )

            EntityRepository().save_entity(
                entity,
                campaign_id=turn_context.campaign.campaign_id,
                conn=conn,
            )

            return super().resolve_turn(
                turn_context,
                player_input,
                recent_turns=recent_turns,
                conn=conn,
            )

    resolver = MutatingFailingResolutionService(
        result
    )

    world_service = RecordingWorldService()

    turn_repository = TurnRepository()

    service = CampaignTurnService(
        turn_resolution_service=resolver,
        world_service=world_service,
        turn_repository=turn_repository,
        turn_execution_lock=TurnExecutionLock(),
    )

    returned = service.play_turn(
        "Exploro."
    )

    assert returned.all_operations_succeeded is False

    entity = one(
        """
        SELECT id
        FROM entities
        WHERE name=?
        """,
        ("Entidad temporal",),
    )

    assert entity is None

    turns = turn_repository.list_turns()

    assert len(turns) == 1

    assert turns[0].player_input == "Exploro."

    assert turns[0].narrative == "Algo sale mal."

    assert turns[0].operation_count == 1

    assert turns[0].successful_operation_count == 0

    assert turns[0].failed_operation_count == 1

    assert turns[0].all_operations_succeeded is False

    assert turns[0].world_changed is False

def test_play_turn_passes_transaction_connection_to_campaign_state_service():
    result = make_result()

    world_service = RecordingWorldService()

    campaign_state_service = (
        RecordingCampaignStateService(
            world_service
        )
    )

    service, _, _, state_service = make_service(
        result=result,
        world_service=world_service,
        campaign_state_service=(
            campaign_state_service
        ),
    )

    service.play_turn(
        "Exploro."
    )

    assert state_service.last_conn is not None