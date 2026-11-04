"""Application use cases for campaign-scoped combat encounters."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from database import get_conn, transaction
from models.combat_encounter_state import CombatEncounterState, EncounterStatus
from models.combatant_state import CombatantState
from models.creature_state import CreatureState
from models.entity import Entity
from repositories.combat_encounter_repository import CombatEncounterRepository
from repositories.creature_repository import CreatureRepository
from rules_engine.dnd5e_2014.combat.death_saves import resolve_death_saving_throw
from rules_engine.dnd5e_2014.combat.initiative import roll_initiative
from rules_engine.dnd5e_2014.core.dice import DiceRoller


class CombatEncounterService:
    """Coordinates encounter lifecycle; rules calculations remain in rules_engine."""

    def __init__(
        self,
        *,
        repository: CombatEncounterRepository,
        character_repository,
        entity_repository,
        creature_repository: CreatureRepository | None = None,
        world_service=None,
        persistent_effect_repository=None,
        equipment_service=None,
        dice_roller: DiceRoller | None = None,
    ) -> None:
        self.repository = repository
        self.character_repository = character_repository
        self.entity_repository = entity_repository
        self.creature_repository = creature_repository or CreatureRepository()
        self.world_service = world_service
        self.persistent_effect_repository = persistent_effect_repository
        self.equipment_service = equipment_service
        self.dice_roller = dice_roller or DiceRoller()

    def create(self, campaign_id: int, participants, encounter_id: str | None = None):
        if not participants:
            raise ValueError("an encounter requires at least one participant")
        encounter_id = encounter_id or uuid4().hex
        created_creature = False
        with transaction("IMMEDIATE") as conn:
            if self.repository.get(encounter_id, campaign_id=campaign_id, conn=conn) is not None:
                raise ValueError("encounter_id already exists in this campaign")
            combatants = []
            for participant in participants:
                if participant.character_id is not None:
                    character = self.character_repository.get_character(
                        participant.character_id, campaign_id=campaign_id, conn=conn
                    )
                    entity = self.entity_repository.get_entity(
                        participant.character_id, campaign_id=campaign_id, conn=conn
                    )
                    if character is None or entity is None:
                        raise ValueError(
                            f"character {participant.character_id} does not exist in this campaign"
                        )
                    armor_class = character.armor_class
                    if self.equipment_service is not None:
                        armor_class = self.equipment_service.armor_class(
                            character, campaign_id=campaign_id, conn=conn
                        ).armor_class
                    combatants.append(CombatantState(
                        combatant_id=f"character-{character.entity_id}",
                        name=entity.name,
                        initiative=0,
                        current_hp=character.current_hp,
                        max_hp=character.max_hp,
                        armor_class=armor_class,
                        entity_id=character.entity_id,
                        is_player_character=True,
                        dexterity=character.dexterity,
                        strength=character.strength,
                        constitution=character.constitution,
                        intelligence=character.intelligence,
                        wisdom=character.wisdom,
                        charisma=character.charisma,
                        proficiency_bonus=character.proficiency_bonus,
                        conscious=character.current_hp > 0,
                    ))
                    continue

                if participant.creature_id is not None:
                    creature = self.creature_repository.get_creature(
                        participant.creature_id, campaign_id=campaign_id, conn=conn
                    )
                    entity = self.entity_repository.get_entity(
                        participant.creature_id, campaign_id=campaign_id, conn=conn
                    )
                    if creature is None or entity is None:
                        raise ValueError(
                            f"creature {participant.creature_id} does not exist in this campaign"
                        )
                else:
                    current_hp = (
                        participant.current_hp
                        if participant.current_hp is not None
                        else participant.max_hp
                    )
                    entity = self.entity_repository.save_entity(
                        Entity(
                            name=participant.name,
                            entity_type="creature",
                            description="NPC combat creature",
                        ),
                        campaign_id=campaign_id,
                        conn=conn,
                    )
                    created_creature = True
                    creature = self.creature_repository.save_creature(
                        CreatureState(
                            entity_id=entity.id,
                            current_hp=current_hp,
                            max_hp=participant.max_hp,
                            armor_class=participant.armor_class,
                            strength=participant.strength,
                            dexterity=participant.dexterity,
                            constitution=participant.constitution,
                            intelligence=participant.intelligence,
                            wisdom=participant.wisdom,
                            charisma=participant.charisma,
                            proficiency_bonus=participant.proficiency_bonus,
                        ),
                        campaign_id=campaign_id,
                        conn=conn,
                    )
                combatants.append(CombatantState(
                    combatant_id=f"creature-{entity.id}",
                    name=entity.name,
                    initiative=0,
                    current_hp=creature.current_hp,
                    max_hp=creature.max_hp,
                    armor_class=creature.armor_class,
                    entity_id=creature.entity_id,
                    is_player_character=False,
                    dexterity=creature.dexterity,
                    strength=creature.strength,
                    constitution=creature.constitution,
                    intelligence=creature.intelligence,
                    wisdom=creature.wisdom,
                    charisma=creature.charisma,
                    proficiency_bonus=creature.proficiency_bonus,
                    conscious=creature.current_hp > 0,
                ))

            encounter = CombatEncounterState.prepare(encounter_id, tuple(combatants))
            saved_encounter = self.repository.save(encounter, campaign_id=campaign_id, conn=conn)
        if created_creature and self.world_service is not None:
            self.world_service.load()
        return saved_encounter

    def get(self, campaign_id: int, encounter_id: str):
        return self.repository.get(encounter_id, campaign_id=campaign_id)

    def list(self, campaign_id: int):
        return self.repository.list_for_campaign(campaign_id)

    def start(
        self,
        campaign_id: int,
        encounter_id: str,
        *,
        dice_mode: str = "automatic",
        manual_rolls: dict[str, int] | None = None,
        initiative_order: tuple[str, ...] | None = None,
    ):
        with get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            encounter = self._require_encounter(campaign_id, encounter_id, conn=conn)
            if encounter.status is not EncounterStatus.PREPARING:
                raise ValueError("only a preparing encounter can be started")
            manual_rolls = manual_rolls or {}
            expected_ids = set(encounter.combatants)
            if dice_mode == "manual":
                if set(manual_rolls) != expected_ids:
                    raise ValueError("manual mode requires exactly one d20 result for every combatant")
            elif dice_mode == "automatic":
                if manual_rolls:
                    raise ValueError("manual_rolls can only be supplied in manual mode")
            else:
                raise ValueError("dice_mode must be automatic or manual")

            updated = {}
            for combatant_id, combatant in encounter.combatants.items():
                result = roll_initiative(
                    combatant_id=combatant_id,
                    dexterity_score=combatant.dexterity,
                    roller=self.dice_roller,
                    manual_rolls=(
                        (manual_rolls[combatant_id],) if dice_mode == "manual" else None
                    ),
                )
                updated[combatant_id] = replace(combatant, initiative=result.total)
            encounter.combatants = updated

            if initiative_order is None:
                tied = encounter.tied_initiative_groups
                if tied:
                    raise ValueError(
                        "initiative tie requires initiative_order to break ties: "
                        + "; ".join(", ".join(group) for group in tied)
                    )
                initiative_order = tuple(
                    sorted(
                        encounter.combatants,
                        key=lambda item: (-encounter.combatants[item].initiative, item),
                    )
                )
            encounter.start(tuple(initiative_order))
            return self.repository.save(encounter, campaign_id=campaign_id, conn=conn)

    def advance_turn(
        self,
        campaign_id: int,
        encounter_id: str,
        *,
        expected_round: int,
        expected_turn_index: int,
    ):
        with get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            encounter = self._require_encounter(campaign_id, encounter_id, conn=conn)
            self._check_position(encounter, expected_round, expected_turn_index)
            if encounter.status is not EncounterStatus.ACTIVE:
                raise ValueError("cannot advance a non-active encounter")
            previous_round = encounter.round_number
            encounter.advance_turn()
            if self.persistent_effect_repository is not None:
                absolute_turn = (
                    (encounter.round_number - 1) * len(encounter.initiative_order)
                    + encounter.turn_index
                )
                self.persistent_effect_repository.expire_encounter_due(
                    campaign_id,
                    encounter_id,
                    round_number=encounter.round_number,
                    absolute_turn=absolute_turn,
                    round_changed=encounter.round_number != previous_round,
                    conn=conn,
                )
            return self.repository.save(encounter, campaign_id=campaign_id, conn=conn)

    def complete(
        self,
        campaign_id: int,
        encounter_id: str,
        *,
        expected_round: int,
        expected_turn_index: int,
    ):
        with get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            encounter = self._require_encounter(campaign_id, encounter_id, conn=conn)
            self._check_position(encounter, expected_round, expected_turn_index)
            encounter.complete()
            if self.persistent_effect_repository is not None:
                self.persistent_effect_repository.expire_encounter(
                    campaign_id, encounter_id, conn=conn
                )
            return self.repository.save(encounter, campaign_id=campaign_id, conn=conn)

    def death_saving_throw(
        self,
        campaign_id: int,
        encounter_id: str,
        *,
        expected_round: int,
        expected_turn_index: int,
        dice_mode: str = "automatic",
        manual_roll: int | None = None,
    ) -> dict:
        """Resolve and persist the active player's death save atomically."""
        with transaction("IMMEDIATE") as conn:
            encounter = self._require_encounter(campaign_id, encounter_id, conn=conn)
            self._check_position(encounter, expected_round, expected_turn_index)
            if encounter.status is not EncounterStatus.ACTIVE:
                raise ValueError("death saving throws require an active encounter")
            combatant = encounter.active_combatant
            if combatant is None or not combatant.is_player_character or combatant.entity_id is None:
                raise ValueError("only the active persisted player character can make a death saving throw")
            if combatant.current_hp != 0:
                raise ValueError("death saving throws require zero hit points")
            if combatant.stable or combatant.dead:
                raise ValueError("this combatant's death saving throw track is already resolved")
            if (combatant.death_save_last_round, combatant.death_save_last_turn_index) == (expected_round, expected_turn_index):
                raise ValueError("a death saving throw has already been made this turn")
            if dice_mode not in ("automatic", "manual"):
                raise ValueError("dice_mode must be automatic or manual")
            if dice_mode == "automatic" and manual_roll is not None:
                raise ValueError("manual_roll can only be supplied in manual mode")
            if dice_mode == "manual" and manual_roll is None:
                raise ValueError("manual mode requires one d20 result")

            result = resolve_death_saving_throw(
                roller=self.dice_roller,
                successes=combatant.death_save_successes,
                failures=combatant.death_save_failures,
                manual_rolls=(manual_roll,) if manual_roll is not None else None,
            )
            recovered = result.regained_hp == 1
            new_hp = 1 if recovered else 0
            updated = replace(
                combatant,
                current_hp=new_hp,
                conscious=recovered,
                death_save_successes=0 if recovered else result.successes,
                death_save_failures=0 if recovered else result.failures,
                stable=result.stable,
                dead=result.dead,
                death_save_last_round=expected_round,
                death_save_last_turn_index=expected_turn_index,
            )
            encounter.combatants[combatant.combatant_id] = updated
            if recovered:
                character = self.character_repository.get_character(
                    combatant.entity_id, campaign_id=campaign_id, conn=conn
                )
                if character is None or character.current_hp != 0:
                    raise RuntimeError("character hit points and encounter snapshot differ; reload encounter")
                self.character_repository.update_current_hp(
                    combatant.entity_id,
                    campaign_id=campaign_id,
                    expected_current_hp=0,
                    new_current_hp=1,
                    conn=conn,
                )
            saved = self.repository.save(encounter, campaign_id=campaign_id, conn=conn)
            return {"encounter": saved, "combatant_id": combatant.combatant_id, "result": result}

    def _require_encounter(self, campaign_id: int, encounter_id: str, *, conn=None):
        encounter = self.repository.get(encounter_id, campaign_id=campaign_id, conn=conn)
        if encounter is None:
            raise LookupError("encounter does not exist in this campaign")
        return encounter

    @staticmethod
    def _check_position(encounter, expected_round, expected_turn_index):
        if encounter.round_number != expected_round:
            raise RuntimeError("encounter round changed; reload the encounter")
        if encounter.turn_index != expected_turn_index:
            raise RuntimeError("encounter turn changed; reload the encounter")
