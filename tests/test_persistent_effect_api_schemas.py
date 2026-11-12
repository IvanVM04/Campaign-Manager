import pytest
from pydantic import ValidationError

from models.persistent_effect_api_schemas import PersistentEffectCreateIn


def _payload(**overrides):
    payload = {
        "effect_type": "narrative",
        "effect_key": "marked",
        "name": "Marcada",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "overrides",
    [
        {"duration_condition": "Hasta descansar"},
        {"duration_minutes": 10},
        {"encounter_id": "combat-1"},
        {"duration_rounds": 1},
        {"duration_turns": 1},
    ],
)
def test_permanent_effect_rejects_duration_fields(overrides):
    with pytest.raises(ValidationError, match="permanent effects"):
        PersistentEffectCreateIn(**_payload(**overrides))


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"duration_condition": "Hasta descansar", "duration_minutes": 10},
        {"duration_condition": "   "},
    ],
)
def test_conditional_effect_requires_only_a_non_empty_condition(overrides):
    with pytest.raises(ValidationError):
        PersistentEffectCreateIn(
            **_payload(duration_type="conditional", **overrides)
        )


def test_conditional_effect_accepts_a_condition():
    effect = PersistentEffectCreateIn(
        **_payload(
            duration_type="conditional",
            duration_condition="Hasta recibir un antídoto",
        )
    )
    assert effect.duration_condition == "Hasta recibir un antídoto"


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"duration_minutes": 10, "encounter_id": "combat-1"},
        {"duration_minutes": 10, "duration_rounds": 1},
        {"duration_minutes": 10, "duration_turns": 1},
        {"duration_minutes": 10, "duration_condition": "until rest"},
    ],
)
def test_campaign_time_effect_requires_minutes_only(overrides):
    with pytest.raises(ValidationError):
        PersistentEffectCreateIn(
            **_payload(duration_type="campaign_time", **overrides)
        )


def test_campaign_time_effect_accepts_positive_strict_integer_minutes():
    effect = PersistentEffectCreateIn(
        **_payload(duration_type="campaign_time", duration_minutes=60)
    )
    assert effect.duration_minutes == 60

    for invalid in (True, 0, -1, "60", 525601):
        with pytest.raises(ValidationError):
            PersistentEffectCreateIn(
                **_payload(duration_type="campaign_time", duration_minutes=invalid)
            )


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"encounter_id": "combat-1"},
        {"encounter_id": "combat-1", "duration_rounds": 1, "duration_turns": 1},
        {"encounter_id": "combat-1", "duration_rounds": 1, "duration_minutes": 1},
        {
            "encounter_id": "combat-1",
            "duration_rounds": 1,
            "duration_condition": "until rest",
        },
    ],
)
def test_encounter_round_effect_requires_encounter_and_rounds_only(overrides):
    with pytest.raises(ValidationError):
        PersistentEffectCreateIn(
            **_payload(duration_type="encounter_rounds", **overrides)
        )


def test_encounter_round_effect_accepts_valid_shape():
    effect = PersistentEffectCreateIn(
        **_payload(
            duration_type="encounter_rounds",
            encounter_id="combat-1",
            duration_rounds=3,
        )
    )
    assert effect.duration_rounds == 3


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"encounter_id": "combat-1"},
        {"encounter_id": "combat-1", "duration_turns": 1, "duration_rounds": 1},
        {"encounter_id": "combat-1", "duration_turns": 1, "duration_minutes": 1},
        {
            "encounter_id": "combat-1",
            "duration_turns": 1,
            "duration_condition": "until rest",
        },
    ],
)
def test_encounter_turn_effect_requires_encounter_and_turns_only(overrides):
    with pytest.raises(ValidationError):
        PersistentEffectCreateIn(
            **_payload(duration_type="encounter_turns", **overrides)
        )


def test_encounter_turn_effect_accepts_valid_shape():
    effect = PersistentEffectCreateIn(
        **_payload(
            duration_type="encounter_turns",
            encounter_id="combat-1",
            duration_turns=2,
        )
    )
    assert effect.duration_turns == 2


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"effect_key": "made_up_condition"}, "canonical D&D"),
        ({"effect_key": "poisoned", "level": 1}, "cannot define a level"),
    ],
)
def test_condition_effect_requires_canonical_condition_without_level(
    overrides, message
):
    payload = {"effect_type": "condition", "effect_key": "poisoned"}
    payload.update(overrides)
    with pytest.raises(ValidationError, match=message):
        PersistentEffectCreateIn(**_payload(**payload))


@pytest.mark.parametrize(
    "overrides",
    [
        {"effect_key": "exhaustion"},
        {"effect_key": "other", "level": 2},
        {"effect_key": "exhaustion", "level": 0},
        {"effect_key": "exhaustion", "level": 7},
        {"effect_key": "exhaustion", "level": True},
    ],
)
def test_exhaustion_requires_canonical_key_and_level(overrides):
    with pytest.raises(ValidationError):
        PersistentEffectCreateIn(
            **_payload(effect_type="exhaustion", **overrides)
        )


def test_exhaustion_accepts_levels_one_to_six():
    for level in range(1, 7):
        effect = PersistentEffectCreateIn(
            **_payload(
                effect_type="exhaustion",
                effect_key="exhaustion",
                level=level,
            )
        )
        assert effect.level == level


@pytest.mark.parametrize(
    "effect_key",
    ["contains spaces", "../escape", "-leading", "_leading", "with/slash", "ümlaut"],
)
def test_narrative_effect_requires_simple_ascii_slug(effect_key):
    with pytest.raises(ValidationError, match="simple slug"):
        PersistentEffectCreateIn(**_payload(effect_key=effect_key))


def test_narrative_effect_rejects_mechanical_level():
    with pytest.raises(ValidationError, match="mechanical level"):
        PersistentEffectCreateIn(**_payload(level=1))


def test_effect_schema_rejects_invalid_source_and_duration_bounds():
    with pytest.raises(ValidationError):
        PersistentEffectCreateIn(**_payload(source_type="unknown_source"))
    with pytest.raises(ValidationError):
        PersistentEffectCreateIn(
            **_payload(duration_type="campaign_time", duration_minutes=525601)
        )
    with pytest.raises(ValidationError):
        PersistentEffectCreateIn(**_payload(source_entity_id=True))
