import pytest
from pydantic import ValidationError

from models.schemas import ManualRollIn, SillyTavernManualRollIn, SillyTavernTurnResolveIn, TurnIn


def test_turn_schema_defaults_to_automatic_dice():
    turn = TurnIn(player_input="Intento abrir la puerta.")
    assert turn.dice_mode == "automatic"


def test_turn_schema_accepts_manual_dice_mode():
    turn = TurnIn(player_input="Intento abrir la puerta.", dice_mode="manual")
    assert turn.dice_mode == "manual"


def test_turn_schema_rejects_unknown_dice_mode():
    with pytest.raises(ValidationError):
        TurnIn(player_input="Intento abrir la puerta.", dice_mode="random")


@pytest.mark.parametrize("rolls", [[0], [21], [1, 2, 3], [True], ["12"]])
def test_manual_roll_schema_rejects_invalid_results(rolls):
    with pytest.raises(ValidationError):
        ManualRollIn(pending_roll_id="a" * 24, rolls=rolls)


def test_manual_roll_schema_accepts_one_or_two_d20_values():
    one = ManualRollIn(pending_roll_id="a" * 24, rolls=[13])
    two = ManualRollIn(pending_roll_id="b" * 24, rolls=[4, 19])

    assert one.rolls == [13]
    assert two.rolls == [4, 19]


def test_silly_tavern_turn_resolve_schema_defaults_to_automatic_mode():
    request = SillyTavernTurnResolveIn(
        player_input="Me escondo.",
        external_turn_id="turn-" + "a" * 24,
        query="Estado de la campaña.",
    )
    assert request.dice_mode == "automatic"


def test_silly_tavern_turn_resolve_schema_accepts_manual_mode():
    request = SillyTavernTurnResolveIn(
        player_input="Me escondo.",
        external_turn_id="turn-" + "b" * 24,
        query="Estado de la campaña.",
        dice_mode="manual",
    )
    assert request.dice_mode == "manual"


def test_silly_tavern_manual_roll_schema_accepts_valid_roll_submission():
    request = SillyTavernManualRollIn(
        pending_roll_id="42:" + "c" * 24,
        rolls=[7, 18],
        query="Estado de la campaña.",
        answer_external_turn_id="answer-" + "d" * 24,
    )
    assert request.rolls == [7, 18]


@pytest.mark.parametrize("rolls", [[0], [21], [2, 3, 4], [True], ["12"]])
def test_silly_tavern_manual_roll_schema_rejects_invalid_roll_submission(rolls):
    with pytest.raises(ValidationError):
        SillyTavernManualRollIn(
            pending_roll_id="42:" + "c" * 24,
            rolls=rolls,
            query="Estado de la campaña.",
            answer_external_turn_id="answer-" + "d" * 24,
        )
