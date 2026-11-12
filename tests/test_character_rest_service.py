from dataclasses import replace

import pytest

from models.character_api_schemas import CharacterCreate
from models.combat_encounter_state import CombatEncounterState
from models.combatant_state import CombatantState
from models.entity import Entity
from models.persistent_effect import EffectDurationType, EffectSourceType, EffectType
from repositories.campaign_clock_repository import CampaignClockRepository
from repositories.campaign_repository import CampaignRepository
from repositories.character_repository import CharacterRepository
from repositories.combat_encounter_repository import CombatEncounterRepository
from repositories.entity_repository import EntityRepository
from repositories.persistent_effect_repository import PersistentEffectRepository
from services.campaign import PersistentEffectService
from services.characters.character_creation_service import CharacterCreationService
from services.characters.character_rest_service import CharacterRestService


def _create_character(
    *,
    level=5,
    class_name="Wizard",
    current_hp=5,
    max_hp=50,
    constitution=12,
):
    character = CharacterCreationService(
        CampaignRepository(),
        EntityRepository(),
        CharacterRepository(),
    ).create_character(
        1,
        CharacterCreate(
            name="Rest Test",
            level=level,
            class_name=class_name,
            current_hp=current_hp,
            max_hp=max_hp,
            constitution=constitution,
        ),
    )
    return character


def _rest_service():
    return CharacterRestService(campaign_id=1)


def test_short_rest_spends_manual_hit_dice_and_applies_constitution_per_die(
    isolated_database,
):
    character = _create_character()

    result = _rest_service().short_rest(
        character.entity_id,
        expected_elapsed_minutes=0,
        hit_dice_to_spend=2,
        manual_rolls=(4, 5),
    )

    assert result.rest_type == "short"
    assert result.dice_rolls == (4, 5)
    assert result.hp_recovered == 11
    assert result.character.current_hp == 16
    assert result.character.hit_die_sides == 6
    assert result.character.hit_dice_used == 2
    assert result.character.level - result.character.hit_dice_used == 3
    assert result.clock.elapsed_minutes == 60
    assert result.clock.version == 1


def test_short_rest_applies_zero_minimum_healing_per_die_and_caps_at_max_hp(
    isolated_database,
):
    injured = _create_character(current_hp=10, constitution=6)
    no_healing = _rest_service().short_rest(
        injured.entity_id,
        expected_elapsed_minutes=0,
        hit_dice_to_spend=2,
        manual_rolls=(1, 2),
    )
    assert no_healing.hp_recovered == 0
    assert no_healing.character.current_hp == 10

    almost_full = CharacterRepository().save_character(
        replace(no_healing.character, current_hp=49),
        campaign_id=1,
    )
    capped = _rest_service().short_rest(
        almost_full.entity_id,
        expected_elapsed_minutes=60,
        hit_dice_to_spend=1,
        manual_rolls=(6,),
    )
    assert capped.hp_recovered == 1
    assert capped.character.current_hp == 50
    assert capped.clock.elapsed_minutes == 120


def test_short_rest_rejects_spending_more_hit_dice_than_available_without_mutation(
    isolated_database,
):
    character = _create_character()
    with pytest.raises(ValueError, match="only 5 remain"):
        _rest_service().short_rest(
            character.entity_id,
            expected_elapsed_minutes=0,
            hit_dice_to_spend=6,
            manual_rolls=(1, 1, 1, 1, 1, 1),
        )
    assert CharacterRepository().get_character(
        character.entity_id,
        campaign_id=1,
    ).hit_dice_used == 0
    assert CampaignClockRepository().get(1) is None


def test_long_rest_restores_hp_and_recovers_half_of_spent_hit_dice(
    isolated_database,
):
    character = _create_character(level=5, current_hp=4)
    seeded = CharacterRepository().save_character(
        replace(character, hit_dice_used=4),
        campaign_id=1,
    )

    result = _rest_service().long_rest(
        seeded.entity_id,
        expected_elapsed_minutes=0,
    )

    assert result.rest_type == "long"
    assert result.character.current_hp == 50
    assert result.hp_recovered == 46
    assert result.hit_dice_recovered == 2
    assert result.character.hit_dice_used == 2
    assert result.clock.elapsed_minutes == 480
    assert result.character.last_long_rest_elapsed_minutes == 480


