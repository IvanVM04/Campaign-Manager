from __future__ import annotations

from dataclasses import dataclass

VALID_STATUSES = frozenset(
    {
        "active",
        "superseded",
        "failed",
    }
)


@dataclass(frozen=True)
class TurnRecord:
    """
    Registro persistente de un turno de campaña.

    Contiene únicamente información histórica del turno.
    El WorldState continúa siendo la fuente de verdad.

    external_turn_id identifica el turno original en el sistema
    externo que lo generó, por ejemplo SillyTavern.
    """

    id: int | None = None
    session_id: int | None = None

    player_input: str = ""
    narrative: str = ""

    operation_count: int = 0
    successful_operation_count: int = 0
    failed_operation_count: int = 0

    all_operations_succeeded: bool = True
    world_changed: bool = False

    created_at: str | None = None

    external_turn_id: str | None = None

    version: int = 1
    status: str = "active"

    def __post_init__(self) -> None:
        self._validate_optional_positive_int(
            self.id,
            "id",
        )

        self._validate_optional_positive_int(
            self.session_id,
            "session_id",
        )

        if (
            not isinstance(self.version, int)
            or isinstance(self.version, bool)
        ):
            raise TypeError(
                "version must be an integer"
            )

        if not isinstance(
            self.status,
            str,
        ):
            raise TypeError(
                "status must be a string"
            )

        if self.status not in VALID_STATUSES:
            raise ValueError(
                "status must be one of: "
                "active, superseded, failed"
            )

        if self.version < 1:
            raise ValueError(
                "version must be greater than zero"
            )

        if not isinstance(
            self.player_input,
            str,
        ):
            raise TypeError(
                "player_input must be a string"
            )

        if not isinstance(
            self.narrative,
            str,
        ):
            raise TypeError(
                "narrative must be a string"
            )

        self._validate_non_negative_int(
            self.operation_count,
            "operation_count",
        )

        self._validate_non_negative_int(
            self.successful_operation_count,
            "successful_operation_count",
        )

        self._validate_non_negative_int(
            self.failed_operation_count,
            "failed_operation_count",
        )

        if not isinstance(
            self.all_operations_succeeded,
            bool,
        ):
            raise TypeError(
                "all_operations_succeeded must be a boolean"
            )

        if not isinstance(
            self.world_changed,
            bool,
        ):
            raise TypeError(
                "world_changed must be a boolean"
            )

        if self.created_at is not None and not isinstance(
            self.created_at,
            str,
        ):
            raise TypeError(
                "created_at must be a string or None"
            )

        if self.external_turn_id is not None:
            if not isinstance(
                self.external_turn_id,
                str,
            ):
                raise TypeError(
                    "external_turn_id must be a string or None"
                )

            if not self.external_turn_id.strip():
                raise ValueError(
                    "external_turn_id must not be empty"
                )

            if len(self.external_turn_id) > 500:
                raise ValueError(
                    "external_turn_id must not be longer than 500 characters"
                )

        if (
            self.successful_operation_count
            + self.failed_operation_count
            != self.operation_count
        ):
            raise ValueError(
                "successful_operation_count + "
                "failed_operation_count must equal "
                "operation_count"
            )

        expected_all_succeeded = (
            self.failed_operation_count == 0
        )

        if (
            self.all_operations_succeeded
            != expected_all_succeeded
        ):
            raise ValueError(
                "all_operations_succeeded is inconsistent "
                "with failed_operation_count"
            )

    @staticmethod
    def _validate_optional_positive_int(
        value,
        field_name: str,
    ) -> None:
        if value is None:
            return

        if (
            not isinstance(value, int)
            or isinstance(value, bool)
        ):
            raise TypeError(
                f"{field_name} must be an integer or None"
            )

        if value < 1:
            raise ValueError(
                f"{field_name} must be greater than zero"
            )

    @staticmethod
    def _validate_non_negative_int(
        value,
        field_name: str,
    ) -> None:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
        ):
            raise TypeError(
                f"{field_name} must be an integer"
            )

        if value < 0:
            raise ValueError(
                f"{field_name} must not be negative"
            )