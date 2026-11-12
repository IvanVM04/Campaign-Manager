import pytest

from database import one
from models.character_state import CharacterState
from models.combat_encounter_state import CombatEncounterState
from models.combatant_state import CombatantState
from models.entity import Entity
from repositories.character_repository import CharacterRepository
from repositories.combat_encounter_repository import CombatEncounterRepository
from repositories.creature_repository import CreatureRepository
from repositories.entity_repository import EntityRepository
from repositories.persistent_effect_repository import PersistentEffectRepository
from rules_engine.dnd5e_2014.combat.movement import GridPosition
from services.campaign import PersistentEffectService
from services.combat import CombatEncounterService


def _active_encounter(*, character: bool = False, position: bool = False):
    entities = EntityRepository()
    encounter_repository = CombatEncounterRepository()
    character_repository = CharacterRepository()
    target = entities.save_entity(
        Entity(name="Mira", entity_type="player_character" if character else "creature"),
        campaign_id=1,
    )
    if character:
        character_repository.save_character(
            CharacterState(
                entity_id=target.id,
                current_hp=0,
                max_hp=10,
                armor_class=15,
            ),
            campaign_id=1,
        )
    other = entities.save_entity(
        Entity(name="Goblin", entity_type="creature"),
        campaign_id=1,
    )
    target_id = f"character-{target.id}" if character else f"creature-{target.id}"
    target_combatant = CombatantState(
        combatant_id=target_id,
        name="Mira",
        initiative=20,
        current_hp=0 if character else 10,
        max_hp=10,
        armor_class=15,
        entity_id=target.id,
        is_player_character=character,
        conscious=not character,
        position_x=0 if position else None,
        position_y=0 if position else None,
        speed_feet=30,
    )
    other_combatant = CombatantState(
        combatant_id=f"creature-{other.id}",
        name="Goblin",
        initiative=10,
        current_hp=7,
        max_hp=7,
        armor_class=13,
        entity_id=other.id,
    )
    encounter = CombatEncounterState.prepare(
        "transaction-atomicity",
        (target_combatant, other_combatant),
    )
    encounter.start((target_id, other_combatant.combatant_id))
    encounter_repository.save(encounter, campaign_id=1)
    service = CombatEncounterService(
        repository=encounter_repository,
        character_repository=character_repository,
        entity_repository=entities,
        creature_repository=CreatureRepository(),
    )
    return service, encounter_repository, entities, character_repository, target, encounter


def _fail_after_save(repository, monkeypatch):
    original_save = repository.save

    def save_then_fail(*args, **kwargs):
        original_save(*args, **kwargs)
        raise RuntimeError("injected failure after encounter write")

    monkeypatch.setattr(repository, "save", save_then_fail)


def test_encounter_creation_rolls_back_entity_creature_and_snapshot_writes(monkeypatch):
    entities = EntityRepository()
    encounter_repository = CombatEncounterRepository()
    service = CombatEncounterService(
        repository=encounter_repository,
        character_repository=CharacterRepository(),
        entity_repository=entities,
        creature_repository=CreatureRepository(),
    )
    _fail_after_save(encounter_repository, monkeypatch)

    from models.combat_api_schemas import EncounterParticipantIn

    with pytest.raises(RuntimeError, match="injected failure"):
        service.create(
            1,
            (
                EncounterParticipantIn(
                    name="Goblin",
                    max_hp=7,
                    current_hp=7,
                    armor_class=13,
                    dexterity=12,
                ),
            ),
            encounter_id="create-rollback",
        )

    assert one("SELECT COUNT(*) AS count FROM entities WHERE entity_type = 'creature'")["count"] == 0
    assert one("SELECT COUNT(*) AS count FROM creature_states")["count"] == 0
    assert one("SELECT COUNT(*) AS count FROM combat_encounters")["count"] == 0


def test_death_save_rolls_back_canonical_hp_and_encounter_snapshot_together(monkeypatch):
    service, repository, _, characters, target, encounter = _active_encounter(character=True)
    _fail_after_save(repository, monkeypatch)

    with pytest.raises(RuntimeError, match="injected failure"):
        service.death_saving_throw(
            1,
            encounter.encounter_id,
            expected_round=1,
            expected_turn_index=0,
            dice_mode="manual",
            manual_roll=20,
        )

    persisted_character = characters.get_character(target.id, campaign_id=1)
    persisted_encounter = repository.get(encounter.encounter_id, campaign_id=1)
    assert persisted_character is not None
    assert persisted_character.current_hp == 0
    assert persisted_encounter is not None
    assert persisted_encounter.active_combatant is not None
    assert persisted_encounter.active_combatant.current_hp == 0
    assert persisted_encounter.active_combatant.death_save_last_round is None


@pytest.mark.parametrize("operation", ["advance", "complete"])
def test_encounter_progression_and_effect_expiration_roll_back_together(
    operation,
    monkeypatch,
):
    service, repository, entities, _, target, encounter = _active_encounter()
    effects_repository = PersistentEffectRepository()
    service.persistent_effect_repository = effects_repository
    effects = PersistentEffectService(
        repository=effects_repository,
        entity_repository=entities,
        campaign_id=1,
        encounter_repository=repository,
    )
    effect = effects.create(
        entity_id=target.id,
        effect_type="condition",
        effect_key="poisoned",
        name="Veneno",
        duration_type="encounter_turns",
        encounter_id=encounter.encounter_id,
        duration_turns=1,
    )
    _fail_after_save(repository, monkeypatch)

    with pytest.raises(RuntimeError, match="injected failure"):
        if operation == "advance":
            service.advance_turn(
                1,
                encounter.encounter_id,
                expected_round=1,
                expected_turn_index=0,
            )
        else:
            service.complete(
                1,
                encounter.encounter_id,
                expected_round=1,
                expected_turn_index=0,
            )

    persisted_encounter = repository.get(encounter.encounter_id, campaign_id=1)
    persisted_effects = effects.list_for_entity(target.id)
    assert persisted_encounter is not None
    assert persisted_encounter.status.value == "active"
    assert (persisted_encounter.round_number, persisted_encounter.turn_index) == (1, 0)
    assert [item.id for item in persisted_effects] == [effect.id]
    assert persisted_effects[0].status.value == "active"


@pytest.mark.parametrize("operation", ["move", "reaction"])
def test_position_and_reaction_mutations_roll_back_after_snapshot_write(
    operation,
    monkeypatch,
):
    service, repository, _, _, _target, encounter = _active_encounter(position=True)
    _fail_after_save(repository, monkeypatch)
    active = encounter.active_combatant
    assert active is not None

    with pytest.raises(RuntimeError, match="injected failure"):
        if operation == "move":
            service.move_combatant(
                1,
                encounter.encounter_id,
                combatant_id=active.combatant_id,
                expected_round=1,
                expected_turn_index=0,
                path=(GridPosition(0, 0), GridPosition(1, 0)),
            )
        else:
            service.use_reaction(
                1,
                encounter.encounter_id,
                combatant_id=active.combatant_id,
                expected_round=1,
                expected_turn_index=0,
            )

    persisted = repository.get(encounter.encounter_id, campaign_id=1)
    assert persisted is not None
    current = persisted.combatants[active.combatant_id]
    if operation == "move":
        assert (current.position_x, current.position_y) == (0, 0)
        assert current.movement_used_feet == 0
    else:
        assert current.reaction_used is False
