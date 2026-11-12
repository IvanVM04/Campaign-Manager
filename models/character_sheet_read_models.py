from pydantic import BaseModel, ConfigDict


class AbilityScoreRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    ability: str
    score: int
    modifier: int


class SkillRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    skill: str
    ability: str
    proficient: bool
    expertise: bool
    modifier: int


class SavingThrowRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    ability: str
    proficient: bool
    modifier: int


class CharacterSheetRead(BaseModel):
    """Detached, player-facing projection of a character's current sheet."""

    model_config = ConfigDict(frozen=True)

    entity_id: int
    name: str
    entity_type: str
    description: str
    active: bool
    level: int
    class_name: str | None
    current_hp: int
    max_hp: int
    armor_class: int
    proficiency_bonus: int
    hit_die_sides: int
    hit_dice_total: int
    hit_dice_used: int
    hit_dice_available: int
    abilities: tuple[AbilityScoreRead, ...]
    saving_throws: tuple[SavingThrowRead, ...]
    skills: tuple[SkillRead, ...]
    weapon_proficiencies: tuple[str, ...]
    armor_proficiencies: tuple[str, ...]
