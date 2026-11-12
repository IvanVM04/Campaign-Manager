from __future__ import annotations

import json
from dataclasses import MISSING
from typing import Any, ClassVar

from operations.operation_reference import OperationReference
from operations.referenced_operation import ReferencedOperation
from operations.turn_operations import TurnOperation

from .operation_registry import (
    DEFAULT_OPERATION_REGISTRY,
    OperationMetadataRegistry,
)


class OperationParseError(ValueError):
    """Raised when an LLM response cannot be converted safely to operations."""


class OperationParser:
    """
    Converts structured output produced by the narrative/LLM layer into
    concrete WorldOperation instances.

    This class performs structural/type normalization only.

    It does NOT inspect WorldState and therefore does not check whether
    referenced entities, items, resources, etc. actually exist.

    Semantic validation belongs to WorldApplier / WorldService.
    """

    _BUILDERS: ClassVar = DEFAULT_OPERATION_REGISTRY.builders

    def __init__(
        self,
        registry: OperationMetadataRegistry = DEFAULT_OPERATION_REGISTRY,
    ) -> None:
        self.registry = registry

    def model_proposable_operation_types(self) -> tuple[str, ...]:
        """Return the explicitly model-proposable operation types."""
        return self.registry.model_proposable_operation_types()

    def parse(
        self,
        payload: str | dict[str, Any],
    ) -> list[TurnOperation | ReferencedOperation]:
        """Parse operations, retaining explicit references for ordered resolution."""

        data = self._decode(payload)

        if not isinstance(data, dict):
            raise OperationParseError("Root JSON must be an object.")

        operations = data.get("operations")

        if not isinstance(operations, list):
            raise OperationParseError("'operations' must be a list.")

        result: list[TurnOperation | ReferencedOperation] = []

        for index, raw_operation in enumerate(operations):
            try:
                operation = self._parse_operation(raw_operation)

                ref = raw_operation.get("ref")

                if ref is not None:
                    if (
                        not isinstance(ref, str)
                        or not ref.strip()
                    ):
                        raise OperationParseError(
                            "'ref' must be a non-empty string."
                        )

                    operation = ReferencedOperation(
                        operation=operation,
                        ref=ref.strip(),
                    )

                result.append(operation)

            except OperationParseError as exc:
                raise OperationParseError(
                    f"Invalid operation at index {index}: {exc}"
                ) from exc

        return result

    # ------------------------------------------------------------------
    # JSON decoding
    # ------------------------------------------------------------------

    def _decode(self, payload: str | dict[str, Any]) -> Any:

        if isinstance(payload, dict):
            return payload

        if not isinstance(payload, str):
            raise OperationParseError(
                "Payload must be a JSON string or dict."
            )

        try:
            return json.loads(payload)

        except json.JSONDecodeError as exc:
            raise OperationParseError(
                "Invalid JSON payload."
            ) from exc

    # ------------------------------------------------------------------
    # Operation parsing
    # ------------------------------------------------------------------

    def _parse_operation(
        self,
        raw: Any,
    ) -> TurnOperation:

        if not isinstance(raw, dict):
            raise OperationParseError(
                "Operation must be an object."
            )

        operation_type = raw.get("type")

        if not isinstance(operation_type, str) or not operation_type:
            raise OperationParseError(
                "Operation requires a non-empty 'type'."
            )

        metadata = self.registry.get(operation_type)

        if metadata is None:
            raise OperationParseError(
                f"Unknown operation type: {operation_type!r}."
            )

        builder = metadata.operation_class
        fields = dict(raw)

        fields.pop("type", None)
        fields.pop("ref", None)

        expected = {
            field.name: field
            for field in metadata.dataclass_fields
        }

        # --------------------------------------------------------------
        # Unknown fields
        # --------------------------------------------------------------

        unknown = set(fields) - set(expected)

        if unknown:
            names = ", ".join(sorted(unknown))

            raise OperationParseError(
                f"Unknown field(s) for {operation_type}: {names}."
            )

        # --------------------------------------------------------------
        # Missing required fields
        # --------------------------------------------------------------

        missing = [
            name
            for name, field in expected.items()
            if (
                field.default is MISSING
                and field.default_factory is MISSING
                and name not in fields
            )
        ]

        if missing:
            raise OperationParseError(
                f"Missing required field(s) for {operation_type}: "
                + ", ".join(missing)
                + "."
            )

        # --------------------------------------------------------------
        # Normalize entity IDs
        # --------------------------------------------------------------

        self._normalize_entity_ids(
            operation_type,
            fields,
        )

        # --------------------------------------------------------------
        # Validate fields
        # --------------------------------------------------------------

        self._validate_fields(
            operation_type,
            fields,
        )

        # --------------------------------------------------------------
        # Build operation
        # --------------------------------------------------------------

        try:
            return builder(**fields)

        except (TypeError, ValueError) as exc:
            raise OperationParseError(
                f"Invalid fields for {operation_type}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Entity ID normalization
    # ------------------------------------------------------------------

    def _normalize_entity_ids(
        self,
        operation_type: str,
        fields: dict[str, Any],
    ) -> None:
        """
        Normalize all ID fields represented as integers.

        Supports references to IDs generated by previous
        operations using the "$reference_name" syntax.

        This performs structural/type normalization only.

        It does NOT check whether referenced records exist.
        Semantic validation belongs to WorldApplier / WorldService.
        """

        metadata = self.registry.get(operation_type)
        id_fields = metadata.reference_fields if metadata is not None else ()

        for field_name in id_fields:
            if field_name not in fields:
                continue

            value = fields[field_name]

            if value is None:
                continue

            if (
                isinstance(value, str)
                and value.startswith("$")
            ):
                reference_name = value[1:].strip()

                if not reference_name:
                    raise OperationParseError(
                        "Operation reference cannot be empty."
                    )

                fields[field_name] = OperationReference(
                    reference_name
                )

            else:
                fields[field_name] = self._parse_entity_id(
                    value
                )

    def _parse_entity_id(
        self,
        value: Any,
    ) -> int:
        """
        Convert an entity ID from an integer or numeric string to int.
        """

        if isinstance(value, bool):
            raise OperationParseError(
                "Entity ID must be an integer or numeric string."
            )

        if isinstance(value, int):
            return value

        if isinstance(value, str):
            value = value.strip()

            if not value:
                raise OperationParseError(
                    "Entity ID cannot be empty."
                )

            try:
                return int(value)

            except ValueError as exc:
                raise OperationParseError(
                    f"Invalid entity ID: {value!r}."
                ) from exc

        raise OperationParseError(
            f"Invalid entity ID type: {type(value).__name__}."
        )

    # ------------------------------------------------------------------
    # Generic field validation
    # ------------------------------------------------------------------

    def _validate_fields(
        self,
        operation_type: str,
        fields: dict[str, Any],
    ) -> None:

        aliases = fields.get("aliases")
        if aliases is not None:
            if not isinstance(aliases, list):
                raise OperationParseError("'aliases' must be a list of strings.")
            if len(aliases) > 20:
                raise OperationParseError("'aliases' cannot contain more than 20 entries.")
            normalized_aliases: list[str] = []
            seen_aliases: set[str] = set()
            for alias in aliases:
                if not isinstance(alias, str):
                    raise OperationParseError("'aliases' must contain only strings.")
                value = alias.strip()
                if not value or len(value) > 100:
                    raise OperationParseError(
                        "Each alias must contain 1 to 100 non-whitespace characters."
                    )
                key = value.casefold()
                if key not in seen_aliases:
                    seen_aliases.add(key)
                    normalized_aliases.append(value)
            fields["aliases"] = normalized_aliases

        metadata = self.registry.get(operation_type)
        integer_fields = metadata.reference_fields if metadata is not None else ()

        for name in integer_fields:
            if name not in fields:
                continue

            value = fields[name]

            if value is None:
                continue

            if isinstance(value, OperationReference):
                continue

            if isinstance(value, bool):
                raise OperationParseError(
                    f"'{name}' must be an integer."
                )

            if not isinstance(value, int):
                raise OperationParseError(
                    f"'{name}' must be an integer."
                )

        # --------------------------------------------------------------
        # Amount
        # --------------------------------------------------------------

        amount = fields.get("amount")

        if amount is not None:
            if operation_type == "change_character_hp":
                if (
                    isinstance(amount, bool)
                    or not isinstance(amount, int)
                ):
                    raise OperationParseError(
                        "'amount' must be an integer."
                    )
            else:
                if (
                    not isinstance(amount, (int, float))
                    or isinstance(amount, bool)
                ):
                    raise OperationParseError(
                        "'amount' must be a number."
                    )

        # --------------------------------------------------------------
        # Metadata
        # --------------------------------------------------------------

        metadata = fields.get("metadata")

        if (
            metadata is not None
            and not isinstance(metadata, dict)
        ):
            raise OperationParseError(
                "'metadata' must be an object or null."
            )

        # --------------------------------------------------------------
        # Active
        # --------------------------------------------------------------

        if "active" in fields:
            active = fields["active"]

            if (
                active is not None
                and not isinstance(active, bool)
            ):
                raise OperationParseError(
                    "'active' must be boolean or null."
                )

        # --------------------------------------------------------------
        # Secret
        # --------------------------------------------------------------

        if "secret" in fields:
            secret = fields["secret"]

            if not isinstance(secret, bool):
                raise OperationParseError(
                    "'secret' must be boolean."
                )

        # --------------------------------------------------------------
        # String fields
        # --------------------------------------------------------------

        string_fields = {
            "name",
            "entity_type",
            "description",
            "notes",
            "significance",
            "weapon_key",
            "armor_key",
            "equipment_slot",
            "resource_type",
            "unit",
            "condition",
            "relation_id",
            "relation_type",
            "event_id",
            "event_type",
            "title",
            "consequences",
        }

        # --------------------------------------------------------------
        # Entity name
        # --------------------------------------------------------------

        if operation_type == "create_entity":
            name = fields.get("name")

            if (
                not isinstance(name, str)
                or not name.strip()
            ):
                raise OperationParseError(
                    "'name' is required for create_entity."
                )

            fields["name"] = name.strip()

        for name in string_fields:
            if name not in fields:
                continue

            value = fields[name]

            if (
                value is not None
                and not isinstance(value, str)
            ):
                raise OperationParseError(
                    f"'{name}' must be a string or null."
                )

        if operation_type == "change_character_hp":
            entity_id = fields.get("entity_id")
            amount = fields.get("amount")

            if isinstance(
                entity_id,
                OperationReference,
            ):
                pass
            elif (
                isinstance(entity_id, bool)
                or not isinstance(entity_id, int)
            ):
                raise OperationParseError(
                    "'entity_id' must be an integer."
                )

            if (
                isinstance(amount, bool)
                or not isinstance(amount, int)
            ):
                raise OperationParseError(
                    "'amount' must be an integer."
                )