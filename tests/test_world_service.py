import pytest

import database
from database import init_db
from models.entity import Entity
from models.operation_result import (
    OperationResult,
    OperationStatus,
)
from models.world_state import WorldState
from operations.operation_reference import OperationReference
from operations.referenced_operation import ReferencedOperation
from operations.world_operations import (
    CreateEntityOperation,
    CreateItemInstanceOperation,
    CreateItemOperation,
    CreateRelationOperation,
    CreateResourceOperation,
    GainResourceOperation,
    SpendResourceOperation,
    TransferResourceOperation,
    UpdateEntityOperation,
)
from repositories.world_repository import WorldRepository
from services.world_service import WorldService


class FakeRepository:

    def __init__(self, world=None):
        self.world = world or WorldState()
        self.saved_world = None
        self.load_calls = 0
        self.save_calls = 0

    def load_world(self, **kwargs):
        self.load_calls += 1
        return self.world

    def save_world(self, world, **kwargs):
        self.save_calls += 1
        self.saved_world = world


class FakeApplier:

    def __init__(self):
        self.called = False
        self.world = None
        self.operation = None

    def apply(self, world, operation, campaign_id):
        self.called = True
        self.world = world
        self.operation = operation

        return OperationResult(
            status=OperationStatus.SUCCESS,
            message="fake success",
            operation=operation,
        )

def test_load_sets_current_world():

    world = WorldState(
        entities={
            1: Entity(
                id=1,
                name="Fungoso",
                entity_type="character",
            )
        }
    )

    repository = FakeRepository(world)

    service = WorldService(
        repository=repository,
        applier=FakeApplier(),
    )

    loaded = service.load()

    assert loaded is world
    assert service.world is world
    assert repository.load_calls == 1

def test_save_persists_current_world():

    repository = FakeRepository()

    service = WorldService(
        repository=repository,
        applier=FakeApplier(),
    )

    service.world.entities[1] = Entity(
        id=1,
        name="Fungoso",
        entity_type="character",
    )

    service.save()

    assert repository.save_calls == 1
    assert repository.saved_world is service.world

def test_apply_delegates_to_applier():

    repository = FakeRepository()
    applier = FakeApplier()

    service = WorldService(
        repository=repository,
        applier=applier,
    )

    operation = object()

    result = service.apply(operation)

    assert result.status == OperationStatus.SUCCESS
    assert result.operation is operation

    assert applier.called is True
    assert applier.world is service.world
    assert applier.operation is operation

def test_apply_does_not_save():

    repository = FakeRepository()
    applier = FakeApplier()

    service = WorldService(
        repository=repository,
        applier=applier,
    )

    service.apply(object())

    assert repository.save_calls == 0


def test_get_world_returns_current_world():

    service = WorldService(
        repository=FakeRepository(),
        applier=FakeApplier(),
    )

    assert service.get_world() is service.world

def test_load_replaces_current_world():

    old_world = WorldState()

    new_world = WorldState(
        entities={
            1: Entity(
                id=1,
                name="Fungoso",
                entity_type="character",
            )
        }
    )

    repository = FakeRepository(new_world)

    service = WorldService(
        repository=repository,
        applier=FakeApplier(),
    )

    service.world = old_world

    loaded = service.load()

    assert loaded is new_world
    assert service.world is new_world
    assert service.world is not old_world


