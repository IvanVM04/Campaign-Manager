"""Standalone dice-tray API, independent from turn resolution."""

from fastapi import APIRouter

from models.turn_api_schemas import DiceRollIn
from rules_engine.dnd5e_2014.core.dice import DiceRoller

router = APIRouter(prefix="/dice", tags=["dice"])


@router.post("/roll")
def roll_dice(data: DiceRollIn):
    """Roll dice without creating a turn or changing campaign state."""
    roller = DiceRoller()
    if data.sides == 20 and data.count == 1:
        result = roller.roll_d20(
            modifier=data.modifier,
            advantage=data.advantage,
            disadvantage=data.disadvantage,
        )
        return {
            "count": len(result.rolls),
            "sides": 20,
            "rolls": list(result.rolls),
            "selected": result.selected,
            "roll_mode": result.mode.value,
            "modifier": result.modifier,
            "total": result.total,
        }

    result = roller.roll(
        data.count,
        data.sides,
        modifier=data.modifier,
    )
    return {
        "count": result.count,
        "sides": result.sides,
        "rolls": list(result.rolls),
        "selected": None,
        "roll_mode": "normal",
        "modifier": result.modifier,
        "total": result.total,
    }
