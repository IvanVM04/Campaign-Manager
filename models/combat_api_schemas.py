"""Validated request schemas for the combat encounter API."""

from typing import Literal

from pydantic import BaseModel, Field, StrictInt, model_validator


class NpcNaturalAttackIn(BaseModel):
    """A self-contained NPC natural weapon profile."""

    key: str = Field(..., min_length=1, max_length=60, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(..., min_length=1, max_length=80)
    ability: Literal["strength", "dexterity"] = "strength"
    damage_dice: str = Field(..., min_length=3, max_length=12, pattern=r"^[1-9][0-9]*d(4|6|8|10|12|20)$")
    damage_type: Literal[
        "acid", "bludgeoning", "cold", "fire", "force", "lightning",
        "necrotic", "piercing", "poison", "psychic", "radiant",
        "slashing", "thunder",
    ]
    reach_feet: StrictInt = Field(default=5, ge=5, le=30)
    proficient: bool = True

    @model_validator(mode="after")
    def validate_profile(self):
        if self.reach_feet % 5:
            raise ValueError("natural attack reach_feet must be a multiple of 5")
        if not isinstance(self.proficient, bool):
            raise TypeError("natural attack proficient must be a boolean")
        return self


class EncounterParticipantIn(BaseModel):
    character_id: int | None = Field(default=None, ge=1)
    creature_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    max_hp: int | None = Field(default=None, ge=1, le=10000)
    current_hp: int | None = Field(default=None, ge=0, le=10000)
    armor_class: int | None = Field(default=None, ge=0, le=100)
    dexterity: int | None = Field(default=None, ge=1, le=30)
    strength: int = Field(default=10, ge=1, le=30)
    constitution: int = Field(default=10, ge=1, le=30)
    intelligence: int = Field(default=10, ge=1, le=30)
    wisdom: int = Field(default=10, ge=1, le=30)
    charisma: int = Field(default=10, ge=1, le=30)
    proficiency_bonus: int = Field(default=2, ge=0, le=20)
    is_player_character: bool = False
    position_x: StrictInt | None = Field(default=None, ge=-10000, le=10000)
    position_y: StrictInt | None = Field(default=None, ge=-10000, le=10000)
    speed_feet: StrictInt = Field(default=30, ge=0, le=1000)
    npc_melee_weapon_key: str | None = Field(default=None, min_length=1, max_length=60)
    npc_melee_weapon_keys: list[str] | None = Field(default=None, min_length=1, max_length=10)
    npc_melee_proficient: bool = True
    npc_natural_attacks: list[NpcNaturalAttackIn] | None = Field(default=None, min_length=1, max_length=10)
    damage_resistances: list[Literal["acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic", "piercing", "poison", "psychic", "radiant", "slashing", "thunder"]] | None = Field(default=None, max_length=13)
    damage_vulnerabilities: list[Literal["acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic", "piercing", "poison", "psychic", "radiant", "slashing", "thunder"]] | None = Field(default=None, max_length=13)
    damage_immunities: list[Literal["acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic", "piercing", "poison", "psychic", "radiant", "slashing", "thunder"]] | None = Field(default=None, max_length=13)

    @model_validator(mode="after")
    def validate_source(self):
        if (self.position_x is None) != (self.position_y is None):
            raise ValueError("position_x and position_y must be supplied together")
        if self.character_id is not None and self.creature_id is not None:
            raise ValueError("participant cannot reference both a character and a creature")
        if self.npc_natural_attacks is not None:
            natural_keys = [profile.key for profile in self.npc_natural_attacks]
            if len(set(natural_keys)) != len(natural_keys):
                raise ValueError("NPC natural attack keys must be unique")
        for field_name in ("damage_resistances", "damage_vulnerabilities", "damage_immunities"):
            values = getattr(self, field_name)
            if values is not None and len(set(values)) != len(values):
                raise ValueError(f"{field_name} must contain unique damage types")
        if self.npc_melee_weapon_key is not None and self.npc_melee_weapon_keys is not None:
            raise ValueError("supply npc_melee_weapon_key or npc_melee_weapon_keys, not both")
        if self.npc_melee_weapon_keys is not None and (
            any(not isinstance(key, str) or not key.strip() for key in self.npc_melee_weapon_keys)
            or len(set(self.npc_melee_weapon_keys)) != len(self.npc_melee_weapon_keys)
        ):
            raise ValueError("NPC melee weapon keys must be non-empty and unique")
        if self.character_id is not None and (
            self.npc_melee_weapon_key is not None or self.npc_melee_weapon_keys is not None
            or self.npc_natural_attacks is not None
            or any(getattr(self, field_name) is not None for field_name in ("damage_resistances", "damage_vulnerabilities", "damage_immunities"))
        ):
            raise ValueError("player characters cannot use NPC attack profiles or creature damage defenses")
        if self.npc_melee_weapon_key is not None and not isinstance(self.npc_melee_proficient, bool):
            raise TypeError("npc_melee_proficient must be a boolean")
        if self.character_id is not None or self.creature_id is not None:
            if any(value is not None for value in (
                self.name, self.max_hp, self.current_hp,
                self.armor_class, self.dexterity,
            )):
                raise ValueError("entity references cannot be combined with manual combatant stats")
            if self.creature_id is not None and self.is_player_character:
                raise ValueError("creatures cannot be marked as player characters")
            if self.creature_id is not None and (
                self.npc_melee_weapon_key is not None or self.npc_melee_weapon_keys is not None
            ):
                return self
            return self
        required = {
            "name": self.name,
            "max_hp": self.max_hp,
            "armor_class": self.armor_class,
            "dexterity": self.dexterity,
        }
        missing = [key for key, value in required.items() if value is None]
        if missing:
            raise ValueError(f"manual combatant is missing: {', '.join(missing)}")
        if self.current_hp is not None and self.max_hp is not None and self.current_hp > self.max_hp:
            raise ValueError("current_hp cannot exceed max_hp")
        if self.is_player_character:
            raise ValueError("manual combatants cannot be marked as player characters")
        return self


class EncounterCreateIn(BaseModel):
    encounter_id: str | None = Field(default=None, min_length=1, max_length=100)
    participants: list[EncounterParticipantIn] = Field(..., min_length=1, max_length=30)


class EncounterStartIn(BaseModel):
    dice_mode: Literal["automatic", "manual"] = "automatic"
    manual_rolls: dict[str, StrictInt] = Field(default_factory=dict)
    initiative_order: list[str] | None = None

    @model_validator(mode="after")
    def validate_manual_rolls(self):
        if any(isinstance(value, bool) or not 1 <= value <= 20 for value in self.manual_rolls.values()):
            raise ValueError("manual initiative rolls must be integers from 1 to 20")
        return self


class EncounterTurnIn(BaseModel):
    """Optimistic concurrency token required for encounter mutations."""

    expected_round: StrictInt = Field(..., ge=1)
    expected_turn_index: StrictInt = Field(..., ge=0)


class EncounterAttackIn(BaseModel):
    target_combatant_id: str = Field(..., min_length=1, max_length=120)
    expected_round: int = Field(..., ge=1)
    expected_turn_index: int = Field(..., ge=0)
    dice_mode: Literal["automatic", "manual"] = "automatic"
    manual_attack_rolls: list[StrictInt] | None = Field(default=None, min_length=1, max_length=2)
    manual_damage_rolls: list[StrictInt] | None = None
    target_within_5_feet: bool = False
    versatile_two_handed: bool = False
    finesse_ability: Literal["strength", "dexterity"] | None = None
    npc_attack_weapon_key: str | None = Field(default=None, min_length=1, max_length=60)
    npc_natural_attack_key: str | None = Field(default=None, min_length=1, max_length=60)

    @model_validator(mode="after")
    def validate_dice_mode(self):
        if self.dice_mode == "automatic":
            if self.manual_attack_rolls is not None or self.manual_damage_rolls is not None:
                raise ValueError("manual dice cannot be supplied in automatic mode")
        elif self.manual_attack_rolls is None or self.manual_damage_rolls is None:
            raise ValueError("manual mode requires attack rolls and damage rolls (use [] on a miss)")
        if self.npc_attack_weapon_key is not None and self.npc_natural_attack_key is not None:
            raise ValueError("select an NPC weapon or natural attack, not both")
        if not isinstance(self.target_within_5_feet, bool) or not isinstance(self.versatile_two_handed, bool):
            raise TypeError("attack options must be booleans")
        if self.manual_attack_rolls is not None and any(not 1 <= value <= 20 for value in self.manual_attack_rolls):
            raise ValueError("manual attack rolls must be from 1 to 20")
        if self.manual_damage_rolls is not None and any(value < 1 for value in self.manual_damage_rolls):
            raise ValueError("manual damage rolls must be positive")
        return self


class DeathSavingThrowIn(BaseModel):
    """One death saving throw for the active player character."""

    expected_round: StrictInt = Field(..., ge=1)
    expected_turn_index: StrictInt = Field(..., ge=0)
    dice_mode: Literal["automatic", "manual"] = "automatic"
    manual_roll: StrictInt | None = Field(default=None, ge=1, le=20)

    @model_validator(mode="after")
    def validate_dice_mode(self):
        if self.dice_mode == "automatic" and self.manual_roll is not None:
            raise ValueError("manual_roll can only be supplied in manual mode")
        if self.dice_mode == "manual" and self.manual_roll is None:
            raise ValueError("manual mode requires one d20 result")
        return self


class EncounterReactionIn(BaseModel):
    combatant_id: str = Field(..., min_length=1, max_length=120)
    expected_round: StrictInt = Field(..., ge=1)
    expected_turn_index: StrictInt = Field(..., ge=0)


class GridPositionIn(BaseModel):
    x: StrictInt = Field(..., ge=-10000, le=10000)
    y: StrictInt = Field(..., ge=-10000, le=10000)


class EncounterMoveIn(EncounterTurnIn):
    combatant_id: str = Field(..., min_length=1, max_length=120)
    path: list[GridPositionIn] = Field(..., min_length=2, max_length=200)


class EncounterOpportunityAttackIn(EncounterAttackIn):
    """Reaction attack made when the active combatant leaves an attacker's reach."""

    attacker_combatant_id: str = Field(..., min_length=1, max_length=120)
    mover_previous_position: GridPositionIn
    reach_feet: StrictInt = Field(default=5, ge=5, le=30)
    npc_attack_weapon_key: str | None = Field(default=None, min_length=1, max_length=60)
    npc_natural_attack_key: str | None = Field(default=None, min_length=1, max_length=60)
    voluntary: bool = True
    disengaging: bool = False

    @model_validator(mode="after")
    def validate_opportunity_context(self):
        if self.reach_feet % 5:
            raise ValueError("reach_feet must be a multiple of 5")
        if self.npc_attack_weapon_key is not None and self.npc_natural_attack_key is not None:
            raise ValueError("select an NPC weapon or natural attack, not both")
        if not isinstance(self.voluntary, bool) or not isinstance(self.disengaging, bool):
            raise TypeError("movement flags must be booleans")
        return self
