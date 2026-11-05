from models.event import Event
from models.operation_result import (
    OperationResult,
    OperationStatus,
)
from models.world_state import WorldState
from operations.world_operations import (
    CreateEntityOperation,
    CreateEventOperation,
    CreateItemInstanceOperation,
    CreateItemOperation,
    CreateRelationOperation,
    CreateResourceOperation,
    GainResourceOperation,
    RemoveRelationOperation,
    SpendResourceOperation,
    TransferItemOperation,
    TransferResourceOperation,
    UpdateEntityOperation,
    UpdateItemInstanceOperation,
    UpdateRelationOperation,
    WorldOperation,
)
from services.world_entity_applier import WorldEntityApplier
from services.world_item_applier import WorldItemApplier
from services.world_relation_applier import WorldRelationApplier
from services.world_resource_applier import WorldResourceApplier


class WorldApplier:
    """
    Aplica operaciones de dominio sobre un WorldState.

    WorldApplier:
        - modifica únicamente el estado en memoria
        - no accede a SQLite
        - no persiste cambios
        - no genera operaciones nuevas

    La persistencia corresponde a WorldService/WorldRepository.
    """

    def __init__(
        self,
        relation_applier=None,
        item_applier=None,
        resource_applier=None,
        entity_applier=None,
    ) -> None:
        self._relation_applier = relation_applier or WorldRelationApplier()
        self._item_applier = item_applier or WorldItemApplier()
        self._resource_applier = resource_applier or WorldResourceApplier()
        self._entity_applier = entity_applier or WorldEntityApplier()

    def apply(
        self,
        world: WorldState,
        operation: WorldOperation,
    ) -> OperationResult:

        if isinstance(operation, (CreateEntityOperation, UpdateEntityOperation)):
            return self._entity_applier.apply(world, operation)

        if isinstance(
            operation,
            (
                CreateItemOperation,
                CreateItemInstanceOperation,
                TransferItemOperation,
                UpdateItemInstanceOperation,
            ),
        ):
            return self._item_applier.apply(world, operation)

        if isinstance(
            operation,
            (
                CreateResourceOperation,
                GainResourceOperation,
                SpendResourceOperation,
                TransferResourceOperation,
            ),
        ):
            return self._resource_applier.apply(world, operation)

        if isinstance(
            operation,
            (CreateRelationOperation, UpdateRelationOperation, RemoveRelationOperation),
        ):
            return self._relation_applier.apply(world, operation)

        if isinstance(operation, CreateEventOperation):
            return self._apply_create_event(world, operation)

        return OperationResult(
            status=OperationStatus.UNSUPPORTED,
            message=(
                f"Unsupported operation: "
                f"{type(operation).__name__}"
            ),
            operation=operation,
        )

    # ============================================================
    # ENTITIES (compatibility delegates)
    # ============================================================

    def _apply_create_entity(self, world, operation):
        return self._entity_applier._apply_create_entity(world, operation)

    def _apply_update_entity(self, world, operation):
        return self._entity_applier._apply_update_entity(world, operation)

    # ============================================================
    # ITEMS (compatibility delegates)
    # ============================================================

    def _apply_create_item(self, world, operation):
        return self._item_applier._apply_create_item(world, operation)

    def _apply_create_item_instance(self, world, operation):
        return self._item_applier._apply_create_item_instance(world, operation)

    def _apply_transfer_item(self, world, operation):
        return self._item_applier._apply_transfer_item(world, operation)

    def _apply_update_item_instance(self, world, operation):
        return self._item_applier._apply_update_item_instance(world, operation)

    # ============================================================
    # RESOURCES (compatibility delegates)
    # ============================================================

    def _apply_create_resource(self, world, operation):
        return self._resource_applier._apply_create_resource(world, operation)

    def _apply_gain_resource(self, world, operation):
        return self._resource_applier._apply_gain_resource(world, operation)

    def _apply_spend_resource(self, world, operation):
        return self._resource_applier._apply_spend_resource(world, operation)

    def _apply_transfer_resource(self, world, operation):
        return self._resource_applier._apply_transfer_resource(world, operation)

    # ============================================================
    # RELATIONS (compatibility delegates)
    # ============================================================

    def _apply_create_relation(self, world, operation):
        return self._relation_applier._apply_create_relation(world, operation)

    def _apply_update_relation(self, world, operation):
        return self._relation_applier._apply_update_relation(world, operation)

    def _apply_remove_relation(self, world, operation):
        return self._relation_applier._apply_remove_relation(world, operation)

    # ============================================================
    # EVENTS
    # ============================================================

    def _apply_create_event(
        self,
        world: WorldState,
        operation: CreateEventOperation,
    ) -> OperationResult:

        if not operation.event_id:
            return OperationResult(
                status=OperationStatus.INVALID,
                message="Event ID cannot be empty.",
                operation=operation,
            )

        if not operation.event_type:
            return OperationResult(
                status=OperationStatus.INVALID,
                message="Event type cannot be empty.",
                operation=operation,
            )

        if not operation.title:
            return OperationResult(
                status=OperationStatus.INVALID,
                message="Event title cannot be empty.",
                operation=operation,
            )

        if operation.event_id in world.events:
            return OperationResult(
                status=OperationStatus.DUPLICATE,
                message=(
                    f"Event "
                    f"'{operation.event_id}' already exists."
                ),
                operation=operation,
            )

        world.events[operation.event_id] = Event(
            id=operation.event_id,
            event_type=operation.event_type,
            title=operation.title,
            description=operation.description,
            consequences=operation.consequences,
            session_id=operation.session_id,
            secret=operation.secret,
            metadata=operation.metadata or {},
        )

        return OperationResult(
            status=OperationStatus.SUCCESS,
            message=(
                f"Event '{operation.event_id}' created."
            ),
            operation=operation,
        )

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _next_entity_id(world):
        return WorldEntityApplier._next_entity_id(world)

    @staticmethod
    def _valid_amount(amount: float) -> bool:
        return WorldResourceApplier._valid_amount(amount)

    @staticmethod
    def _find_balance(world, resource_id, owner_id):
        return WorldResourceApplier._find_balance(world, resource_id, owner_id)

    @staticmethod
    def _next_balance_id(world):
        return WorldResourceApplier._next_balance_id(world)

    @staticmethod
    def _coerce_entity_id(value) -> int | None:
        return WorldRelationApplier._coerce_entity_id(value)

    def _next_item_id(self, world):
        return self._item_applier._next_item_id(world)

    def _next_item_instance_id(self, world):
        return self._item_applier._next_item_instance_id(world)

    def _next_resource_id(self, world):
        return self._resource_applier._next_resource_id(world)