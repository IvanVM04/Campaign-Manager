"""In-memory application of world entity operations."""

from models.entity import Entity
from models.operation_result import OperationResult, OperationStatus
from models.world_state import WorldState
from operations.world_operations import CreateEntityOperation, UpdateEntityOperation


class WorldEntityApplier:
    """Applies entity creation and updates without persistence concerns."""

    def apply(self, world: WorldState, operation) -> OperationResult:
        if isinstance(operation, CreateEntityOperation):
            return self._apply_create_entity(world, operation)
        if isinstance(operation, UpdateEntityOperation):
            return self._apply_update_entity(world, operation)
        return OperationResult(
            status=OperationStatus.UNSUPPORTED,
            message=f"Unsupported entity operation: {type(operation).__name__}",
            operation=operation,
        )

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
            data={"entity_id": entity_id},
        )

    def _apply_update_entity(
        self,
        world: WorldState,
        operation: UpdateEntityOperation,
    ) -> OperationResult:
        if not isinstance(operation.entity_id, int) or isinstance(
            operation.entity_id, bool
        ):
            return OperationResult(
                status=OperationStatus.INVALID,
                message="Entity reference must be resolved before applying the update.",
                operation=operation,
            )

        entity = world.entities.get(operation.entity_id)

        if entity is None:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=f"Entity '{operation.entity_id}' does not exist.",
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
                        message=f"Entity named '{name}' already exists.",
                        operation=operation,
                    )

            if entity.name != name:
                entity.name = name
                changed = True

        if operation.entity_type is not None and entity.entity_type != operation.entity_type:
            entity.entity_type = operation.entity_type
            changed = True

        if operation.description is not None and entity.description != operation.description:
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
            data={"entity_id": operation.entity_id},
        )

    @staticmethod
    def _next_entity_id(world: WorldState) -> int:
        numeric_ids = [
            entity_id
            for entity_id in world.entities
            if isinstance(entity_id, int) and not isinstance(entity_id, bool)
        ]
        return max(numeric_ids, default=0) + 1
