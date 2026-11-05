import copy
from dataclasses import fields, replace

from database import get_conn
from models.operation_result import OperationResult
from models.world_application_result import (
    WorldApplicationResult,
)
from models.world_state import WorldState
from operations.character_operations import CharacterOperation
from operations.operation_reference import OperationReference
from operations.referenced_operation import ReferencedOperation
from operations.world_operations import (
    WorldOperation,
)
from repositories.character_repository import (
    CharacterRepository,
)
from repositories.world_repository import (
    WorldRepository,
)
from services.character_applier import (
    CharacterApplier,
)
from services.character_service import (
    CharacterService,
)

from .world_applier import (
    WorldApplier,
)


class _WorldTurnOperationFailure(Exception):
    def __init__(self, results):
        self.results = tuple(results)

class WorldService:
    """
    Fachada principal para trabajar con el estado persistente del mundo.

    Responsabilidades:

    - Cargar el mundo desde el repositorio.
    - Mantener el WorldState en memoria.
    - Aplicar operaciones mediante WorldApplier.
    - Persistir el estado mediante WorldRepository.

    WorldService NO contiene la lógica específica de cada operación.
    """

    def __init__(
        self,
        repository: WorldRepository | None = None,
        applier: WorldApplier | None = None,
        character_applier: CharacterApplier | None = None,
        campaign_id: int = 1,
    ):
        if campaign_id is None:
            raise ValueError("campaign_id is required")

        self.campaign_id = campaign_id

        self.repository = (
            repository or WorldRepository()
        )

        self.applier = (
            applier or WorldApplier()
        )

        self.character_applier = (
            character_applier
            or CharacterApplier(
                CharacterService(
                    CharacterRepository()
                )
            )
        )

        self.world = WorldState()


    def load(self, *, conn=None) -> WorldState:
        """
        Carga el mundo de la campaña asociada a este servicio.
        """

        self.world = self.repository.load_world(
            campaign_id=self.campaign_id,
            conn=conn,
        )

        return self.world

    def save(self) -> None:
        """
        Persiste el mundo de la campaña asociada a este servicio.
        """

        self.repository.save_world(
            self.world,
            campaign_id=self.campaign_id,
        )


    def apply(
        self,
        operation,
    ) -> OperationResult:
        """
        Aplica una operación al mundo en memoria.

        No guarda automáticamente en SQLite.

        Devuelve el OperationResult producido por WorldApplier.
        """

        return self.applier.apply(
            self.world,
            operation,
        )

    def apply_operations(
        self,
        operations,
    ) -> WorldApplicationResult:
        """
        Aplica varias operaciones de forma atómica sobre WorldState.

        Las operaciones se aplican sobre una copia.

        Si alguna operación falla:

            - se descarta el estado de trabajo
            - se conserva el WorldState original
            - changed=False
            - no se persiste nada

        Si todas tienen éxito:

            - el nuevo WorldState pasa a ser el estado actual
            - changed=True si hubo operaciones
        """

        original_state = self.world

        working_state = copy.deepcopy(
            original_state
        )

        self.world = working_state

        results = []
        references = {}

        try:

            for raw_operation in operations:

                if isinstance(
                    raw_operation,
                    ReferencedOperation,
                ):
                    ref = raw_operation.ref
                    operation = raw_operation.operation
                else:
                    ref = None
                    operation = raw_operation

                operation = self._resolve_operation_references(
                    operation,
                    references,
                )

                result = self.apply(
                    operation
                )

                results.append(result)

                self._register_operation_reference(
                    ref,
                    result,
                    references,
                    self.world,
                )

                if not result.success:

                    self.world = original_state

                    return WorldApplicationResult(
                        success=False,
                        changed=False,
                        results=tuple(results),
                        world=original_state,
                    )

            changed = any(
                result.changed
                for result in results
            )

            return WorldApplicationResult(
                success=True,
                changed=changed,
                results=tuple(results),
                world=self.world,
            )

        except Exception:

            self.world = original_state

            raise

    def apply_operations_and_save(
        self,
        operations,
    ) -> WorldApplicationResult:
        """
        Aplica operaciones de forma atómica y persiste únicamente
        si el WorldState ha cambiado realmente.

        Reglas:

            0 operaciones
                -> success=True
                -> changed=False
                -> NO guarda

            todas SUCCESS
                -> success=True
                -> changed=True
                -> guarda una vez

            alguna falla
                -> success=False
                -> changed=False
                -> NO guarda

            error durante persistencia
                -> restaura la referencia original en memoria
                -> propaga la excepción
        """

        original_world = self.world

        result = self.apply_operations(
            operations
        )

        if not result.success:
            return result

        if not result.changed:
            return result

        try:
            self.save()

        except Exception:
            self.world = original_world
            raise

        return result

    def apply_turn_operations(
        self,
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

        original_world = self.world

        working_world = copy.deepcopy(
            original_world
        )

        self.world = working_world

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
                self._resolve_operation_references(
                    operation,
                    references,
                )
            )

            result = self.applier.apply(
                self.world,
                operation,
            )

            results.append(result)

            if not result.success:
                raise _WorldTurnOperationFailure(
                    results
                )

            if result.changed:
                world_operation_applied = True

            self._register_operation_reference(
                ref,
                result,
                references,
                self.world,
            )

        def apply_character_operation(
            raw_operation,
            connection,
        ):
            operation, ref = unwrap_operation(
                raw_operation
            )

            operation = (
                self._resolve_operation_references(
                    operation,
                    references,
                )
            )

            result = self.character_applier.apply(
                operation,
                campaign_id=campaign_id,
                conn=connection,
            )

            results.append(result)

            if not result.success:
                raise _WorldTurnOperationFailure(
                    results
                )

            self._register_operation_reference(
                ref,
                result,
                references,
                self.world,
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

                self.repository.save_world(
                    self.world,
                    campaign_id=self.campaign_id,
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
                self.world = original_world
                return tuple(exc.results)

            except Exception:
                self.world = original_world
                raise

        else:
            # Si el caller proporciona la conexión, también posee
            # la transacción. WorldService no debe hacer rollback:
            # el caller decidirá si confirma o revierte.
            try:
                apply_with_connection(conn)

            except _WorldTurnOperationFailure as exc:
                self.world = original_world
                return tuple(exc.results)

            except Exception:
                self.world = original_world
                raise

        # El TurnContext puede estar utilizando exactamente la misma
        # instancia de WorldState que tenía WorldService antes de
        # comenzar el turno.
        #
        # Hemos trabajado sobre una copia para mantener la atomicidad,
        # pero al completar correctamente debemos publicar el nuevo
        # estado sobre la instancia original para no romper esa
        # identidad compartida.
        original_world.entities = self.world.entities
        original_world.items = self.world.items
        original_world.item_instances = (
            self.world.item_instances
        )
        original_world.resources = self.world.resources
        original_world.resource_balances = (
            self.world.resource_balances
        )
        original_world.relations = self.world.relations
        original_world.events = self.world.events

        self.world = original_world

        return tuple(results)

    def get_world(self) -> WorldState:
        """
        Devuelve el estado actual del mundo.
        """

        return self.world

    @staticmethod
    def _resolve_operation_references(
        operation,
        references,
    ):
        """
        Sustituye OperationReference por los IDs generados por
        operaciones anteriores.
        """

        if not hasattr(operation, "__dataclass_fields__"):
            return operation

        changes = {}

        for field in fields(operation):
            value = getattr(
                operation,
                field.name,
            )

            if not isinstance(
                value,
                OperationReference,
            ):
                continue

            if value.name not in references:
                raise ValueError(
                    f"Unknown operation reference: "
                    f"${value.name}"
                )

            changes[field.name] = references[
                value.name
            ]

        if not changes:
            return operation

        return replace(
            operation,
            **changes,
        )

    @staticmethod
    def _register_operation_reference(
        ref,
        result,
        references,
        world=None,
    ):
        """
        Registra el ID generado por una operación.

        Las operaciones que pueden utilizar ReferencedOperation
        deben devolver exactamente un ID generado mediante
        OperationResult.data.

        El ID se identifica mediante cualquier clave terminada
        en "_id".
        """

        if ref is None:
            return

        if not isinstance(ref, str):
            raise TypeError(
                "Operation reference must be a string or None."
            )

        ref = ref.strip()

        if not ref:
            raise ValueError(
                "Operation reference must not be empty."
            )

        if ref in references:
            raise ValueError(
                f"Operation reference '{ref}' is already defined."
            )

        if not result.success:
            return

        data = result.data or {}

        generated_ids = [
            value
            for key, value in data.items()
            if key.endswith("_id")
        ]

        if len(generated_ids) == 1:
            references[ref] = generated_ids[0]
            return

        if len(generated_ids) > 1:
            raise ValueError(
                f"Operation reference '{ref}' produced "
                "multiple generated IDs."
            )

        raise ValueError(
            f"Operation reference '{ref}' did not "
            "produce exactly one generated ID."
        )