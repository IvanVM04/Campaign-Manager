from __future__ import annotations

from dataclasses import dataclass

from models.mechanics import MechanicsResult
from operations.character_operations import (
    CharacterOperation,
)
from operations.world_operations import WorldOperation


@dataclass(frozen=True)
class TurnResolutionResult:
    """
    Resultado completo de la resolución de un turno.

    Contiene:

    - entrada del jugador
    - narrativa generada por el DM
    - operaciones detectadas por el extractor
    - resultado de aplicar las operaciones

    En caso de una repetición idempotente, las operaciones no se
    vuelven a ejecutar. En ese caso se utilizan los metadatos
    persistidos del TurnRecord.
    """

    player_input: str
    narrative: str

    operations: tuple[WorldOperation, ...] = ()

    character_operations: tuple[
        CharacterOperation,
        ...
    ] = ()

    operation_results: tuple = ()

    mechanics_result: MechanicsResult | None = None

    pending_roll_id: str | None = None
    pending_roll: dict | None = None
    pending_clarification_id: str | None = None

    already_processed: bool = False

    persisted_operation_count: int | None = None

    persisted_successful_operation_count: int | None = None

    persisted_failed_operation_count: int | None = None

    persisted_all_operations_succeeded: bool | None = None

    persisted_world_changed: bool | None = None

    @classmethod
    def from_persisted_turn(
        cls,
        turn,
    ) -> TurnResolutionResult:
        """
        Reconstruye la representación de un turno ya persistido.

        No vuelve a ejecutar ninguna operación.
        """

        return cls(
            player_input=turn.player_input,
            narrative=turn.narrative,
            already_processed=True,
            persisted_operation_count=(
                turn.operation_count
            ),
            persisted_successful_operation_count=(
                turn.successful_operation_count
            ),
            persisted_failed_operation_count=(
                turn.failed_operation_count
            ),
            persisted_all_operations_succeeded=(
                turn.all_operations_succeeded
            ),
            persisted_world_changed=(
                turn.world_changed
            ),
        )

    @property
    def world_changed(self) -> bool:
        """
        Indica si el turno produjo algún cambio confirmado.
        """

        if self.already_processed:
            return bool(
                self.persisted_world_changed
            )

        if self.operation_count == 0:
            return False

        if (
            len(self.operation_results)
            != self.operation_count
        ):
            return False

        if not self.all_operations_succeeded:
            return False

        return any(
            self._result_changed(result)
            for result in self.operation_results
        )

    @staticmethod
    def _result_changed(result) -> bool:
        """
        Obtiene si un resultado representa un cambio.
        """

        return bool(
            getattr(
                result,
                "changed",
                False,
            )
        )

    @property
    def all_operations_succeeded(self) -> bool:
        """
        Indica si todas las operaciones detectadas
        fueron aplicadas correctamente.
        """

        if self.already_processed:
            return bool(
                self.persisted_all_operations_succeeded
            )

        if (
            len(self.operation_results)
            != self.operation_count
        ):
            return False

        return all(
            self._result_success(result)
            for result in self.operation_results
        )

    @property
    def operation_count(self) -> int:
        """
        Número total de operaciones detectadas.
        """

        if self.already_processed:
            return int(
                self.persisted_operation_count or 0
            )

        return (
            len(self.operations)
            + len(self.character_operations)
        )

    @property
    def successful_operation_count(self) -> int:
        """
        Número de operaciones aplicadas correctamente.
        """

        if self.already_processed:
            return int(
                self.persisted_successful_operation_count
                or 0
            )

        return sum(
            self._result_success(result)
            for result in self.operation_results
        )

    @property
    def failed_operation_count(self) -> int:
        """
        Número de operaciones que no se aplicaron correctamente.
        """

        if self.already_processed:
            return int(
                self.persisted_failed_operation_count
                or 0
            )

        return sum(
            not self._result_success(result)
            for result in self.operation_results
        )

    @property
    def response(self) -> str:
        """
        Alias semántico para la narrativa.
        """

        return self.narrative

    @staticmethod
    def _result_success(result) -> bool:
        """
        Obtiene si un resultado representa una operación exitosa.
        """

        return bool(
            getattr(
                result,
                "success",
                False,
            )
        )