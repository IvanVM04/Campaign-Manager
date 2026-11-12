from __future__ import annotations

from typing import Any, cast

import pytest

from models.character_state import CharacterState
from models.combatant_state import CombatantState
from models.creature_state import CreatureState
from repositories.character_repository import CharacterRepository
from repositories.creature_repository import CreatureRepository
from repositories.weapon_equipment_repository import WeaponEquipmentRepository
from services.combat.attack_profile_resolver import AttackProfileResolver


class _CharacterRepository:
    def __init__(self, character=None):
        self.character = character

    def get_character(self, entity_id, *, campaign_id, conn):
        assert campaign_id == 3
        assert conn == "transaction"
        return self.character


class _WeaponRepository:
    def __init__(self, equipped=None):
        self.equipped = equipped

    def get_equipped(self, *, campaign_id, character_entity_id, conn):
        assert campaign_id == 3
        assert character_entity_id == 11
        assert conn == "transaction"
        return self.equipped


class _CreatureRepository:
    def __init__(self, creature=None):
        self.creature = creature

    def get_creature(self, entity_id, *, campaign_id, conn):
        assert campaign_id == 3
        assert entity_id == 21
        assert conn == "transaction"
        return self.creature


def _character(*, hp=20, weapon_proficiencies=frozenset({"martial_melee"})):
    return CharacterState(
        entity_id=11,
        current_hp=hp,
        max_hp=20,
        strength=16,
        dexterity=12,
        proficiency_bonus=2,
        weapon_proficiencies=weapon_proficiencies,
    )


def _creature(*, hp=18, metadata=None):
    return CreatureState(
        entity_id=21,
        current_hp=hp,
        max_hp=18,
        armor_class=13,
        strength=16,
        dexterity=12,
        proficiency_bonus=2,
        metadata=metadata or {},
    )


def _attacker(*, player=False, entity_id=None, hp=20):
    return CombatantState(
        combatant_id="character-11" if player else "creature-21",
        name="Attacker",
        initiative=15,
        current_hp=hp,
        max_hp=20 if player else 18,
        armor_class=12,
        entity_id=11 if player else 21 if entity_id is None else entity_id,
        is_player_character=player,
        strength=16,
        dexterity=12,
    )


def _resolver(*, character=None, equipped=None, creature=None):
    return AttackProfileResolver(
        character_repository=cast(
            CharacterRepository, _CharacterRepository(character)
        ),
        weapon_repository=cast(
            WeaponEquipmentRepository, _WeaponRepository(equipped)
        ),
        creature_repository=cast(
            CreatureRepository, _CreatureRepository(creature)
        ),
    )


def _natural(**overrides: Any) -> dict[str, Any]:
    profile = {
        "key": "bite",
        "name": "Bite",
        "ability": "strength",
        "damage_dice": "1d6",
        "damage_type": "piercing",
        "reach_feet": 5,
        "proficient": True,
    }
    return {**profile, **overrides}


def test_player_weapon_profile_uses_canonical_character_and_equipped_weapon():
    resolver = _resolver(
        character=_character(),
        equipped={"weapon_key": "longsword"},
    )

    result = resolver.resolve(
        attacker=_attacker(player=True),
        campaign_id=3,
        conn="transaction",
    )

    assert result.weapon_key == "longsword"
    assert result.natural_attack_key is None
    assert result.attack_ability == "strength"
    assert result.attack_bonus == 5
    assert result.damage_dice == "1d8"
    assert result.damage_bonus == 3
    assert result.damage_type == "slashing"
    assert result.proficient is True
    assert result.reach_feet == 5


def test_player_finesse_profile_respects_explicit_dexterity_choice():
    resolver = _resolver(
        character=_character(),
        equipped={"weapon_key": "rapier"},
    )

    result = resolver.resolve(
        attacker=_attacker(player=True),
        campaign_id=3,
        conn="transaction",
        finesse_ability="dexterity",
    )

    assert result.attack_ability == "dexterity"
    assert result.attack_bonus == 3
    assert result.damage_bonus == 1


def test_player_versatile_weapon_uses_two_handed_damage_dice():
    resolver = _resolver(
        character=_character(),
        equipped={"weapon_key": "longsword"},
    )

    result = resolver.resolve(
        attacker=_attacker(player=True),
        campaign_id=3,
        conn="transaction",
        versatile_two_handed=True,
    )

    assert result.damage_dice == "1d10"


def test_player_profile_rejects_npc_attack_selection():
    resolver = _resolver(
        character=_character(),
        equipped={"weapon_key": "longsword"},
    )

    with pytest.raises(ValueError, match="NPC attack selection"):
        resolver.resolve(
            attacker=_attacker(player=True),
            campaign_id=3,
            conn="transaction",
            npc_attack_weapon_key="battleaxe",
        )


def test_player_profile_requires_character_record():
    resolver = _resolver(
        character=None,
        equipped={"weapon_key": "longsword"},
    )

    with pytest.raises(LookupError, match="attacking character"):
        resolver.resolve(
            attacker=_attacker(player=True),
            campaign_id=3,
            conn="transaction",
        )


