from __future__ import annotations

import json
from typing import Any

from operations.character_operations import CharacterOperation
from operations.turn_operations import TurnOperation
from operations.world_operations import WorldOperation

from .llm_extraction_errors import LLMExtractionError
from .operation_registry import DEFAULT_OPERATION_REGISTRY


class LLMWorldResponseParser:
    """Decode provider JSON and validate its parsed world-operation types."""

    def __init__(self, operation_parser) -> None:
        if operation_parser is None:
            raise TypeError("operation_parser is required")
        self.operation_parser = operation_parser
        self.operation_registry = (
            getattr(operation_parser, "registry", None)
            or DEFAULT_OPERATION_REGISTRY
        )

    @staticmethod
    def parse_response(raw_response: Any) -> dict[str, Any]:
        if not isinstance(raw_response, str):
            raise LLMExtractionError("LLM response must be a string")

        response = raw_response.strip()
        if not response:
            raise LLMExtractionError("LLM returned an empty response")

        if response.startswith("```"):
            lines = response.splitlines()
            if len(lines) >= 2 and lines[-1].strip() == "```":
                response = "\n".join(lines[1:-1]).strip()

        try:
            payload = json.loads(response)
        except json.JSONDecodeError as exc:
            raise LLMExtractionError("LLM response is not valid JSON") from exc

        if not isinstance(payload, dict):
            raise LLMExtractionError("LLM response must be a JSON object")

        operations = payload.get("operations")
        if operations is None:
            raise LLMExtractionError("Missing 'operations' field")
        if not isinstance(operations, list):
            raise LLMExtractionError("'operations' must be a list")

        return payload

    def parse_operations(self, payload: dict[str, Any]) -> list[TurnOperation]:
        raw_operations = payload.get("operations")
        if not isinstance(raw_operations, list):
            raise LLMExtractionError("Proposal operations must be a list")

        for index, raw_operation in enumerate(raw_operations):
            if not isinstance(raw_operation, dict):
                raise LLMExtractionError(
                    f"Invalid operation at index {index}: expected an object"
                )
            operation_type = raw_operation.get("type")
            if (
                not isinstance(operation_type, str)
                or not self.operation_registry.is_model_proposable(operation_type)
            ):
                raise LLMExtractionError(
                    f"Operation type {operation_type!r} is not permitted in model proposals"
                )

        try:
            operations = self.operation_parser.parse(payload)
        except Exception as exc:
            raise LLMExtractionError("Failed to parse operations") from exc

        if not isinstance(operations, list):
            raise LLMExtractionError(
                "Operation parser returned an invalid result"
            )

        for index, operation in enumerate(operations):
            if isinstance(operation, CharacterOperation):
                raise LLMExtractionError(
                    "Character-state operations require verified "
                    "rules-engine resolution and cannot be extracted "
                    f"from narrative (operation index {index})"
                )
            if not isinstance(operation, WorldOperation):
                raise LLMExtractionError(
                    "Operation parser returned "
                    f"invalid operation at index {index}"
                )

        return operations
