import pytest

from rules_engine.dnd5e_2014.combat.condition_effects import (
    condition_imposes_disadvantage_on_check,
    derive_condition_effects,
    is_charmed_by_target,
    saving_throw_auto_fails,
)
from rules_engine.dnd5e_2014.combat.conditions import Condition, ConditionSet
from rules_engine.dnd5e_2014.core.abilities import Ability


def test_derive_condition_effects_projects_all_clear_and_restrictive_states():
    clear = derive_condition_effects(ConditionSet())
    assert not any(vars(clear).values())

    restricted = derive_condition_effects(
        ConditionSet(
            frozenset({Condition.STUNNED, Condition.POISONED}),
            exhaustion_level=6,
        )
    )
    assert restricted.speed_is_zero
    assert restricted.cannot_take_actions
    assert restricted.cannot_take_reactions
    assert restricted.auto_fail_strength_saves
    assert restricted.auto_fail_dexterity_saves
    assert restricted.attacks_against_have_advantage
    assert restricted.attacks_have_disadvantage
    assert restricted.ability_checks_have_disadvantage
    assert restricted.saving_throws_have_disadvantage
    assert restricted.speed_halved is False
    assert restricted.hit_point_maximum_halved
    assert restricted.dies_at_exhaustion_six


def test_derive_condition_effects_rejects_untyped_input():
    with pytest.raises(TypeError, match="ConditionSet"):
        derive_condition_effects(object())


@pytest.mark.parametrize(
    ("ability", "expected"),
    [
        (Ability.STRENGTH, True),
        (Ability.DEXTERITY, True),
        (Ability.CONSTITUTION, False),
        (Ability.WISDOM, False),
    ],
)
def test_saving_throw_auto_fail_is_limited_to_strength_and_dexterity(
    ability, expected
):
    conditions = ConditionSet(frozenset({Condition.PARALYZED}))
    assert saving_throw_auto_fails(conditions, ability) is expected
    assert saving_throw_auto_fails(ConditionSet(), ability) is False


def test_saving_throw_auto_fail_rejects_untyped_inputs():
    with pytest.raises(TypeError, match="ConditionSet"):
        saving_throw_auto_fails(object(), Ability.STRENGTH)
    with pytest.raises(TypeError, match="Ability"):
        saving_throw_auto_fails(ConditionSet(), "strength")


def test_frightened_disadvantage_depends_on_source_visibility():
    frightened = ConditionSet(frozenset({Condition.FRIGHTENED}))
    assert condition_imposes_disadvantage_on_check(
        frightened,
        frightened_source_visible=False,
    ) is False
    assert condition_imposes_disadvantage_on_check(
        frightened,
        frightened_source_visible=True,
    ) is True

    poisoned = ConditionSet(frozenset({Condition.POISONED}))
    assert condition_imposes_disadvantage_on_check(
        poisoned,
        frightened_source_visible=False,
    ) is True


def test_condition_disadvantage_rejects_untyped_inputs():
    with pytest.raises(TypeError, match="ConditionSet"):
        condition_imposes_disadvantage_on_check(object())
    with pytest.raises(TypeError, match="boolean"):
        condition_imposes_disadvantage_on_check(
            ConditionSet(),
            frightened_source_visible=1,
        )


def test_charmed_projection_is_explicit():
    assert is_charmed_by_target(
        ConditionSet(frozenset({Condition.CHARMED}))
    )
    assert not is_charmed_by_target(ConditionSet())
