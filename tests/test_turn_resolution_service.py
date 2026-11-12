import pytest

from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.entity import Entity
from models.operation_result import (
    OperationStatus,
)
from models.session_state import SessionState
from models.turn_context import TurnContext
from models.world_state import WorldState
from operations.character_operations import ChangeCharacterHpOperation
from operations.operation_reference import OperationReference
from operations.referenced_operation import ReferencedOperation
from operations.world_operations import (
    CreateEntityOperation,
    UpdateEntityOperation,
    WorldOperation,
)
from services.context import ContextBuilder
from services.llm_world import LLMWorldExtractor
from services.providers import FakeLLMProvider
from services.turns import DMService
from services.turns.turn_resolution_service import (
    TurnResolutionService,
    TurnResolutionServiceError,
)
from services.world import WorldApplier, WorldService


class RecordingDMService(DMService):

    def __init__(self):
        provider = FakeLLMProvider(
            response="La puerta se abre lentamente."
        )

        super().__init__(
            provider=provider,
            context_builder=ContextBuilder(),
        )

        self.calls = []

    def generate(
        self,
        turn_context,
        player_input,
    ):
        self.calls.append(
            (
                "generate",
                turn_context,
                player_input,
            )
        )

        return super().generate(
            turn_context,
            player_input,
        )


class RecordingExtractor(LLMWorldExtractor):

    def __init__(self, operations=None):
        self.operations = operations or []
        self.received_text = None
        self.received_context = None
        self.received_projection = None
        self.calls = []

    def propose(
        self,
        player_intent,
        context,
        *,
        mechanics_result=None,
        context_projection=None,
    ):
        self.received_text = player_intent
        self.received_context = context
        self.received_projection = context_projection
        self.calls.append(("propose", player_intent))
        return self.operations


class RecordingApplier(WorldApplier):

    def __init__(self):
        super().__init__()
        self.calls = []

    def apply(
        self,
        world,
        operation,
    ):
        self.calls.append(
            operation
        )

        return super().apply(
            world,
            operation,
        )


def make_world():

    return WorldState()

def make_turn_context(world=None):
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
        world=world if world is not None else WorldState(),
    )

def make_service(
    *,
    dm_service=None,
    extractor=None,
    applier=None,
    context_builder=None,
    proposal_context_max_tokens=4096,
):
    dm_service = (
        dm_service
        or RecordingDMService()
    )

    extractor = (
        extractor
        or RecordingExtractor()
    )

    applier = (
        applier
        or RecordingApplier()
    )

    world_service = WorldService(
        applier=applier,
    )

    return (
        TurnResolutionService(
            dm_service=dm_service,
            extractor=extractor,
            world_service=world_service,
            context_builder=context_builder,
            proposal_context_max_tokens=proposal_context_max_tokens,
        ),
        dm_service,
        extractor,
        applier,
    )


# ============================================================
# CONSTRUCTOR
# ============================================================


def test_constructor_requires_dm_service():

    with pytest.raises(TypeError):

        TurnResolutionService(
            dm_service=object(),
            extractor=RecordingExtractor(),
            world_service=WorldService(
                applier=RecordingApplier(),
            ),
        )


def test_constructor_requires_extractor():

    dm_service = RecordingDMService()

    with pytest.raises(TypeError):

        TurnResolutionService(
            dm_service=dm_service,
            extractor=object(),
            world_service=WorldService(
                applier=RecordingApplier(),
            ),
        )


def test_constructor_requires_world_service():

    dm_service = RecordingDMService()

    with pytest.raises(TypeError):

        TurnResolutionService(
            dm_service=dm_service,
            extractor=RecordingExtractor(),
            world_service=object(),
        )


# ============================================================
# VALIDATION
# ============================================================


def test_turn_context_must_be_turn_context():

    service, *_ = make_service()

    with pytest.raises(
        TypeError,
        match="turn_context must be a TurnContext or WorldState"
    ):

        service.resolve_turn(
            object(),
            "Exploro.",
        )


