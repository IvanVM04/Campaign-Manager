import pytest
from pydantic import ValidationError

from models.schemas import ManualRollIn, TurnIn


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
