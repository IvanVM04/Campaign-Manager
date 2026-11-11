
from __future__ import annotations

from database import (
    execute,
    execute_in_conn,
    one,
    one_in_conn,
    rows,
)
from models.entity import Entity


class EntityRepository:
    """Repositorio de entidades persistentes por campaña."""

    def get_entity(
        self,
        entity_id: int,
        *,
        campaign_id: int,
        conn=None,
    ) -> Entity | None:
        query = """
            SELECT
                id,
                name,
                entity_type,
                description,
                notes,
                active
            FROM entities
            WHERE id = ?
              AND campaign_id = ?
        """
        params = (entity_id, campaign_id)

        row = (
            one(query, params)
            if conn is None
            else one_in_conn(conn, query, params)
        )

        if row is None:
            return None

        return self._row_to_model(row)

    def save_entity(
        self,
        entity: Entity,
        *,
        campaign_id: int,
        conn=None,
    ) -> Entity:
        if entity.id is None:
            query = """
                INSERT INTO entities (
                    name,
                    entity_type,
                    description,
                    notes,
                    active,
                    campaign_id
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """
            params = (
                entity.name,
                entity.entity_type,
                entity.description,
                entity.notes,
                int(entity.active),
                campaign_id,
            )

            entity_id = (
                execute(query, params)
                if conn is None
                else execute_in_conn(conn, query, params)
            )
        else:
            query = """
                INSERT INTO entities (
                    id,
                    name,
                    entity_type,
                    description,
                    notes,
                    active,
                    campaign_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id)
                DO UPDATE SET
                    name = excluded.name,
                    entity_type = excluded.entity_type,
                    description = excluded.description,
                    notes = excluded.notes,
                    active = excluded.active,
                    updated_at = CURRENT_TIMESTAMP
                WHERE entities.campaign_id = excluded.campaign_id
            """
            params = (
                entity.id,
                entity.name,
                entity.entity_type,
                entity.description,
                entity.notes,
                int(entity.active),
                campaign_id,
            )

            if conn is None:
                execute(query, params)
            else:
                execute_in_conn(conn, query, params)

            entity_id = entity.id

        if entity_id is None:
            raise RuntimeError("failed to retrieve id of saved entity")

        loaded = self.get_entity(
            entity_id,
            campaign_id=campaign_id,
            conn=conn,
        )

        if loaded is None:
            raise RuntimeError(
                f"Entity {entity_id} could not be saved "
                f"for campaign {campaign_id}"
            )

        return loaded

    def delete_entity(
        self,
        entity_id: int,
        *,
        campaign_id: int,
    ) -> None:
        execute(
            """
            DELETE FROM entities
            WHERE id = ?
              AND campaign_id = ?
            """,
            (entity_id, campaign_id),
        )

    def list_entities(
        self,
        *,
        campaign_id: int,
    ) -> list[Entity]:
        rows_data = rows(
            """
            SELECT
                id,
                name,
                entity_type,
                description,
                notes,
                active
            FROM entities
            WHERE campaign_id = ?
            ORDER BY id
            """,
            (campaign_id,),
        )

        return [
            self._row_to_model(row)
            for row in rows_data
        ]

    @staticmethod
    def _row_to_model(row) -> Entity:
        return Entity(
            id=row["id"],
            name=row["name"],
            entity_type=row["entity_type"],
            description=row["description"],
            notes=row["notes"],
            active=bool(row["active"]),
        )
