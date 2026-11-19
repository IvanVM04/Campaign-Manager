"""Shared offset-preserving text and transcript primitives for discourse stages."""

from __future__ import annotations

import re
import unicodedata


class DiscourseText:
    @staticmethod
    def _entity_value(entity: object, field: str, default=None):
        if isinstance(entity, dict):
            return entity.get(field, default)
        return getattr(entity, field, default)

    @staticmethod
    def _turn_fields(turn: object) -> tuple[str, str, int | None]:
        if isinstance(turn, dict):
            player_input, narrative, turn_id = (
                turn.get("player_input", ""), turn.get("narrative", ""), turn.get("id")
            )
        else:
            player_input = getattr(turn, "player_input", "")
            narrative = getattr(turn, "narrative", "")
            turn_id = getattr(turn, "id", None)
        return (
            player_input if isinstance(player_input, str) else "",
            narrative if isinstance(narrative, str) else "",
            turn_id if isinstance(turn_id, int) and not isinstance(turn_id, bool) and turn_id > 0 else None,
        )

    @staticmethod
    def normalize(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value.casefold())
        return " ".join(
            "".join(ch for ch in decomposed if not unicodedata.combining(ch)).split()
        )

    @staticmethod
    def _without_quoted_spans(value: str) -> str:
        """Remove quoted text before detecting discourse-control markers.

        A phrase mentioned as dialogue is evidence about what someone said,
        not an instruction to change the current topic or repeat an action.
        """
        return re.sub(
            r"«[^»]*»|“[^”]*”|\"[^\"]*\"|'[^']*'",
            " ",
            value,
        )

    @staticmethod
    def _mask_quoted_spans(value: str) -> str:
        """Mask quoted text without changing offsets in the source utterance."""
        return re.sub(
            r"«[^»]*»|“[^”]*”|\"[^\"]*\"|'[^']*'",
            lambda match: " " * len(match.group(0)),
            value,
        )