def test_player_input_must_be_string():

    service, *_ = make_service()

    with pytest.raises(TypeError):

        service.resolve_turn(
            make_turn_context(),
            123,
        )


def test_empty_player_input_is_rejected():

    service, *_ = make_service()

    with pytest.raises(
        TurnResolutionServiceError
    ):

        service.resolve_turn(
            make_turn_context(),
            "   ",
        )


def test_player_input_is_stripped():

    service, dm, *_ = make_service()

    context = make_turn_context()

    result = service.resolve_turn(
        context,
        "   Exploro.   ",
    )

    assert result.player_input == "Exploro."

    assert len(dm.calls) == 1

    assert dm.calls[0][0] == "generate"
    assert dm.calls[0][1] is context
    assert dm.calls[0][2] == "Exploro."


# ============================================================
# NARRATIVE
# ============================================================


def test_narrative_is_returned():

    service, *_ = make_service()

    result = service.resolve_turn(
        make_turn_context(),
        "Abro la puerta.",
    )

    assert (
        result.narrative
        == "La puerta se abre lentamente."
    )


def test_empty_narrative_is_rejected():

    dm = RecordingDMService()

    dm.generate = (
        lambda turn_context, player_input: ""
    )

    service = TurnResolutionService(
        dm_service=dm,
        extractor=RecordingExtractor(),
        world_service=WorldService(
            applier=RecordingApplier(),
        ),
    )

    with pytest.raises(
        TurnResolutionServiceError
    ):

        service.resolve_turn(
            make_turn_context(),
            "Abro.",
        )


def test_dm_failure_is_wrapped():

    dm = RecordingDMService()

    def failing_generate(
        turn_context,
        player_input,
    ):
        raise RuntimeError("boom")

    dm.generate = failing_generate

    service = TurnResolutionService(
        dm_service=dm,
        extractor=RecordingExtractor(),
        world_service=WorldService(
            applier=RecordingApplier(),
        ),
    )

    with pytest.raises(
        TurnResolutionServiceError,
        match="DMService failed",
    ):

        service.resolve_turn(
            make_turn_context(),
            "Abro.",
        )


# ============================================================
# EXTRACTION
# ============================================================


def test_no_operations_are_valid():

    service, _, extractor, applier = (
        make_service()
    )

    result = service.resolve_turn(
        make_turn_context(),
        "Miro alrededor.",
    )

    assert result.operations == ()
    assert result.operation_results == ()

    assert extractor.calls
    assert applier.calls == []


def test_proposer_receives_player_intent():

    service, _, extractor, _ = (
        make_service()
    )

    service.resolve_turn(
        make_turn_context(),
        "Abro la puerta.",
    )

    assert extractor.calls == [
        (
            "propose",
            "La puerta se abre lentamente.",
        )
    ]


def test_extractor_failure_is_wrapped():

    class FailingExtractor(LLMWorldExtractor):

        def __init__(self):
            super().__init__(
                provider=lambda prompt: "",
                operation_parser=object(),
            )

        def propose(
            self,
            text,
            world,
        ):
            raise RuntimeError("extract failed")

    service, dm, _, _applier = (
        make_service()
    )

    service = TurnResolutionService(
        dm_service=dm,
        extractor=FailingExtractor(),
        world_service=WorldService(
            applier=RecordingApplier(),
        ),
    )

    with pytest.raises(
        TurnResolutionServiceError,
        match="LLMWorldExtractor failed",
    ):

        service.resolve_turn(
            make_turn_context(),
            "Abro.",
        )


