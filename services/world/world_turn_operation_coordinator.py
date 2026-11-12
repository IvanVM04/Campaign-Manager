"""Atomic coordination for mixed world and character turn operations."""

import copy

from database import get_conn
from operations.character_operations import CharacterOperation
from operations.referenced_operation import ReferencedOperation
from operations.world_operations import WorldOperation


class _WorldTurnOperationFailure(Exception):
    def __init__(self, results):
        self.results = tuple(results)


class WorldTurnOperationCoordinator:
    """Apply ordered world/character operations on one caller-owned connection."""

    @staticmethod
    def apply(
        world_service,
        world_operations,
        character_operations,
        *,
        campaign_id: int,
        conn=None,
        ordered_operations=None,
    ) -> tuple:
        """
        Aplica las operaciones de mundo y personaje de un turno.

        Las operaciones pueden ser ReferencedOperation.

        Las referencias se resuelven en orden dentro de cada grupo
        de operaciones y los IDs generados quedan disponibles para
        operaciones posteriores.

        Si una operación falla, se restaura el WorldState original y
        la transacción de SQLite se revierte explícitamente.
        """

        if world_operations is None:
            raise TypeError(
                "world_operations must not be None"
            )

        if character_operations is None:
            raise TypeError(
                "character_operations must not be None"
            )

        try:
            world_operations = tuple(
                world_operations
            )
        except TypeError as exc:
            raise TypeError(
                "world_operations must be iterable"
            ) from exc

        try:
            character_operations = tuple(
                character_operations
            )
        except TypeError as exc:
            raise TypeError(
                "character_operations must be iterable"
            ) from exc

        if ordered_operations is not None:
            try:
                ordered_operations = tuple(
                    ordered_operations
                )
            except TypeError as exc:
                raise TypeError(
                    "ordered_operations must be iterable"
                ) from exc

        original_world = world_service.world

        working_world = copy.deepcopy(
            original_world
        )

        world_service.world = working_world

        results = []
        references = {}
        world_operation_applied = False

        def unwrap_operation(raw_operation):
            if isinstance(
                raw_operation,
                ReferencedOperation,
            ):
                return (
                    raw_operation.operation,
                    raw_operation.ref,
                )

            return (
                raw_operation,
                None,
            )

        def apply_world_operation(
            raw_operation,
            connection,
        ):
            nonlocal world_operation_applied

            operation, ref = unwrap_operation(
                raw_operation
            )

            operation = (
                world_service._resolve_operation_references(
                    operation,
                    references,
                )
            )

            result = world_service.applier.apply(
                world_service.world,
                operation,
            )

            results.append(result)

            if not result.success:
                raise _WorldTurnOperationFailure(
                    results
                )

            if result.changed:
                world_operation_applied = True

            world_service._register_operation_reference(
                ref,
                result,
                references,
                world_service.world,
            )

        def apply_character_operation(
            raw_operation,
            connection,
        ):
            operation, ref = unwrap_operation(
                raw_operation
            )

            operation = (
                world_service._resolve_operation_references(
                    operation,
                    references,
                )
            )

            result = world_service.character_applier.apply(
                operation,
                campaign_id=campaign_id,
                conn=connection,
            )

            results.append(result)

            if not result.success:
                raise _WorldTurnOperationFailure(
                    results
                )

            world_service._register_operation_reference(
                ref,
                result,
                references,
                world_service.world,
            )

        def apply_with_connection(connection):

            if ordered_operations is not None:

                for operation in ordered_operations:

                    operation_to_apply = operation

                    if isinstance(
                        operation,
                        ReferencedOperation,
                    ):
                        operation_to_apply = (
                            operation.operation
                        )

                    if isinstance(
                        operation_to_apply,
                        WorldOperation,
                    ):
                        apply_world_operation(
                            operation,
                            connection,
                        )

                    elif isinstance(
                        operation_to_apply,
                        CharacterOperation,
                    ):
                        apply_character_operation(
                            operation,
                            connection,
                        )

                    else:
                        raise TypeError(
                            f"Unsupported operation type: "
                            f"{type(operation_to_apply).__name__}"
                        )

            else:

                for operation in world_operations:
                    apply_world_operation(
                        operation,
                        connection,
                    )

                for operation in character_operations:
                    apply_character_operation(
                        operation,
                        connection,
                    )

            if world_operation_applied:

                world_service.repository.save_world(
                    world_service.world,
                    campaign_id=world_service.campaign_id,
                    conn=connection,
                )


                # Si no recibimos conexión, esta función es propietaria
        # de la transacción. Dejamos que get_conn() gestione el
        # rollback mediante la excepción.
        if conn is None:
            try:
                with get_conn() as owned_conn:
                    apply_with_connection(owned_conn)

            except _WorldTurnOperationFailure as exc:
                world_service.world = original_world
                return tuple(exc.results)

            except Exception:
                world_service.world = original_world
                raise

        else:
            # Si el caller proporciona la conexión, también posee
            # la transacción. WorldService no debe hacer rollback:
            # el caller decidirá si confirma o revierte.
            try:
                apply_with_connection(conn)

            except _WorldTurnOperationFailure as exc:
                world_service.world = original_world
                return tuple(exc.results)

            except Exception:
                world_service.world = original_world
                raise

        # El TurnContext puede estar utilizando exactamente la misma
        # instancia de WorldState que tenía WorldService antes de
        # comenzar el turno.
        #
        # Hemos trabajado sobre una copia para mantener la atomicidad,
        # pero al completar correctamente debemos publicar el nuevo
        # estado sobre la instancia original para no romper esa
        # identidad compartida.
        original_world.entities = world_service.world.entities
        original_world.items = world_service.world.items
        original_world.item_instances = (
            world_service.world.item_instances
        )
        original_world.resources = world_service.world.resources
        original_world.resource_balances = (
            world_service.world.resource_balances
        )
        original_world.relations = world_service.world.relations
        original_world.events = world_service.world.events

        world_service.world = original_world

        return tuple(results)
