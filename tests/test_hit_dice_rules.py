import pytest

from rules_engine.dnd5e_2014.core.hit_dice import hit_die_sides_for_class


@pytest.mark.parametrize(
    ("class_name", "expected_sides"),
    [
        ("Barbarian", 12),
        ("Fighter", 10),
        ("Paladin", 10),
        ("Ranger", 10),
        ("Sorcerer", 6),
        ("Wizard", 6),
        ("Bard", 8),
        ("Cleric", 8),
        ("Druid", 8),
        ("Monk", 8),
        ("Rogue", 8),
        ("Warlock", 8),
    ],
)
def test_hit_die_sides_match_2014_class_progression(class_name, expected_sides):
    assert hit_die_sides_for_class(class_name) == expected_sides


@pytest.mark.parametrize("class_name", [None, "Artificer", "Fighter / Wizard", ""])
def test_unknown_or_untyped_class_uses_documented_d8_fallback(class_name):
    assert hit_die_sides_for_class(class_name) == 8


def test_hit_die_class_lookup_normalizes_case_and_whitespace():
    assert hit_die_sides_for_class("  BARBARIAN  ") == 12


def test_hit_die_class_lookup_rejects_non_string_values():
    with pytest.raises(TypeError, match="class_name must be a string"):
        hit_die_sides_for_class(12)
