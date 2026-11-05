from __future__ import annotations

import json
from typing import Any

from operations.character_operations import CharacterOperation
from operations.turn_operations import TurnOperation
from operations.world_operations import WorldOperation

from .llm_extraction_errors import LLMExtractionError


class LLMWorldResponseParser:
    """Decode provider JSON and validate its parsed world-operation types."""

    def __init__(self, operation_parser) -> None:
        if operation_parser is None:
            raise TypeError("operation_parser is required")
        self.operation_parser = operation_parser

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
