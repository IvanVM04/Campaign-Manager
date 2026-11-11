import json


def _required_snapshot_id(row: dict, table: str) -> int:
    value = row.get("id")
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"Snapshot row in '{table}' must contain an integer id")
    return value

from models.campaign_scope import CampaignScope
from models.character_state import CharacterState
from models.entity import Entity
from models.event import Event
from models.item import Item, ItemInstance
from models.relation import Relation
from models.resource import Resource, ResourceBalance
from models.world_state import WorldState


class WorldSnapshotRepository:
    """
    Persiste snapshots completos del estado mutable de la campaña.

    El snapshot está diseñado para permitir reconciliación de turnos:
    
        snapshot
            ↓
        restaurar estado anterior
            ↓
        aplicar nueva versión

    No contiene la tabla turns.
    """

    SNAPSHOT_TABLES = (
        "entities",
        "items",
        "item_instances",
        "resources",
        "resource_balances",
        "relations",
        "world_events",
        "character_states",
    )

    RESTORE_DELETE_ORDER = (
        "world_events",
        "relations",
        "resource_balances",
        "item_instances",
        "character_states",
        "resources",
        "items",
        "entities",
    )

    RESTORE_INSERT_ORDER = (
        "entities",
        "items",
        "item_instances",
        "resources",
        "resource_balances",
        "relations",
        "world_events",
        "character_states",
    )

    def create_snapshot(self, conn, *, scope: CampaignScope) -> str:
        """
        Crea un snapshot JSON del estado actual.

        Debe llamarse dentro de la misma transacción que
        posteriormente aplicará el turno.
        """

        self._validate_scope(scope)
        snapshot = {}

        campaign = conn.execute(
            """
            SELECT current_location_id, current_session_id,
                   active_character_id
            FROM campaign
            WHERE id = ?
            """,
            (scope.campaign_id,),
        ).fetchone()

        if campaign is None:
            raise LookupError(
                f"campaign {scope.campaign_id} does not exist"
            )

        snapshot["_campaign_pointers"] = {
            "current_location_id": campaign["current_location_id"],
            "current_session_id": campaign["current_session_id"],
            "active_character_id": campaign["active_character_id"],
        }

        for table in self.SNAPSHOT_TABLES:
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE campaign_id = ?",
                (scope.campaign_id,),
            ).fetchall()

            snapshot[table] = [
                dict(row)
                for row in rows
            ]

        return json.dumps(
            snapshot,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def restore_snapshot(
        self,
        conn,
        snapshot: str,
        *,
        scope: CampaignScope,
    ) -> None:
        """
        Restaura exactamente el estado contenido en el snapshot.

        Se utiliza para revertir una versión anterior de un turno
        antes de aplicar una nueva versión.
        """

        self._validate_scope(scope)

        if not isinstance(snapshot, str):
            raise TypeError(
                "snapshot must be a string"
            )

        try:
            data = json.loads(snapshot)
        except json.JSONDecodeError as exc:
            raise TypeError(
                "World snapshot must contain an object"
            ) from exc

        if not isinstance(data, dict):
            raise TypeError(
                "World snapshot must contain an object"
            )

        missing_tables = [
            table
            for table in self.SNAPSHOT_TABLES
            if table not in data
        ]

        if missing_tables:
            raise ValueError(
                "World snapshot is missing tables: "
                + ", ".join(missing_tables)
            )

        # Prefer pointers captured with the snapshot. Older snapshots do
        # not contain them, so retain the current database values as a
        # backwards-compatible fallback.
        campaign = conn.execute(
            """
            SELECT current_location_id, current_session_id,
                   active_character_id
            FROM campaign
            WHERE id = ?
            """,
            (scope.campaign_id,),
        ).fetchone()

        if campaign is None:
            raise LookupError(
                f"campaign {scope.campaign_id} does not exist"
            )

        snapshot_pointers = data.get("_campaign_pointers")
        if snapshot_pointers is not None:
            if not isinstance(snapshot_pointers, dict):
                raise TypeError(
                    "Snapshot campaign pointers must contain an object"
                )
            campaign_pointers = {
                "current_location_id": snapshot_pointers.get(
                    "current_location_id"
                ),
                "current_session_id": snapshot_pointers.get(
                    "current_session_id"
                ),
                "active_character_id": snapshot_pointers.get(
                    "active_character_id"
                ),
            }
        else:
            campaign_pointers = {
                "current_location_id": campaign["current_location_id"],
                "current_session_id": campaign["current_session_id"],
                "active_character_id": campaign["active_character_id"],
            }

        # ------------------------------------------------------------
        # DELETE CURRENT STATE
        # ------------------------------------------------------------

        for table in self.RESTORE_DELETE_ORDER:
            conn.execute(
                f"DELETE FROM {table} WHERE campaign_id = ?",
                (scope.campaign_id,),
            )

        # ------------------------------------------------------------
        # RESTORE SNAPSHOT
        # ------------------------------------------------------------

        for table in self.RESTORE_INSERT_ORDER:
            table_rows = data[table]

            if not isinstance(table_rows, list):
                raise TypeError(
                    f"Snapshot table '{table}' must contain a list"
                )

            for row in table_rows:

                if not isinstance(row, dict):
                    raise TypeError(
                        f"Snapshot row in '{table}' "
                        "must contain an object"
                    )

                if not row:
                    continue

                # Los snapshots históricos anteriores a multi-campaña
                # no contienen campaign_id y pertenecen a la campaña 1.
                row = dict(row)
                row_campaign_id = row.setdefault("campaign_id", 1)
                if row_campaign_id != scope.campaign_id:
                    raise ValueError(
                        f"Snapshot row in '{table}' belongs to a different campaign"
                    )

                columns = list(row.keys())

                placeholders = ",".join(
                    "?" for _ in columns
                )

                column_sql = ",".join(
                    f'"{column}"'
                    for column in columns
                )

                conn.execute(
                    f"""
                    INSERT INTO "{table}" (
                        {column_sql}
                    )
                    VALUES (
                        {placeholders}
                    )
                    """,
                    [
                        row[column]
                        for column in columns
                    ],
                )

        # DELETE triggers (migration 014) may have cleared these pointers
        # while their target rows were temporarily removed. Restore only
        # pointers whose targets exist in the restored state.
        restored_pointers = {}
        pointer_targets = {
            "current_location_id": ("entities", "id"),
            "current_session_id": ("sessions", "id"),
            "active_character_id": ("character_states", "entity_id"),
        }

        for pointer, (table, target_column) in pointer_targets.items():
            target_id = campaign_pointers[pointer]
            if target_id is None:
                restored_pointers[pointer] = None
                continue

            exists = conn.execute(
                f"""
                SELECT 1
                FROM {table}
                WHERE {target_column} = ?
                  AND campaign_id = ?
                """,
                (target_id, scope.campaign_id),
            ).fetchone()

            restored_pointers[pointer] = (
                target_id if exists is not None else None
            )

        conn.execute(
            """
            UPDATE campaign
            SET current_location_id = ?,
                current_session_id = ?,
                active_character_id = ?
            WHERE id = ?
            """,
            (
                restored_pointers["current_location_id"],
                restored_pointers["current_session_id"],
                restored_pointers["active_character_id"],
                scope.campaign_id,
            ),
        )

    @staticmethod
    def _validate_scope(scope: CampaignScope) -> None:
        if not isinstance(scope, CampaignScope):
            raise TypeError("scope must be a CampaignScope")

    def load_snapshot_state(
        self,
        snapshot: str,
    ) -> tuple[WorldState, dict[int, CharacterState]]:
        """
        Construye un estado de mundo temporal a partir de un snapshot.

        No modifica SQLite ni el WorldService.

        Se utiliza para que una regeneración pueda ejecutar el
        extractor contra el estado existente antes de la versión
        que se está regenerando.
        """

        if not isinstance(snapshot, str):
            raise TypeError(
                "snapshot must be a string"
            )

        try:
            data = json.loads(snapshot)
        except json.JSONDecodeError as exc:
            raise TypeError(
                "World snapshot must contain an object"
            ) from exc

        if not isinstance(data, dict):
            raise TypeError(
                "World snapshot must contain an object"
            )

        missing_tables = [
            table
            for table in self.SNAPSHOT_TABLES
            if table not in data
        ]

        if missing_tables:
            raise ValueError(
                "World snapshot is missing tables: "
                + ", ".join(missing_tables)
            )

        world = WorldState()

        # --------------------------------------------------------
        # ENTITIES
        # --------------------------------------------------------

        for row in data["entities"]:
            if not isinstance(row, dict):
                raise TypeError(
                    "Snapshot row in 'entities' must contain an object"
                )

            entity_id = _required_snapshot_id(row, "entities")
            entity = Entity(
                id=entity_id,
                name=row["name"],
                entity_type=row["entity_type"],
                description=row["description"],
                notes=row["notes"],
                active=bool(row["active"]),
            )

            world.entities[entity_id] = entity

        # --------------------------------------------------------
        # ITEMS
        # --------------------------------------------------------

        for row in data["items"]:
            if not isinstance(row, dict):
                raise TypeError(
                    "Snapshot row in 'items' must contain an object"
                )

            item_id = _required_snapshot_id(row, "items")
            item = Item(
                id=item_id,
                name=row["name"],
                description=row["description"],
                significance=row["significance"],
                unique=bool(row["unique_item"]),
                notes=row["notes"],
            )

            world.items[item_id] = item

        # --------------------------------------------------------
        # ITEM INSTANCES
        # --------------------------------------------------------

        for row in data["item_instances"]:
            if not isinstance(row, dict):
                raise TypeError(
                    "Snapshot row in 'item_instances' "
                    "must contain an object"
                )

            instance_id = _required_snapshot_id(row, "item_instances")
            instance = ItemInstance(
                id=instance_id,
                item_id=row["item_id"],
                instance_number=row["instance_number"],
                owner_id=row["owner_id"],
                location_id=row["location_id"],
                condition=row["condition"],
                notes=row["notes"],
                active=bool(row["active"]),
            )

            world.item_instances[instance_id] = instance

        # --------------------------------------------------------
        # RESOURCES
        # --------------------------------------------------------

        for row in data["resources"]:
            if not isinstance(row, dict):
                raise TypeError(
                    "Snapshot row in 'resources' must contain an object"
                )

            resource_id = _required_snapshot_id(row, "resources")
            resource = Resource(
                id=resource_id,
                name=row["name"],
                resource_type=row["resource_type"],
                unit=row["unit"],
                notes=row["notes"],
            )

            world.resources[resource_id] = resource

        # --------------------------------------------------------
        # RESOURCE BALANCES
        # --------------------------------------------------------

        for row in data["resource_balances"]:
            if not isinstance(row, dict):
                raise TypeError(
                    "Snapshot row in 'resource_balances' "
                    "must contain an object"
                )

            balance_id = _required_snapshot_id(row, "resource_balances")
            balance = ResourceBalance(
                id=balance_id,
                resource_id=row["resource_id"],
                owner_id=row["owner_id"],
                amount=row["amount"],
                notes=row["notes"],
            )

            world.resource_balances[balance_id] = balance

        # --------------------------------------------------------
        # RELATIONS
        # --------------------------------------------------------

        for row in data["relations"]:
            if not isinstance(row, dict):
                raise TypeError(
                    "Snapshot row in 'relations' "
                    "must contain an object"
                )

            metadata = row["metadata"]

            if isinstance(metadata, str):
                metadata = json.loads(metadata)

            relation = Relation(
                id=row["id"],
                subject_id=row["subject_id"],
                relation_type=row["relation_type"],
                target_id=row["target_id"],
                metadata=metadata,
                active=bool(row["active"]),
            )

            world.relations[relation.id] = relation

        # --------------------------------------------------------
        # EVENTS
        # --------------------------------------------------------

        for row in data["world_events"]:
            if not isinstance(row, dict):
                raise TypeError(
                    "Snapshot row in 'world_events' "
                    "must contain an object"
                )

            metadata = row["metadata"]

            if isinstance(metadata, str):
                metadata = json.loads(metadata)

            event = Event(
                id=row["id"],
                event_type=row["event_type"],
                title=row["title"],
                description=row["description"],
                consequences=row["consequences"],
                session_id=row["session_id"],
                secret=bool(row["secret"]),
                metadata=metadata or {},
            )

            world.events[event.id] = event

        # --------------------------------------------------------
        # CHARACTER STATES
        # --------------------------------------------------------

        character_states = {}

        for row in data["character_states"]:
            if not isinstance(row, dict):
                raise TypeError(
                    "Snapshot row in 'character_states' "
                    "must contain an object"
                )

            metadata = row["metadata"]

            if isinstance(metadata, str):
                metadata = json.loads(metadata)

            character = CharacterState(
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
                armor_proficiencies=json.loads(row.get("armor_proficiencies", "[]")),
                metadata=metadata or {},
            )

            character_states[character.entity_id] = character

        return world, character_states