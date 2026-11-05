"""Backward-compatible imports for character services."""

from services.characters.character_service import (
    CharacterService,
    CharacterServiceError,
)

__all__ = ["CharacterService", "CharacterServiceError"]
