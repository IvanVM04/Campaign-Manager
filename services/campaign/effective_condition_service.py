"""Project active campaign effects into the existing D&D condition rules model."""

from rules_engine.dnd5e_2014.combat.conditions import Condition, ConditionSet


def condition_set_from_effects(effects, *, base: ConditionSet | None = None) -> ConditionSet:
    if base is not None and not isinstance(base, ConditionSet):
        raise TypeError("base must be a ConditionSet or None")
    conditions = set(base.conditions if base is not None else ())
    exhaustion = base.exhaustion_level if base is not None else 0
    for effect in effects:
        if effect.status.value != "active":
            continue
        if effect.effect_type.value == "condition":
            conditions.add(Condition(effect.effect_key))
        elif effect.effect_type.value == "exhaustion":
            exhaustion = max(exhaustion, effect.level or 0)
    return ConditionSet(frozenset(conditions), exhaustion)


class EffectiveConditionService:
    def __init__(self, repository):
        self.repository = repository

    def for_entity(self, entity_id: int, *, campaign_id: int, base=None, conn=None):
        effects = self.repository.list_for_entity(
            entity_id, campaign_id=campaign_id, active_only=True, conn=conn
        )
        return condition_set_from_effects(effects, base=base)
