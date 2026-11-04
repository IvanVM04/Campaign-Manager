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
        dice_roller: DiceRoller | None = None,
    ) -> None:
        self.repository = repository
        self.character_repository = character_repository
        self.entity_repository = entity_repository
        self.creature_repository = creature_repository or CreatureRepository()
        self.dice_roller = dice_roller or DiceRoller()

    def create(self, campaign_id: int, participants, encounter_id: str | None = None):
        if not participants:
            raise ValueError("an encounter requires at least one participant")
        encounter_id = encounter_id or uuid4().hex
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
                    combatants.append(CombatantState(
                        combatant_id=f"character-{character.entity_id}",
                        name=entity.name,
                        initiative=0,
                        current_hp=character.current_hp,
                        max_hp=character.max_hp,
                        armor_class=character.armor_class,
                        entity_id=character.entity_id,
                        is_player_character=True,
                        dexterity=character.dexterity,
                        strength=character.strength,
                        constitution=character.constitution,
                        intelligence=character.intelligence,
                        wisdom=character.wisdom,
                        charisma=character.charisma,
                        proficiency_bonus=character.proficiency_bonus,
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
                ))

            encounter = CombatEncounterState.prepare(encounter_id, tuple(combatants))
            return self.repository.save(encounter, campaign_id=campaign_id, conn=conn)

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
        expected_round: int | None = None,
        expected_turn_index: int | None = None,
    ):
        with get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            encounter = self._require_encounter(campaign_id, encounter_id, conn=conn)
            self._check_position(encounter, expected_round, expected_turn_index)
            if encounter.status is not EncounterStatus.ACTIVE:
                raise ValueError("cannot advance a non-active encounter")
            encounter.advance_turn()
            return self.repository.save(encounter, campaign_id=campaign_id, conn=conn)

    def complete(
        self,
        campaign_id: int,
        encounter_id: str,
        *,
        expected_round: int | None = None,
        expected_turn_index: int | None = None,
    ):
        with get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            encounter = self._require_encounter(campaign_id, encounter_id, conn=conn)
            self._check_position(encounter, expected_round, expected_turn_index)
            encounter.complete()
            return self.repository.save(encounter, campaign_id=campaign_id, conn=conn)

    def _require_encounter(self, campaign_id: int, encounter_id: str, *, conn=None):
        encounter = self.repository.get(encounter_id, campaign_id=campaign_id, conn=conn)
        if encounter is None:
            raise LookupError("encounter does not exist in this campaign")
        return encounter

    @staticmethod
    def _check_position(encounter, expected_round, expected_turn_index):
        if expected_round is not None and encounter.round_number != expected_round:
            raise RuntimeError("encounter round changed; reload the encounter")
        if (
            expected_turn_index is not None
            and encounter.turn_index != expected_turn_index
        ):
            raise RuntimeError("encounter turn changed; reload the encounter")
