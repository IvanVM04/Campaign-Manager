"""Transactional short/long rest use cases for persisted player characters."""

from __future__ import annotations

from dataclasses import dataclass

from database import transaction
from models.campaign_clock import CampaignClock
from models.character_state import CharacterState
from repositories.campaign_clock_repository import CampaignClockRepository
from repositories.campaign_repository import CampaignRepository
from repositories.character_repository import CharacterRepository
from repositories.combat_encounter_repository import CombatEncounterRepository
from repositories.persistent_effect_repository import PersistentEffectRepository
from rules_engine.dnd5e_2014.core.abilities import ability_modifier
from rules_engine.dnd5e_2014.core.dice import DiceRoller


SHORT_REST_MINUTES = 60
LONG_REST_MINUTES = 8 * 60
LONG_REST_RECOVERY_INTERVAL_MINUTES = 24 * 60


@dataclass(frozen=True, slots=True)
class CharacterRestResult:
    """Detached result of one fully committed rest."""

    rest_type: str
    character: CharacterState
    clock: CampaignClock
    hp_recovered: int
    hit_dice_spent: int
    hit_dice_recovered: int
    dice_rolls: tuple[int, ...]


class CharacterRestService:
    """Apply rest recovery to canonical character state and campaign time."""

    def __init__(
        self,
        *,
        campaign_id: int,
        campaign_repository: CampaignRepository | None = None,
        character_repository: CharacterRepository | None = None,
        clock_repository: CampaignClockRepository | None = None,
        encounter_repository: CombatEncounterRepository | None = None,
        effect_repository: PersistentEffectRepository | None = None,
        dice_roller: DiceRoller | None = None,
    ) -> None:
        if isinstance(campaign_id, bool) or not isinstance(campaign_id, int) or campaign_id < 1:
            raise ValueError("campaign_id must be a positive integer")
        self.campaign_id = campaign_id
        self.campaign_repository = campaign_repository or CampaignRepository()
        self.character_repository = character_repository or CharacterRepository()
        self.clock_repository = clock_repository or CampaignClockRepository()
        self.encounter_repository = encounter_repository or CombatEncounterRepository()
        self.effect_repository = effect_repository or PersistentEffectRepository()
        self.dice_roller = dice_roller or DiceRoller()

    def short_rest(
        self,
        character_entity_id: int,
        *,
        expected_elapsed_minutes: int,
        hit_dice_to_spend: int = 0,
        manual_rolls: tuple[int, ...] | None = None,
    ) -> CharacterRestResult:
        """Spend up to the available Hit Dice, then advance one fictional hour."""
        self._validate_non_negative_integer(
            expected_elapsed_minutes, "expected_elapsed_minutes"
        )
        self._validate_non_negative_integer(hit_dice_to_spend, "hit_dice_to_spend")
        if hit_dice_to_spend > 20:
            raise ValueError("hit_dice_to_spend cannot exceed 20")

        with transaction("IMMEDIATE") as conn:
            character, clock = self._load_rest_context(
                character_entity_id,
                expected_elapsed_minutes=expected_elapsed_minutes,
                conn=conn,
            )
            available = character.level - character.hit_dice_used
            if hit_dice_to_spend > available:
                raise ValueError(
                    f"cannot spend {hit_dice_to_spend} Hit Dice; "
                    f"only {available} remain"
                )
            if hit_dice_to_spend == 0 and manual_rolls is not None:
                raise ValueError("manual rolls require at least one Hit Die")
            if hit_dice_to_spend > 0 and manual_rolls is not None:
                if not isinstance(manual_rolls, tuple):
                    raise TypeError("manual_rolls must be a tuple")
                if len(manual_rolls) != hit_dice_to_spend:
                    raise ValueError("manual_rolls must contain one result per spent Hit Die")

            rolls: tuple[int, ...] = ()
            if hit_dice_to_spend:
                roll = self.dice_roller.roll(
                    hit_dice_to_spend,
                    character.hit_die_sides,
                    manual_rolls=manual_rolls,
                )
                rolls = roll.rolls

            constitution_modifier = ability_modifier(character.constitution)
            # Each die heals independently and cannot produce negative healing.
            healing = sum(max(0, value + constitution_modifier) for value in rolls)
            new_hp = min(character.max_hp, character.current_hp + healing)
            hp_recovered = new_hp - character.current_hp
            new_hit_dice_used = character.hit_dice_used + hit_dice_to_spend

            advanced_clock = self.clock_repository.advance(
                self.campaign_id,
                minutes=SHORT_REST_MINUTES,
                expected_elapsed_minutes=expected_elapsed_minutes,
                conn=conn,
            )
            self.effect_repository.expire_due(
                self.campaign_id,
                advanced_clock.elapsed_minutes,
                conn=conn,
            )
            updated_character = self.character_repository.update_rest_state(
                character.entity_id,
                campaign_id=self.campaign_id,
                expected_current_hp=character.current_hp,
                expected_hit_dice_used=character.hit_dice_used,
                expected_last_long_rest_elapsed_minutes=(
                    character.last_long_rest_elapsed_minutes
                ),
                new_current_hp=new_hp,
                new_hit_dice_used=new_hit_dice_used,
                new_last_long_rest_elapsed_minutes=(
                    character.last_long_rest_elapsed_minutes
                ),
                conn=conn,
            )
            return CharacterRestResult(
                rest_type="short",
                character=updated_character,
                clock=advanced_clock,
                hp_recovered=hp_recovered,
                hit_dice_spent=hit_dice_to_spend,
                hit_dice_recovered=0,
                dice_rolls=rolls,
            )

    def long_rest(
        self,
        character_entity_id: int,
        *,
        expected_elapsed_minutes: int,
    ) -> CharacterRestResult:
        """Restore HP, recover up to half of expended Hit Dice, and advance eight hours."""
        self._validate_non_negative_integer(
            expected_elapsed_minutes, "expected_elapsed_minutes"
        )
        with transaction("IMMEDIATE") as conn:
            character, clock = self._load_rest_context(
                character_entity_id,
                expected_elapsed_minutes=expected_elapsed_minutes,
                conn=conn,
            )
            last_rest = character.last_long_rest_elapsed_minutes
            if last_rest is not None and (
                clock.elapsed_minutes - last_rest
                < LONG_REST_RECOVERY_INTERVAL_MINUTES
            ):
                remaining = (
                    LONG_REST_RECOVERY_INTERVAL_MINUTES
                    - (clock.elapsed_minutes - last_rest)
                )
                raise ValueError(
                    "a character can benefit from only one long rest per 24 hours; "
                    f"{remaining} campaign minutes remain"
                )

            hit_dice_recovered = min(
                character.hit_dice_used,
                max(1, character.level // 2),
            )
            new_hit_dice_used = character.hit_dice_used - hit_dice_recovered
            advanced_clock = self.clock_repository.advance(
                self.campaign_id,
                minutes=LONG_REST_MINUTES,
                expected_elapsed_minutes=expected_elapsed_minutes,
                conn=conn,
            )
            self.effect_repository.expire_due(
                self.campaign_id,
                advanced_clock.elapsed_minutes,
                conn=conn,
            )
            updated_character = self.character_repository.update_rest_state(
                character.entity_id,
                campaign_id=self.campaign_id,
                expected_current_hp=character.current_hp,
                expected_hit_dice_used=character.hit_dice_used,
                expected_last_long_rest_elapsed_minutes=last_rest,
                new_current_hp=character.max_hp,
                new_hit_dice_used=new_hit_dice_used,
                new_last_long_rest_elapsed_minutes=advanced_clock.elapsed_minutes,
                conn=conn,
            )
            return CharacterRestResult(
                rest_type="long",
                character=updated_character,
                clock=advanced_clock,
                hp_recovered=character.max_hp - character.current_hp,
                hit_dice_spent=0,
                hit_dice_recovered=hit_dice_recovered,
                dice_rolls=(),
            )

    def _load_rest_context(
        self,
        character_entity_id: int,
        *,
        expected_elapsed_minutes: int,
        conn,
    ) -> tuple[CharacterState, CampaignClock]:
        if (
            isinstance(character_entity_id, bool)
            or not isinstance(character_entity_id, int)
            or character_entity_id < 1
        ):
            raise ValueError("character_entity_id must be a positive integer")
        if self.campaign_repository.get_campaign(self.campaign_id, conn=conn) is None:
            raise LookupError("campaign does not exist")
        character = self.character_repository.get_character(
            character_entity_id,
            campaign_id=self.campaign_id,
            conn=conn,
        )
        if character is None:
            raise LookupError("character does not exist in this campaign")
        if self.encounter_repository.has_active_for_campaign(
            self.campaign_id,
            conn=conn,
        ):
            raise ValueError("a character cannot rest while a combat encounter is active")
        clock = self.clock_repository.ensure(self.campaign_id, conn=conn)
        if clock.elapsed_minutes != expected_elapsed_minutes:
            raise RuntimeError("campaign clock changed; reload before resting")
        return character, clock

    @staticmethod
    def _validate_non_negative_integer(value: int, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
