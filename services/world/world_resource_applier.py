"""In-memory application of resource definitions and balances."""

import math
from typing import cast

from models.operation_result import OperationResult, OperationStatus
from models.resource import Resource, ResourceBalance
from models.world_state import WorldState
from operations.world_operations import (
    CreateResourceOperation,
    GainResourceOperation,
    SpendResourceOperation,
    TransferResourceOperation,
)


class WorldResourceApplier:
    def apply(self, world: WorldState, operation) -> OperationResult:
        if isinstance(operation, CreateResourceOperation):
            return self._apply_create_resource(world, operation)
        if isinstance(operation, GainResourceOperation):
            return self._apply_gain_resource(world, operation)
        if isinstance(operation, SpendResourceOperation):
            return self._apply_spend_resource(world, operation)
        if isinstance(operation, TransferResourceOperation):
            return self._apply_transfer_resource(world, operation)
        return OperationResult(
            status=OperationStatus.UNSUPPORTED,
            message=f"Unsupported resource operation: {type(operation).__name__}",
            operation=operation,
        )

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
            cast(int, operation.resource_id),
            cast(int, operation.owner_id),
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
            resource_id=cast(int, operation.resource_id),
            owner_id=cast(int, operation.owner_id),
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
            cast(int, operation.resource_id),
            cast(int, operation.subject_id),
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
            cast(int, operation.resource_id),
            cast(int, operation.target_id),
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

    def _next_resource_id(
        self,
        world: WorldState,
    ) -> int:

        if not world.resources:
            return 1

        return max(world.resources.keys()) + 1