def test_load_replaces_current_world_completely(tmp_path):

    original_db_path = database.DB_PATH
    database.DB_PATH = tmp_path / "test_campaign.db"

    try:
        init_db()

        repository = WorldRepository()

        # --------------------------------------------------------
        # Estado que realmente existe en SQLite
        # --------------------------------------------------------

        persisted_entity = Entity(
            id=1,
            name="Goblin",
            entity_type="creature",
        )

        persisted_world = WorldState(
            entities={
                1: persisted_entity,
            }
        )

        repository.save_world(persisted_world, campaign_id=1)

        # --------------------------------------------------------
        # Servicio con estado diferente en memoria
        # --------------------------------------------------------

        service = WorldService(
            repository=repository,
        )

        stale_entity = Entity(
            id=99,
            name="Entidad vieja",
            entity_type="character",
        )

        service.world = WorldState(
            entities={
                99: stale_entity,
            }
        )

        # --------------------------------------------------------
        # LOAD
        # --------------------------------------------------------

        loaded = service.load()

        # --------------------------------------------------------
        # Debe coincidir exactamente con SQLite
        # --------------------------------------------------------

        assert loaded == persisted_world
        assert service.world == persisted_world

        # La entidad antigua NO puede sobrevivir.
        assert 99 not in service.world.entities

        # La persistida sí.
        assert 1 in service.world.entities

    finally:
        database.DB_PATH = original_db_path

def test_apply_returns_success_result_for_successful_operation():

    service = WorldService()

    operation = CreateEntityOperation(
        name="Fungoso",
        entity_type="character",
    )

    result = service.apply(operation)

    assert result.success is True
    assert result.status == OperationStatus.SUCCESS
    assert result.operation == operation

def test_apply_returns_failure_result_for_invalid_operation():

    service = WorldService()

    operation = CreateEntityOperation(
        name="",
        entity_type="character",
    )

    result = service.apply(operation)

    assert result.success is False
    assert result.status != OperationStatus.SUCCESS

def test_apply_operations_applies_all_operations_without_saving():
    repository = FakeRepository()
    applier = FakeApplier()

    service = WorldService(
        repository=repository,
        applier=applier,
    )

    operations = [
        CreateEntityOperation(
            name="Fungoso",
            entity_type="character",
        ),
        CreateEntityOperation(
            name="Goblin",
            entity_type="creature",
        ),
    ]

    result = service.apply_operations(
        operations
    )

    assert result.success is True
    assert len(result.results) == 2

    assert repository.save_calls == 0

    assert service.world is result.world

def test_apply_operations_rolls_back_when_one_operation_fails(
    monkeypatch,
):
    service = WorldService()

    original_world = service.world

    operation_1 = CreateEntityOperation(
        name="Fungoso",
        entity_type="character",
    )

    operation_2 = CreateEntityOperation(
        name="Goblin",
        entity_type="creature",
    )

    call_count = 0

    def fake_apply(operation):
        nonlocal call_count

        call_count += 1

        if call_count == 1:
            service.world.entities[1] = Entity(
                id=1,
                name="Fungoso",
                entity_type="character",
            )

            return OperationResult(
                status=OperationStatus.SUCCESS,
                message="Success",
                operation=operation,
            )

        return OperationResult(
            status=OperationStatus.INVALID,
            message="Operation failed",
            operation=operation,
        )

    monkeypatch.setattr(
        service,
        "apply",
        fake_apply,
    )

    result = service.apply_operations(
        [
            operation_1,
            operation_2,
        ]
    )

    assert result.success is False

    assert service.world is original_world
    assert service.world.entities == {}

def test_apply_operations_restores_original_world_when_apply_raises(
    monkeypatch,
):
    service = WorldService()

    original_world = service.world

    operation = CreateEntityOperation(
        name="Fungoso",
        entity_type="character",
    )

    def failing_apply(operation):
        service.world.entities[1] = Entity(
            id=1,
            name="Fungoso",
            entity_type="character",
        )

        raise RuntimeError("Unexpected failure")

    monkeypatch.setattr(
        service,
        "apply",
        failing_apply,
    )

    try:
        service.apply_operations(
            [operation]
        )
    except RuntimeError:
        pass

    assert service.world is original_world
    assert service.world.entities == {}

