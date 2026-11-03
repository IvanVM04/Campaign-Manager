"""Persistent effect projection into the existing condition rules."""

from models.entity import Entity
from models.persistent_effect import EffectStatus
from repositories.entity_repository import EntityRepository
from repositories.persistent_effect_repository import PersistentEffectRepository
from services.effective_condition_service import EffectiveConditionService
from services.persistent_effect_service import PersistentEffectService


def test_effect_projection_ignores_suspended_and_removed_records(isolated_database):
    entities = EntityRepository()
    entity = entities.save_entity(Entity(name="Mira"), campaign_id=1)
    repo = PersistentEffectRepository()
    service = PersistentEffectService(repository=repo, entity_repository=entities, campaign_id=1)
    poisoned = service.create(entity_id=entity.id, effect_type="condition", effect_key="poisoned", name="Veneno")
    exhausted = service.create(entity_id=entity.id, effect_type="exhaustion", effect_key="exhaustion", level=2, name="Agotamiento")
    service.set_status(exhausted.id, EffectStatus.SUSPENDED)
    projected = EffectiveConditionService(repo).for_entity(entity.id, campaign_id=1)
    assert projected.has("poisoned")
    assert projected.exhaustion_level == 0
    service.remove(poisoned.id)
    assert not EffectiveConditionService(repo).for_entity(entity.id, campaign_id=1).has("poisoned")
