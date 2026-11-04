from fastapi import APIRouter, HTTPException

from api.runtime_context import (
    combat_encounter_service,
    get_current_runtime,
    turn_execution_lock,
)
from models.combat_api_schemas import (
    DeathSavingThrowIn,
    EncounterAttackIn,
    EncounterCreateIn,
    EncounterStartIn,
    EncounterTurnIn,
)

router = APIRouter()


# ============================================================
# D&D COMBAT ENCOUNTERS
# ============================================================


def _encounter_payload(encounter):
    active = encounter.active_combatant
    return {
        "encounter_id": encounter.encounter_id,
        "status": encounter.status.value,
        "round_number": encounter.round_number,
        "turn_index": encounter.turn_index,
        "initiative_order": list(encounter.initiative_order),
        "active_combatant_id": active.combatant_id if active else None,
        "tied_initiative_groups": [
            list(group) for group in encounter.tied_initiative_groups
        ],
        "combatants": {
            combatant_id: {
                "combatant_id": combatant.combatant_id,
                "name": combatant.name,
                "initiative": combatant.initiative,
                "current_hp": combatant.current_hp,
                "max_hp": combatant.max_hp,
                "armor_class": combatant.armor_class,
                "dexterity": combatant.dexterity,
                "strength": combatant.strength,
                "constitution": combatant.constitution,
                "intelligence": combatant.intelligence,
                "wisdom": combatant.wisdom,
                "charisma": combatant.charisma,
                "proficiency_bonus": combatant.proficiency_bonus,
                "death_save_successes": combatant.death_save_successes,
                "death_save_failures": combatant.death_save_failures,
                "stable": combatant.stable,
                "dead": combatant.dead,
                "death_save_last_round": combatant.death_save_last_round,
                "death_save_last_turn_index": combatant.death_save_last_turn_index,
                "action_used": combatant.action_used,
                "entity_id": combatant.entity_id,
                "is_player_character": combatant.is_player_character,
                "conscious": combatant.conscious,
                "defeated": combatant.defeated,
                "conditions": sorted(
                    condition.value for condition in combatant.conditions.conditions
                ),
                "exhaustion_level": combatant.conditions.exhaustion_level,
            }
            for combatant_id, combatant in encounter.combatants.items()
        },
    }


@router.get("/encounters")
def list_combat_encounters():
    return [
        _encounter_payload(encounter)
        for encounter in combat_encounter_service.list(
            get_current_runtime().campaign_id
        )
    ]


@router.post("/encounters", status_code=201)
def create_combat_encounter(data: EncounterCreateIn):
    try:
        with turn_execution_lock.acquire():
            encounter = combat_encounter_service.create(
                get_current_runtime().campaign_id,
                data.participants,
                data.encounter_id,
            )
        return _encounter_payload(encounter)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/encounters/{encounter_id}")