def test_invalid_extractor_result_is_rejected():

    class InvalidExtractor(LLMWorldExtractor):

        def __init__(self):
            super().__init__(
                provider=lambda prompt: "",
                operation_parser=object(),
            )

        def propose(
            self,
            text,
            world,
        ):
            return [
                "not an operation"
            ]

    service, dm, _, _applier = (
        make_service()
    )

    service = TurnResolutionService(
        dm_service=dm,
        extractor=InvalidExtractor(),
        world_service=WorldService(
            applier=RecordingApplier(),
        ),
    )

    with pytest.raises(
        TurnResolutionServiceError,
        match="LLMWorldExtractor returned an invalid operation"
    ):

        service.resolve_turn(
            make_turn_context(),
            "Abro.",
        )


# ============================================================
# APPLICATION
# ============================================================


def test_operations_are_applied():

    world = make_world()

    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
        description="Mercader.",
        notes="",
        active=True,
    )

    extractor = RecordingExtractor(
        operations=[
            operation,
        ]
    )

    service, _, _, applier = (
        make_service(
            extractor=extractor
        )
    )

    result = service.resolve_turn(
        world,
        "Conozco a Aldric.",
    )

    assert result.operation_count == 1
    assert result.successful_operation_count == 1
    assert result.world_changed is True

    assert 1 in service.world_service.world.entities
    assert (
        service.world_service.world.entities[1].name
        == "Aldric"
    )

    assert len(
        applier.calls
    ) == 1


def test_operation_result_is_preserved():

    world = make_world()

    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
        description="Mercader.",
        notes="",
        active=True,
    )

    extractor = RecordingExtractor(
        operations=[
            operation,
        ]
    )

    service, *_ = make_service(
        extractor=extractor
    )

    result = service.resolve_turn(
        world,
        "Conozco a Aldric.",
    )

    assert len(
        result.operation_results
    ) == 1

    operation_result = (
        result.operation_results[0]
    )

    assert (
        operation_result.status
        == OperationStatus.SUCCESS
    )


def test_failed_operation_rolls_back_entire_turn():

    world = make_world()

    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
        description="Mercader.",
        notes="",
        active=True,
    )

    extractor = RecordingExtractor(
        operations=[
            operation,
            operation,
        ]
    )

    service, *_ = make_service(
        extractor=extractor
    )

    result = service.resolve_turn(
        world,
        "Conozco a Aldric.",
    )

    assert result.operation_count == 2

    assert (
        result.operation_results[0].success
        is True
    )

    assert (
        result.operation_results[1].success
        is False
    )

    assert (
        result.all_operations_succeeded
        is False
    )

    assert (
        result.successful_operation_count
        == 1
    )

    assert (
        result.failed_operation_count
        == 1
    )

    # La operación que había tenido éxito debe
    # desaparecer también por el rollback.
    assert (
        service.world_service.world.entities == {}
        and world.entities == {}
    )

# ============================================================
# ORDER
# ============================================================


def test_turn_resolution_order():

    order = []

    dm = RecordingDMService()

    original_generate = dm.generate

    def generate(
        turn_context,
        player_input,
    ):
        order.append("dm")

        return original_generate(
            turn_context,
            player_input,
        )

    dm.generate = generate

    extractor = RecordingExtractor()

    original_propose = extractor.propose

    def propose(
        text,
        world,
    ):
        order.append("proposer")

        return original_propose(
            text,
            world,
        )

    extractor.propose = propose

    applier = RecordingApplier()

    original_apply = applier.apply

    def apply(
        world,
        operation,
    ):
        order.append("applier")

        return original_apply(
            world,
            operation,
        )

    applier.apply = apply

    world_service = WorldService(
        applier=applier,
    )

    service = TurnResolutionService(
        dm_service=dm,
        extractor=extractor,
        world_service=world_service,
    )

    service.resolve_turn(
        make_turn_context(),
        "Exploro.",
    )

    assert order == ["proposer", "dm"]


# ============================================================
# WORLD STATE
# ============================================================


def test_no_operations_leave_world_unchanged():

    world = make_world()

    before = dict(
        world.entities
    )

    service, *_ = make_service()

    service.resolve_turn(
        world,
        "Miro.",
    )

    assert world.entities == before

