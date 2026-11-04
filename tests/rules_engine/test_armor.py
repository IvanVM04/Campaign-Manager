import pytest

from rules_engine.dnd5e_2014.armor import (
    ARMOR_CATALOG,
    ArmorCategory,
    derive_armor_class,
    derive_armor_proficiency,
    get_armor,
    list_armor,
)


def test_srd_armor_catalog_contains_all_13_armor_and_shield_entries():
    assert len(ARMOR_CATALOG) == 13
    assert len({armor.key for armor in list_armor()}) == 13
    assert get_armor("plate").base_armor_class == 18
    assert get_armor("shield").category is ArmorCategory.SHIELD


@pytest.mark.parametrize(
    ("dexterity", "armor", "shield", "expected"),
    [
        (10, None, False, 10),
        (16, None, False, 13),
        (16, "leather", False, 14),
        (16, "studded_leather", False, 15),
        (18, "hide", False, 14),
        (18, "breastplate", False, 16),
        (18, "half_plate", False, 17),
        (18, "chain_mail", False, 16),
        (18, "plate", False, 18),
        (18, "plate", True, 20),
        (8, "leather", True, 12),
    ],
)
def test_armor_class_calculation(dexterity, armor, shield, expected):
    result = derive_armor_class(
        dexterity_score=dexterity,
        armor_key=armor,
        shield_equipped=shield,
    )
    assert result.armor_class == expected


def test_medium_armor_caps_positive_dexterity_modifier_at_two():
    result = derive_armor_class(dexterity_score=20, armor_key="half_plate")
    assert result.dexterity_modifier == 5
    assert result.dexterity_applied == 2
    assert result.armor_class == 17


def test_heavy_armor_does_not_add_dexterity_modifier():
    result = derive_armor_class(dexterity_score=8, armor_key="plate")
    assert result.dexterity_modifier == -1
    assert result.dexterity_applied == 0
    assert result.armor_class == 18


def test_armor_result_exposes_strength_and_stealth_constraints():
    chain = derive_armor_class(
        dexterity_score=10, armor_key="chain_mail", strength_score=12
    )
    scale = derive_armor_class(dexterity_score=10, armor_key="scale_mail")
    plate = derive_armor_class(
        dexterity_score=10, armor_key="plate", strength_score=16
    )
    assert not chain.strength_requirement_met
    assert chain.speed_penalty_ft == 10
    assert scale.stealth_disadvantage
    assert plate.strength_requirement_met
    assert plate.speed_penalty_ft == 0
    assert plate.stealth_disadvantage


@pytest.mark.parametrize(
    ("armor", "strength", "expected_penalty"),
    [
        ("chain_mail", 12, 10),
        ("chain_mail", 13, 0),
        ("splint", 14, 10),
        ("plate", 15, 0),
        ("ring_mail", 3, 0),
        ("leather", 3, 0),
        (None, 3, 0),
    ],
)
def test_armor_strength_requirement_derives_speed_penalty(
    armor, strength, expected_penalty
):
    result = derive_armor_class(
        dexterity_score=10,
        strength_score=strength,
        armor_key=armor,
    )
    assert result.speed_penalty_ft == expected_penalty


def test_shield_is_not_accepted_as_body_armor():
    with pytest.raises(ValueError, match="shield"):
        derive_armor_class(dexterity_score=10, armor_key="shield")


@pytest.mark.parametrize("value", [True, 0, 31, 10.5])
def test_armor_class_rejects_invalid_ability_scores(value):
    with pytest.raises((TypeError, ValueError)):
        derive_armor_class(dexterity_score=value)


def test_unknown_armor_is_rejected():
    with pytest.raises(LookupError, match="unknown SRD armor"):
        derive_armor_class(dexterity_score=10, armor_key="mithril_bikini")


@pytest.mark.parametrize(
    ("armor", "shield", "proficiencies", "expected"),
    [
        ("leather", False, {"light"}, True),
        ("chain_mail", False, {"heavy"}, True),
        ("chain_mail", False, {"medium"}, False),
        (None, True, {"shields"}, True),
        (None, True, {"light"}, False),
        ("leather", True, {"light", "shields"}, True),
        ("leather", True, {"light"}, False),
    ],
)
def test_armor_proficiency_rules(armor, shield, proficiencies, expected):
    result = derive_armor_proficiency(
        armor_key=armor,
        shield_equipped=shield,
        proficiencies=proficiencies,
    )
    assert result.armor_proficient is expected
    assert result.strength_dexterity_disadvantage is (not expected)
    assert result.spellcasting_blocked is (not expected)


def test_armor_proficiency_reports_each_untrained_item():
    result = derive_armor_proficiency(
        armor_key="plate",
        shield_equipped=True,
        proficiencies={"light"},
    )
    assert result.unproficient_armor_keys == ("plate", "shield")


def test_armor_proficiency_rejects_unknown_training():
    with pytest.raises(ValueError, match="unknown armor proficiency"):
        derive_armor_proficiency(
            armor_key="leather",
            shield_equipped=False,
            proficiencies={"plate"},
        )