def test_apply_operations_and_save_persists_successful_operations(
    monkeypatch,
):
    service = WorldService()

    operation = CreateEntityOperation(
        name="Fungoso",
        entity_type="character",
    )

    original_save = service.repository.save_world
    save_calls = []

    def spy_save_world(
        world,
        *,
        campaign_id,
        conn=None,
    ):
        save_calls.append(world)
        return original_save(
            world,
            campaign_id=campaign_id,
            conn=conn,
        )

    monkeypatch.setattr(
        service.repository,
        "save_world",
        spy_save_world,
    )

    result = service.apply_operations_and_save(
        [operation]
    )

    assert result.success is True
    assert len(save_calls) == 1
    assert save_calls[0] is service.get_world()

def test_apply_operations_and_save_restores_original_world_when_save_fails(
    monkeypatch,
):
    service = WorldService()

    operation = CreateEntityOperation(
        name="Fungoso",
        entity_type="character",
    )

    original_world = service.get_world()

    def failing_save_world(
        world,
        *,
        campaign_id,
        conn=None,
    ):
        raise RuntimeError("database failed")

    monkeypatch.setattr(
        service.repository,
        "save_world",
        failing_save_world,
    )

    with pytest.raises(
        RuntimeError,
        match="database failed",
    ):
        service.apply_operations_and_save(
            [operation]
        )

    assert service.get_world() is original_world

def test_apply_operations_and_save_does_not_save_when_operation_fails(
    monkeypatch,
):
    service = WorldService()

    operation = CreateEntityOperation(
        name="Fungoso",
        entity_type="character",
    )

    original_world = service.get_world()

    save_called = False

    def spy_save_world(world):
        nonlocal save_called
        save_called = True

    def failing_apply(
        world,
        operation,
    ):
        return OperationResult(
            status=OperationStatus.INVALID,
            message="operation failed",
            operation=operation,
        )

    monkeypatch.setattr(
        service.repository,
        "save_world",
        spy_save_world,
    )

    monkeypatch.setattr(
        service.applier,
        "apply",
        failing_apply,
    )

    result = service.apply_operations_and_save(
        [operation]
    )

    assert result.success is False
    assert save_called is False
    assert service.get_world() is original_world
    assert result.changed is False
    assert len(result.results) == 1

def test_apply_operations_and_save_does_not_save_when_there_are_no_operations(
    monkeypatch,
):
    service = WorldService()

    save_called = False

    def spy_save_world(world):
        nonlocal save_called
        save_called = True

    monkeypatch.setattr(
        service.repository,
        "save_world",
        spy_save_world,
    )

    result = service.apply_operations_and_save(
        []
    )

    assert result.success is True
    assert result.changed is False
    assert result.results == ()
    assert save_called is False

def test_apply_operations_and_save_marks_world_as_changed(
    monkeypatch,
):
    service = WorldService()

    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="character",
    )

    save_calls = []

    def spy_save_world(
        world,
        *,
        campaign_id,
        conn=None,
    ):
        save_calls.append(world)

    monkeypatch.setattr(
        service.repository,
        "save_world",
        spy_save_world,
    )

    result = service.apply_operations_and_save(
        [operation]
    )

    assert result.success is True
    assert result.changed is True
    assert len(result.results) == 1
    assert result.results[0].success is True

    assert len(save_calls) == 1

def test_apply_turn_operations_saves_world_operation_from_ordered_operations(
    monkeypatch,
):
    service = WorldService()

    operation = CreateEntityOperation(
        name="OrderedEntity",
        entity_type="character",
    )

    save_calls = []

    def spy_save_world(
        world,
        *,
        campaign_id,
        conn=None,
    ):
        save_calls.append(
            (
                world,
                conn,
            )
        )

    monkeypatch.setattr(
        service.repository,
        "save_world",
        spy_save_world,
    )

    result = service.apply_turn_operations(
        world_operations=(),
        character_operations=(),
        ordered_operations=(
            operation,
        ),
        campaign_id=1,
    )

    assert len(result) == 1
    assert result[0].success is True

    assert len(save_calls) == 1
    assert save_calls[0][0] == service.world

    assert len(service.world.entities) == 1

    entity = next(
        iter(service.world.entities.values())
    )

    assert entity.name == "OrderedEntity"
    assert entity.entity_type == "character"

