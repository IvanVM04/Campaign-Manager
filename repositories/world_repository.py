
import copy
import json

from database import get_conn, rows
from models.entity import Entity
from models.event import Event
from models.item import Item, ItemInstance
from models.relation import Relation
from models.resource import Resource, ResourceBalance
from models.world_state import WorldState


class WorldRepository:
    """
    Persiste un WorldState aislado por campaña.

    Los IDs siguen siendo globales, pero ninguna operación puede
    leer, modificar o borrar registros de otra campaña.
    """

    # ============================================================
    # LOAD
    # ============================================================

    def load_world(
        self,
        *,
        campaign_id: int,
        conn=None,
    ) -> WorldState:
        if campaign_id is None:
            raise ValueError("campaign_id is required")

        world = WorldState()

        self._load_entities(world, campaign_id=campaign_id, conn=conn)
        self._load_items(world, campaign_id=campaign_id, conn=conn)
        self._load_item_instances(
            world, campaign_id=campaign_id, conn=conn
        )
        self._load_resources(world, campaign_id=campaign_id, conn=conn)
        self._load_resource_balances(
            world, campaign_id=campaign_id, conn=conn
        )
        self._load_relations(world, campaign_id=campaign_id, conn=conn)
        self._load_events(world, campaign_id=campaign_id, conn=conn)

        return world

    def _rows(self, query: str, params=(), *, conn=None):
        if conn is None:
            return rows(query, params)

        return [
            dict(row)
            for row in conn.execute(query, params).fetchall()
        ]

    def _load_entities(self, world, *, campaign_id, conn=None):
        data = self._rows("""
            SELECT id, name, entity_type, description, notes, active, aliases
            FROM entities
            WHERE campaign_id = ?
        """, (campaign_id,), conn=conn)

        for row in data:
            entity = Entity(
                id=row["id"],
                name=row["name"],
                entity_type=row["entity_type"],
                description=row["description"],
                notes=row["notes"],
                active=bool(row["active"]),
                aliases=json.loads(row["aliases"] or "[]"),
            )
            world.entities[entity.id] = entity

    def _load_items(self, world, *, campaign_id, conn=None):
        data = self._rows("""
            SELECT id, name, description, significance, unique_item, notes, weapon_key, armor_key, equipment_slot
            FROM items
            WHERE campaign_id = ?
        """, (campaign_id,), conn=conn)

        for row in data:
            item = Item(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                significance=row["significance"],
                unique=bool(row["unique_item"]),
                notes=row["notes"],
                weapon_key=row["weapon_key"],
                armor_key=row["armor_key"],
                equipment_slot=row["equipment_slot"],
            )
            world.items[item.id] = item

    def _load_item_instances(self, world, *, campaign_id, conn=None):
        data = self._rows("""
            SELECT
                id, item_id, instance_number, owner_id, location_id,
                condition, notes, active
            FROM item_instances
            WHERE campaign_id = ?
        """, (campaign_id,), conn=conn)

        for row in data:
            instance = ItemInstance(
                id=row["id"],
                item_id=row["item_id"],
                instance_number=row["instance_number"],
                owner_id=row["owner_id"],
                location_id=row["location_id"],
                condition=row["condition"],
                notes=row["notes"],
                active=bool(row["active"]),
            )
            world.item_instances[instance.id] = instance

    def _load_resources(self, world, *, campaign_id, conn=None):
        data = self._rows("""
            SELECT id, name, resource_type, unit, notes
            FROM resources
            WHERE campaign_id = ?
        """, (campaign_id,), conn=conn)

        for row in data:
            resource = Resource(
                id=row["id"],
                name=row["name"],
                resource_type=row["resource_type"],
                unit=row["unit"],
                notes=row["notes"],
            )
            world.resources[resource.id] = resource

    def _load_resource_balances(
        self, world, *, campaign_id, conn=None
    ):
        data = self._rows("""
            SELECT id, resource_id, owner_id, amount, notes
            FROM resource_balances
            WHERE campaign_id = ?
        """, (campaign_id,), conn=conn)

        for row in data:
            balance = ResourceBalance(
                id=row["id"],
                resource_id=row["resource_id"],
                owner_id=row["owner_id"],
                amount=row["amount"],
                notes=row["notes"],
            )
            world.resource_balances[balance.id] = balance

    def _load_relations(self, world, *, campaign_id, conn=None):
        data = self._rows("""
            SELECT
                id, subject_id, relation_type, target_id, metadata, active
            FROM relations
            WHERE campaign_id = ?
        """, (campaign_id,), conn=conn)

        for row in data:
            relation = Relation(
                id=row["id"],
                subject_id=row["subject_id"],
                relation_type=row["relation_type"],
                target_id=row["target_id"],
                metadata=(
                    json.loads(row["metadata"])
                    if row["metadata"] is not None
                    else None
                ),
                active=bool(row["active"]),
            )
            world.relations[relation.id] = relation

    def _load_events(self, world, *, campaign_id, conn=None):
        data = self._rows("""
            SELECT
                id, event_type, title, description, consequences,
                session_id, secret, metadata, epistemic_status,
                provenance_source, visibility_scope, known_by_entity_ids,
                source_entity_id, campaign_elapsed_minutes, supersedes_event_id
            FROM world_events
            WHERE campaign_id = ?
        """, (campaign_id,), conn=conn)

        for row in data:
            event = Event(
                id=row["id"],
                event_type=row["event_type"],
                title=row["title"],
                description=row["description"],
                consequences=row["consequences"],
                session_id=row["session_id"],
                secret=bool(row["secret"]),
                metadata=(
                    json.loads(row["metadata"])
                    if row["metadata"] is not None
                    else {}
                ),
                epistemic_status=row["epistemic_status"],
                provenance_source=row["provenance_source"],
                visibility_scope=row["visibility_scope"],
                known_by_entity_ids=json.loads(row["known_by_entity_ids"] or "[]"),
                source_entity_id=row["source_entity_id"],
                campaign_elapsed_minutes=row["campaign_elapsed_minutes"],
                supersedes_event_id=row["supersedes_event_id"],
            )
            world.events[event.id] = event

    # ============================================================
    # SAVE
    # ============================================================

    def save_world(
        self,
        world: WorldState,
        *,
        campaign_id: int,
        conn=None,
    ) -> None:
        if campaign_id is None:
            raise ValueError("campaign_id is required")

        world_to_save = copy.deepcopy(world)

        if conn is None:
            with get_conn() as connection:
                self._save_world(
                    connection,
                    world_to_save,
                    campaign_id=campaign_id,
                )
            return

        self._save_world(
            conn,
            world_to_save,
            campaign_id=campaign_id,
        )

    def _save_world(self, conn, world, *, campaign_id):
        self._normalize_world_dependencies(world)

        self._delete_missing_records(
            conn,
            world,
            campaign_id=campaign_id,
        )

        self._save_entities(conn, world, campaign_id=campaign_id)
        self._save_items(conn, world, campaign_id=campaign_id)
        self._save_item_instances(
            conn, world, campaign_id=campaign_id
        )
        self._save_resources(conn, world, campaign_id=campaign_id)
        self._save_resource_balances(
            conn, world, campaign_id=campaign_id
        )
        self._save_relations(conn, world, campaign_id=campaign_id)
        self._save_events(conn, world, campaign_id=campaign_id)

    @staticmethod
    def _execute_campaign_upsert(
        conn,
        *,
        table: str,
        query: str,
        params: tuple,
        record_id,
    ) -> None:
        cursor = conn.execute(query, params)

        if cursor.rowcount != 1:
            raise RuntimeError(
                f"Cannot save {table} record {record_id}: "
                "the ID may belong to another campaign."
            )

    # ============================================================
    # SAVE ENTITIES
    # ============================================================

    def _save_entities(self, conn, world, *, campaign_id):
        for entity in world.entities.values():
            self._execute_campaign_upsert(
                conn,
                table="entities",
                record_id=entity.id,
                query="""
                    INSERT INTO entities (
                        id, name, entity_type, description, notes,
                        active, aliases, campaign_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        entity_type = excluded.entity_type,
                        description = excluded.description,
                        notes = excluded.notes,
                        active = excluded.active,
                        aliases = excluded.aliases,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE entities.campaign_id = excluded.campaign_id
                """,
                params=(
                    entity.id,
                    entity.name,
                    entity.entity_type,
                    entity.description,
                    entity.notes,
                    int(entity.active),
                    json.dumps(entity.aliases, ensure_ascii=False, separators=(",", ":")),
                    campaign_id,
                ),
            )

    # ============================================================
    # SAVE ITEMS
    # ============================================================

    def _save_items(self, conn, world, *, campaign_id):
        for item in world.items.values():
            self._execute_campaign_upsert(
                conn,
                table="items",
                record_id=item.id,
                query="""
                    INSERT INTO items (
                        id, name, description, significance,
                        unique_item, notes, weapon_key, armor_key, equipment_slot, campaign_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        description = excluded.description,
                        significance = excluded.significance,
                        unique_item = excluded.unique_item,
                        notes = excluded.notes,
                        weapon_key = excluded.weapon_key,
                        armor_key = excluded.armor_key,
                        equipment_slot = excluded.equipment_slot,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE items.campaign_id = excluded.campaign_id
                """,
                params=(
                    item.id,
                    item.name,
                    item.description,
                    item.significance,
                    int(item.unique),
                    item.notes,
                    item.weapon_key,
                    item.armor_key,
                    item.equipment_slot,
                    campaign_id,
                ),
            )

    # ============================================================
    # SAVE ITEM INSTANCES
    # ============================================================

    def _save_item_instances(self, conn, world, *, campaign_id):
        for instance in world.item_instances.values():
            self._execute_campaign_upsert(
                conn,
                table="item_instances",
                record_id=instance.id,
                query="""
                    INSERT INTO item_instances (
                        id, item_id, instance_number, owner_id,
                        location_id, condition, notes, active, campaign_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        item_id = excluded.item_id,
                        instance_number = excluded.instance_number,
                        owner_id = excluded.owner_id,
                        location_id = excluded.location_id,
                        condition = excluded.condition,
                        notes = excluded.notes,
                        active = excluded.active,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE item_instances.campaign_id = excluded.campaign_id
                """,
                params=(
                    instance.id,
                    instance.item_id,
                    instance.instance_number,
                    instance.owner_id,
                    instance.location_id,
                    instance.condition,
                    instance.notes,
                    int(instance.active),
                    campaign_id,
                ),
            )

    # ============================================================
    # SAVE RESOURCES
    # ============================================================

    def _save_resources(self, conn, world, *, campaign_id):
        for resource in world.resources.values():
            self._execute_campaign_upsert(
                conn,
                table="resources",
                record_id=resource.id,
                query="""
                    INSERT INTO resources (
                        id, name, resource_type, unit, notes, campaign_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        resource_type = excluded.resource_type,
                        unit = excluded.unit,
                        notes = excluded.notes,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE resources.campaign_id = excluded.campaign_id
                """,
                params=(
                    resource.id,
                    resource.name,
                    resource.resource_type,
                    resource.unit,
                    resource.notes,
                    campaign_id,
                ),
            )

    # ============================================================
    # SAVE RESOURCE BALANCES
    # ============================================================

    def _save_resource_balances(self, conn, world, *, campaign_id):
        for balance in world.resource_balances.values():
            self._execute_campaign_upsert(
                conn,
                table="resource_balances",
                record_id=balance.id,
                query="""
                    INSERT INTO resource_balances (
                        id, resource_id, owner_id, amount, notes, campaign_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        resource_id = excluded.resource_id,
                        owner_id = excluded.owner_id,
                        amount = excluded.amount,
                        notes = excluded.notes,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE resource_balances.campaign_id = excluded.campaign_id
                """,
                params=(
                    balance.id,
                    balance.resource_id,
                    balance.owner_id,
                    balance.amount,
                    balance.notes,
                    campaign_id,
                ),
            )

    # ============================================================
    # SAVE RELATIONS
    # ============================================================

    def _save_relations(self, conn, world, *, campaign_id):
        for relation in world.relations.values():
            metadata = (
                json.dumps(relation.metadata)
                if relation.metadata is not None
                else None
            )

            self._execute_campaign_upsert(
                conn,
                table="relations",
                record_id=relation.id,
                query="""
                    INSERT INTO relations (
                        id, subject_id, relation_type, target_id,
                        metadata, active, campaign_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        subject_id = excluded.subject_id,
                        relation_type = excluded.relation_type,
                        target_id = excluded.target_id,
                        metadata = excluded.metadata,
                        active = excluded.active,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE relations.campaign_id = excluded.campaign_id
                """,
                params=(
                    relation.id,
                    relation.subject_id,
                    relation.relation_type,
                    relation.target_id,
                    metadata,
                    int(relation.active),
                    campaign_id,
                ),
            )

    # ============================================================
    # SAVE EVENTS
    # ============================================================

    @staticmethod
    def _events_in_supersession_order(world):
        """Order event rows so every superseded event exists before its successor."""
        pending = dict(world.events)
        ordered = []
        saved_ids: set[str] = set()
        while pending:
            ready = [
                event
                for event in pending.values()
                if (
                    event.supersedes_event_id is None
                    or event.supersedes_event_id in saved_ids
                )
            ]
            if not ready:
                raise ValueError("event supersession references contain a cycle")
            for event in ready:
                ordered.append(event)
                saved_ids.add(event.id)
                pending.pop(event.id, None)
        return ordered

    def _save_events(self, conn, world, *, campaign_id):
        for event in self._events_in_supersession_order(world):
            metadata = (
                json.dumps(event.metadata)
                if event.metadata is not None
                else None
            )

            self._execute_campaign_upsert(
                conn,
                table="world_events",
                record_id=event.id,
                query="""
                    INSERT INTO world_events (
                        id, event_type, title, description, consequences,
                        session_id, secret, metadata, epistemic_status,
                        provenance_source, visibility_scope, known_by_entity_ids,
                        source_entity_id, campaign_elapsed_minutes, supersedes_event_id,
                        campaign_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        event_type = excluded.event_type,
                        title = excluded.title,
                        description = excluded.description,
                        consequences = excluded.consequences,
                        session_id = excluded.session_id,
                        secret = excluded.secret,
                        metadata = excluded.metadata,
                        epistemic_status = excluded.epistemic_status,
                        provenance_source = excluded.provenance_source,
                        visibility_scope = excluded.visibility_scope,
                        known_by_entity_ids = excluded.known_by_entity_ids,
                        source_entity_id = excluded.source_entity_id,
                        campaign_elapsed_minutes = excluded.campaign_elapsed_minutes,
                        supersedes_event_id = excluded.supersedes_event_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE world_events.campaign_id = excluded.campaign_id
                """,
                params=(
                    event.id,
                    event.event_type,
                    event.title,
                    event.description,
                    event.consequences,
                    event.session_id,
                    int(event.secret),
                    metadata,
                    event.epistemic_status,
                    event.provenance_source,
                    event.visibility_scope,
                    json.dumps(event.known_by_entity_ids, separators=(",", ":")),
                    event.source_entity_id,
                    event.campaign_elapsed_minutes,
                    event.supersedes_event_id,
                    campaign_id,
                ),
            )

    # ============================================================
    # DELETE RECORDS MISSING FROM SNAPSHOT
    # ============================================================

    def _delete_missing_records(
        self,
        conn,
        world,
        *,
        campaign_id,
    ):
        records = (
            ("relations", list(world.relations.keys())),
            ("item_instances", list(world.item_instances.keys())),
            ("resource_balances", list(world.resource_balances.keys())),
            ("world_events", list(world.events.keys())),
            ("items", list(world.items.keys())),
            ("resources", list(world.resources.keys())),
            ("entities", list(world.entities.keys())),
        )

        for table, record_ids in records:
            if record_ids:
                placeholders = ",".join("?" for _ in record_ids)
                conn.execute(
                    f"""
                    DELETE FROM {table}
                    WHERE campaign_id = ?
                      AND id NOT IN ({placeholders})
                    """,
                    (campaign_id, *record_ids),
                )
            else:
                conn.execute(
                    f"DELETE FROM {table} WHERE campaign_id = ?",
                    (campaign_id,),
                )

    # ============================================================
    # NORMALIZE DEPENDENCIES
    # ============================================================

    def _normalize_world_dependencies(self, world):
        """
        El WorldState es el snapshot autoritativo.

        Elimina del snapshot de trabajo las referencias que quedarían
        huérfanas al persistirlo. El WorldState original no se modifica,
        porque save_world trabaja sobre una copia.
        """

        entity_ids = set(world.entities.keys())
        item_ids = set(world.items.keys())
        resource_ids = set(world.resources.keys())

        world.relations = {
            relation_id: relation
            for relation_id, relation in world.relations.items()
            if (
                relation.subject_id in entity_ids
                and relation.target_id in entity_ids
            )
        }

        world.item_instances = {
            instance_id: instance
            for instance_id, instance in world.item_instances.items()
            if (
                instance.item_id in item_ids
                and (
                    instance.owner_id is None
                    or instance.owner_id in entity_ids
                )
                and (
                    instance.location_id is None
                    or instance.location_id in entity_ids
                )
            )
        }

        world.resource_balances = {
            balance_id: balance
            for balance_id, balance in world.resource_balances.items()
            if (
                balance.resource_id in resource_ids
                and balance.owner_id in entity_ids
            )
        }

        for event in world.events.values():
            if event.source_entity_id is not None and event.source_entity_id not in entity_ids:
                raise ValueError(
                    f"event {event.id!r} references a source entity outside this world"
                )
            missing_known_by = set(event.known_by_entity_ids) - entity_ids
            if missing_known_by:
                raise ValueError(
                    f"event {event.id!r} references unknown character visibility IDs"
                )
            if (
                event.supersedes_event_id is not None
                and event.supersedes_event_id not in world.events
            ):
                raise ValueError(
                    f"event {event.id!r} supersedes an event outside this world"
                )
