import pytest

from models.entity import Entity
from models.persistent_effect import EffectStatus, EffectType
from repositories.campaign_repository import CampaignRepository
from repositories.entity_repository import EntityRepository
from repositories.persistent_effect_repository import PersistentEffectRepository
from services.campaign import PersistentEffectService


def build_service(campaign_id=1):
    entities = EntityRepository()
    return PersistentEffectService(
        repository=PersistentEffectRepository(),
        entity_repository=entities,
        campaign_id=campaign_id,
    ), entities


def test_effect_persists_and_can_be_reloaded_after_runtime_recreation(isolated_database):
    service, entities = build_service()
    entity = entities.save_entity(Entity(name="Mira", entity_type="player_character"), campaign_id=1)

    created = service.create(
        entity_id=entity.id,
        effect_type="condition",
        effect_key="poisoned",
        name="Veneno de araña",
        source_type="creature",
        duration_type="conditional",
        duration_condition="Hasta recibir un antídoto",
    )

    recreated, _ = build_service()
    loaded = recreated.list_for_entity(entity.id)

    assert loaded == [created]
    assert loaded[0].status is EffectStatus.ACTIVE
    assert loaded[0].effect_type is EffectType.CONDITION


def test_effect_supports_exhaustion_levels_and_narrative_states(isolated_database):
    service, entities = build_service()
    entity = entities.save_entity(Entity(name="Mira"), campaign_id=1)

    exhaustion = service.create(
        entity_id=entity.id,
        effect_type="exhaustion",
        effect_key="exhaustion",
        level=2,
        name="Agotamiento",
    )
    narrative = service.create(
        entity_id=entity.id,
        effect_type="narrative",
        effect_key="wounded-arm",
        name="Brazo herido",
        description="La herida dificulta sujetar objetos, pendiente de adjudicación.",
    )

    assert exhaustion.level == 2
    assert narrative.effect_type is EffectType.NARRATIVE
    assert len(service.list_for_entity(entity.id)) == 2


def test_effect_rejects_entity_from_another_campaign(isolated_database):
    _service_one, entities = build_service(1)
    service_two, _ = build_service(2)
    entity = entities.save_entity(Entity(name="Private NPC"), campaign_id=1)

    with pytest.raises(LookupError, match="target entity"):
        service_two.create(
            entity_id=entity.id,
            effect_type="condition",
            effect_key="blinded",
            name="Ceguera",
        )


def test_effect_rejects_cross_campaign_source_entity(isolated_database):
    service, entities = build_service(1)
    source = entities.save_entity(Entity(name="Poisonous spider"), campaign_id=1)
    target = entities.save_entity(Entity(name="Mira"), campaign_id=1)
    CampaignRepository().create_campaign(name="Second campaign", system="D&D 5e 2014")
    other = entities.save_entity(Entity(name="Other campaign source"), campaign_id=2)

    with pytest.raises(LookupError, match="source entity"):
        service.create(
            entity_id=target.id,
            effect_type="condition",
            effect_key="poisoned",
            name="Venom",
            source_type="creature",
            source_entity_id=other.id,
        )

    assert service.list_for_entity(target.id) == []
    assert source.id != other.id


def test_effect_lifecycle_is_idempotent_and_removed_is_terminal(isolated_database):
    service, entities = build_service()
    entity = entities.save_entity(Entity(name="Mira"), campaign_id=1)
    created = service.create(
        entity_id=entity.id,
        effect_type="narrative",
        effect_key="marked",
        name="Marcada",
    )

    suspended = service.set_status(created.id, "suspended")
    assert suspended.status is EffectStatus.SUSPENDED
    assert service.set_status(created.id, "suspended") == suspended

    removed = service.remove(created.id)
    assert removed.status is EffectStatus.REMOVED
    assert removed.removed_at is not None
    assert service.remove(created.id).status is EffectStatus.REMOVED
    assert service.list_for_entity(entity.id) == []
    assert service.list_for_entity(entity.id, include_removed=True) == [removed]

    with pytest.raises(ValueError, match="terminal"):
        service.set_status(created.id, "active")


def test_effects_are_deleted_with_their_target_entity(isolated_database):
    service, entities = build_service()
    entity = entities.save_entity(Entity(name="Mira"), campaign_id=1)
    effect = service.create(
        entity_id=entity.id,
        effect_type="condition",
        effect_key="frightened",
        name="Miedo",
    )

    entities.delete_entity(entity.id, campaign_id=1)

    assert service.repository.get(effect.id, campaign_id=1) is None


def test_effect_model_rejects_unregistered_mechanical_payloads(isolated_database):
    service, entities = build_service()
    entity = entities.save_entity(Entity(name="Mira"), campaign_id=1)

    with pytest.raises(ValueError, match="canonical D&D"):
        service.create(
            entity_id=entity.id,
            effect_type="condition",
            effect_key="arbitrary_bonus",
            name="Bonus arbitrario",
        )