def test_apply_turn_operations_rolls_back_when_character_operation_fails(
    monkeypatch,
):
    from services.character_applier import (
        CharacterApplierError,
    )

    class RecordingConnection:
        def __init__(self):
            self.committed = False
            self.rolled_back = False

    connection = RecordingConnection()

    class ConnectionContext:

        def __enter__(self):
            return connection

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            if exc_type is None:
                connection.committed = True
            else:
                connection.rolled_back = True

            return False

    monkeypatch.setattr(
        "services.world_service.get_conn",
        lambda: ConnectionContext(),
    )

    class FailingCharacterApplier:

        def apply(
            self,
            operation,
            *,
            campaign_id,
            conn=None,
        ):
            raise CharacterApplierError(
                "character failure"
            )

    service = WorldService(
        character_applier=FailingCharacterApplier(),
    )

    original_world = service.world

    with pytest.raises(
        CharacterApplierError,
        match="character failure",
    ):
        service.apply_turn_operations(
            world_operations=(),
            character_operations=(object(),),
            campaign_id=1,
        )

    assert service.world is original_world
    assert connection.committed is False
    assert connection.rolled_back is True

def test_apply_turn_operations_rolls_back_when_world_operation_fails(
    monkeypatch,
):
    class RecordingConnection:
        def __init__(self):
            self.committed = False
            self.rolled_back = False

    connection = RecordingConnection()

    class ConnectionContext:

        def __enter__(self):
            return connection

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            if exc_type is None:
                connection.committed = True
            else:
                connection.rolled_back = True

            return False

    monkeypatch.setattr(
        "services.world_service.get_conn",
        lambda: ConnectionContext(),
    )

    service = WorldService()

    original_world = service.world

    class FailingWorldApplier:

        def apply(
            self,
            world,
            operation,
            campaign_id,
        ):
            return OperationResult(
                status=OperationStatus.INVALID,
                message="world operation failed",
                operation=operation,
            )

    service.applier = FailingWorldApplier()

    result = service.apply_turn_operations(
        world_operations=(object(),),
        character_operations=(),
        campaign_id=1,
    )

    assert len(result) == 1
    assert result[0].success is False
    assert result[0].status == OperationStatus.INVALID

    assert service.world is original_world

    assert connection.committed is False
    assert connection.rolled_back is True

def test_apply_turn_operations_rolls_back_when_character_operation_returns_failure(
    isolated_database,
):
    from models.operation_result import (
        OperationResult,
        OperationStatus,
    )
    from operations.character_operations import (
        ChangeCharacterHpOperation,
    )
    from services.world_service import (
        WorldService,
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
                message="character operation failed",
                operation=operation,
            )

    service = WorldService(
        character_applier=FailingCharacterApplier(),
    )

    original_world = service.world

    operation = ChangeCharacterHpOperation(
        entity_id=1,
        amount=-5,
    )

    results = service.apply_turn_operations(
        world_operations=[],
        character_operations=[
            operation,
        ],
        campaign_id=1,
    )

    assert len(results) == 1

    assert results[0].success is False

    assert service.world is original_world

def test_apply_operations_resolves_generated_item_reference():
    service = WorldService()

    result = service.apply_operations(
        [
            ReferencedOperation(
                operation=CreateItemOperation(
                    name="Espada oxidada",
                ),
                ref="sword",
            ),
            CreateItemInstanceOperation(
                item_id=OperationReference(
                    "sword"
                ),
                owner_id=None,
            ),
        ]
    )

    assert result.success is True
    assert result.changed is True
    assert len(result.results) == 2

    assert len(service.world.items) == 1
    assert len(service.world.item_instances) == 1

    item = next(
        iter(service.world.items.values())
    )

    instance = next(
        iter(
            service.world.item_instances.values()
        )
    )

    assert instance.item_id == item.id

