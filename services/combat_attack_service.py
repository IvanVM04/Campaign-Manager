"""Atomic weapon attack use case for active campaign encounters."""

import re
from dataclasses import replace

from database import transaction
from models.character_state import CharacterState
from models.combat_encounter_state import EncounterStatus
from repositories.character_repository import CharacterRepository
from repositories.combat_encounter_repository import CombatEncounterRepository
from repositories.creature_repository import CreatureRepository
from repositories.weapon_equipment_repository import WeaponEquipmentRepository
from rules_engine.dnd5e_2014.combat.attack import resolve_attack
from rules_engine.dnd5e_2014.combat.conditions import attack_roll_advantage_state
from rules_engine.dnd5e_2014.combat.damage import DamageType, apply_hit_point_damage
from rules_engine.dnd5e_2014.combat.movement import (
    GridPosition,
    grid_distance_feet,
    provokes_opportunity_attack,
)
from rules_engine.dnd5e_2014.core.dice import DiceRoller
from rules_engine.dnd5e_2014.weapons.attack_profile import derive_attack_profile
from rules_engine.dnd5e_2014.weapons.catalog import WeaponProperty, get_weapon

_DAMAGE_DICE = re.compile(r"^(\d+)d(\d+)$")


class CombatAttackService:
    """Resolve a supported weapon attack and persist both HP snapshots atomically."""

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
        opportunity_attack: bool = False,
        attacker_combatant_id: str | None = None,
        mover_previous_position: GridPosition | None = None,
        reach_feet: int = 5,
        npc_attack_weapon_key: str | None = None,
        voluntary: bool = True,
        disengaging: bool = False,
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

            if not isinstance(opportunity_attack, bool):
                raise TypeError("opportunity_attack must be a boolean")
            if opportunity_attack:
                if not attacker_combatant_id or mover_previous_position is None:
                    raise ValueError("opportunity attacks require an attacker and previous mover position")
                attacker = encounter.combatants.get(attacker_combatant_id)
                if attacker is None:
                    raise ValueError("opportunity attacker is not part of this encounter")
                if attacker.combatant_id == encounter.active_combatant.combatant_id:
                    raise ValueError("the active combatant cannot make an opportunity attack against itself")
                if attacker.reaction_used:
                    raise ValueError("this combatant has already used its reaction")
            else:
                if attacker_combatant_id is not None or mover_previous_position is not None:
                    raise ValueError("movement context is only valid for an opportunity attack")
                attacker = encounter.active_combatant
                if attacker is None or attacker.action_used:
                    raise ValueError("the active combatant has already used its action")
            if attacker is None or attacker.entity_id is None:
                raise ValueError("attacker must be a persisted campaign entity")
            if not attacker.is_player_character and not opportunity_attack:
                raise ValueError("NPCs can only make opportunity attacks in this release")
            if attacker.defeated or not attacker.conscious or attacker.conditions.is_incapacitated:
                raise ValueError("an unconscious, defeated or incapacitated combatant cannot attack")
            target = encounter.combatants.get(target_combatant_id)
            if target is None:
                raise ValueError("target is not part of this encounter")
            if target.combatant_id == attacker.combatant_id:
                raise ValueError("a combatant cannot target itself")
            if target.dead:
                raise ValueError("cannot attack a dead target")
            if opportunity_attack:
                active = encounter.active_combatant
                if active is None or target.combatant_id != active.combatant_id:
                    raise ValueError("opportunity attacks can only target the combatant currently moving")
                if target.position_x is None or target.position_y is None:
                    raise ValueError("moving combatant has no persisted tactical position")
                if attacker.position_x is None or attacker.position_y is None:
                    raise ValueError("opportunity attacker has no persisted tactical position")
                mover_next_position = GridPosition(target.position_x, target.position_y)
                if grid_distance_feet(mover_previous_position, mover_next_position) != 5:
                    raise ValueError("opportunity attack movement must be one adjacent square")
                if not provokes_opportunity_attack(
                    attacker_position=GridPosition(attacker.position_x, attacker.position_y),
                    mover_previous_position=mover_previous_position,
                    mover_next_position=mover_next_position,
                    reach_feet=reach_feet,
                    voluntary=voluntary,
                    disengaging=disengaging,
                    attacker_incapacitated=attacker.conditions.is_incapacitated,
                    attacker_dead=attacker.dead,
                    attacker_reaction_available=not attacker.reaction_used,
                ):
                    raise ValueError("this movement does not provoke an opportunity attack")
                target_within_5_feet = (
                    grid_distance_feet(
                        GridPosition(attacker.position_x, attacker.position_y),
                        mover_previous_position,
                    ) <= 5
                )
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

            if attacker.is_player_character:
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
                if npc_attack_weapon_key is not None:
                    raise ValueError("NPC weapon selection is only valid for NPC opportunity attacks")
            else:
                creature = self.creature_repository.get_creature(
                    attacker.entity_id, campaign_id=campaign_id, conn=conn
                )
                if creature is None:
                    raise LookupError("attacking creature does not exist in this campaign")
                if creature.current_hp != attacker.current_hp:
                    raise RuntimeError("creature hit points and encounter snapshot differ; reload encounter")
                npc_attacks = creature.metadata.get("npc_melee_attacks")
                if not isinstance(npc_attacks, list) or not npc_attacks:
                    legacy_profile = creature.metadata.get("npc_melee_attack")
                    npc_attacks = [legacy_profile] if isinstance(legacy_profile, dict) else []
                if not npc_attacks:
                    raise ValueError("NPC opportunity attacker requires a configured melee weapon profile")
                if any(
                    not isinstance(profile, dict)
                    or not isinstance(profile.get("weapon_key"), str)
                    for profile in npc_attacks
                ):
                    raise ValueError("NPC melee weapon configuration is invalid")
                selected_profile = (
                    next(
                        (profile for profile in npc_attacks
                         if profile["weapon_key"] == npc_attack_weapon_key),
                        None,
                    )
                    if npc_attack_weapon_key is not None else npc_attacks[0]
                )
                if selected_profile is None:
                    raise ValueError("selected NPC weapon is not configured for this creature")
                weapon = get_weapon(selected_profile["weapon_key"])
                proficient = selected_profile.get("proficient", True)
                if not isinstance(proficient, bool):
                    raise ValueError("NPC melee proficiency configuration is invalid")
                character = CharacterState(
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
                    weapon_proficiencies=(
                        frozenset({weapon.category.value}) if proficient else frozenset()
                    ),
                )
            if opportunity_attack:
                if weapon.is_ranged:
                    raise ValueError("opportunity attacks require a melee weapon")
                expected_reach = 10 if WeaponProperty.REACH in weapon.properties else 5
                if reach_feet != expected_reach:
                    raise ValueError("reach_feet must match the equipped weapon's reach")
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
                attacker.is_player_character
                and self.equipment_service is not None
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
                    was_stable = stable
                    stable = False
                    if was_stable:
                        death_save_successes = 0
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
                    # Massive damage is an immediate death; keep the terminal
                    # state consistent with the three-failure invariant.
                    death_save_failures = 3 if dead else 0
                    stable = False
                if dead:
                    new_target_hp = 0
                    conscious = False
            updated_combatants = dict(encounter.combatants)
            updated_combatants[attacker.combatant_id] = (
                replace(attacker, reaction_used=True)
                if opportunity_attack
                else replace(attacker, action_used=True)
            )
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
                "opportunity_attack": opportunity_attack,
            }