def test_database_rejects_cross_campaign_target_and_source_even_when_bypassing_service(isolated_database):
    import sqlite3

    from database import get_conn

    _service, entities = build_service(1)
    CampaignRepository().create_campaign(name="Second campaign", system="D&D 5e 2014")
    target = entities.save_entity(Entity(name="Target"), campaign_id=1)
    foreign = entities.save_entity(Entity(name="Foreign source"), campaign_id=2)

    with get_conn() as conn, pytest.raises(sqlite3.IntegrityError, match="effect source"):
        conn.execute(
                """
                INSERT INTO persistent_effects (
                    id, campaign_id, entity_id, effect_type, effect_key,
                    name, source_type, source_entity_id, duration_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "a" * 32, 1, target.id, "condition", "poisoned",
                    "Venom", "creature", foreign.id, "permanent",
                ),
            )


def test_database_rejects_exhaustion_without_level(isolated_database):
    import sqlite3

    from database import get_conn

    _service, entities = build_service()
    target = entities.save_entity(Entity(name="Target"), campaign_id=1)

    with get_conn() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
                """
                INSERT INTO persistent_effects (
                    id, campaign_id, entity_id, effect_type, effect_key,
                    name, source_type, duration_type, level
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "b" * 32, 1, target.id, "exhaustion", "exhaustion",
                    "Exhaustion", "unknown", "permanent", None,
                ),
            )



def test_campaign_time_effect_expires_at_exact_deadline_and_is_retained(isolated_database):
    from services.campaign import CampaignClockService

    service, entities = build_service()
    entity = entities.save_entity(Entity(name="Mira"), campaign_id=1)
    effect = service.create(
        entity_id=entity.id,
        effect_type="condition",
        effect_key="poisoned",
        name="Veneno temporal",
        duration_type="campaign_time",
        duration_minutes=60,
    )

    assert effect.duration_type.value == "campaign_time"
    assert effect.duration_minutes == 60
    assert effect.expires_at_minute == 60
    assert effect.status is EffectStatus.ACTIVE

    clock = CampaignClockService(campaign_id=1)
    clock.advance(minutes=59, expected_elapsed_minutes=0)
    still_active = service.list_for_entity(entity.id)
    assert len(still_active) == 1
    assert still_active[0].status is EffectStatus.ACTIVE

    clock.advance(minutes=1, expected_elapsed_minutes=59)
    assert service.list_for_entity(entity.id) == []
    history = service.list_for_entity(entity.id, include_removed=True)
    assert len(history) == 1
    assert history[0].status.value == "expired"
    assert history[0].expired_at_minute == 60
    assert history[0].removed_at is not None


def test_suspended_campaign_time_effect_still_expires(isolated_database):
    from services.campaign import CampaignClockService

    service, entities = build_service()
    entity = entities.save_entity(Entity(name="Mira"), campaign_id=1)
    effect = service.create(
        entity_id=entity.id,
        effect_type="narrative",
        effect_key="temporary-mark",
        name="Marca temporal",
        duration_type="campaign_time",
        duration_minutes=10,
    )
    service.set_status(effect.id, "suspended")

    CampaignClockService(campaign_id=1).advance(
        minutes=10, expected_elapsed_minutes=0
    )
    history = service.list_for_entity(entity.id, include_removed=True)
    assert history[0].status.value == "expired"
    assert history[0].expired_at_minute == 10


def test_campaign_time_effect_expiration_rolls_back_with_clock_on_failure(isolated_database, monkeypatch):
    from database import get_conn
    from repositories.persistent_effect_repository import PersistentEffectRepository
    from services.campaign import CampaignClockService

    service, entities = build_service()
    entity = entities.save_entity(Entity(name="Mira"), campaign_id=1)
    effect = service.create(
        entity_id=entity.id,
        effect_type="condition",
        effect_key="frightened",
        name="Miedo temporal",
        duration_type="campaign_time",
        duration_minutes=5,
    )

    def fail_expiration(self, campaign_id, elapsed_minutes, *, conn):
        raise RuntimeError("simulated expiration failure")

    monkeypatch.setattr(PersistentEffectRepository, "expire_due", fail_expiration)
    with pytest.raises(RuntimeError, match="simulated expiration failure"):
        CampaignClockService(campaign_id=1).advance(
            minutes=5, expected_elapsed_minutes=0
        )

    with get_conn() as conn:
        clock = conn.execute(
            "SELECT elapsed_minutes FROM campaign_clocks WHERE campaign_id = 1"
        ).fetchone()
    assert clock["elapsed_minutes"] == 0
    assert service.list_for_entity(entity.id)[0].id == effect.id
    assert service.list_for_entity(entity.id)[0].status is EffectStatus.ACTIVE


def test_campaign_time_effect_requires_positive_duration(isolated_database):
    service, entities = build_service()
    entity = entities.save_entity(Entity(name="Mira"), campaign_id=1)
    with pytest.raises(ValueError, match="duration_minutes"):
        service.create(
            entity_id=entity.id,
            effect_type="condition",
            effect_key="blinded",
            name="Ceguera temporal",
            duration_type="campaign_time",
            duration_minutes=0,
        )