def test_apply_operations_rejects_unknown_operation_reference():
    service = WorldService()

    with pytest.raises(
        ValueError,
        match=r"Unknown operation reference: \$missing",
    ):
        service.apply_operations(
            [
                CreateItemInstanceOperation(
                    item_id=OperationReference(
                        "missing"
                    ),
                ),
            ]
        )

    assert service.world.items == {}
    assert service.world.item_instances == {}

def test_apply_turn_operations_resolves_generated_character_reference(
    monkeypatch,
):
    from models.operation_result import (
        OperationResult,
        OperationStatus,
    )
    from operations.character_operations import (
        ChangeCharacterHpOperation,
    )

    class RecordingCharacterApplier:
        def __init__(self):
            self.operations = []

        def apply(
            self,
            operation,
            *,
            campaign_id,
            conn=None,
        ):
            self.operations.append(operation)

            return OperationResult(
                status=OperationStatus.SUCCESS,
                message="Character HP changed",
                operation=operation,
                data={
                    "entity_id": operation.entity_id,
                    "current_hp": 8,
                },
            )

    character_applier = RecordingCharacterApplier()

    service = WorldService(
        character_applier=character_applier,
    )

    create_operation = CreateEntityOperation(
        name="Aldric",
        entity_type="character",
    )

    referenced_create = ReferencedOperation(
        operation=create_operation,
        ref="aldric",
    )

    hp_operation = ChangeCharacterHpOperation(
        entity_id=OperationReference("aldric"),
        amount=-2,
    )

    result = service.apply_turn_operations(
        world_operations=[
            referenced_create,
        ],
        character_operations=[
            hp_operation,
        ],
        campaign_id=1,
    )

    assert len(result) == 2

    assert result[0].success is True
    assert result[1].success is True

    assert len(character_applier.operations) == 1

    applied_operation = (
        character_applier.operations[0]
    )

    assert applied_operation.entity_id == 1
    assert applied_operation.amount == -2

def test_apply_operations_rejects_empty_operation_reference():
    service = WorldService()

    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
        description="Mercader.",
        notes="",
        active=True,
    )

    referenced_operation = ReferencedOperation(
        operation=operation,
        ref="",
    )

    with pytest.raises(
        ValueError,
        match="Operation reference must not be empty",
    ):
        service.apply_operations(
            [
                referenced_operation,
            ]
        )

    assert service.world.entities == {}


def test_apply_operations_rejects_whitespace_operation_reference():
    service = WorldService()

    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
        description="Mercader.",
        notes="",
        active=True,
    )

    referenced_operation = ReferencedOperation(
        operation=operation,
        ref="   ",
    )

    with pytest.raises(
        ValueError,
        match="Operation reference must not be empty",
    ):
        service.apply_operations(
            [
                referenced_operation,
            ]
        )

    assert service.world.entities == {}


def test_apply_operations_rejects_duplicate_operation_reference():
    service = WorldService()

    first_operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
        description="Primer mercader.",
        notes="",
        active=True,
    )

    second_operation = CreateEntityOperation(
        name="Brann",
        entity_type="npc",
        description="Segundo mercader.",
        notes="",
        active=True,
    )

    with pytest.raises(
        ValueError,
        match="Operation reference 'merchant' is already defined",
    ):
        service.apply_operations(
            [
                ReferencedOperation(
                    operation=first_operation,
                    ref="merchant",
                ),
                ReferencedOperation(
                    operation=second_operation,
                    ref="merchant",
                ),
            ]
        )

    assert service.world.entities == {}

def test_apply_operations_accepts_no_change_as_success_without_marking_world_changed():
    from models.entity import Entity
    from models.operation_result import OperationStatus
    from operations.world_operations import UpdateEntityOperation

    service = WorldService()

    service.world.entities[1] = Entity(
        id=1,
        name="Aldric",
        entity_type="npc",
        description="Mercader.",
        notes="",
        active=True,
    )

    result = service.apply_operations(
        [
            UpdateEntityOperation(
                entity_id=1,
                name="Aldric",
            )
        ]
    )

    assert result.success is True
    assert result.changed is False
    assert result.results[0].status == OperationStatus.NO_CHANGE

    assert service.world.entities[1].name == "Aldric"

