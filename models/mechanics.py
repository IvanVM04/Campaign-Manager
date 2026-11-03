from dataclasses import dataclass
from enum import Enum

from rules_engine.dnd5e_2014.checks import CheckResult
from rules_engine.dnd5e_2014.core.abilities import Ability
from rules_engine.dnd5e_2014.core.skills import Skill


class MechanicsDecisionType(str, Enum):
    NONE = "none"
    CLARIFICATION = "clarification"
    ABILITY_CHECK = "ability_check"
    SKILL_CHECK = "skill_check"
    SAVING_THROW = "saving_throw"


@dataclass(frozen=True)
class MechanicsDecision:
    """Validated mechanical request proposed by the adjudicator."""

    decision: MechanicsDecisionType
    skill: Skill | None = None
    ability: Ability | None = None
    dc: int | None = None
    advantage: bool = False
    disadvantage: bool = False
    situational_modifier: int = 0
    reason: str = ""
    question: str | None = None


@dataclass(frozen=True)
class MechanicsResult:
    """Auditable result produced by the deterministic rules engine."""

    decision: MechanicsDecision
    check: CheckResult

    @property
    def outcome(self) -> str:
        return "success" if self.check.success else "failure"

    def to_prompt_text(self) -> str:
        roll = self.check.roll
        rolls = ", ".join(str(value) for value in roll.rolls)
        return (
            f"Tipo: {self.check.kind}\n"
            f"Característica: {self.check.ability.value}\n"
            f"Dado(s): [{rolls}], seleccionado: {roll.selected}\n"
            f"Modificador total: {roll.modifier:+d}\n"
            f"Total: {self.check.total}\n"
            f"CD: {self.check.dc}\n"
            f"Resultado: {self.outcome}\n"
            f"Motivo de la prueba: {self.decision.reason}"
        )
