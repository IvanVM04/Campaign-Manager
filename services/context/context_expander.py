from __future__ import annotations

from typing import Any

from models.world_state import WorldState
from services.world.world_serializer import WorldSerializer

from .context_ranker import ContextRanker


class ContextExpander:
    """
    Expande los resultados de búsqueda dentro del WorldState.

    Responsabilidades:

    - Expandir entidades siguiendo relaciones activas.
    - Propagar relevancia.
    - Obtener relaciones relacionadas.
    - Obtener eventos públicos relacionados.
    - Resolver objetos padre.
    - No modificar WorldState.
    - No acceder directamente a SQLite.

    ContextExpander NO:

    - busca información;
    - renderiza texto;
    - aplica presupuesto;
    - decide cómo presentar el contexto.
    """

    def __init__(
        self,
        ranker: ContextRanker | None = None,
    ) -> None:
        if ranker is not None and not isinstance(
            ranker,
            ContextRanker,
        ):
            raise TypeError(
                "ranker must be a ContextRanker"
            )

        self.ranker = ranker or ContextRanker()

    # ============================================================
    # MAIN EXPANSION
    # ============================================================

    def expand(
        self,
        world: WorldState,
        search_result: dict[str, Any],
        max_depth: int = 1,
    ) -> dict[str, Any]:
        """
        Enriquece un resultado de búsqueda.

        No modifica search_result ni WorldState.
        """

        self._validate_world(world)

        if max_depth < 0:
            raise ValueError(
                "max_depth must be >= 0"
            )

        result = self._copy_search_result(
            search_result
        )

        result = self.resolve_parent_objects(
            world,
            result,
        )

        entities = self.expand_entities(
            world,
            result.get("entities", []),
            max_depth=max_depth,
        )

        relations = self.related_relations(
            world,
            entities,
        )

        events = self.related_events(
            world,
            entities,
        )

        result["entities"] = entities
        result["relations"] = relations
        result["events"] = events

        return result

    # ============================================================
    # ENTITY EXPANSION
    # ============================================================

    def expand_entities(
        self,
        world: WorldState,
        matched_entities: list[dict[str, Any]],
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """
        Expande entidades encontradas siguiendo relaciones activas.

        La relevancia se propaga por el grafo.
        """

        if max_depth < 0:
            raise ValueError(
                "max_depth must be >= 0"
            )

        entity_depths: dict[int, int] = {}
        entity_relevance: dict[int, float] = {}

        # --------------------------------------------------------
        # DIRECT ENTITIES
        # --------------------------------------------------------

        for entity in matched_entities:
            if not isinstance(entity, dict):
                continue

            entity_id = entity.get("id")

            if not isinstance(entity_id, int):
                continue

            entity_depths[entity_id] = 0

            entity_relevance[entity_id] = (
                self.ranker.DIRECT_ENTITY_RELEVANCE
            )

        # --------------------------------------------------------
        # GRAPH EXPANSION
        # --------------------------------------------------------

        for depth in range(max_depth):

            current_ids = {
                entity_id
                for entity_id, entity_depth
                in entity_depths.items()
                if entity_depth == depth
            }

            if not current_ids:
                break

            for relation in world.relations.values():

                if not getattr(
                    relation,
                    "active",
                    True,
                ):
                    continue

                subject_id = getattr(
                    relation,
                    "subject_id",
                    None,
                )

                target_id = getattr(
                    relation,
                    "target_id",
                    None,
                )

                relation_type = getattr(
                    relation,
                    "relation_type",
                    "",
                )

                relation_weight = (
                    self.ranker.get_relation_relevance(
                        relation_type
                    )
                )

                depth_factor = (
                    self.ranker.RELATED_ENTITY_RELEVANCE
                    ** (depth + 1)
                )

                propagation_factor = (
                    relation_weight
                    * depth_factor
                )

                # SUBJECT -> TARGET

                if (
                    isinstance(subject_id, int)
                    and not isinstance(subject_id, bool)
                    and subject_id in current_ids
                ):
                    if not isinstance(target_id, int) or isinstance(target_id, bool):
                        continue
                    target = world.entities.get(target_id)

                    if (
                        target is not None
                        and getattr(
                            target,
                            "active",
                            True,
                        )
                    ):
                        candidate_relevance = (
                            entity_relevance[subject_id]
                            * propagation_factor
                        )

                        self._register_related_entity(
                            entity_depths,
                            entity_relevance,
                            target_id,
                            depth + 1,
                            candidate_relevance,
                        )

                # TARGET -> SUBJECT

                if (
                    isinstance(target_id, int)
                    and not isinstance(target_id, bool)
                    and target_id in current_ids
                ):
                    if not isinstance(subject_id, int) or isinstance(subject_id, bool):
                        continue
                    subject = world.entities.get(subject_id)

                    if (
                        subject is not None
                        and getattr(
                            subject,
                            "active",
                            True,
                        )
                    ):
                        candidate_relevance = (
                            entity_relevance[target_id]
                            * propagation_factor
                        )

                        self._register_related_entity(
                            entity_depths,
                            entity_relevance,
                            subject_id,
                            depth + 1,
                            candidate_relevance,
                        )

        # --------------------------------------------------------
        # BUILD RESULT
        # --------------------------------------------------------

        result: list[dict[str, Any]] = []

        for entity_id in entity_depths:

            entity = world.entities.get(
                entity_id
            )

            if entity is None:
                continue

            if not getattr(
                entity,
                "active",
                True,
            ):
                continue

            entity_data = (
                WorldSerializer.entity_to_dict(
                    entity
                )
            )

            entity_data["_relevance"] = (
                entity_relevance.get(
                    entity_id,
                    0.0,
                )
            )

            entity_data["_depth"] = (
                entity_depths.get(
                    entity_id,
                    max_depth + 1,
                )
            )

            result.append(
                entity_data
            )

        result.sort(
            key=lambda entity: (
                -entity.get(
                    "_relevance",
                    0.0,
                ),
                entity.get(
                    "_depth",
                    max_depth + 1,
                ),
                entity.get(
                    "id",
                    0,
                ),
            )
        )

        return result

    # ============================================================
    # RELATED ENTITY
    # ============================================================

    @staticmethod
    def _register_related_entity(
        entity_depths: dict[int, int],
        entity_relevance: dict[int, float],
        entity_id: int,
        depth: int,
        relevance: float,
    ) -> None:
        existing_depth = entity_depths.get(
            entity_id
        )

        existing_relevance = entity_relevance.get(
            entity_id,
            0.0,
        )

        if existing_depth is None:
            entity_depths[entity_id] = depth
            entity_relevance[entity_id] = relevance
            return

        if relevance > existing_relevance:
            entity_relevance[entity_id] = relevance

        if depth < existing_depth:
            entity_depths[entity_id] = depth

    # ============================================================
    # RELATIONS
    # ============================================================

    @staticmethod
    def related_relations(
        world: WorldState,
        entities: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:

        entity_ids = {
            entity.get("id")
            for entity in entities
            if isinstance(entity, dict)
        }

        result: list[dict[str, Any]] = []

        for relation in world.relations.values():

            if not getattr(
                relation,
                "active",
                True,
            ):
                continue

            subject_id = getattr(
                relation,
                "subject_id",
                None,
            )

            target_id = getattr(
                relation,
                "target_id",
                None,
            )

            if (
                subject_id not in entity_ids
                and target_id not in entity_ids
            ):
                continue

            result.append(
                WorldSerializer.relation_to_dict(
                    relation
                )
            )

        result.sort(
            key=lambda relation: str(
                relation.get(
                    "id",
                    "",
                )
            )
        )

        return result

    # ============================================================
    # EVENTS
    # ============================================================

    @staticmethod
    def related_events(
        world: WorldState,
        entities: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:

        entity_ids = {
            entity.get("id")
            for entity in entities
            if isinstance(entity, dict)
        }

        result: list[dict[str, Any]] = []

        for event in world.events.values():

            if getattr(
                event,
                "secret",
                False,
            ):
                continue

            metadata = getattr(
                event,
                "metadata",
                None,
            )

            if not isinstance(
                metadata,
                dict,
            ):
                continue

            related_ids = metadata.get(
                "entity_ids",
                [],
            )

            if not isinstance(
                related_ids,
                (list, tuple, set),
            ):
                continue

            if not entity_ids.intersection(
                related_ids
            ):
                continue

            result.append(
                WorldSerializer.event_to_dict(
                    event
                )
            )

        result.sort(
            key=lambda event: str(
                event.get(
                    "id",
                    "",
                )
            )
        )

        return result

    # ============================================================
    # PARENT OBJECT RESOLUTION
    # ============================================================

    def resolve_parent_objects(
        self,
        world: WorldState,
        search_result: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Completa el resultado con objetos relacionados con las entidades
        encontradas y resuelve sus objetos padre.

        Relaciones de propiedad:

            Entity
                -> ItemInstance
                -> ResourceBalance

        Relaciones de parentesco:

            ItemInstance
                -> Item

            ResourceBalance
                -> Resource

        No modifica WorldState.
        """

        result = self._copy_search_result(
            search_result
        )

        # ============================================================
        # ENTIDADES RELEVANTES
        # ============================================================

        entity_ids = {
            entity.get("id")
            for entity in result.get(
                "entities",
                [],
            )
            if isinstance(entity, dict)
            and isinstance(
                entity.get("id"),
                int,
            )
        }

        # ============================================================
        # OWNED ITEM INSTANCES
        # ============================================================

        existing_instance_ids = {
            instance.get("id")
            for instance in result.get(
                "item_instances",
                [],
            )
            if isinstance(instance, dict)
        }

        for instance in world.item_instances.values():

            if not getattr(
                instance,
                "active",
                True,
            ):
                continue

            owner_id = getattr(
                instance,
                "owner_id",
                None,
            )

            if owner_id not in entity_ids:
                continue

            instance_id = getattr(
                instance,
                "id",
                None,
            )

            if instance_id in existing_instance_ids:
                continue

            result["item_instances"].append(
                WorldSerializer.item_instance_to_dict(
                    instance
                )
            )

            existing_instance_ids.add(
                instance_id
            )

        # ============================================================
        # OWNED RESOURCE BALANCES
        # ============================================================

        existing_balance_ids = {
            balance.get("id")
            for balance in result.get(
                "resource_balances",
                [],
            )
            if isinstance(balance, dict)
        }

        for balance in world.resource_balances.values():

            if not getattr(
                balance,
                "active",
                True,
            ):
                continue

            owner_id = getattr(
                balance,
                "owner_id",
                None,
            )

            if owner_id not in entity_ids:
                continue

            balance_id = getattr(
                balance,
                "id",
                None,
            )

            if balance_id in existing_balance_ids:
                continue

            result["resource_balances"].append(
                WorldSerializer.resource_balance_to_dict(
                    balance
                )
            )

            existing_balance_ids.add(
                balance_id
            )

        # ============================================================
        # ITEM PARENTS
        # ============================================================

        existing_item_ids = {
            item.get("id")
            for item in result.get(
                "items",
                [],
            )
            if isinstance(item, dict)
        }

        for instance in result.get(
            "item_instances",
            [],
        ):
            if not isinstance(
                instance,
                dict,
            ):
                continue

            item_id = instance.get(
                "item_id"
            )

            if item_id is None:
                continue

            if item_id in existing_item_ids:
                continue

            item = world.items.get(
                item_id
            )

            if item is None:
                continue

            if not getattr(
                item,
                "active",
                True,
            ):
                continue

            result["items"].append(
                WorldSerializer.item_to_dict(
                    item
                )
            )

            existing_item_ids.add(
                item_id
            )

        # ============================================================
        # RESOURCE PARENTS
        # ============================================================

        existing_resource_ids = {
            resource.get("id")
            for resource in result.get(
                "resources",
                [],
            )
            if isinstance(resource, dict)
        }

        for balance in result.get(
            "resource_balances",
            [],
        ):
            if not isinstance(
                balance,
                dict,
            ):
                continue

            resource_id = balance.get(
                "resource_id"
            )

            if resource_id is None:
                continue

            if resource_id in existing_resource_ids:
                continue

            resource = world.resources.get(
                resource_id
            )

            if resource is None:
                continue

            if not getattr(
                resource,
                "active",
                True,
            ):
                continue

            result["resources"].append(
                WorldSerializer.resource_to_dict(
                    resource
                )
            )

            existing_resource_ids.add(
                resource_id
            )

        return result

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _copy_search_result(
        search_result: dict[str, Any],
    ) -> dict[str, Any]:

        return {
            key: list(value)
            if isinstance(value, list)
            else value
            for key, value in search_result.items()
        }

    @staticmethod
    def _validate_world(
        world: WorldState,
    ) -> None:

        if not isinstance(
            world,
            WorldState,
        ):
            raise TypeError(
                "world must be a WorldState"
            )