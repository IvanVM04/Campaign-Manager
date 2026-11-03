
from database import get_conn
from models.character_state import CharacterState
from models.entity import Entity


class CharacterCreationService:

    def __init__(
        self,
        campaign_repository,
        entity_repository,
        character_repository,
    ):
        self.campaign_repository = campaign_repository
        self.entity_repository = entity_repository
        self.character_repository = character_repository

    def create_character(
        self,
        campaign_id: int,
        data,
        activate: bool = True,
    ) -> CharacterState:

        with get_conn() as conn:

            campaign = self.campaign_repository.get_campaign(
                campaign_id,
                conn=conn,
            )

            if campaign is None:
                raise ValueError(
                    f"Campaign '{campaign_id}' does not exist"
                )

            entity = Entity(
                name=data.name,
                entity_type="player_character",
                description="",
                notes="",
                active=True,
            )

            entity = self.entity_repository.save_entity(
                entity,
                campaign_id=campaign_id,
                conn=conn,
            )

            current_hp = (
                data.current_hp
                if data.current_hp is not None
                else data.max_hp
            )

            character = CharacterState(
                entity_id=entity.id,
                level=data.level,
                class_name=data.class_name,
                current_hp=current_hp,
                max_hp=data.max_hp,
                armor_class=data.armor_class,
                strength=data.strength,
                dexterity=data.dexterity,
                constitution=data.constitution,
                intelligence=data.intelligence,
                wisdom=data.wisdom,
                charisma=data.charisma,
                proficiency_bonus=data.proficiency_bonus,
                skill_proficiencies=data.skill_proficiencies,
                skill_expertise=data.skill_expertise,
                saving_throw_proficiencies=data.saving_throw_proficiencies,
                metadata=data.metadata,
            )

            character = self.character_repository.save_character(
                character,
                campaign_id=campaign_id,
                conn=conn,
            )

            if activate:
                self.campaign_repository.update_active_character(
                    campaign_id,
                    entity.id,
                    conn=conn,
                )

            return character
