import math

from models.entity import Entity
from models.event import Event
from models.item import Item, ItemInstance
from models.operation_result import (
    OperationResult,
    OperationStatus,
)
from models.resource import Resource, ResourceBalance
from models.world_state import WorldState
from operations.world_operations import (
    _UNSET,
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
from rules_engine.dnd5e_2014.armor.catalog import get_armor
from services.world_relation_applier import WorldRelationApplier


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

    def __init__(self, relation_applier=None) -> None:
        self._relation_applier = relation_applier or WorldRelationApplier()

    def apply(
        self,
        world: WorldState,
        operation: WorldOperation,
    ) -> OperationResult:

        if isinstance(operation, CreateEntityOperation):
            return self._apply_create_entity(world, operation)

        if isinstance(operation, UpdateEntityOperation):
            return self._apply_update_entity(world, operation)

        if isinstance(operation, TransferItemOperation):
            return self._apply_transfer_item(world, operation)

        if isinstance(operation, GainResourceOperation):
            return self._apply_gain_resource(world, operation)

        if isinstance(operation, SpendResourceOperation):
            return self._apply_spend_resource(world, operation)

        if isinstance(operation, TransferResourceOperation):
            return self._apply_transfer_resource(world, operation)

        if isinstance(
            operation,
            (CreateRelationOperation, UpdateRelationOperation, RemoveRelationOperation),
        ):
            return self._relation_applier.apply(world, operation)

        if isinstance(operation, CreateEventOperation):
            return self._apply_create_event(world, operation)

        if isinstance(operation, CreateItemOperation):
            return self._apply_create_item(world, operation)

        if isinstance(operation, CreateItemInstanceOperation):
            return self._apply_create_item_instance(world, operation)

        if isinstance(operation, CreateResourceOperation):
            return self._apply_create_resource(world, operation)

        if isinstance(operation, UpdateItemInstanceOperation):
            return self._apply_update_item_instance(world, operation)

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
    # ITEMS
    # ============================================================

    def _apply_create_item(
        self,
        world: WorldState,
        operation: CreateItemOperation,
    ) -> OperationResult:

        name = operation.name.strip()

        if not name:
            return OperationResult(
                status=OperationStatus.INVALID,
                message="Item name cannot be empty.",
                operation=operation,
            )

        for item in world.items.values():
            if item.name.strip().lower() == name.lower():
                return OperationResult(
                    status=OperationStatus.DUPLICATE,
                    message=f"Item '{name}' already exists.",
                    operation=operation,
                )

        equipment_slot = operation.equipment_slot
        allowed_slots = {
            "main_hand", "off_hand", "body", "head", "hands", "feet",
            "cloak", "neck", "ring_1", "ring_2", "waist", "wondrous",
            "ammunition",
        }
        if equipment_slot is not None and equipment_slot not in allowed_slots:
            return OperationResult(
                status=OperationStatus.INVALID,
                message="unsupported equipment slot",
                operation=operation,
            )
        if operation.weapon_key is not None and operation.armor_key is not None:
            return OperationResult(
                status=OperationStatus.INVALID,
                message="an item cannot be both a weapon and armor",
                operation=operation,
            )
        if operation.armor_key is not None:
            try:
                armor = get_armor(operation.armor_key)
            except LookupError:
                return OperationResult(
                    status=OperationStatus.INVALID,
                    message="unknown SRD armor definition",
                    operation=operation,
                )
            expected_slot = "off_hand" if armor.category.value == "shield" else "body"
            equipment_slot = equipment_slot or expected_slot
            if equipment_slot != expected_slot:
                return OperationResult(
                    status=OperationStatus.INVALID,
                    message="armor items must use body; shields must use off_hand",
                    operation=operation,
                )
        if operation.weapon_key is not None:
            equipment_slot = equipment_slot or "main_hand"
            if equipment_slot not in ("main_hand", "off_hand"):
                return OperationResult(
                    status=OperationStatus.INVALID,
                    message="weapon items must use main_hand or off_hand equipment slots",
                    operation=operation,
                )

        item_id = self._next_item_id(world)

        item = Item(
            id=item_id,
            name=name,
            description=operation.description,
            significance=operation.significance,
            unique=operation.unique,
            notes=operation.notes,
            weapon_key=operation.weapon_key,
            armor_key=operation.armor_key,
            equipment_slot=equipment_slot,
        )

        world.items[item_id] = item

        return OperationResult(
            status=OperationStatus.SUCCESS,
            message=f"Item '{name}' created.",
            operation=operation,
            data={
                "item_id": item_id,
            },
        )


    def _apply_create_item_instance(
        self,
        world: WorldState,
        operation: CreateItemInstanceOperation,
    ) -> OperationResult:

        if operation.item_id not in world.items:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"Item '{operation.item_id}' does not exist."
                ),
                operation=operation,
            )

        if (
            operation.owner_id is not None
            and operation.owner_id not in world.entities
        ):
            return OperationResult(
                    status=OperationStatus.NOT_FOUND,
                    message=(
                        f"Owner '{operation.owner_id}' "
                        f"does not exist."
                    ),
                    operation=operation,
                )

        if (
            operation.location_id is not None
            and operation.location_id not in world.entities
        ):
            return OperationResult(
                    status=OperationStatus.NOT_FOUND,
                    message=(
                        f"Location '{operation.location_id}' "
                        f"does not exist."
                    ),
                    operation=operation,
                )

        if operation.instance_number < 1:
            return OperationResult(
                status=OperationStatus.INVALID,
                message="Instance number must be >= 1.",
                operation=operation,
            )

        for instance in world.item_instances.values():
            if (
                instance.item_id == operation.item_id
                and instance.instance_number
                == operation.instance_number
            ):
                return OperationResult(
                    status=OperationStatus.DUPLICATE,
                    message=(
                        f"Item instance "
                        f"'{operation.item_id}#"
                        f"{operation.instance_number}' "
                        f"already exists."
                    ),
                    operation=operation,
                )

        instance_id = self._next_item_instance_id(world)

        instance = ItemInstance(
            id=instance_id,
            item_id=operation.item_id,
            instance_number=operation.instance_number,
            owner_id=operation.owner_id,
            location_id=operation.location_id,
            condition=operation.condition,
            notes=operation.notes,
            active=operation.active,
        )

        world.item_instances[instance_id] = instance

        return OperationResult(
            status=OperationStatus.SUCCESS,
            message=(
                f"Item instance '{instance_id}' created."
            ),
            operation=operation,
            data={
                "instance_id": instance_id,
            },
        )

    def _apply_transfer_item(
        self,
        world: WorldState,
        operation: TransferItemOperation,
    ) -> OperationResult:

        instance = world.item_instances.get(
            operation.instance_id
        )

        if instance is None:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"Item instance "
                    f"'{operation.instance_id}' does not exist."
                ),
                operation=operation,
            )

        if operation.new_owner_id not in world.entities:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"New owner "
                    f"'{operation.new_owner_id}' does not exist."
                ),
                operation=operation,
            )

        if instance.owner_id == operation.new_owner_id:
            return OperationResult(
                status=OperationStatus.NO_CHANGE,
                message=(
                    "Item instance already belongs "
                    "to the requested owner."
                ),
                operation=operation,
            )

        instance.owner_id = operation.new_owner_id

        return OperationResult(
            status=OperationStatus.SUCCESS,
            message=(
                f"Item instance '{operation.instance_id}' "
                f"transferred successfully."
            ),
            operation=operation,
        )

    def _apply_update_item_instance(
        self,
        world: WorldState,
        operation: UpdateItemInstanceOperation,
    ) -> OperationResult:
        instance = world.item_instances.get(
            operation.instance_id
        )

        if instance is None:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"Item instance "
                    f"'{operation.instance_id}' "
                    f"does not exist."
                ),
                operation=operation,
            )

        # ------------------------------------------------------------
        # Validate owner before modifying anything.
        # None is valid here and means "remove owner".
        # ------------------------------------------------------------
        if (
            operation.owner_id is not _UNSET
            and operation.owner_id is not None
            and operation.owner_id not in world.entities
        ):
                return OperationResult(
                    status=OperationStatus.NOT_FOUND,
                    message=(
                        f"Owner "
                        f"'{operation.owner_id}' "
                        f"does not exist."
                    ),
                    operation=operation,
                )

        # ------------------------------------------------------------
        # Validate location before modifying anything.
        # None is valid here and means "remove location".
        # ------------------------------------------------------------
        if (
            operation.location_id is not _UNSET
            and operation.location_id is not None
            and operation.location_id not in world.entities
        ):
                return OperationResult(
                    status=OperationStatus.NOT_FOUND,
                    message=(
                        f"Location "
                        f"'{operation.location_id}' "
                        f"does not exist."
                    ),
                    operation=operation,
                )

        changed = False

        # ------------------------------------------------------------
        # Update owner.
        # _UNSET = do not modify
        # None   = remove owner
        # int    = assign owner
        # ------------------------------------------------------------
        if (
            operation.owner_id is not _UNSET
            and instance.owner_id != operation.owner_id
        ):
            instance.owner_id = operation.owner_id
            changed = True

        # ------------------------------------------------------------
        # Update location.
        # _UNSET = do not modify
        # None   = remove location
        # int    = assign location
        # ------------------------------------------------------------
        if (
            operation.location_id is not _UNSET
            and instance.location_id != operation.location_id
        ):
            instance.location_id = operation.location_id
            changed = True

        # ------------------------------------------------------------
        # Update condition.
        # _UNSET = do not modify
        # None   = clear condition
        # str    = set condition
        # ------------------------------------------------------------
        if (
            operation.condition is not _UNSET
            and instance.condition != operation.condition
        ):
            instance.condition = (
                "" if operation.condition is None
                else operation.condition
            )
            changed = True

        # ------------------------------------------------------------
        # Update notes.
        # _UNSET = do not modify
        # None   = clear notes
        # str    = set notes
        # ------------------------------------------------------------
        if (
            operation.notes is not _UNSET
            and instance.notes != operation.notes
        ):
            instance.notes = (
                "" if operation.notes is None
                else operation.notes
            )
            changed = True

        # ------------------------------------------------------------
        # Update active.
        # _UNSET = do not modify
        # bool   = set active state
        #
        # active=None is treated as invalid rather than persisted,
        # because ItemInstance.active is a bool field.
        # ------------------------------------------------------------
        if operation.active is not _UNSET:
            if operation.active is None:
                return OperationResult(
                    status=OperationStatus.INVALID,
                    message="Item instance 'active' cannot be None.",
                    operation=operation,
                )

            if instance.active != operation.active:
                instance.active = operation.active
                changed = True

        if not changed:
            return OperationResult(
                status=OperationStatus.NO_CHANGE,
                message=(
                    "Item instance already had "
                    "the requested state."
                ),
                operation=operation,
            )

        return OperationResult(
            status=OperationStatus.SUCCESS,
            message=(
                f"Item instance "
                f"'{instance.id}' "
                f"updated successfully."
            ),
            operation=operation,
            data={
                "instance_id": instance.id,
            },
        )

    # ============================================================
    # RESOURCES
    # ============================================================

    def _apply_create_resource(
        self,
        world: WorldState,
        operation: CreateResourceOperation,
    ) -> OperationResult:

        name = operation.name.strip()

        if not name:
            return OperationResult(
                status=OperationStatus.INVALID,
                message="Resource name cannot be empty.",
                operation=operation,
            )

        for resource in world.resources.values():
            if resource.name.strip().lower() == name.lower():
                return OperationResult(
                    status=OperationStatus.DUPLICATE,
                    message=(
                        f"Resource '{name}' already exists."
                    ),
                    operation=operation,
                )

        resource_id = self._next_resource_id(world)

        resource = Resource(
            id=resource_id,
            name=name,
            resource_type=operation.resource_type,
            unit=operation.unit,
            notes=operation.notes,
        )

        world.resources[resource_id] = resource

        return OperationResult(
            status=OperationStatus.SUCCESS,
            message=f"Resource '{name}' created.",
            operation=operation,
            data={
                "resource_id": resource_id,
            },
        )

    def _apply_gain_resource(
        self,
        world: WorldState,
        operation: GainResourceOperation,
    ) -> OperationResult:

        if operation.resource_id not in world.resources:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"Resource "
                    f"'{operation.resource_id}' does not exist."
                ),
                operation=operation,
            )

        if operation.owner_id not in world.entities:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"Owner "
                    f"'{operation.owner_id}' does not exist."
                ),
                operation=operation,
            )

        if not self._valid_amount(operation.amount):
            return OperationResult(
                status=OperationStatus.INVALID,
                message=(
                    f"Invalid resource amount: "
                    f"{operation.amount!r}."
                ),
                operation=operation,
            )

        balance = self._find_balance(
            world,
            operation.resource_id,
            operation.owner_id,
        )

        if balance is not None:
            balance.amount += operation.amount

            return OperationResult(
                status=OperationStatus.SUCCESS,
                message=(
                    f"Added {operation.amount} of resource "
                    f"'{operation.resource_id}' "
                    f"to owner '{operation.owner_id}'."
                ),
                operation=operation,
            )

        balance_id = self._next_balance_id(world)

        world.resource_balances[balance_id] = ResourceBalance(
            id=balance_id,
            resource_id=operation.resource_id,
            owner_id=operation.owner_id,
            amount=operation.amount,
        )

        return OperationResult(
            status=OperationStatus.SUCCESS,
            message=(
                f"Created resource balance with "
                f"{operation.amount} of resource "
                f"'{operation.resource_id}'."
            ),
            operation=operation,
        )

    def _apply_spend_resource(
        self,
        world: WorldState,
        operation: SpendResourceOperation,
    ) -> OperationResult:

        if operation.resource_id not in world.resources:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"Resource "
                    f"'{operation.resource_id}' does not exist."
                ),
                operation=operation,
            )

        if operation.owner_id not in world.entities:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"Owner "
                    f"'{operation.owner_id}' does not exist."
                ),
                operation=operation,
            )

        if not self._valid_amount(operation.amount):
            return OperationResult(
                status=OperationStatus.INVALID,
                message=(
                    f"Invalid resource amount: "
                    f"{operation.amount!r}."
                ),
                operation=operation,
            )

        balance = self._find_balance(
            world,
            operation.resource_id,
            operation.owner_id,
        )

        if balance is None:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"No balance exists for resource "
                    f"'{operation.resource_id}' "
                    f"and owner '{operation.owner_id}'."
                ),
                operation=operation,
            )

        if balance.amount < operation.amount:
            return OperationResult(
                status=OperationStatus.INVALID,
                message=(
                    f"Insufficient resource balance. "
                    f"Available: {balance.amount}, "
                    f"requested: {operation.amount}."
                ),
                operation=operation,
            )

        balance.amount -= operation.amount

        return OperationResult(
            status=OperationStatus.SUCCESS,
            message=(
                f"Spent {operation.amount} of resource "
                f"'{operation.resource_id}' "
                f"from owner '{operation.owner_id}'."
            ),
            operation=operation,
        )

    def _apply_transfer_resource(
        self,
        world: WorldState,
        operation: TransferResourceOperation,
    ) -> OperationResult:

        if operation.resource_id not in world.resources:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"Resource "
                    f"'{operation.resource_id}' does not exist."
                ),
                operation=operation,
            )

        if operation.subject_id not in world.entities:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"Source entity "
                    f"'{operation.subject_id}' does not exist."
                ),
                operation=operation,
            )

        if operation.target_id not in world.entities:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"Target entity "
                    f"'{operation.target_id}' does not exist."
                ),
                operation=operation,
            )

        if not self._valid_amount(operation.amount):
            return OperationResult(
                status=OperationStatus.INVALID,
                message=(
                    f"Invalid resource amount: "
                    f"{operation.amount!r}."
                ),
                operation=operation,
            )

        if operation.subject_id == operation.target_id:
            return OperationResult(
                status=OperationStatus.INVALID,
                message="Source and target cannot be the same entity.",
                operation=operation,
            )

        source_balance = self._find_balance(
            world,
            operation.resource_id,
            operation.subject_id,
        )

        if source_balance is None:
            return OperationResult(
                status=OperationStatus.NOT_FOUND,
                message=(
                    f"Source entity "
                    f"'{operation.subject_id}' has no balance "
                    f"for resource '{operation.resource_id}'."
                ),
                operation=operation,
            )

        if source_balance.amount < operation.amount:
            return OperationResult(
                status=OperationStatus.INVALID,
                message=(
                    f"Insufficient resource balance. "
                    f"Available: {source_balance.amount}, "
                    f"requested: {operation.amount}."
                ),
                operation=operation,
            )

        target_balance = self._find_balance(
            world,
            operation.resource_id,
            operation.target_id,
        )

        if target_balance is None:

            balance_id = self._next_balance_id(world)

            target_balance = ResourceBalance(
                id=balance_id,
                resource_id=operation.resource_id,
                owner_id=operation.target_id,
                amount=0,
            )

            world.resource_balances[balance_id] = target_balance

        source_balance.amount -= operation.amount
        target_balance.amount += operation.amount

        return OperationResult(
            status=OperationStatus.SUCCESS,
            message=(
                f"Transferred {operation.amount} of resource "
                f"'{operation.resource_id}' from "
                f"'{operation.subject_id}' to "
                f"'{operation.target_id}'."
            ),
            operation=operation,
        )

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

        if isinstance(amount, bool):
            return False

        if not isinstance(amount, (int, float)):
            return False

        if not math.isfinite(amount):
            return False

        return amount > 0

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

    def _next_item_id(
        self,
        world: WorldState,
    ) -> int:

        if not world.items:
            return 1

        return max(world.items.keys()) + 1


    def _next_item_instance_id(
        self,
        world: WorldState,
    ) -> int:

        if not world.item_instances:
            return 1

        return max(world.item_instances.keys()) + 1


    def _next_resource_id(
        self,
        world: WorldState,
    ) -> int:

        if not world.resources:
            return 1

        return max(world.resources.keys()) + 1