"""Validated request/transport schemas for the character API context."""

from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from rules_engine.dnd5e_2014.core.abilities import Ability
from rules_engine.dnd5e_2014.core.skills import Skill

class CharacterCreate(BaseModel):
    """
    Datos mínimos necesarios para crear el personaje jugador.

    No pretende ser todavía un character builder completo de D&D.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )

    class_name: str | None = Field(
        default=None,
        max_length=100,
    )

    level: int = Field(
        default=1,
        ge=1,
        le=20,
    )

    max_hp: int = Field(
        ...,
        ge=1,
        le=1000,
    )

    current_hp: int | None = Field(
        default=None,
        ge=0,
        le=1000,
    )

    armor_class: int = Field(
        default=10,
        ge=0,
        le=100,
    )

    strength: int = Field(
        default=10,
        ge=1,
        le=30,
    )

    dexterity: int = Field(
        default=10,
        ge=1,
        le=30,
    )

    constitution: int = Field(
        default=10,
        ge=1,
        le=30,
    )

    intelligence: int = Field(
        default=10,
        ge=1,
        le=30,
    )

    wisdom: int = Field(
        default=10,
        ge=1,
        le=30,
    )

    charisma: int = Field(
        default=10,
        ge=1,
        le=30,
    )

    proficiency_bonus: int = Field(
        default=2,
        ge=2,
        le=6,
    )

    skill_proficiencies: list[Skill] = Field(default_factory=list)

    skill_expertise: list[Skill] = Field(default_factory=list)

    saving_throw_proficiencies: list[Ability] = Field(default_factory=list)

    armor_proficiencies: list[Literal["light", "medium", "heavy", "shields"]] = Field(
        default_factory=list
    )

    metadata: dict = Field(
        default_factory=dict,
    )

    @model_validator(mode="after")
    def validate_proficiencies(self):
        if len(set(self.skill_proficiencies)) != len(self.skill_proficiencies):
            raise ValueError("skill_proficiencies cannot contain duplicates")
        if len(set(self.skill_expertise)) != len(self.skill_expertise):
            raise ValueError("skill_expertise cannot contain duplicates")
        if len(set(self.saving_throw_proficiencies)) != len(self.saving_throw_proficiencies):
            raise ValueError("saving_throw_proficiencies cannot contain duplicates")
        if len(set(self.armor_proficiencies)) != len(self.armor_proficiencies):
            raise ValueError("armor_proficiencies cannot contain duplicates")
        if not set(self.skill_expertise).issubset(self.skill_proficiencies):
            raise ValueError("skill expertise requires skill proficiency")
        unarmored_defense = self.metadata.get("unarmored_defense")
        if unarmored_defense not in (None, "barbarian", "monk"):
            raise ValueError("metadata.unarmored_defense must be barbarian, monk or omitted")
        return self

    @field_validator("name")
    @classmethod
    def validate_name(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "name must not be empty"
            )

        return value

    @field_validator("class_name")
    @classmethod
    def validate_class_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        return value

    @field_validator("current_hp")
    @classmethod
    def validate_current_hp(
        cls,
        value: int | None,
        info,
    ) -> int | None:
        if value is None:
            return value

        max_hp = info.data.get("max_hp")

        if max_hp is not None and value > max_hp:
            raise ValueError(
                "current_hp cannot exceed max_hp"
            )

        return value