def test_player_profile_rejects_hp_snapshot_drift():
    resolver = _resolver(
        character=_character(hp=17),
        equipped={"weapon_key": "longsword"},
    )

    with pytest.raises(RuntimeError, match="character hit points"):
        resolver.resolve(
            attacker=_attacker(player=True, hp=20),
            campaign_id=3,
            conn="transaction",
        )


@pytest.mark.parametrize("equipped", [None, {"weapon_key": None}])
def test_player_profile_requires_an_equipped_weapon(equipped):
    resolver = _resolver(character=_character(), equipped=equipped)

    with pytest.raises(ValueError, match="no equipped weapon"):
        resolver.resolve(
            attacker=_attacker(player=True),
            campaign_id=3,
            conn="transaction",
        )


def test_player_profile_rejects_unknown_weapon_definition():
    resolver = _resolver(
        character=_character(),
        equipped={"weapon_key": "not-in-catalog"},
    )

    with pytest.raises(LookupError, match="unknown SRD weapon"):
        resolver.resolve(
            attacker=_attacker(player=True),
            campaign_id=3,
            conn="transaction",
        )


def test_npc_uses_first_weapon_profile_when_no_selection_is_supplied():
    creature = _creature(metadata={
        "npc_melee_attacks": [
            {"weapon_key": "battleaxe", "proficient": True},
            {"weapon_key": "rapier", "proficient": False},
        ],
    })

    result = _resolver(creature=creature).resolve(
        attacker=_attacker(player=False, hp=18),
        campaign_id=3,
        conn="transaction",
    )

    assert result.weapon_key == "battleaxe"
    assert result.attack_bonus == 5
    assert result.proficient is True


def test_npc_can_select_a_later_weapon_profile_and_its_own_proficiency():
    creature = _creature(metadata={
        "npc_melee_attacks": [
            {"weapon_key": "battleaxe", "proficient": True},
            {"weapon_key": "rapier", "proficient": False},
        ],
    })

    result = _resolver(creature=creature).resolve(
        attacker=_attacker(player=False, hp=18),
        campaign_id=3,
        conn="transaction",
        npc_attack_weapon_key="rapier",
        finesse_ability="dexterity",
    )

    assert result.weapon_key == "rapier"
    assert result.attack_ability == "dexterity"
    assert result.attack_bonus == 1
    assert result.damage_bonus == 1
    assert result.proficient is False


def test_npc_reads_legacy_single_weapon_profile():
    creature = _creature(metadata={
        "npc_melee_attack": {"weapon_key": "longsword", "proficient": False},
    })

    result = _resolver(creature=creature).resolve(
        attacker=_attacker(player=False, hp=18),
        campaign_id=3,
        conn="transaction",
    )

    assert result.weapon_key == "longsword"
    assert result.proficient is False
    assert result.attack_bonus == 3


def test_npc_rejects_unconfigured_weapon_selection():
    creature = _creature(metadata={
        "npc_melee_attacks": [{"weapon_key": "battleaxe"}],
    })

    with pytest.raises(ValueError, match="selected NPC weapon"):
        _resolver(creature=creature).resolve(
            attacker=_attacker(player=False, hp=18),
            campaign_id=3,
            conn="transaction",
            npc_attack_weapon_key="longsword",
        )


def test_npc_without_attack_profiles_cannot_attack():
    creature = _creature()

    with pytest.raises(ValueError, match="requires a configured melee weapon"):
        _resolver(creature=creature).resolve(
            attacker=_attacker(player=False, hp=18),
            campaign_id=3,
            conn="transaction",
        )


@pytest.mark.parametrize(
    "profiles",
    [
        "not-a-list",
        [None],
        [{}],
        [{"weapon_key": 12}],
        [{"weapon_key": "longsword", "proficient": "yes"}],
        [
            {"weapon_key": "longsword"},
            {"weapon_key": "longsword", "proficient": False},
        ],
    ],
)
def test_npc_weapon_metadata_fails_closed_for_invalid_profiles(profiles):
    creature = _creature(metadata={"npc_melee_attacks": profiles})

    with pytest.raises(ValueError):
        _resolver(creature=creature).resolve(
            attacker=_attacker(player=False, hp=18),
            campaign_id=3,
            conn="transaction",
        )


def test_npc_weapon_metadata_rejects_unsupported_special_weapon():
    creature = _creature(metadata={
        "npc_melee_attacks": [{"weapon_key": "lance"}],
    })

    with pytest.raises(ValueError, match="special attack resolver"):
        _resolver(creature=creature).resolve(
            attacker=_attacker(player=False, hp=18),
            campaign_id=3,
            conn="transaction",
        )


