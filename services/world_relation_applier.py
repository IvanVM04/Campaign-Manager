"""In-memory application of relationship operations to world state."""

from models.operation_result import OperationResult, OperationStatus
from models.relation import Relation
from models.world_state import WorldState
from operations.world_operations import (
    CreateRelationOperation,
    RemoveRelationOperation,
    UpdateRelationOperation,
)


class WorldRelationApplier:
    """Owns validation and mutation for world relationship operations."""

    def apply(self, world: WorldState, operation) -> OperationResult:
        if isinstance(operation, CreateRelationOperation):
            return self._apply_create_relation(world, operation)
        if isinstance(operation, UpdateRelationOperation):
            return self._apply_update_relation(world, operation)
        if isinstance(operation, RemoveRelationOperation):
            return self._apply_remove_relation(world, operation)
        return OperationResult(
            status=OperationStatus.UNSUPPORTED,
            message=f"Unsupported relationship operation: {type(operation).__name__}",
            operation=operation,
        )

    def _apply_create_relation(
        self,
        world: WorldState,
        operation: CreateRelationOperation,
    ) -> OperationResult:

        if operation.relation_id in world.relations:
            return OperationResult(
                status=OperationStatus.DUPLICATE,
                message=(
                    f"Relation "
                    f"'{operation.relation_id}' already exists."
                ),
                operation=operation,
            )

        if not operation.relation_type:
            return OperationResult(
                status=OperationStatus.INVALID,
                message="Relation type cannot be empty.",
                operation=operation,
            )

        subject_id = self._coerce_entity_id(
            operation.subject_id
        )

        target_id = self._coerce_entity_id(
            operation.target_id
        )

        if subject_id is None:
            return OperationResult(
                status=OperationStatus.INVALID,
                message=(
                    f"Invalid subject entity ID: "
                    f"{operation.subject_id!r}."
                ),
                operation=operation,
            )

        if target_id is None:
            return OperationResult(
                status=OperationStatus.INVALID,
                message=(
                    f"Invalid target entity ID: "
                    f"{operation.target_id!r}."
                ),
                operation=operation,
            )

        if subject_id not in world.entities:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"Subject entity "
                    f"'{subject_id}' does not exist."
                ),
                operation=operation,
            )

        if target_id not in world.entities:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"Target entity "
                    f"'{target_id}' does not exist."
                ),
                operation=operation,
            )

        world.relations[operation.relation_id] = Relation(
            id=operation.relation_id,
            subject_id=subject_id,
            relation_type=operation.relation_type,
            target_id=target_id,
            metadata=operation.metadata,
            active=True,
        )

        return OperationResult(
            status=OperationStatus.SUCCESS,
            message=(
                f"Relation '{operation.relation_id}' created."
            ),
            operation=operation,
        )

    def _apply_update_relation(
        self,
        world: WorldState,
        operation: UpdateRelationOperation,
    ) -> OperationResult:

        relation = world.relations.get(
            operation.relation_id
        )

        if relation is None:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"Relation "
                    f"'{operation.relation_id}' does not exist."
                ),
                operation=operation,
            )

        changed = False

        if operation.relation_type is not None:

            if not operation.relation_type:
                return OperationResult(
                    status=OperationStatus.INVALID,
                    message="Relation type cannot be empty.",
                    operation=operation,
                )

            if relation.relation_type != operation.relation_type:
                relation.relation_type = operation.relation_type
                changed = True

        if operation.target_id is not None:

            target_id = self._coerce_entity_id(
                operation.target_id
            )

            if target_id is None:
                return OperationResult(
                    status=OperationStatus.INVALID,
                    message=(
                        f"Invalid target entity ID: "
                        f"{operation.target_id!r}."
                    ),
                    operation=operation,
                )

            if target_id not in world.entities:
                return OperationResult(
                    status=OperationStatus.NOT_FOUND,
                    message=(
                        f"Target entity "
                        f"'{target_id}' does not exist."
                    ),
                    operation=operation,
                )

            if relation.target_id != target_id:
                relation.target_id = target_id
                changed = True

        if (
            operation.metadata is not None
            and relation.metadata != operation.metadata
        ):
            relation.metadata = operation.metadata
            changed = True

        if operation.active is not None and relation.active != operation.active:
            relation.active = operation.active
            changed = True

        if not changed:
            return OperationResult(
                status=OperationStatus.NO_CHANGE,
                message=(
                    f"Relation "
                    f"'{operation.relation_id}' already had "
                    f"the requested state."
                ),
                operation=operation,
            )

        return OperationResult(
            status=OperationStatus.SUCCESS,
            message=(
                f"Relation "
                f"'{operation.relation_id}' updated."
            ),
            operation=operation,
        )

    def _apply_remove_relation(
        self,
        world: WorldState,
        operation: RemoveRelationOperation,
    ) -> OperationResult:

        relation = world.relations.get(
            operation.relation_id
        )

        if relation is None:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"Relation "
                    f"'{operation.relation_id}' does not exist."
                ),
                operation=operation,
            )

        if not relation.active:
            return OperationResult(
                status=OperationStatus.NO_CHANGE,
                message=(
                    f"Relation "
                    f"'{operation.relation_id}' is already inactive."
                ),
                operation=operation,
            )

        relation.active = False

        return OperationResult(
            status=OperationStatus.SUCCESS,
            message=(
                f"Relation "
                f"'{operation.relation_id}' removed."
            ),
            operation=operation,
        )

    @staticmethod
    def _coerce_entity_id(value) -> int | None:

        if value is None:
            return None

        if isinstance(value, bool):
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