def test_apply_operations_marks_world_changed_when_operation_changes_state():
    from models.entity import Entity
    from operations.world_operations import UpdateEntityOperation

    service = WorldService()

    service.world.entities[1] = Entity(
        id=1,
        name="Aldric",
        entity_type="npc",
        description="Mercader.",
        notes="",
        active=True,
    )

    result = service.apply_operations(
        [
            UpdateEntityOperation(
                entity_id=1,
                name="Aldric el Mercader",
            )
        ]
    )

    assert result.success is True
    assert result.changed is True
    assert result.results[0].changed is True

    assert (
        service.world.entities[1].name
        == "Aldric el Mercader"
    )

def test_update_entity_rejects_unknown_operation_reference():
    service = WorldService()

    operation = UpdateEntityOperation(
        entity_id=OperationReference("missing_entity"),
        description="Should never be applied",
    )

    with pytest.raises(
        ValueError,
        match=r"Unknown operation reference: \$missing_entity",
    ):
        service.apply_operations(
            [operation]
        )

def test_create_item_instance_resolves_references_end_to_end():
    service = WorldService()

    results = service.apply_operations(
        [
            ReferencedOperation(
                operation=CreateItemOperation(
                    name="Espada de hierro",
                ),
                ref="sword",
            ),
            ReferencedOperation(
                operation=CreateEntityOperation(
                    name="Aldren",
                    entity_type="npc",
                ),
                ref="npc",
            ),
            ReferencedOperation(
                operation=CreateEntityOperation(
                    name="La cripta",
                    entity_type="location",
                ),
                ref="location",
            ),
            ReferencedOperation(
                operation=CreateItemInstanceOperation(
                    item_id=OperationReference("sword"),
                    instance_number=1,
                    owner_id=OperationReference("npc"),
                    location_id=OperationReference("location"),
                    condition="intacto",
                ),
                ref="sword_instance",
            ),
        ]
    )

    assert results.success
    assert results.changed

    world = service.get_world()

    item = next(
        item
        for item in world.items.values()
        if item.name == "Espada de hierro"
    )

    npc = next(
        entity
        for entity in world.entities.values()
        if entity.name == "Aldren"
    )

    location = next(
        entity
        for entity in world.entities.values()
        if entity.name == "La cripta"
    )

    instance = next(
        instance
        for instance in world.item_instances.values()
        if instance.item_id == item.id
    )

    assert instance.item_id == item.id
    assert instance.owner_id == npc.id
    assert instance.location_id == location.id
    assert instance.condition == "intacto"

def test_resource_operations_resolve_references_end_to_end():
    service = WorldService()

    result = service.apply_operations(
        [
            ReferencedOperation(
                operation=CreateResourceOperation(
                    name="Oro",
                    resource_type="currency",
                    unit="gp",
                ),
                ref="gold",
            ),
            ReferencedOperation(
                operation=CreateEntityOperation(
                    name="Aldren",
                    entity_type="npc",
                ),
                ref="npc1",
            ),
            ReferencedOperation(
                operation=CreateEntityOperation(
                    name="Neria",
                    entity_type="npc",
                ),
                ref="npc2",
            ),
            GainResourceOperation(
                resource_id=OperationReference("gold"),
                owner_id=OperationReference("npc1"),
                amount=100,
            ),
            TransferResourceOperation(
                resource_id=OperationReference("gold"),
                subject_id=OperationReference("npc1"),
                target_id=OperationReference("npc2"),
                amount=40,
            ),
            SpendResourceOperation(
                resource_id=OperationReference("gold"),
                owner_id=OperationReference("npc2"),
                amount=10,
            ),
        ]
    )

    assert result.success is True
    assert result.changed is True

    world = service.get_world()

    gold = next(
        resource
        for resource in world.resources.values()
        if resource.name == "Oro"
    )

    aldren = next(
        entity
        for entity in world.entities.values()
        if entity.name == "Aldren"
    )

    neria = next(
        entity
        for entity in world.entities.values()
        if entity.name == "Neria"
    )

    aldren_balance = next(
        balance
        for balance in world.resource_balances.values()
        if (
            balance.resource_id == gold.id
            and balance.owner_id == aldren.id
        )
    )

    neria_balance = next(
        balance
        for balance in world.resource_balances.values()
        if (
            balance.resource_id == gold.id
            and balance.owner_id == neria.id
        )
    )

    assert aldren_balance.amount == 60
    assert neria_balance.amount == 30