def test_campaign_time_api_schema_requires_strict_positive_minutes():
    from pydantic import ValidationError

    from models.persistent_effect_api_schemas import PersistentEffectCreateIn

    valid = PersistentEffectCreateIn(
        effect_type="condition",
        effect_key="poisoned",
        name="Poison",
        duration_type="campaign_time",
        duration_minutes=30,
    )
    assert valid.duration_minutes == 30

    with pytest.raises(ValidationError):
        PersistentEffectCreateIn(
            effect_type="condition",
            effect_key="poisoned",
            name="Poison",
            duration_type="campaign_time",
        )
    with pytest.raises(ValidationError):
        PersistentEffectCreateIn(
            effect_type="condition",
            effect_key="poisoned",
            name="Poison",
            duration_type="campaign_time",
            duration_minutes=True,
        )



def test_encounter_turn_and_round_effects_expire_atomically_with_progression(isolated_database):
    from models.combat_encounter_state import CombatEncounterState
    from models.combatant_state import CombatantState
    from repositories.character_repository import CharacterRepository
    from repositories.combat_encounter_repository import CombatEncounterRepository
    from services.combat import CombatEncounterService

    entities = EntityRepository()
    target = entities.save_entity(Entity(name="Mira", entity_type="player_character"), campaign_id=1)
    other = entities.save_entity(Entity(name="Goblin", entity_type="creature"), campaign_id=1)
    encounter_repo = CombatEncounterRepository()
    encounter = CombatEncounterState.prepare(
        "effect-duration-encounter",
        (
            CombatantState(
                combatant_id=f"character-{target.id}", name="Mira", initiative=20,
                current_hp=10, max_hp=10, armor_class=15, entity_id=target.id,
                is_player_character=True,
            ),
            CombatantState(
                combatant_id=f"creature-{other.id}", name="Goblin", initiative=10,
                current_hp=7, max_hp=7, armor_class=13, entity_id=other.id,
            ),
        ),
    )
    encounter.start((f"character-{target.id}", f"creature-{other.id}"))
    encounter_repo.save(encounter, campaign_id=1)

    effects_repo = PersistentEffectRepository()
    effects = PersistentEffectService(
        repository=effects_repo,
        entity_repository=entities,
        campaign_id=1,
        encounter_repository=encounter_repo,
    )
    one_turn = effects.create(
        entity_id=target.id,
        effect_type="condition",
        effect_key="poisoned",
        name="Veneno de un turno",
        duration_type="encounter_turns",
        encounter_id=encounter.encounter_id,
        duration_turns=1,
    )
    one_round = effects.create(
        entity_id=target.id,
        effect_type="condition",
        effect_key="blinded",
        name="Ceguera de una ronda",
        duration_type="encounter_rounds",
        encounter_id=encounter.encounter_id,
        duration_rounds=1,
    )
    assert one_turn.expires_at_turn == 1
    assert one_round.expires_at_round == 2

    # Encounter timers must not be consumed by campaign-clock advancement.
    from services.campaign import CampaignClockService
    CampaignClockService(campaign_id=1).advance(
        minutes=1, expected_elapsed_minutes=0
    )
    still_active = effects.list_for_entity(target.id)
    assert {item.id for item in still_active} == {one_turn.id, one_round.id}

    combat = CombatEncounterService(
        repository=encounter_repo,
        character_repository=CharacterRepository(),
        entity_repository=entities,
        persistent_effect_repository=effects_repo,
    )
    combat.advance_turn(1, encounter.encounter_id, expected_round=1, expected_turn_index=0)

    after_one_turn = effects.list_for_entity(target.id, include_removed=True)
    turn_effect = next(item for item in after_one_turn if item.id == one_turn.id)
    round_effect = next(item for item in after_one_turn if item.id == one_round.id)
    assert turn_effect.status.value == "expired"
    assert turn_effect.expired_at_turn == 1
    assert round_effect.status.value == "active"

    combat.advance_turn(1, encounter.encounter_id, expected_round=1, expected_turn_index=1)
    after_round = effects.list_for_entity(target.id, include_removed=True)
    round_effect = next(item for item in after_round if item.id == one_round.id)
    assert round_effect.status.value == "expired"
    assert round_effect.expired_at_round == 2


def test_persistent_effect_api_schema_uses_enum_defaults():
    from models.persistent_effect_api_schemas import (
        EffectDurationInput,
        EffectSourceInput,
        EffectTypeInput,
        PersistentEffectCreateIn,
    )

    effect = PersistentEffectCreateIn(
        effect_type=EffectTypeInput.NARRATIVE,
        effect_key="marked",
        name="Marcada",
    )

    assert effect.source_type is EffectSourceInput.UNKNOWN
    assert effect.duration_type is EffectDurationInput.PERMANENT
