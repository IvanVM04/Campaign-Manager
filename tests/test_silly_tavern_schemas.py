import pytest
from pydantic import ValidationError

from models.schemas import (
    SillyTavernClarificationIn,
    SillyTavernContextIn,
    SillyTavernTurnCompleteIn,
)


def test_silly_tavern_clarification_schema_requires_stable_answer_identity():
    data = SillyTavernClarificationIn(
        pending_clarification_id="42:challenge-token-long-enough",
        answer="La puerta de roble.",
        answer_external_turn_id="stable-answer-message-id",
        query="Estado actual de la campaña.",
    )
    assert data.answer_external_turn_id == "stable-answer-message-id"


def test_silly_tavern_context_schema_strips_query():
    data = SillyTavernContextIn(query="  Entro en la taberna.  ")
    assert data.query == "Entro en la taberna."


def test_silly_tavern_context_schema_rejects_empty_query():
    with pytest.raises(ValidationError):
        SillyTavernContextIn(query="   ")


def test_silly_tavern_completion_requires_external_turn_identity():
    with pytest.raises(ValidationError):
        SillyTavernTurnCompleteIn(
            player_input="Abro la puerta.",
            narrative="La puerta se abre.",
        )


def test_silly_tavern_completion_strips_required_identity_and_text():
    data = SillyTavernTurnCompleteIn(
        player_input="  Abro la puerta.  ",
        narrative="  La puerta se abre.  ",
        external_turn_id="  external-turn-123  ",
    )
    assert data.player_input == "Abro la puerta."
    assert data.narrative == "La puerta se abre."
    assert data.external_turn_id == "external-turn-123"


def test_silly_tavern_completion_rejects_empty_external_turn_identity():
    with pytest.raises(ValidationError):
        SillyTavernTurnCompleteIn(
            player_input="Abro la puerta.",
            narrative="La puerta se abre.",
            external_turn_id="   ",
        )