def test_npc_natural_attack_defaults_to_first_profile_without_weapon_profiles():
    creature = _creature(metadata={
        "npc_natural_attacks": [
            _natural(),
            _natural(key="claw", name="Claw", damage_dice="1d4", damage_type="slashing"),
        ],
    })

    result = _resolver(creature=creature).resolve(
        attacker=_attacker(player=False, hp=18),
        campaign_id=3,
        conn="transaction",
    )

    assert result.weapon is None
    assert result.weapon_key is None
    assert result.natural_attack_key == "bite"
    assert result.attack_bonus == 5
    assert result.damage_bonus == 3
    assert result.damage_type == "piercing"
    assert result.reach_feet == 5


def test_npc_can_select_natural_attack_even_when_weapon_profiles_exist():
    creature = _creature(metadata={
        "npc_melee_attacks": [{"weapon_key": "longsword"}],
        "npc_natural_attacks": [
            _natural(),
            _natural(
                key="claw",
                name="Claw",
                ability="dexterity",
                damage_dice="1d4",
                damage_type="slashing",
                reach_feet=10,
                proficient=False,
            ),
        ],
    })

    result = _resolver(creature=creature).resolve(
        attacker=_attacker(player=False, hp=18),
        campaign_id=3,
        conn="transaction",
        npc_natural_attack_key="claw",
    )

    assert result.weapon is None
    assert result.natural_attack_key == "claw"
    assert result.attack_ability == "dexterity"
    assert result.attack_bonus == 1
    assert result.damage_bonus == 1
    assert result.damage_dice == "1d4"
    assert result.damage_type == "slashing"
    assert result.reach_feet == 10
    assert result.proficient is False


def test_npc_natural_attack_selection_rejects_unknown_key():
    creature = _creature(metadata={"npc_natural_attacks": [_natural()]})

    with pytest.raises(ValueError, match="selected NPC natural attack"):
        _resolver(creature=creature).resolve(
            attacker=_attacker(player=False, hp=18),
            campaign_id=3,
            conn="transaction",
            npc_natural_attack_key="claw",
        )


def test_npc_natural_attack_rejects_weapon_only_options():
    creature = _creature(metadata={"npc_natural_attacks": [_natural()]})

    with pytest.raises(ValueError, match="weapon-specific options"):
        _resolver(creature=creature).resolve(
            attacker=_attacker(player=False, hp=18),
            campaign_id=3,
            conn="transaction",
            npc_natural_attack_key="bite",
            versatile_two_handed=True,
        )


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"key": ""}, "configuration is invalid"),
        ({"name": ""}, "configuration is invalid"),
        ({"ability": "intelligence"}, "configuration is invalid"),
        ({"damage_dice": "1d3"}, "configuration is invalid"),
        ({"reach_feet": 7}, "configuration is invalid"),
        ({"reach_feet": True}, "configuration is invalid"),
        ({"proficient": "yes"}, "configuration is invalid"),
        ({"damage_type": "void"}, "damage type is invalid"),
    ],
)
def test_npc_natural_attack_metadata_is_validated(override, message):
    creature = _creature(metadata={
        "npc_natural_attacks": [_natural(**override)],
    })

    with pytest.raises(ValueError, match=message):
        _resolver(creature=creature).resolve(
            attacker=_attacker(player=False, hp=18),
            campaign_id=3,
            conn="transaction",
        )


def test_npc_natural_attack_metadata_rejects_duplicate_keys():
    creature = _creature(metadata={
        "npc_natural_attacks": [_natural(), _natural(name="Second bite")],
    })

    with pytest.raises(ValueError, match="keys must be unique"):
        _resolver(creature=creature).resolve(
            attacker=_attacker(player=False, hp=18),
            campaign_id=3,
            conn="transaction",
        )


def test_npc_natural_attack_metadata_requires_a_list():
    creature = _creature(metadata={"npc_natural_attacks": {"key": "bite"}})

    with pytest.raises(ValueError, match="configuration is invalid"):
        _resolver(creature=creature).resolve(
            attacker=_attacker(player=False, hp=18),
            campaign_id=3,
            conn="transaction",
        )


def test_npc_profile_resolution_rejects_creature_hp_snapshot_drift():
    creature = _creature(hp=17, metadata={
        "npc_melee_attacks": [{"weapon_key": "longsword"}],
    })

    with pytest.raises(RuntimeError, match="creature hit points"):
        _resolver(creature=creature).resolve(
            attacker=_attacker(player=False, hp=18),
            campaign_id=3,
            conn="transaction",
        )


def test_npc_profile_resolution_requires_persisted_creature():
    with pytest.raises(LookupError, match="attacking creature"):
        _resolver(creature=None).resolve(
            attacker=_attacker(player=False, hp=18),
            campaign_id=3,
            conn="transaction",
        )


def test_resolver_rejects_ambiguous_weapon_and_natural_selection():
    creature = _creature(metadata={
        "npc_melee_attacks": [{"weapon_key": "longsword"}],
        "npc_natural_attacks": [_natural()],
    })

    with pytest.raises(ValueError, match="not both"):
        _resolver(creature=creature).resolve(
            attacker=_attacker(player=False, hp=18),
            campaign_id=3,
            conn="transaction",
            npc_attack_weapon_key="longsword",
            npc_natural_attack_key="bite",
        )