def test_turn_resolution_order_with_operation():

    order = []

    dm = RecordingDMService()

    original_generate = dm.generate

    def generate(
        turn_context,
        player_input,
    ):
        order.append("dm")

        return original_generate(
            turn_context,
            player_input,
        )

    dm.generate = generate

    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
        description="Mercader.",
        notes="",
        active=True,
    )

    extractor = RecordingExtractor(
        operations=[
            operation,
        ]
    )

    original_propose = extractor.propose

    def propose(
        text,
        world,
    ):
        order.append("proposer")

        return original_propose(
            text,
            world,
        )

    extractor.propose = propose

    applier = RecordingApplier()

    original_apply = applier.apply

    def apply(
        world,
        operation,
    ):
        order.append("applier")

        return original_apply(
            world,
            operation,
        )

    applier.apply = apply

    world_service = WorldService(
        applier=applier,
    )

    service = TurnResolutionService(
        dm_service=dm,
        extractor=extractor,
        world_service=world_service,
    )

    service.resolve_turn(
        make_turn_context(),
        "Conozco a Aldric.",
    )

    assert order == ["proposer", "applier", "dm"]

def test_turn_resolution_uses_world_from_turn_context():

    world = make_world()

    service, dm, extractor, _ = make_service()

    context = TurnContext(
        campaign=CampaignState(
            campaign_id=1,
            name="Test Campaign",
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
        world=world,
    )

    service.resolve_turn(
        context,
        "Exploro.",
    )

    assert dm.calls == [
        (
            "generate",
            context,
            "Exploro.",
        )
    ]

    assert extractor.received_context is context

def test_turn_resolution_passes_complete_turn_context_to_dm():
    world = make_world()

    service, dm, _, _ = make_service()

    context = TurnContext(
        campaign=CampaignState(
            campaign_id=1,
            name="Test Campaign",
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
        world=world,
    )

    service.resolve_turn(
        context,
        "Exploro.",
    )

    assert len(dm.calls) == 1

    (
        call_name,
        received_context,
        received_input,
    ) = dm.calls[0]

    assert call_name == "generate"
    assert received_context is context
    assert received_input == "Exploro."

def test_world_state_compatibility_creates_typed_turn_context():
    service, dm, *_ = make_service()

    world = WorldState()

    service.resolve_turn(
        world,
        "Exploro.",
    )

    assert len(dm.calls) == 1

    _, context, player_input = dm.calls[0]

    assert isinstance(
        context,
        TurnContext,
    )

    assert isinstance(
        context.campaign,
        CampaignState,
    )

    assert context.current_session is None
    assert context.active_character is None
    assert context.world is world
    assert player_input == "Exploro."


def test_turn_resolution_separates_world_and_character_operations(
    monkeypatch,
):
    from operations.character_operations import (
        ChangeCharacterHpOperation,
    )
    from operations.world_operations import (
        WorldOperation,
    )
    from services.llm_world import (
        LLMWorldExtractor,
    )

    world_operation = WorldOperation()

    character_operation = ChangeCharacterHpOperation(
        entity_id=1,
        amount=-4,
    )

    service, dm, _, _ = make_service()

    extractor = LLMWorldExtractor.__new__(
        LLMWorldExtractor
    )

    def fake_propose(*args, **kwargs):
        return [
            world_operation,
            character_operation,
        ]

    monkeypatch.setattr(
        extractor,
        "propose",
        fake_extract,
    )

    service = TurnResolutionService(
        dm_service=dm,
        extractor=extractor,
        world_service=WorldService(
            applier=RecordingApplier(),
        ),
    )

    result = service.resolve_turn(
        turn_context=make_turn_context(),
        player_input="Ataco al enemigo.",
    )

    assert result.operations == (
        world_operation,
    )

    assert result.character_operations == (
        character_operation,
    )

    assert result.operation_count == 2

def test_turn_resolution_uses_turn_context():

    world = make_world()

    service, dm, extractor, _ = make_service()

    context = TurnContext(
        campaign=CampaignState(
            campaign_id=1,
            name="Test Campaign",
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
        world=world,
    )

    service.resolve_turn(
        context,
        "Exploro.",
    )

    assert dm.calls == [
        (
            "generate",
            context,
            "Exploro.",
        )
    ]

    assert extractor.received_context is context

def test_resolve_turn_preserves_operation_reference():
    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
        description="Mercader.",
        notes="",
        active=True,
    )

    referenced_operation = ReferencedOperation(
        operation=operation,
        ref="aldric",
    )

    dm = RecordingDMService()

    extractor = RecordingExtractor(
        operations=[
            referenced_operation,
        ],
    )

    applier = RecordingApplier()

    world_service = WorldService(
        applier=applier,
    )

    service = TurnResolutionService(
        dm_service=dm,
        extractor=extractor,
        world_service=world_service,
    )

    context = make_turn_context()

    world_service.world = context.world

    result = service.resolve_turn(
        context,
        "Conozco a Aldric.",
    )

    assert result.operation_results

    assert (
        result.operation_results[0].success
        is True
    )

    assert len(
        world_service.world.entities
    ) == 1

    entity_id = next(
        iter(
            world_service.world.entities
        )
    )

    assert (
        world_service.world.entities[
            entity_id
        ].name
        == "Aldric"
    )

def test_referenced_world_operation_keeps_reference():
    referenced_operation = ReferencedOperation(
        operation=CreateEntityOperation(
            name="Aldren",
            entity_type="npc",
        ),
        ref="npc",
    )

    normalized_operations = (
        referenced_operation,
    )

    world_operations = tuple(
        operation
        for operation in normalized_operations
        if isinstance(
            operation.operation
            if isinstance(
                operation,
                ReferencedOperation,
            )
            else operation,
            WorldOperation,
        )
    )

    assert len(world_operations) == 1

    operation = world_operations[0]

    assert isinstance(
        operation,
        ReferencedOperation,
    )

    assert operation.ref == "npc"

    assert isinstance(
        operation.operation,
        CreateEntityOperation,
    )

def test_referenced_operation_survives_turn_resolution():
    operations = [
        ReferencedOperation(
            operation=CreateEntityOperation(
                name="Aldren",
                entity_type="npc",
            ),
            ref="npc",
        ),
        UpdateEntityOperation(
            entity_id=OperationReference("npc"),
            description="Guerrero veterano.",
        ),
    ]

    normalized_operations = tuple(
        operations
    )

    world_operations = tuple(
        operation
        for operation in normalized_operations
        if isinstance(
            operation.operation
            if isinstance(
                operation,
                ReferencedOperation,
            )
            else operation,
            WorldOperation,
        )
    )

    assert len(world_operations) == 2

    first = world_operations[0]

    assert isinstance(
        first,
        ReferencedOperation,
    )

    assert first.ref == "npc"

    assert isinstance(
        first.operation,
        CreateEntityOperation,
    )

    second = world_operations[1]

    assert isinstance(
        second,
        UpdateEntityOperation,
    )

    assert isinstance(
        second.entity_id,
        OperationReference,
    )

    assert second.entity_id.name == "npc"

def test_resolve_turn_preserves_global_operation_order(
    monkeypatch,
):
    operations = [
        CreateEntityOperation(
            name="Aldren",
            entity_type="npc",
        ),
        ChangeCharacterHpOperation(
            entity_id=1,
            amount=-2,
        ),
        UpdateEntityOperation(
            entity_id=1,
            notes="Herido durante el combate.",
        ),
    ]

    dm = RecordingDMService()

    extractor = RecordingExtractor(
        operations=operations,
    )

    world_service = WorldService()

    service = TurnResolutionService(
        dm_service=dm,
        extractor=extractor,
        world_service=world_service,
    )

    context = make_turn_context()

    received_world_operations = None
    received_character_operations = None

    def fake_apply_turn_operations(
        world_operations,
        character_operations,
        *,
        campaign_id,
        conn=None,
        ordered_operations=None,
    ):
        nonlocal received_world_operations
        nonlocal received_character_operations

        received_world_operations = tuple(
            world_operations
        )

        received_character_operations = tuple(
            character_operations
        )

        assert ordered_operations is not None

        received_operations = tuple(
            ordered_operations
        )

        assert received_operations == tuple(
            operations
        )

        assert campaign_id == 1

        return ()

    monkeypatch.setattr(
        world_service,
        "apply_turn_operations",
        fake_apply_turn_operations,
    )

    service.resolve_turn(
        context,
        "Ataco a Aldren.",
    )

# ============================================================
# PLAN / APPLY SEPARATION
# ============================================================


def test_prepare_turn_generates_plan_without_mutating_world():
    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
        description="Mercader.",
        notes="",
        active=True,
    )
    extractor = RecordingExtractor(operations=[operation])
    service, dm, _, applier = make_service(extractor=extractor)
    context = make_turn_context()
    original_world = context.world

    plan = service.prepare_turn(context, "Conozco a Aldric.")

    assert plan.player_input == "Conozco a Aldric."
    assert plan.narrative == ""
    assert plan.world_operations == (operation,)
    assert context.world is original_world
    assert context.world.entities == {}
    assert applier.calls == []
    assert dm.calls == []


def test_apply_plan_applies_only_after_plan_is_prepared():
    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
        description="Mercader.",
        notes="",
        active=True,
    )
    extractor = RecordingExtractor(operations=[operation])
    service, _, _, applier = make_service(extractor=extractor)
    context = make_turn_context()

    plan = service.prepare_turn(context, "Conozco a Aldric.")
    assert context.world.entities == {}
    assert applier.calls == []

    result = service.apply_plan(context, plan)

    assert result.player_input == "Conozco a Aldric."
    assert result.operation_count == 1
    assert result.all_operations_succeeded is True
    assert len(applier.calls) == 1
    assert service.world_service.world.entities[1].name == "Aldric"