def test_create_relation_resolves_entity_references_end_to_end():
    service = WorldService()

    result = service.apply_operations(
        [
            ReferencedOperation(
                operation=CreateEntityOperation(
                    name="Aldren",
                    entity_type="npc",
                ),
                ref="npc",
            ),
            ReferencedOperation(
                operation=CreateEntityOperation(
                    name="Guardia",
                    entity_type="faction",
                ),
                ref="faction",
            ),
            CreateRelationOperation(
                relation_id="aldren_guardia",
                subject_id=OperationReference("npc"),
                relation_type="miembro_de",
                target_id=OperationReference("faction"),
            ),
        ]
    )

    assert result.success is True
    assert result.changed is True

    world = service.get_world()

    aldren = next(
        entity
        for entity in world.entities.values()
        if entity.name == "Aldren"
    )

    guardia = next(
        entity
        for entity in world.entities.values()
        if entity.name == "Guardia"
    )

    relation = world.relations["aldren_guardia"]

    assert relation.subject_id == aldren.id
    assert relation.target_id == guardia.id
    assert relation.relation_type == "miembro_de"

def test_update_entity_resolves_reference_end_to_end():
    service = WorldService()

    result = service.apply_operations(
        [
            ReferencedOperation(
                operation=CreateEntityOperation(
                    name="Aldren",
                    entity_type="npc",
                    description="Un guerrero.",
                ),
                ref="npc",
            ),
            UpdateEntityOperation(
                entity_id=OperationReference("npc"),
                description="Un guerrero veterano.",
                notes="Conoce los caminos de Vorder's Hold.",
            ),
        ]
    )

    assert result.success is True
    assert result.changed is True

    world = service.get_world()

    entity = next(
        entity
        for entity in world.entities.values()
        if entity.name == "Aldren"
    )

    assert entity.entity_type == "npc"
    assert entity.description == "Un guerrero veterano."
    assert entity.notes == "Conoce los caminos de Vorder's Hold."

def test_operation_reference_requires_generated_id():
    service = WorldService()

    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
    )

    result = OperationResult(
        status=OperationStatus.SUCCESS,
        message="Success",
        operation=operation,
        data=None,
    )

    with pytest.raises(
        ValueError,
        match=(
            r"Operation reference 'npc' did not "
            r"produce exactly one generated ID."
        ),
    ):
        service._register_operation_reference(
            "npc",
            result,
            {},
            service.world,
        )

def test_operation_reference_uses_generated_id_from_result_data():
    service = WorldService()

    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
    )

    result = OperationResult(
        status=OperationStatus.SUCCESS,
        message="Success",
        operation=operation,
        data={
            "entity_id": 42,
        },
    )

    references = {}

    service._register_operation_reference(
        "npc",
        result,
        references,
        service.world,
    )

    assert references == {
        "npc": 42,
    }