def get_combat_encounter(encounter_id: str):
    try:
        encounter = combat_encounter_service.get(
            get_current_runtime().campaign_id,
            encounter_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if encounter is None:
        raise HTTPException(status_code=404, detail="encounter not found")
    return _encounter_payload(encounter)


@router.post("/encounters/{encounter_id}/start")
def start_combat_encounter(encounter_id: str, data: EncounterStartIn):
    try:
        with turn_execution_lock.acquire():
            encounter = combat_encounter_service.start(
                get_current_runtime().campaign_id,
                encounter_id,
                dice_mode=data.dice_mode,
                manual_rolls=data.manual_rolls,
                initiative_order=(
                    tuple(data.initiative_order)
                    if data.initiative_order is not None
                    else None
                ),
            )
        return _encounter_payload(encounter)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/encounters/{encounter_id}/death-save")
def resolve_encounter_death_save(encounter_id: str, data: DeathSavingThrowIn):
    try:
        with turn_execution_lock.acquire():
            result = combat_encounter_service.death_saving_throw(
                get_current_runtime().campaign_id,
                encounter_id,
                expected_round=data.expected_round,
                expected_turn_index=data.expected_turn_index,
                dice_mode=data.dice_mode,
                manual_roll=data.manual_roll,
            )
        roll = result["result"]
        return {
            "encounter": _encounter_payload(result["encounter"]),
            "combatant_id": result["combatant_id"],
            "death_save": {
                "rolls": list(roll.rolls),
                "selected": roll.selected,
                "successes": roll.successes,
                "failures": roll.failures,
                "stable": roll.stable,
                "dead": roll.dead,
                "regained_hp": roll.regained_hp,
            },
        }
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/encounters/{encounter_id}/advance")
def advance_combat_encounter(encounter_id: str, data: EncounterTurnIn):
    try:
        with turn_execution_lock.acquire():
            result = combat_encounter_service.advance_turn_with_events(
                get_current_runtime().campaign_id,
                encounter_id,
                expected_round=data.expected_round,
                expected_turn_index=data.expected_turn_index,
            )
        payload = _encounter_payload(result["encounter"])
        roll = result["death_save"]
        payload["turn_start_death_save"] = (
            {
                "combatant_id": result["combatant_id"],
                "rolls": list(roll.rolls),
                "selected": roll.selected,
                "successes": roll.successes,
                "failures": roll.failures,
                "stable": roll.stable,
                "dead": roll.dead,
                "regained_hp": roll.regained_hp,
            }
            if roll is not None
            else None
        )
        return payload
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/encounters/{encounter_id}/complete")
def complete_combat_encounter(encounter_id: str, data: EncounterTurnIn):
    try:
        with turn_execution_lock.acquire():
            encounter = combat_encounter_service.complete(
                get_current_runtime().campaign_id,
                encounter_id,
                expected_round=data.expected_round,
                expected_turn_index=data.expected_turn_index,
            )
        return _encounter_payload(encounter)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc




@router.post("/encounters/{encounter_id}/attack")
def attack_in_combat_encounter(encounter_id: str, data: EncounterAttackIn):
    try:
        with turn_execution_lock.acquire():
            result = get_current_runtime().combat_attack_service.attack(
                campaign_id=get_current_runtime().campaign_id,
                encounter_id=encounter_id,
                target_combatant_id=data.target_combatant_id,
                expected_round=data.expected_round,
                expected_turn_index=data.expected_turn_index,
                dice_mode=data.dice_mode,
                manual_attack_rolls=(
                    tuple(data.manual_attack_rolls)
                    if data.manual_attack_rolls is not None else None
                ),
                manual_damage_rolls=(
                    tuple(data.manual_damage_rolls)
                    if data.manual_damage_rolls is not None else None
                ),
                target_within_5_feet=data.target_within_5_feet,
                versatile_two_handed=data.versatile_two_handed,
                finesse_ability=data.finesse_ability,
            )
        attack = result["result"]
        damage_roll = attack.damage_roll
        return {
            "encounter": _encounter_payload(result["encounter"]),
            "attacker_combatant_id": result["attacker_combatant_id"],
            "target_combatant_id": result["target_combatant_id"],
            "weapon_key": result["weapon_key"],
            "attack_ability": result["attack_ability"],
            "attack_bonus": result["attack_bonus"],
            "proficient": result["proficient"],
            "advantage": result["advantage"],
            "disadvantage": result["disadvantage"],
            "armor_training_penalty": result["armor_training_penalty"],
            "attack": {
                "rolls": list(attack.attack_roll.rolls),
                "selected": attack.attack_roll.selected,
                "total": attack.attack_roll.total,
                "target_ac": attack.target_ac,
                "hit": attack.hit,
                "critical": attack.critical,
            },
            "damage": {
                "type": attack.damage_type.value,
                "rolls": list(damage_roll.rolls) if damage_roll else [],
                "raw": attack.raw_damage,
                "after_defenses": attack.damage_after_defenses,
                "target_current_hp": result["target_current_hp"],
            },
        }
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
