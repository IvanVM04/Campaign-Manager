"""Backward-compatible import for the character operation applier."""

from services.characters.character_applier import (
    CharacterApplier,
    CharacterApplierError,
)

__all__ = ["CharacterApplier", "CharacterApplierError"]
