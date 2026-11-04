"""Atomic weapon attack use case for active campaign encounters."""

import re
from dataclasses import replace

from database import transaction
from models.combat_encounter_state import EncounterStatus
from repositories.character_repository import CharacterRepository
from repositories.combat_encounter_repository import CombatEncounterRepository
from repositories.creature_repository import CreatureRepository
from repositories.weapon_equipment_repository import WeaponEquipmentRepository
from rules_engine.dnd5e_2014.combat.attack import resolve_attack
from rules_engine.dnd5e_2014.combat.conditions import attack_roll_advantage_state
from rules_engine.dnd5e_2014.combat.damage import DamageType, apply_hit_point_damage
from rules_engine.dnd5e_2014.core.dice import DiceRoller
from rules_engine.dnd5e_2014.weapons.attack_profile import derive_attack_profile
from rules_engine.dnd5e_2014.weapons.catalog import WeaponProperty, get_weapon

_DAMAGE_DICE = re.compile(r"^(\d+)d(\d+)$")


class CombatAttackService:
    """Resolve an equipped PC weapon attack and persist both HP snapshots atomically."""

    def __init__(
        self,
        *,
        encounter_repository: CombatEncounterRepository,
        character_repository: CharacterRepository,
        weapon_repository: WeaponEquipmentRepository,
        dice_roller: DiceRoller | None = None,
        effective_condition_service=None,
        creature_repository: CreatureRepository | None = None,
        equipment_service=None,
    ) -> None:
        self.encounter_repository = encounter_repository
        self.character_repository = character_repository
        self.weapon_repository = weapon_repository
        self.dice_roller = dice_roller or DiceRoller()
        self.effective_condition_service = effective_condition_service
        self.creature_repository = creature_repository or CreatureRepository()
        self.equipment_service = equipment_service

    def attack(
        self,
        *,
        campaign_id: int,
        encounter_id: str,
        target_combatant_id: str,
        expected_round: int,
        expected_turn_index: int,
        dice_mode: str = "automatic",
        manual_attack_rolls: tuple[int, ...] | None = None,
        manual_damage_rolls: tuple[int, ...] | None = None,
        target_within_5_feet: bool = False,
        versatile_two_handed: bool = False,
        finesse_ability: str | None = None,
    ) -> dict:
        with transaction("IMMEDIATE") as conn:
            # Acquire the SQLite write lock before reading the encounter so a
            # concurrent action cannot pass the same expected turn position.
            encounter = self.encounter_repository.get(
                encounter_id, campaign_id=campaign_id, conn=conn
            )
            if encounter is None:
                raise LookupError("encounter does not exist in this campaign")
            if encounter.status is not EncounterStatus.ACTIVE:
                raise ValueError("attacks require an active encounter")
            if (encounter.round_number, encounter.turn_index) != (
                expected_round, expected_turn_index
            ):
                raise RuntimeError("encounter turn changed; reload the encounter")

            attacker = encounter.active_combatant
            if attacker is None or attacker.entity_id is None or not attacker.is_player_character:
                raise ValueError("only a persisted player character can attack in this release")
            if attacker.action_used:
                raise ValueError("the active combatant has already used its action")
            if attacker.defeated or not attacker.conscious or attacker.conditions.is_incapacitated:
                raise ValueError("an unconscious, defeated or incapacitated combatant cannot attack")
            target = encounter.combatants.get(target_combatant_id)
            if target is None:
                raise ValueError("target is not part of this encounter")
            if target.combatant_id == attacker.combatant_id:
                raise ValueError("a combatant cannot target itself")
            if target.dead:
                raise ValueError("cannot attack a dead target")
            if dice_mode not in ("automatic", "manual"):
                raise ValueError("dice_mode must be automatic or manual")
            if dice_mode == "automatic" and (
                manual_attack_rolls is not None or manual_damage_rolls is not None
            ):
                raise ValueError("manual dice cannot be supplied in automatic mode")
            if dice_mode == "manual" and (
                manual_attack_rolls is None or manual_damage_rolls is None
            ):
                raise ValueError("manual mode requires attack and damage rolls")

            character = self.character_repository.get_character(
                attacker.entity_id, campaign_id=campaign_id, conn=conn
            )
            if character is None:
                raise LookupError("attacking character does not exist in this campaign")
            if character.current_hp != attacker.current_hp:
                raise RuntimeError("character hit points and encounter snapshot differ; reload encounter")

            equipped = self.weapon_repository.get_equipped(
                campaign_id=campaign_id,
                character_entity_id=attacker.entity_id,
                conn=conn,
            )
            if equipped is None or equipped["weapon_key"] is None:
                raise ValueError("attacking character has no equipped weapon")
            weapon = get_weapon(equipped["weapon_key"])
            if WeaponProperty.SPECIAL in weapon.properties:
                raise ValueError("this weapon requires a special attack resolver")
            if WeaponProperty.AMMUNITION in weapon.properties:
                raise ValueError("ammunition tracking is not implemented yet")
            if versatile_two_handed and WeaponProperty.TWO_HANDED in weapon.properties:
                raise ValueError("this weapon is already two-handed, not versatile")
            if versatile_two_handed and WeaponProperty.VERSATILE not in weapon.properties:
                raise ValueError("weapon does not have the versatile property")

            profile = derive_attack_profile(
                character,
                weapon,
                versatile_two_handed=versatile_two_handed,
                finesse_ability=finesse_ability,
            )
            match = _DAMAGE_DICE.fullmatch(profile.damage_dice)
            if match:
                dice_count, die_sides, fixed_damage = int(match.group(1)), int(match.group(2)), 0
            else:
                try:
                    dice_count, die_sides, fixed_damage = 0, 0, int(profile.damage_dice)
                except ValueError as exc:
                    raise ValueError("weapon damage expression is not supported") from exc

            attacker_conditions = attacker.conditions
            target_conditions = target.conditions
            if self.effective_condition_service is not None:
                if attacker.entity_id is not None:
                    attacker_conditions = self.effective_condition_service.for_entity(attacker.entity_id, campaign_id=campaign_id, base=attacker_conditions, conn=conn)
                if target.entity_id is not None:
                    target_conditions = self.effective_condition_service.for_entity(target.entity_id, campaign_id=campaign_id, base=target_conditions, conn=conn)
            if attacker_conditions.is_incapacitated:
                raise ValueError("persistent conditions prevent this combatant from attacking")
            advantage, disadvantage = attack_roll_advantage_state(
                attacker=attacker_conditions,
                target=target_conditions,
                target_within_5_feet=target_within_5_feet,
            )
            armor_training_penalty = False
            if (
                self.equipment_service is not None
                and profile.attack_ability in {"strength", "dexterity"}
            ):
                armor_training = self.equipment_service.armor_proficiency(
                    character, campaign_id=campaign_id, conn=conn
                )
                armor_training_penalty = armor_training.strength_dexterity_disadvantage
                disadvantage = disadvantage or armor_training_penalty
            target_armor_class = target.armor_class
            if (
                target.is_player_character
                and target.entity_id is not None
                and self.equipment_service is not None
            ):
                target_character_for_ac = self.character_repository.get_character(
                    target.entity_id, campaign_id=campaign_id, conn=conn
                )
                if target_character_for_ac is None:
                    raise LookupError("target character does not exist in this campaign")
                target_armor_class = self.equipment_service.armor_class(
                    target_character_for_ac, campaign_id=campaign_id, conn=conn
                ).armor_class

            result = resolve_attack(
                roller=self.dice_roller,
                attack_bonus=profile.attack_bonus,
                target_ac=target_armor_class,
                damage_dice_count=dice_count,
                damage_die_sides=die_sides,
                damage_bonus=profile.damage_bonus,
                fixed_damage=fixed_damage,
                damage_type=DamageType(profile.damage_type),
                advantage=advantage,
                disadvantage=disadvantage,
                manual_attack_rolls=manual_attack_rolls,
                manual_damage_rolls=(
                    tuple(manual_damage_rolls) if manual_damage_rolls is not None else None
                ),
            )

            damage = result.damage_after_defenses
            new_target_hp = apply_hit_point_damage(target.current_hp, damage)
            death_save_successes = target.death_save_successes
            death_save_failures = target.death_save_failures
            stable = target.stable
            dead = target.dead
            conscious = target.conscious
            if damage > 0:
                if target.current_hp == 0:
                    # Damage while dying causes one failed save, or two on a
                    # critical hit. Stable creatures become unstable again.
                    stable = False
                    death_save_failures = min(
                        3, death_save_failures + (2 if result.critical else 1)
                    )
                    dead = death_save_failures >= 3
                    conscious = False
                elif new_target_hp == 0:
                    # Massive damage can kill outright when the excess damage
                    # equals or exceeds the creature's hit point maximum.
                    dead = damage - target.current_hp >= target.max_hp
                    conscious = False
                    death_save_successes = 0
                    death_save_failures = 0
                    stable = False
                if dead:
                    new_target_hp = 0
                    conscious = False
            updated_combatants = dict(encounter.combatants)
            updated_combatants[attacker.combatant_id] = replace(attacker, action_used=True)
            updated_combatants[target.combatant_id] = replace(
                target,
                current_hp=new_target_hp,
                armor_class=target_armor_class,
                conscious=conscious,
                death_save_successes=death_save_successes,
                death_save_failures=death_save_failures,
                stable=stable,
                dead=dead,
            )
            encounter.combatants = updated_combatants

            if target.is_player_character:
                if target.entity_id is None:
                    raise RuntimeError("player combatant is missing its entity reference")
                target_character = self.character_repository.get_character(
                    target.entity_id, campaign_id=campaign_id, conn=conn
                )
                if target_character is None or target_character.current_hp != target.current_hp:
                    raise RuntimeError("target character hit points changed; reload encounter")
                self.character_repository.update_current_hp(
                    target.entity_id,
                    campaign_id=campaign_id,
                    expected_current_hp=target.current_hp,
                    new_current_hp=new_target_hp,
                    conn=conn,
                )
            elif target.entity_id is not None:
                target_creature = self.creature_repository.get_creature(
                    target.entity_id, campaign_id=campaign_id, conn=conn
                )
                if target_creature is None or target_creature.current_hp != target.current_hp:
                    raise RuntimeError("creature hit points and encounter snapshot differ; reload encounter")
                self.creature_repository.update_current_hp(
                    target.entity_id,
                    campaign_id=campaign_id,
                    expected_current_hp=target.current_hp,
                    new_current_hp=new_target_hp,
                    conn=conn,
                )

            self.encounter_repository.save(encounter, campaign_id=campaign_id, conn=conn)
            return {
                "encounter": encounter,
                "attacker_combatant_id": attacker.combatant_id,
                "target_combatant_id": target.combatant_id,
                "weapon_key": weapon.key,
                "attack_ability": profile.attack_ability,
                "attack_bonus": profile.attack_bonus,
                "proficient": profile.proficient,
                "advantage": advantage,
                "disadvantage": disadvantage,
                "armor_training_penalty": armor_training_penalty,
                "result": result,
                "target_current_hp": new_target_hp,
                "target_armor_class": target_armor_class,
            }
