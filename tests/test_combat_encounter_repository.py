import pytest

from database import get_conn
from models.combat_encounter_state import CombatEncounterState, EncounterStatus
from models.combatant_state import CombatantState
from repositories.combat_encounter_repository import CombatEncounterRepository
from rules_engine.dnd5e_2014.combat.conditions import Condition, ConditionSet


def make_encounter():
    return CombatEncounterState.prepare(
        "encounter-1",
        (
            CombatantState(
                "hero", "Hero", 18, 12, 12, 16, entity_id=1,
                is_player_character=True,
                conditions=ConditionSet(frozenset({Condition.POISONED}), 2),
            ),
            CombatantState("goblin", "Goblin", 12, 7, 7, 15),
        ),
    )


def test_save_and_reload_round_trips_full_encounter_state():
    repository = CombatEncounterRepository()
    encounter = make_encounter()
    encounter.start(("hero", "goblin"))

    saved = repository.save(encounter, campaign_id=1)
    loaded = repository.get("encounter-1", campaign_id=1)

    assert saved == loaded
    assert loaded is not None
    assert loaded.status is EncounterStatus.ACTIVE
    assert loaded.active_combatant.combatant_id == "hero"
    assert loaded.combatants["hero"].conditions.conditions == frozenset({Condition.POISONED})
    assert loaded.combatants["hero"].conditions.exhaustion_level == 2


def test_encounters_are_isolated_by_campaign():
    repository = CombatEncounterRepository()
    repository.save(make_encounter(), campaign_id=1)

    assert repository.get("encounter-1", campaign_id=2) is None
    assert repository.list_for_campaign(2) == []


def test_save_uses_supplied_connection_and_rolls_back_atomically():
    repository = CombatEncounterRepository()
    encounter = make_encounter()

    with pytest.raises(RuntimeError, match="rollback"):
        with get_conn() as conn:
            repository.save(encounter, campaign_id=1, conn=conn)
            assert repository.get("encounter-1", campaign_id=1, conn=conn) is not None
            raise RuntimeError("rollback")

    assert repository.get("encounter-1", campaign_id=1) is None


def test_list_and_delete_are_campaign_scoped():
    repository = CombatEncounterRepository()
    repository.save(make_encounter(), campaign_id=1)

    assert [item.encounter_id for item in repository.list_for_campaign(1)] == ["encounter-1"]
    assert repository.delete("encounter-1", campaign_id=2) is True
    assert repository.get("encounter-1", campaign_id=1) is not None
    assert repository.delete("encounter-1", campaign_id=1) is True
    assert repository.get("encounter-1", campaign_id=1) is None
