"""Typed resolution of player and NPC combat attack profiles."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from models.character_state import CharacterState
from models.combatant_state import CombatantState
from models.creature_state import CreatureState
from repositories.character_repository import CharacterRepository
from repositories.creature_repository import CreatureRepository
from repositories.weapon_equipment_repository import WeaponEquipmentRepository
from rules_engine.dnd5e_2014.combat.damage import DamageType
from rules_engine.dnd5e_2014.weapons.attack_profile import (
    derive_attack_profile,
    derive_natural_attack_profile,
)
from rules_engine.dnd5e_2014.weapons.catalog import (
    WeaponDefinition,
    WeaponProperty,
    get_weapon,
)

_NATURAL_DAMAGE_DICE = re.compile(r"^([1-9][0-9]*)d(4|6|8|10|12|20)$")


@dataclass(frozen=True, slots=True)
class NpcWeaponAttackConfiguration:
    weapon_key: str
    proficient: bool = True


@dataclass(frozen=True, slots=True)
class NpcNaturalAttackConfiguration:
    key: str
    name: str
    ability: str
    damage_dice: str
    damage_type: DamageType
    reach_feet: int
    proficient: bool


@dataclass(frozen=True, slots=True)
class ResolvedCombatAttackProfile:
    """A normalized, immutable profile consumed by the attack use case."""

    character: CharacterState
    weapon: WeaponDefinition | None
    natural_attack_key: str | None
    attack_ability: str
    attack_bonus: int
    damage_dice: str
    damage_bonus: int
    damage_type: str
    proficient: bool
    properties: frozenset[WeaponProperty]
    reach_feet: int

    @property
    def weapon_key(self) -> str | None:
        return self.weapon.key if self.weapon is not None else None


class AttackProfileResolver:
    """Load canonical attacker state and derive one supported attack profile.

    Repository reads use the caller-owned transaction connection. The resolver
    does not mutate persistence, encounter state, resources or hit points.
    """

    def __init__(
        self,
        *,
        character_repository: CharacterRepository,
        weapon_repository: WeaponEquipmentRepository,
        creature_repository: CreatureRepository,
    ) -> None:
        self.character_repository = character_repository
        self.weapon_repository = weapon_repository
        self.creature_repository = creature_repository

    def resolve(
        self,
        *,
        attacker: CombatantState,
        campaign_id: int,
        conn: Any,
        npc_attack_weapon_key: str | None = None,
        npc_natural_attack_key: str | None = None,
        versatile_two_handed: bool = False,
        finesse_ability: str | None = None,
    ) -> ResolvedCombatAttackProfile:
        if npc_attack_weapon_key is not None and npc_natural_attack_key is not None:
            raise ValueError("select an NPC weapon or natural attack, not both")
        if attacker.entity_id is None:
            raise ValueError("attacker must be a persisted campaign entity")
        if attacker.is_player_character:
            return self._resolve_player_character(
                attacker=attacker,
                campaign_id=campaign_id,
                conn=conn,
                npc_attack_weapon_key=npc_attack_weapon_key,
                npc_natural_attack_key=npc_natural_attack_key,
                versatile_two_handed=versatile_two_handed,
                finesse_ability=finesse_ability,
            )
        return self._resolve_creature(
            attacker=attacker,
            campaign_id=campaign_id,
            conn=conn,
            npc_attack_weapon_key=npc_attack_weapon_key,
            npc_natural_attack_key=npc_natural_attack_key,
            versatile_two_handed=versatile_two_handed,
            finesse_ability=finesse_ability,
        )

    def _resolve_player_character(
        self,
        *,
        attacker: CombatantState,
        campaign_id: int,
        conn: Any,
        npc_attack_weapon_key: str | None,
        npc_natural_attack_key: str | None,
        versatile_two_handed: bool,
        finesse_ability: str | None,
    ) -> ResolvedCombatAttackProfile:
        if npc_attack_weapon_key is not None or npc_natural_attack_key is not None:
            raise ValueError("NPC attack selection cannot be used by player characters")
        entity_id = attacker.entity_id
        if entity_id is None:
            raise ValueError("attacker must be a persisted campaign entity")
        character = self.character_repository.get_character(
            entity_id,
            campaign_id=campaign_id,
            conn=conn,
        )
        if character is None:
            raise LookupError("attacking character does not exist in this campaign")
        if character.current_hp != attacker.current_hp:
            raise RuntimeError(
                "character hit points and encounter snapshot differ; reload encounter"
            )
        equipped = self.weapon_repository.get_equipped(
            campaign_id=campaign_id,
            character_entity_id=entity_id,
            conn=conn,
        )
        if equipped is None or equipped.get("weapon_key") is None:
            raise ValueError("attacking character has no equipped weapon")
        weapon = get_weapon(equipped["weapon_key"])
        return self._from_weapon(
            character=character,
            weapon=weapon,
            versatile_two_handed=versatile_two_handed,
            finesse_ability=finesse_ability,
        )

    def _resolve_creature(
        self,
        *,
        attacker: CombatantState,
        campaign_id: int,
        conn: Any,
        npc_attack_weapon_key: str | None,
        npc_natural_attack_key: str | None,
        versatile_two_handed: bool,
        finesse_ability: str | None,
    ) -> ResolvedCombatAttackProfile:
        entity_id = attacker.entity_id
        if entity_id is None:
            raise ValueError("attacker must be a persisted campaign entity")
        creature = self.creature_repository.get_creature(
            entity_id,
            campaign_id=campaign_id,
            conn=conn,
        )
        if creature is None:
            raise LookupError("attacking creature does not exist in this campaign")
        if creature.current_hp != attacker.current_hp:
            raise RuntimeError(
                "creature hit points and encounter snapshot differ; reload encounter"
            )

        natural_attacks = self._parse_natural_attacks(
            creature.metadata.get("npc_natural_attacks", [])
        )
        weapon_attacks = self._parse_weapon_attacks(creature.metadata)

        selected_natural = None
        if npc_natural_attack_key is not None:
            selected_natural = next(
                (item for item in natural_attacks if item.key == npc_natural_attack_key),
                None,
            )
            if selected_natural is None:
                raise ValueError(
                    "selected NPC natural attack is not configured for this creature"
                )
        elif not weapon_attacks and natural_attacks and npc_attack_weapon_key is None:
            selected_natural = natural_attacks[0]

        if selected_natural is not None:
            if versatile_two_handed or finesse_ability is not None:
                raise ValueError(
                    "weapon-specific options cannot be used with an NPC natural attack"
                )
            return self._from_natural_attack(creature, selected_natural)

        if npc_natural_attack_key is not None:
            raise ValueError(
                "selected NPC natural attack is not configured for this creature"
            )
        if not weapon_attacks:
            raise ValueError(
                "NPC attacker requires a configured melee weapon profile or natural attack profile"
            )
        selected_weapon = (
            next(
                (item for item in weapon_attacks if item.weapon_key == npc_attack_weapon_key),
                None,
            )
            if npc_attack_weapon_key is not None
            else weapon_attacks[0]
        )
        if selected_weapon is None:
            raise ValueError("selected NPC weapon is not configured for this creature")
        weapon = get_weapon(selected_weapon.weapon_key)
        if weapon.is_ranged:
            raise ValueError("NPC melee attack profiles must use melee weapons")
        character = self._character_from_creature(
            creature,
            weapon_proficiencies=(
                frozenset({weapon.category.value})
                if selected_weapon.proficient
                else frozenset()
            ),
        )
        return self._from_weapon(
            character=character,
            weapon=weapon,
            versatile_two_handed=versatile_two_handed,
            finesse_ability=finesse_ability,
        )

    @staticmethod
    def _parse_weapon_attacks(
        metadata: dict[str, Any],
    ) -> tuple[NpcWeaponAttackConfiguration, ...]:
        raw_profiles = metadata.get("npc_melee_attacks")
        if not isinstance(raw_profiles, list) or not raw_profiles:
            legacy_profile = metadata.get("npc_melee_attack")
            raw_profiles = [legacy_profile] if isinstance(legacy_profile, dict) else []
        if not raw_profiles:
            return ()

        profiles: list[NpcWeaponAttackConfiguration] = []
        seen_keys: set[str] = set()
        for item in raw_profiles:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("weapon_key"), str)
                or not item["weapon_key"].strip()
            ):
                raise ValueError("NPC melee weapon configuration is invalid")
            weapon_key = item["weapon_key"]
            proficient = item.get("proficient", True)
            if not isinstance(proficient, bool):
                raise TypeError("NPC melee proficiency configuration is invalid")
            if weapon_key in seen_keys:
                raise ValueError("NPC melee weapon keys must be unique")
            seen_keys.add(weapon_key)
            profiles.append(
                NpcWeaponAttackConfiguration(
                    weapon_key=weapon_key,
                    proficient=proficient,
                )
            )
        return tuple(profiles)

    @staticmethod
    def _parse_natural_attacks(
        raw_profiles: object,
    ) -> tuple[NpcNaturalAttackConfiguration, ...]:
        if not isinstance(raw_profiles, list):
            raise TypeError("NPC natural attack configuration must be a list")

        profiles: list[NpcNaturalAttackConfiguration] = []
        seen_keys: set[str] = set()
        required = (
            "key",
            "name",
            "ability",
            "damage_dice",
            "damage_type",
            "reach_feet",
            "proficient",
        )
        for item in raw_profiles:
            if not isinstance(item, dict) or any(key not in item for key in required):
                raise ValueError("NPC natural attack configuration is invalid")
            key = item["key"]
            name = item["name"]
            ability = item["ability"]
            damage_dice = item["damage_dice"]
            reach_feet = item["reach_feet"]
            proficient = item["proficient"]
            if (
                not isinstance(key, str)
                or not key.strip()
                or not isinstance(name, str)
                or not name.strip()
                or ability not in ("strength", "dexterity")
                or not isinstance(damage_dice, str)
                or _NATURAL_DAMAGE_DICE.fullmatch(damage_dice) is None
                or isinstance(reach_feet, bool)
                or not isinstance(reach_feet, int)
                or not 5 <= reach_feet <= 30
                or reach_feet % 5
                or not isinstance(proficient, bool)
            ):
                raise ValueError("NPC natural attack configuration is invalid")
            try:
                damage_type = DamageType(item["damage_type"])
            except (TypeError, ValueError) as exc:
                raise ValueError("NPC natural attack damage type is invalid") from exc
            if key in seen_keys:
                raise ValueError("NPC natural attack keys must be unique")
            seen_keys.add(key)
            profiles.append(
                NpcNaturalAttackConfiguration(
                    key=key,
                    name=name,
                    ability=ability,
                    damage_dice=damage_dice,
                    damage_type=damage_type,
                    reach_feet=reach_feet,
                    proficient=proficient,
                )
            )
        return tuple(profiles)

    @staticmethod
    def _character_from_creature(
        creature: CreatureState,
        *,
        weapon_proficiencies: frozenset[str] = frozenset(),
    ) -> CharacterState:
        return CharacterState(
            entity_id=creature.entity_id,
            current_hp=creature.current_hp,
            max_hp=creature.max_hp,
            armor_class=creature.armor_class,
            strength=creature.strength,
            dexterity=creature.dexterity,
            constitution=creature.constitution,
            intelligence=creature.intelligence,
            wisdom=creature.wisdom,
            charisma=creature.charisma,
            proficiency_bonus=creature.proficiency_bonus,
            weapon_proficiencies=weapon_proficiencies,
        )

    @staticmethod
    def _from_weapon(
        *,
        character: CharacterState,
        weapon: WeaponDefinition,
        versatile_two_handed: bool,
        finesse_ability: str | None,
    ) -> ResolvedCombatAttackProfile:
        if WeaponProperty.SPECIAL in weapon.properties:
            raise ValueError("this weapon requires a special attack resolver")
        if WeaponProperty.AMMUNITION in weapon.properties:
            raise ValueError("ammunition tracking is not implemented yet")
        if versatile_two_handed and WeaponProperty.VERSATILE not in weapon.properties:
            raise ValueError("weapon does not have the versatile property")
        profile = derive_attack_profile(
            character,
            weapon,
            versatile_two_handed=versatile_two_handed,
            finesse_ability=finesse_ability,
        )
        return ResolvedCombatAttackProfile(
            character=character,
            weapon=weapon,
            natural_attack_key=None,
            attack_ability=profile.attack_ability,
            attack_bonus=profile.attack_bonus,
            damage_dice=profile.damage_dice,
            damage_bonus=profile.damage_bonus,
            damage_type=profile.damage_type,
            proficient=profile.proficient,
            properties=weapon.properties,
            reach_feet=10 if WeaponProperty.REACH in weapon.properties else 5,
        )

    @staticmethod
    def _from_natural_attack(
        creature: CreatureState,
        profile: NpcNaturalAttackConfiguration,
    ) -> ResolvedCombatAttackProfile:
        character = AttackProfileResolver._character_from_creature(creature)
        derived = derive_natural_attack_profile(
            character,
            attack_ability=profile.ability,
            damage_dice=profile.damage_dice,
            damage_type=profile.damage_type.value,
            proficient=profile.proficient,
        )
        return ResolvedCombatAttackProfile(
            character=character,
            weapon=None,
            natural_attack_key=profile.key,
            attack_ability=derived.attack_ability,
            attack_bonus=derived.attack_bonus,
            damage_dice=derived.damage_dice,
            damage_bonus=derived.damage_bonus,
            damage_type=derived.damage_type,
            proficient=derived.proficient,
            properties=frozenset(),
            reach_feet=profile.reach_feet,
        )
