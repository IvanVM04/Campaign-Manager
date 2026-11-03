import pytest

from models.entity import Entity
from models.persistent_effect import EffectStatus, EffectType
from repositories.entity_repository import EntityRepository
from repositories.persistent_effect_repository import PersistentEffectRepository
from services.persistent_effect_service import PersistentEffectService


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
    service_one, entities = build_service(1)
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