def test_apply_turn_operations_rolls_back_character_database_changes_on_failure(
    isolated_database,
    monkeypatch,
):
    from models.schemas import CharacterCreate
    from operations.character_operations import (
        ChangeCharacterHpOperation,
    )
    from repositories.campaign_repository import (
        CampaignRepository,
    )
    from repositories.character_repository import (
        CharacterRepository,
    )
    from repositories.entity_repository import (
        EntityRepository,
    )
    from services.character_creation_service import (
        CharacterCreationService,
    )

    # --------------------------------------------------------
    # Crear un personaje real en SQLite
    # --------------------------------------------------------

    character_creation_service = CharacterCreationService(
        campaign_repository=CampaignRepository(),
        entity_repository=EntityRepository(),
        character_repository=CharacterRepository(),
    )

    character = character_creation_service.create_character(
        campaign_id=1,
        data=CharacterCreate(
            name="Rollback Test Character",
            class_name="Fighter",
            level=1,
            max_hp=20,
            current_hp=20,
            armor_class=16,
            strength=16,
            dexterity=12,
            constitution=14,
            intelligence=10,
            wisdom=10,
            charisma=10,
            proficiency_bonus=2,
        ),
        activate=False,
    )

    character_id = character.entity_id

    character_repository = CharacterRepository()

    original_character = (
        character_repository.get_character(
            character_id,
            campaign_id=1,
        )
    )

    assert original_character is not None
    assert original_character.current_hp == 20

    # --------------------------------------------------------
    # El save REAL se ejecuta primero.
    #
    # Después provocamos el fallo.
    #
    # Esto garantiza que SQLite ya ha recibido el UPDATE
    # cuando la operación termina en failure.
    # --------------------------------------------------------

    original_save_character = (
        CharacterRepository.save_character
    )

    def save_character_then_fail(
        repository_self,
        character,
        *,
        campaign_id,
        conn=None,
    ):
        original_save_character(
            repository_self,
            character,
            campaign_id=campaign_id,
            conn=conn,
        )

        raise RuntimeError(
            "forced failure after database write"
        )

    monkeypatch.setattr(
        CharacterRepository,
        "save_character",
        save_character_then_fail,
    )

    # --------------------------------------------------------
    # WorldService utiliza el CharacterApplier real,
    # CharacterService real y CharacterRepository real.
    # --------------------------------------------------------

    service = WorldService()

    operation = ChangeCharacterHpOperation(
        entity_id=character_id,
        amount=-5,
    )

    # --------------------------------------------------------
    # La operación debe terminar como failure.
    # CharacterService convierte el error de persistencia
    # en CharacterServiceError y CharacterApplier lo convierte
    # en OperationResult fallido.
    # --------------------------------------------------------

    results = service.apply_turn_operations(
        world_operations=[],
        character_operations=[
            operation,
        ],
        campaign_id=1,
    )

    assert len(results) == 1
    assert results[0].success is False

    # --------------------------------------------------------
    # PRUEBA REAL DEL BUG:
    #
    # Antes:
    #
    #   20 -> 15
    #   failure
    #   owned connection hace COMMIT
    #   => 15 ❌
    #
    # Después del fix:
    #
    #   20 -> 15
    #   failure
    #   rollback
    #   => 20 ✅
    # --------------------------------------------------------

    restored_character = (
        character_repository.get_character(
            character_id,
            campaign_id=1,
        )
    )

    assert restored_character is not None
    assert restored_character.current_hp == 20

def test_apply_turn_operations_does_not_save_world_for_no_change(
    monkeypatch,
):
    service = WorldService()

    existing_entity = Entity(
        id=1,
        name="Aldric",
        entity_type="character",
    )

    service.world.entities[1] = existing_entity

    operation = UpdateEntityOperation(
        entity_id=1,
        name="Aldric",
    )

    save_calls = []

    def spy_save_world(
        world,
        *,
        conn=None,
    ):
        save_calls.append(
            (
                world,
                conn,
            )
        )

    monkeypatch.setattr(
        service.repository,
        "save_world",
        spy_save_world,
    )

    result = service.apply_turn_operations(
        world_operations=(
            operation,
        ),
        character_operations=(),
        campaign_id=1,
    )

    assert len(result) == 1
    assert result[0].success is True
    assert result[0].changed is False
    assert result[0].status == OperationStatus.NO_CHANGE

    assert save_calls == []