from models.entity import Entity
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

    def __init__(self, relation_applier=None, item_applier=None, resource_applier=None) -> None:
        self._relation_applier = relation_applier or WorldRelationApplier()
        self._item_applier = item_applier or WorldItemApplier()
        self._resource_applier = resource_applier or WorldResourceApplier()

    def apply(
        self,
        world: WorldState,
        operation: WorldOperation,
    ) -> OperationResult:

        if isinstance(operation, CreateEntityOperation):
            return self._apply_create_entity(world, operation)

        if isinstance(operation, UpdateEntityOperation):
            return self._apply_update_entity(world, operation)

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
            (CreateResourceOperation, GainResourceOperation, SpendResourceOperation, TransferResourceOperation),
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
    # ENTITIES
    # ============================================================

    def _apply_create_entity(
        self,
        world: WorldState,
        operation: CreateEntityOperation,
    ) -> OperationResult:

        name = operation.name.strip()

        if not name:
            return OperationResult(
                status=OperationStatus.INVALID,
                message="Entity name cannot be empty.",
                operation=operation,
            )

        # Evitar duplicados por nombre.
        for entity in world.entities.values():
            if entity.name.strip().lower() == name.lower():
                return OperationResult(
                    status=OperationStatus.DUPLICATE,
                    message=f"Entity '{name}' already exists.",
                    operation=operation,
                )

        entity_id = self._next_entity_id(world)

        entity = Entity(
            id=entity_id,
            name=name,
            entity_type=operation.entity_type,
            description=operation.description,
            notes=operation.notes,
            active=operation.active,
        )

        world.entities[entity_id] = entity

        return OperationResult(
            status=OperationStatus.SUCCESS,
            message=f"Entity '{entity.name}' created.",
            operation=operation,
            data={
                "entity_id": entity_id,
            },
        )

    def _apply_update_entity(
        self,
        world: WorldState,
        operation: UpdateEntityOperation,
    ) -> OperationResult:

        entity = world.entities.get(operation.entity_id)

        if entity is None:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"Entity '{operation.entity_id}' "
                    f"does not exist."
                ),
                operation=operation,
            )

        changed = False

        if operation.name is not None:

            name = operation.name.strip()

            if not name:
                return OperationResult(
                    status=OperationStatus.INVALID,
                    message="Entity name cannot be empty.",
                    operation=operation,
                )

            for entity_id, other in world.entities.items():

                if entity_id == operation.entity_id:
                    continue

                if other.name.strip().lower() == name.lower():
                    return OperationResult(
                        status=OperationStatus.DUPLICATE,
                        message=(
                            f"Entity named '{name}' "
                            f"already exists."
                        ),
                        operation=operation,
                    )

            if entity.name != name:
                entity.name = name
                changed = True

        if (
            operation.entity_type is not None
            and entity.entity_type != operation.entity_type
        ):
            entity.entity_type = operation.entity_type
            changed = True

        if (
            operation.description is not None
            and entity.description != operation.description
        ):
            entity.description = operation.description
            changed = True

        if operation.notes is not None and entity.notes != operation.notes:
            entity.notes = operation.notes
            changed = True

        if operation.active is not None and entity.active != operation.active:
            entity.active = operation.active
            changed = True

        if not changed:
            return OperationResult(
                status=OperationStatus.NO_CHANGE,
                message="Entity already had the requested state.",
                operation=operation,
            )

        return OperationResult(
            status=OperationStatus.SUCCESS,
            message=f"Entity '{entity.name}' updated.",
            operation=operation,
            data={
                "entity_id": operation.entity_id,
            },
        )

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
    # RESOURCES
    # ============================================================

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
    def _next_entity_id(
        world: WorldState,
    ) -> int:

        numeric_ids = [
            entity_id
            for entity_id in world.entities
            if isinstance(entity_id, int)
            and not isinstance(entity_id, bool)
        ]

        return max(numeric_ids, default=0) + 1

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

    @staticmethod
    def _find_balance(
        world: WorldState,
        resource_id: int,
        owner_id: int,
    ) -> ResourceBalance | None:

        for balance in world.resource_balances.values():

            if (
                balance.resource_id == resource_id
                and balance.owner_id == owner_id
            ):
                return balance

        return None

    @staticmethod
    def _next_balance_id(
        world: WorldState,
    ) -> int:

        numeric_ids = [
            balance_id
            for balance_id in world.resource_balances
            if isinstance(balance_id, int)
            and not isinstance(balance_id, bool)
        ]

        return max(numeric_ids, default=0) + 1

    def _next_item_id(self, world):
        return self._item_applier._next_item_id(world)

    def _next_item_instance_id(self, world):
        return self._item_applier._next_item_instance_id(world)

    def _next_resource_id(self, world):
        return self._resource_applier._next_resource_id(world)