def test_level_one_long_rest_recovers_at_least_one_hit_die(
    isolated_database,
):
    character = _create_character(level=1)
    spent = CharacterRepository().save_character(
        replace(character, hit_dice_used=1),
        campaign_id=1,
    )

    result = _rest_service().long_rest(
        spent.entity_id,
        expected_elapsed_minutes=0,
    )

    assert result.hit_dice_recovered == 1
    assert result.character.hit_dice_used == 0


def test_long_rest_cannot_be_benefited_from_twice_within_24_campaign_hours(
    isolated_database,
):
    character = _create_character()
    service = _rest_service()
    first = service.long_rest(character.entity_id, expected_elapsed_minutes=0)

    with pytest.raises(ValueError, match="only one long rest per 24 hours"):
        service.long_rest(
            character.entity_id,
            expected_elapsed_minutes=first.clock.elapsed_minutes,
        )

    from database import transaction

    with transaction("IMMEDIATE") as conn:
        CampaignClockRepository().advance(
            1,
            minutes=960,
            expected_elapsed_minutes=first.clock.elapsed_minutes,
            conn=conn,
        )

    second = service.long_rest(
        character.entity_id,
        expected_elapsed_minutes=first.clock.elapsed_minutes + 960,
    )
    assert second.clock.elapsed_minutes == 1920



def test_rest_is_rejected_while_an_encounter_is_active(isolated_database):
    character = _create_character()
    encounter_repository = CombatEncounterRepository()
    combatant = CombatantState(
        combatant_id="character-rest-block",
        name="Rest Test",
        initiative=20,
        current_hp=character.current_hp,
        max_hp=character.max_hp,
        armor_class=character.armor_class,
        entity_id=character.entity_id,
        is_player_character=True,
    )
    encounter = CombatEncounterState.prepare("rest-block", (combatant,))
    encounter.start((combatant.combatant_id,))
    encounter_repository.save(encounter, campaign_id=1)

    service = CharacterRestService(
        campaign_id=1,
        encounter_repository=encounter_repository,
    )
    with pytest.raises(ValueError, match="while a combat encounter is active"):
        service.short_rest(
            character.entity_id,
            expected_elapsed_minutes=0,
            hit_dice_to_spend=0,
        )
    with pytest.raises(ValueError, match="while a combat encounter is active"):
        service.long_rest(
            character.entity_id,
            expected_elapsed_minutes=0,
        )


def test_short_rest_expires_campaign_time_effects_with_clock_advance(
    isolated_database,
):
    character = _create_character()
    effect_service = PersistentEffectService(
        repository=PersistentEffectRepository(),
        entity_repository=EntityRepository(),
        campaign_id=1,
    )
    effect = effect_service.create(
        entity_id=character.entity_id,
        effect_type=EffectType.CONDITION,
        effect_key="poisoned",
        name="Poison",
        source_type=EffectSourceType.ENVIRONMENT,
        duration_type=EffectDurationType.CAMPAIGN_TIME,
        duration_minutes=60,
    )

    result = _rest_service().short_rest(
        character.entity_id,
        expected_elapsed_minutes=0,
    )

    effects = PersistentEffectRepository().list_for_entity(
        character.entity_id,
        campaign_id=1,
        include_removed=True,
    )
    persisted = next(item for item in effects if item.id == effect.id)
    assert result.clock.elapsed_minutes == 60
    assert persisted.status.value == "expired"


def test_rest_rolls_back_clock_and_effect_expiry_when_character_write_fails(
    isolated_database,
    monkeypatch,
):
    character = _create_character()
    effect_service = PersistentEffectService(
        repository=PersistentEffectRepository(),
        entity_repository=EntityRepository(),
        campaign_id=1,
    )
    effect = effect_service.create(
        entity_id=character.entity_id,
        effect_type=EffectType.CONDITION,
        effect_key="poisoned",
        name="Poison",
        source_type=EffectSourceType.ENVIRONMENT,
        duration_type=EffectDurationType.CAMPAIGN_TIME,
        duration_minutes=60,
    )

    repository = CharacterRepository()

    def fail_rest_write(*args, **kwargs):
        raise RuntimeError("injected character rest write failure")

    monkeypatch.setattr(repository, "update_rest_state", fail_rest_write)
    service = CharacterRestService(
        campaign_id=1,
        character_repository=repository,
    )
    with pytest.raises(RuntimeError, match="injected character rest"):
        service.short_rest(
            character.entity_id,
            expected_elapsed_minutes=0,
        )

    assert CampaignClockRepository().get(1) is None
    persisted_effect = PersistentEffectRepository().get(effect.id, campaign_id=1)
    assert persisted_effect is not None
    assert persisted_effect.status.value == "active"