def test_prepare_turn_can_propose_consequences_without_generating_narrative():
    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
        description="Tabernero.",
        notes="",
        active=True,
    )
    extractor = RecordingExtractor(operations=[operation])
    service, dm, _, _ = make_service(extractor=extractor)

    plan = service.prepare_turn(
        make_turn_context(),
        "Busco al tabernero Aldric.",
    )

    assert plan.narrative == ""
    assert plan.ordered_operations == (operation,)
    assert extractor.calls == [
        ("propose", "Busco al tabernero Aldric.")
    ]
    assert dm.calls == []


def test_intent_proposals_cannot_change_character_hp_directly():
    extractor = RecordingExtractor(
        operations=[ChangeCharacterHpOperation(entity_id=20, amount=-5)]
    )
    service, *_ = make_service(extractor=extractor)

    with pytest.raises(
        TurnResolutionServiceError,
        match="deterministic mechanics",
    ):
        service.prepare_turn(
            make_turn_context(),
            "Ataco al goblin.",
        )


def test_prepare_turn_builds_bounded_context_for_structured_proposal():
    world = WorldState(
        entities={
            20: Entity(id=20, name="Fungoso", entity_type="character"),
            21: Entity(id=21, name="Mara", entity_type="npc"),
            22: Entity(id=22, name="Aldric", entity_type="npc"),
            23: Entity(id=23, name="Mercado", entity_type="location"),
        }
    )
    context = make_turn_context(world=world)
    context.campaign.current_location_id = 23
    service, _dm, extractor, _applier = make_service(
        context_builder=ContextBuilder(),
        proposal_context_max_tokens=500,
    )

    service.prepare_turn(
        context,
        "Quiero hablar con Mara.",
    )

    projection = extractor.received_projection
    assert projection is not None
    assert set(projection.world.entities) == {20, 21, 23}
    assert projection.diagnostics.estimated_tokens <= 500
