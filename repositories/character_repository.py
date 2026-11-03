
import json
import sqlite3

from database import execute, one, rows
from models.character_state import CharacterState


class CharacterRepository:

    _SELECT_FIELDS = """
        entity_id,
        level,
        class_name,
        current_hp,
        max_hp,
        armor_class,
        strength,
        dexterity,
        constitution,
        intelligence,
        wisdom,
        charisma,
        proficiency_bonus,
        skill_proficiencies,
        skill_expertise,
        saving_throw_proficiencies,
        weapon_proficiencies,
        metadata
    """

    def get_character(
        self,
        entity_id: int,
        *,
        campaign_id: int,
        conn=None,
    ) -> CharacterState | None:

        query = f"""
            SELECT {self._SELECT_FIELDS}
            FROM character_states
            WHERE entity_id = ?
              AND campaign_id = ?
        """

        params = (entity_id, campaign_id)

        if conn is None:
            row = one(query, params)
        else:
            row = conn.execute(
                query,
                params,
            ).fetchone()

            row = dict(row) if row else None

        if row is None:
            return None

        return self._row_to_model(row)

    def save_character(
        self,
        character: CharacterState,
        *,
        campaign_id: int,
        conn=None,
    ) -> CharacterState:

        query = """
            INSERT INTO character_states (
                entity_id,
                level,
                class_name,
                current_hp,
                max_hp,
                armor_class,
                strength,
                dexterity,
                constitution,
                intelligence,
                wisdom,
                charisma,
                proficiency_bonus,
                skill_proficiencies,
                skill_expertise,
                saving_throw_proficiencies,
                weapon_proficiencies,
                metadata,
                campaign_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_id)
            DO UPDATE SET
                level = excluded.level,
                class_name = excluded.class_name,
                current_hp = excluded.current_hp,
                max_hp = excluded.max_hp,
                armor_class = excluded.armor_class,
                strength = excluded.strength,
                dexterity = excluded.dexterity,
                constitution = excluded.constitution,
                intelligence = excluded.intelligence,
                wisdom = excluded.wisdom,
                charisma = excluded.charisma,
                proficiency_bonus = excluded.proficiency_bonus,
                skill_proficiencies = excluded.skill_proficiencies,
                skill_expertise = excluded.skill_expertise,
                saving_throw_proficiencies = excluded.saving_throw_proficiencies,
                weapon_proficiencies = excluded.weapon_proficiencies,
                metadata = excluded.metadata
            WHERE character_states.campaign_id = excluded.campaign_id
        """

        params = (
            character.entity_id,
            character.level,
            character.class_name,
            character.current_hp,
            character.max_hp,
            character.armor_class,
            character.strength,
            character.dexterity,
            character.constitution,
            character.intelligence,
            character.wisdom,
            character.charisma,
            character.proficiency_bonus,
            json.dumps(sorted(skill.value for skill in character.skill_proficiencies)),
            json.dumps(sorted(skill.value for skill in character.skill_expertise)),
            json.dumps(sorted(ability.value for ability in character.saving_throw_proficiencies)),
            json.dumps(sorted(character.weapon_proficiencies)),
            json.dumps(character.metadata),
            campaign_id,
        )

        try:
            if conn is None:
                execute(query, params)
            else:
                conn.execute(query, params)

        except sqlite3.IntegrityError as exc:
            if "cross-campaign reference is not allowed" in str(exc):
                raise RuntimeError(
                    f"Character {character.entity_id} belongs to "
                    f"a different campaign"
                ) from exc

            raise

        loaded = self.get_character(
            character.entity_id,
            campaign_id=campaign_id,
            conn=conn,
        )

        if loaded is None:
            raise RuntimeError(
                f"Character {character.entity_id} could not be saved "
                f"for campaign {campaign_id}"
            )

        return loaded

    def delete_character(
        self,
        entity_id: int,
        *,
        campaign_id: int,
    ) -> None:

        execute(
            """
            DELETE FROM character_states
            WHERE entity_id = ?
              AND campaign_id = ?
            """,
            (entity_id, campaign_id),
        )

    def list_characters(
        self,
        *,
        campaign_id: int,
    ) -> list[CharacterState]:

        rows_data = rows(
            f"""
            SELECT {self._SELECT_FIELDS}
            FROM character_states
            WHERE campaign_id = ?
            ORDER BY entity_id
            """,
            (campaign_id,),
        )

        return [
            self._row_to_model(row)
            for row in rows_data
        ]

    @staticmethod
    def _row_to_model(row) -> CharacterState:

        metadata = row["metadata"]

        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return CharacterState(
            entity_id=row["entity_id"],
            level=row["level"],
            class_name=row["class_name"],
            current_hp=row["current_hp"],
            max_hp=row["max_hp"],
            armor_class=row["armor_class"],
            strength=row["strength"],
            dexterity=row["dexterity"],
            constitution=row["constitution"],
            intelligence=row["intelligence"],
            wisdom=row["wisdom"],
            charisma=row["charisma"],
            proficiency_bonus=row["proficiency_bonus"],
            skill_proficiencies=json.loads(row["skill_proficiencies"]),
            skill_expertise=json.loads(row["skill_expertise"]),
            saving_throw_proficiencies=json.loads(row["saving_throw_proficiencies"]),
            weapon_proficiencies=json.loads(row["weapon_proficiencies"]),
            metadata=metadata,
        )
