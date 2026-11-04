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
    assert loaded.combatants["hero"].dexterity == 10
    assert loaded.combatants["hero"].reaction_used is False


def test_encounters_are_isolated_by_campaign():
    repository = CombatEncounterRepository()
    repository.save(make_encounter(), campaign_id=1)

    assert repository.get("encounter-1", campaign_id=2) is None
    assert repository.list_for_campaign(2) == []


def test_save_uses_supplied_connection_and_rolls_back_atomically():
    repository = CombatEncounterRepository()
    encounter = make_encounter()

    with pytest.raises(RuntimeError, match="rollback"), get_conn() as conn:
        repository.save(encounter, campaign_id=1, conn=conn)
        assert repository.get("encounter-1", campaign_id=1, conn=conn) is not None
        raise RuntimeError("rollback")

    assert repository.get("encounter-1", campaign_id=1) is None


def test_list_and_delete_are_campaign_scoped():
    repository = CombatEncounterRepository()
    repository.save(make_encounter(), campaign_id=1)

    assert [item.encounter_id for item in repository.list_for_campaign(1)] == ["encounter-1"]
    assert repository.delete("encounter-1", campaign_id=2) is False
    assert repository.get("encounter-1", campaign_id=1) is not None
    assert repository.delete("encounter-1", campaign_id=1) is True
    assert repository.get("encounter-1", campaign_id=1) is None


def test_deserialize_legacy_snapshot_without_death_save_fields():
    import json

    row = {
        "encounter_id": "legacy-encounter",
        "status": "preparing",
        "round_number": 0,
        "turn_index": 0,
        "initiative_order": "[]",
        "combatants": json.dumps({
            "hero": {
                "name": "Hero",
                "initiative": 0,
                "current_hp": 12,
                "max_hp": 12,
                "armor_class": 16,
            },
            "stable_hero": {
                "name": "Stable Hero",
                "initiative": 0,
                "current_hp": 0,
                "max_hp": 12,
                "armor_class": 16,
                "stable": True,
            }
        }),
    }

    loaded = CombatEncounterRepository._deserialize(row)
    hero = loaded.combatants["hero"]
    stable_hero = loaded.combatants["stable_hero"]

    assert stable_hero.stable is True
    assert stable_hero.conscious is False
    assert stable_hero.death_save_successes == 3
    assert hero.death_save_successes == 0
    assert hero.death_save_failures == 0
    assert hero.stable is False
    assert hero.dead is False
    assert hero.death_save_last_round is None
    assert hero.death_save_last_turn_index is None


def test_repository_round_trips_consumed_reaction():
    from dataclasses import replace

    repository = CombatEncounterRepository()
    encounter = make_encounter()
    encounter.start(("hero", "goblin"))
    encounter.combatants["hero"] = replace(
        encounter.combatants["hero"], reaction_used=True
    )

    loaded = repository.save(encounter, campaign_id=1)

    assert loaded.combatants["hero"].reaction_used is True
    assert loaded.combatants["goblin"].reaction_used is False
