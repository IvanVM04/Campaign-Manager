"""D&D 5e (2014) conditions and exhaustion state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Condition(str, Enum):
    BLINDED = "blinded"
    CHARMED = "charmed"
    DEAFENED = "deafened"
    FRIGHTENED = "frightened"
    GRAPPLED = "grappled"
    INCAPACITATED = "incapacitated"
    INVISIBLE = "invisible"
    PARALYZED = "paralyzed"
    PETRIFIED = "petrified"
    POISONED = "poisoned"
    PRONE = "prone"
    RESTRAINED = "restrained"
    STUNNED = "stunned"
    UNCONSCIOUS = "unconscious"


@dataclass(frozen=True)
class ConditionSet:
    conditions: frozenset[Condition] = field(default_factory=frozenset)
    exhaustion_level: int = 0

    def __post_init__(self) -> None:
        try:
            normalized = frozenset(Condition(value) for value in self.conditions)
        except (TypeError, ValueError) as exc:
            raise ValueError("conditions must contain valid D&D 5e conditions") from exc
        object.__setattr__(self, "conditions", normalized)
        if (
            isinstance(self.exhaustion_level, bool)
            or not isinstance(self.exhaustion_level, int)
            or not 0 <= self.exhaustion_level <= 6
        ):
            raise ValueError("exhaustion_level must be an integer from 0 to 6")

    def has(self, condition: Condition) -> bool:
        return Condition(condition) in self.conditions

    @property
    def is_incapacitated(self) -> bool:
        return bool(
            self.conditions
            & {
                Condition.INCAPACITATED,
                Condition.PARALYZED,
                Condition.PETRIFIED,
                Condition.STUNNED,
                Condition.UNCONSCIOUS,
            }
        )

    @property
    def speed_is_zero(self) -> bool:
        return bool(
            self.conditions
            & {
                Condition.GRAPPLED,
                Condition.BLINDED,
                Condition.PETRIFIED,
                Condition.RESTRAINED,
                Condition.STUNNED,
                Condition.UNCONSCIOUS,
            }
        )

    @property
    def automatically_fails_strength_and_dexterity_saves(self) -> bool:
        return bool(
            self.conditions
            & {
                Condition.PARALYZED,
                Condition.PETRIFIED,
                Condition.STUNNED,
                Condition.UNCONSCIOUS,
            }
        )

    @property
    def attacks_against_have_advantage(self) -> bool:
        return bool(
            self.conditions
            & {
                Condition.PARALYZED,
                Condition.PETRIFIED,
                Condition.RESTRAINED,
                Condition.STUNNED,
                Condition.UNCONSCIOUS,
            }
        )

    @property
    def attacks_against_have_advantage_within_5_feet(self) -> bool:
        return self.has(Condition.PRONE) or self.has(Condition.PARALYZED)

    @property
    def attacks_have_disadvantage(self) -> bool:
        return bool(
            self.conditions
            & {
                Condition.BLINDED,
                Condition.POISONED,
                Condition.RESTRAINED,
                Condition.PRONE,
            }
        ) or self.exhaustion_level >= 3

    @property
    def ability_checks_have_disadvantage(self) -> bool:
        return self.has(Condition.POISONED) or self.exhaustion_level >= 1

    @property
    def saving_throws_have_disadvantage(self) -> bool:
        return self.has(Condition.POISONED) or self.exhaustion_level >= 3

    @property
    def speed_halved(self) -> bool:
        return self.exhaustion_level >= 2

    @property
    def hit_point_maximum_halved(self) -> bool:
        return self.exhaustion_level >= 4

    @property
    def dies_at_exhaustion_six(self) -> bool:
        return self.exhaustion_level == 6


def attack_roll_advantage_state(
    *,
    attacker: ConditionSet,
    target: ConditionSet,
    target_within_5_feet: bool,
    attacker_can_see_target: bool = True,
    target_can_see_attacker: bool = True,
    frightened_source_visible: bool = False,
) -> tuple[bool, bool]:
    """Return (advantage, disadvantage), preserving 5e cancellation rules."""
    if not isinstance(attacker, ConditionSet) or not isinstance(target, ConditionSet):
        raise TypeError("attacker and target must be ConditionSet values")
    if not isinstance(target_within_5_feet, bool):
        raise TypeError("target_within_5_feet must be a boolean")
    if not isinstance(attacker_can_see_target, bool) or not isinstance(target_can_see_attacker, bool):
        raise TypeError("visibility flags must be booleans")
    if not isinstance(frightened_source_visible, bool):
        raise TypeError("frightened_source_visible must be a boolean")

    advantage = target.attacks_against_have_advantage
    if target_within_5_feet and target.attacks_against_have_advantage_within_5_feet:
        advantage = True
    if attacker.has(Condition.INVISIBLE):
        advantage = True
    if not target_can_see_attacker:
        advantage = True

    disadvantage = attacker.attacks_have_disadvantage
    if attacker.has(Condition.BLINDED) or not attacker_can_see_target:
        disadvantage = True
    if attacker.has(Condition.FRIGHTENED) and frightened_source_visible:
        disadvantage = True
    if target.has(Condition.INVISIBLE) or not attacker_can_see_target:
        disadvantage = True
    if target.has(Condition.PRONE) and not target_within_5_feet:
        disadvantage = True
    if attacker.exhaustion_level >= 3:
        disadvantage = True
    return advantage, disadvantage
