import copy
from dataclasses import fields, replace

from models.operation_result import OperationResult
from models.world_application_result import (
    WorldApplicationResult,
)
from models.world_state import WorldState
from operations.operation_reference import OperationReference
from repositories.character_repository import (
    CharacterRepository,
)
from repositories.world_repository import (
    WorldRepository,
)
from services.characters import (
    CharacterApplier,
    CharacterService,
)

from .world_applier import (
    WorldApplier,
)
from .world_turn_operation_coordinator import WorldTurnOperationCoordinator


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
        """Apply a turn's mixed operations through the transaction coordinator."""
        return WorldTurnOperationCoordinator.apply(
            self,
            world_operations,
            character_operations,
            campaign_id=campaign_id,
            conn=conn,
            ordered_operations=ordered_operations,
        )

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