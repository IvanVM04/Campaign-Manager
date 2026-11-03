import pytest

from rules_engine.dnd5e_2014.combat.damage import (
    DamageAdjustment,
    DamageType,
    apply_damage_modifiers,
    apply_hit_point_damage,
)


@pytest.mark.parametrize(
    ("damage", "adjustment", "expected"),
    [
        (25, DamageAdjustment(resistant=True), 12),
        (25, DamageAdjustment(vulnerable=True), 50),
        (25, DamageAdjustment(immune=True), 0),
        (25, DamageAdjustment(resistant=True, vulnerable=True), 25),
        (0, DamageAdjustment(vulnerable=True), 0),
    ],
)
def test_damage_defenses_follow_2014_rules(damage, adjustment, expected):
    assert apply_damage_modifiers(damage, adjustment) == expected


def test_damage_type_enum_contains_2014_damage_types():
    assert DamageType.FORCE.value == "force"
    assert DamageType.PSYCHIC.value == "psychic"


@pytest.mark.parametrize("damage", [-1, 1.5, True])
def test_invalid_damage_is_rejected(damage):
    with pytest.raises((TypeError, ValueError)):
        apply_damage_modifiers(damage)


def test_hit_point_damage_never_goes_below_zero():
    assert apply_hit_point_damage(7, 12) == 0
    assert apply_hit_point_damage(12, 7) == 5
