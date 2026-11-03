"""In-memory encounter turn order and round progression."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from models.combatant_state import CombatantState


class EncounterStatus(str, Enum):
    PREPARING = "preparing"
    ACTIVE = "active"
    COMPLETED = "completed"


@dataclass
class CombatEncounterState:
    """A rules-oriented encounter snapshot, independent from persistence."""

    encounter_id: str
    combatants: dict[str, CombatantState] = field(default_factory=dict)
    initiative_order: tuple[str, ...] = ()
    round_number: int = 0
    turn_index: int = 0
    status: EncounterStatus = EncounterStatus.PREPARING

    def __post_init__(self) -> None:
        if not isinstance(self.encounter_id, str) or not self.encounter_id.strip():
            raise ValueError("encounter_id must be a non-empty string")
        if not isinstance(self.status, EncounterStatus):
            self.status = EncounterStatus(self.status)
        if isinstance(self.round_number, bool) or not isinstance(self.round_number, int):
            raise TypeError("round_number must be an integer")
        if isinstance(self.turn_index, bool) or not isinstance(self.turn_index, int):
            raise TypeError("turn_index must be an integer")
        if self.round_number < 0 or self.turn_index < 0:
            raise ValueError("round_number and turn_index cannot be negative")
        if not isinstance(self.combatants, dict) or any(
            key != value.combatant_id or not isinstance(value, CombatantState)
            for key, value in self.combatants.items()
        ):
            raise TypeError("combatants must map ids to matching CombatantState values")
        self.initiative_order = tuple(self.initiative_order)
        self._validate_order()

    @classmethod
    def prepare(
        cls,
        encounter_id: str,
        combatants: tuple[CombatantState, ...],
    ) -> CombatEncounterState:
        if not isinstance(combatants, tuple) or not combatants:
            raise ValueError("an encounter requires at least one combatant")
        if any(not isinstance(item, CombatantState) for item in combatants):
            raise TypeError("combatants must contain CombatantState values")
        ids = [item.combatant_id for item in combatants]
        if len(ids) != len(set(ids)):
            raise ValueError("combatant ids must be unique")
        return cls(
            encounter_id=encounter_id,
            combatants={item.combatant_id: item for item in combatants},
        )

    def _validate_order(self) -> None:
        if not self.initiative_order:
            if self.status is not EncounterStatus.PREPARING:
                raise ValueError("active encounters require an initiative order")
            if self.round_number != 0 or self.turn_index != 0:
                raise ValueError("unstarted encounters must have zero round and turn index")
            return
        if len(self.initiative_order) != len(self.combatants):
            raise ValueError("initiative order must contain every combatant exactly once")
        if set(self.initiative_order) != set(self.combatants):
            raise ValueError("initiative order contains unknown or missing combatants")
        totals = [self.combatants[item].initiative for item in self.initiative_order]
        if totals != sorted(totals, reverse=True):
            raise ValueError("initiative order must be descending by initiative total")
        if self.turn_index >= len(self.initiative_order) and self.status is not EncounterStatus.COMPLETED:
            raise ValueError("turn_index is outside initiative order")
        if self.status is EncounterStatus.ACTIVE and self.round_number < 1:
            raise ValueError("active encounters start at round one")

    @property
    def tied_initiative_groups(self) -> tuple[tuple[str, ...], ...]:
        groups: list[list[str]] = []
        for combatant_id in sorted(
            self.combatants,
            key=lambda item: self.combatants[item].initiative,
            reverse=True,
        ):
            score = self.combatants[combatant_id].initiative
            if not groups or self.combatants[groups[-1][0]].initiative != score:
                groups.append([combatant_id])
            else:
                groups[-1].append(combatant_id)
        return tuple(tuple(group) for group in groups if len(group) > 1)

    def start(self, initiative_order: tuple[str, ...]) -> None:
        if self.status is not EncounterStatus.PREPARING:
            raise ValueError("only a preparing encounter can be started")
        if not isinstance(initiative_order, tuple):
            raise TypeError("initiative_order must be a tuple")
        if len(initiative_order) != len(self.combatants):
            raise ValueError("initiative order must contain every combatant exactly once")
        if set(initiative_order) != set(self.combatants):
            raise ValueError("initiative order contains unknown or missing combatants")
        totals = [self.combatants[item].initiative for item in initiative_order]
        if totals != sorted(totals, reverse=True):
            raise ValueError("initiative order must be descending by initiative total")
        self.initiative_order = initiative_order
        self.round_number = 1
        self.turn_index = 0
        self.status = EncounterStatus.ACTIVE

    @property
    def active_combatant(self) -> CombatantState | None:
        if self.status is not EncounterStatus.ACTIVE:
            return None
        return self.combatants[self.initiative_order[self.turn_index]]

    def advance_turn(self) -> CombatantState:
        if self.status is not EncounterStatus.ACTIVE:
            raise ValueError("cannot advance a non-active encounter")
        self.turn_index += 1
        if self.turn_index >= len(self.initiative_order):
            self.turn_index = 0
            self.round_number += 1
        return self.active_combatant

    def complete(self) -> None:
        if self.status is not EncounterStatus.ACTIVE:
            raise ValueError("only an active encounter can be completed")
        self.status = EncounterStatus.COMPLETED
