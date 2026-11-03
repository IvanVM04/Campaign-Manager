import pytest

from models.combat_encounter_state import (
    CombatEncounterState,
    EncounterStatus,
)
from models.combatant_state import CombatantState


def make_combatants():
    return (
        CombatantState("hero", "Aventurero", 18, 12, 12, 16, entity_id=1, is_player_character=True),
        CombatantState("goblin-a", "Goblin A", 15, 7, 7, 15),
        CombatantState("goblin-b", "Goblin B", 15, 7, 7, 15),
    )


def test_prepare_encounter_does_not_start_combat_implicitly():
    encounter = CombatEncounterState.prepare("enc-1", make_combatants())

    assert encounter.status is EncounterStatus.PREPARING
    assert encounter.round_number == 0
    assert encounter.active_combatant is None
    assert encounter.tied_initiative_groups == (("goblin-a", "goblin-b"),)


def test_start_requires_explicit_order_for_tied_initiative():
    encounter = CombatEncounterState.prepare("enc-1", make_combatants())

    with pytest.raises(ValueError, match="descending"):
        encounter.start(("goblin-a", "hero", "goblin-b"))

    encounter.start(("hero", "goblin-b", "goblin-a"))

    assert encounter.status is EncounterStatus.ACTIVE
    assert encounter.round_number == 1
    assert encounter.active_combatant.combatant_id == "hero"


def test_turn_advancement_wraps_and_increments_round():
    encounter = CombatEncounterState.prepare("enc-1", make_combatants())
    encounter.start(("hero", "goblin-a", "goblin-b"))

    assert encounter.advance_turn().combatant_id == "goblin-a"
    assert encounter.advance_turn().combatant_id == "goblin-b"
    assert encounter.advance_turn().combatant_id == "hero"
    assert encounter.round_number == 2


def test_completed_encounter_has_no_active_combatant():
    encounter = CombatEncounterState.prepare("enc-1", make_combatants())
    encounter.start(("hero", "goblin-a", "goblin-b"))
    encounter.complete()

    assert encounter.status is EncounterStatus.COMPLETED
    assert encounter.active_combatant is None
    with pytest.raises(ValueError, match="non-active"):
        encounter.advance_turn()


def test_prepare_rejects_duplicate_combatant_ids():
    duplicate = CombatantState("hero", "Duplicate", 10, 5, 5, 10)
    with pytest.raises(ValueError, match="unique"):
        CombatEncounterState.prepare("enc-1", (make_combatants()[0], duplicate))


def test_encounter_rejects_order_missing_combatants():
    encounter = CombatEncounterState.prepare("enc-1", make_combatants())
    with pytest.raises(ValueError, match="every combatant"):
        encounter.start(("hero", "goblin-a"))


def test_action_is_reset_when_combatant_turn_begins():
    from dataclasses import replace

    encounter = CombatEncounterState.prepare("enc-action", make_combatants())
    encounter.start(("hero", "goblin-a", "goblin-b"))
    encounter.combatants["hero"] = replace(encounter.combatants["hero"], action_used=True)
    encounter.advance_turn()
    encounter.advance_turn()
    active = encounter.advance_turn()
    assert active.combatant_id == "hero"
    assert active.action_used is False
