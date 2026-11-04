
from models.character_state import CharacterState
from models.operation_result import OperationStatus
from repositories.character_repository import (
    CharacterRepository,
)


class CharacterServiceError(Exception):

    def __init__(
        self,
        message: str,
        *,
        status: OperationStatus = OperationStatus.INVALID,
    ):
        super().__init__(message)
        self.status = status


class CharacterService:

    def __init__(
        self,
        character_repository: CharacterRepository,
    ):
        self.character_repository = character_repository

    def change_hp(
        self,
        entity_id: int,
        amount: int,
        *,
        campaign_id: int,
        conn=None,
    ) -> CharacterState:

        character = self.character_repository.get_character(
            entity_id,
            campaign_id=campaign_id,
            conn=conn,
        )

        if character is None:
            raise CharacterServiceError(
                f"Character {entity_id} not found",
                status=OperationStatus.NOT_FOUND,
            )

        new_hp = max(
            0,
            min(
                character.current_hp + amount,
                character.max_hp,
            ),
        )

        updated = CharacterState(
            entity_id=character.entity_id,
            level=character.level,
            class_name=character.class_name,
            current_hp=new_hp,
            max_hp=character.max_hp,
            armor_class=character.armor_class,
            strength=character.strength,
            dexterity=character.dexterity,
            constitution=character.constitution,
            intelligence=character.intelligence,
            wisdom=character.wisdom,
            charisma=character.charisma,
            proficiency_bonus=character.proficiency_bonus,
            skill_proficiencies=character.skill_proficiencies,
            skill_expertise=character.skill_expertise,
            saving_throw_proficiencies=character.saving_throw_proficiencies,
            armor_proficiencies=character.armor_proficiencies,
            metadata=dict(character.metadata),
        )

        try:
            return self.character_repository.save_character(
                updated,
                campaign_id=campaign_id,
                conn=conn,
            )

        except Exception as exc:
            raise CharacterServiceError(
                "failed to save character",
                status=OperationStatus.INVALID,
            ) from exc
