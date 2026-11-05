"""In-memory application of item definition and inventory operations."""

from models.item import Item, ItemInstance
from models.operation_result import OperationResult, OperationStatus
from models.world_state import WorldState
from operations.world_operations import (
    _UNSET,
    CreateItemInstanceOperation,
    CreateItemOperation,
    TransferItemOperation,
    UpdateItemInstanceOperation,
)
from rules_engine.dnd5e_2014.armor.catalog import get_armor


class WorldItemApplier:
    """Owns item definition and item-instance mutations on WorldState."""

    def apply(self, world: WorldState, operation) -> OperationResult:
        if isinstance(operation, CreateItemOperation):
            return self._apply_create_item(world, operation)
        if isinstance(operation, CreateItemInstanceOperation):
            return self._apply_create_item_instance(world, operation)
        if isinstance(operation, TransferItemOperation):
            return self._apply_transfer_item(world, operation)
        if isinstance(operation, UpdateItemInstanceOperation):
            return self._apply_update_item_instance(world, operation)
        return OperationResult(
            status=OperationStatus.UNSUPPORTED,
            message=f"Unsupported item operation: {type(operation).__name__}",
            operation=operation,
        )

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
