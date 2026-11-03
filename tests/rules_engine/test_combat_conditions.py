import pytest

from rules_engine.dnd5e_2014.combat.condition_effects import (
    condition_imposes_disadvantage_on_check,
    derive_condition_effects,
    saving_throw_auto_fails,
)
from rules_engine.dnd5e_2014.combat.conditions import (
    Condition,
    ConditionSet,
    attack_roll_advantage_state,
)
from rules_engine.dnd5e_2014.core.abilities import Ability


def test_grappled_and_restrained_reduce_speed_to_zero():
    assert ConditionSet(frozenset({Condition.GRAPPLED})).speed_is_zero
    assert ConditionSet(frozenset({Condition.RESTRAINED})).speed_is_zero


def test_incapacitating_conditions_prevent_actions_and_reactions():
    effects = derive_condition_effects(
        ConditionSet(frozenset({Condition.STUNNED}))
    )
    assert effects.cannot_take_actions
    assert effects.cannot_take_reactions
    assert effects.auto_fail_strength_saves
    assert effects.auto_fail_dexterity_saves


def test_paralyzed_target_causes_melee_attacks_to_have_advantage():
    attacker = ConditionSet()
    target = ConditionSet(frozenset({Condition.PARALYZED}))
    advantage, disadvantage = attack_roll_advantage_state(
        attacker=attacker,
        target=target,
        target_within_5_feet=True,
    )
    assert advantage is True
    assert disadvantage is False


def test_prone_target_has_different_effect_based_on_attack_distance():
    attacker = ConditionSet()
    target = ConditionSet(frozenset({Condition.PRONE}))
    close = attack_roll_advantage_state(
        attacker=attacker, target=target, target_within_5_feet=True
    )
    far = attack_roll_advantage_state(
        attacker=attacker, target=target, target_within_5_feet=False
    )
    assert close == (True, False)
    assert far == (False, True)


def test_advantage_and_disadvantage_can_coexist_for_dice_engine_to_cancel():
    attacker = ConditionSet(frozenset({Condition.POISONED}))
    target = ConditionSet(frozenset({Condition.RESTRAINED}))
    assert attack_roll_advantage_state(
        attacker=attacker, target=target, target_within_5_feet=True
    ) == (True, True)


def test_exhaustion_levels_apply_cumulative_2014_effects():
    level_one = derive_condition_effects(ConditionSet(exhaustion_level=1))
    level_two = derive_condition_effects(ConditionSet(exhaustion_level=2))
    level_three = derive_condition_effects(ConditionSet(exhaustion_level=3))
    level_four = derive_condition_effects(ConditionSet(exhaustion_level=4))
    level_six = derive_condition_effects(ConditionSet(exhaustion_level=6))

    assert level_one.ability_checks_have_disadvantage
    assert level_two.speed_halved
    assert level_three.attacks_have_disadvantage
    assert level_three.saving_throws_have_disadvantage
    assert level_four.hit_point_maximum_halved
    assert level_six.dies_at_exhaustion_six


def test_exhaustion_six_is_not_a_condition_but_a_terminal_state_flag():
    assert ConditionSet(exhaustion_level=6).dies_at_exhaustion_six


def test_condition_saving_throw_auto_fail_only_for_strength_and_dexterity():
    conditions = ConditionSet(frozenset({Condition.UNCONSCIOUS}))
    assert saving_throw_auto_fails(conditions, Ability.STRENGTH)
    assert saving_throw_auto_fails(conditions, Ability.DEXTERITY)
    assert not saving_throw_auto_fails(conditions, Ability.WISDOM)


@pytest.mark.parametrize("level", [-1, 7, True, 1.5])
def test_invalid_exhaustion_level_is_rejected(level):
    with pytest.raises(ValueError):
        ConditionSet(exhaustion_level=level)


def test_invisible_attacker_has_advantage_but_visibility_can_add_disadvantage():
    attacker = ConditionSet(frozenset({Condition.INVISIBLE, Condition.POISONED}))
    target = ConditionSet()
    assert attack_roll_advantage_state(
        attacker=attacker,
        target=target,
        target_within_5_feet=True,
        attacker_can_see_target=True,
        target_can_see_attacker=False,
    ) == (True, True)



def test_paralyzed_target_only_grants_advantage_to_attacks_within_five_feet():
    attacker = ConditionSet()
    target = ConditionSet(frozenset({Condition.PARALYZED}))

    close = attack_roll_advantage_state(
        attacker=attacker, target=target, target_within_5_feet=True
    )
    far = attack_roll_advantage_state(
        attacker=attacker, target=target, target_within_5_feet=False
    )

    assert close == (True, False)
    assert far == (False, False)


def test_blinded_target_grants_advantage_to_attacks_against_it():
    advantage, disadvantage = attack_roll_advantage_state(
        attacker=ConditionSet(),
        target=ConditionSet(frozenset({Condition.BLINDED})),
        target_within_5_feet=False,
    )
    assert advantage is True
    assert disadvantage is False


def test_frightened_disadvantage_depends_on_source_visibility():
    conditions = ConditionSet(frozenset({Condition.FRIGHTENED}))
    assert not condition_imposes_disadvantage_on_check(conditions)
    assert condition_imposes_disadvantage_on_check(
        conditions, frightened_source_visible=True
    )



def test_blinded_does_not_reduce_speed_but_paralyzed_does():
    assert not ConditionSet(frozenset({Condition.BLINDED})).speed_is_zero
    assert ConditionSet(frozenset({Condition.PARALYZED})).speed_is_zero


def test_exhaustion_level_five_reduces_speed_to_zero():
    effects = derive_condition_effects(ConditionSet(exhaustion_level=5))
    assert effects.speed_is_zero
    assert not effects.speed_halved
