from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from models.entity import Entity
from models.event import Event
from models.item import Item, ItemInstance
from models.relation import Relation
from models.resource import Resource, ResourceBalance
from models.world_context_projection import (
    ContextProjectionDiagnostics,
    WorldContextProjection,
    estimate_tokens,
)
from models.world_state import WorldState

from .context_expander import ContextExpander
from .context_ranker import ContextRanker
from .context_renderer import ContextRenderer
from .memory_search_service import MemorySearchService

RecordKey = tuple[str, int | str]

_RECORD_CATEGORIES = (
    "entities",
    "items",
    "item_instances",
    "resources",
    "resource_balances",
    "relations",
    "events",
)


class ProposalContextBudgetError(ValueError):
    """Raised when mandatory facts cannot fit the configured context budget."""


class ProposalContextSelector:
    """Select a deterministic, relevant subset of world records for one proposal.

    Search and graph expansion are reused from the regular context pipeline.
    Records are then ranked and admitted as dependency-aware bundles so that a
    relation never loses its referenced entities and an item instance never
    loses its item definition.
    """

    def __init__(
        self,
        *,
        memory_search_service: MemorySearchService,
        context_expander: ContextExpander,
        ranker: ContextRanker,
    ) -> None:
        self.memory_search_service = memory_search_service
        self.context_expander = context_expander
        self.ranker = ranker

    def build(
        self,
        world: WorldState,
        query: str,
        *,
        max_estimated_tokens: int,
        mandatory_entity_ids: tuple[int, ...] | list[int] = (),
    ) -> WorldContextProjection:
        if not isinstance(world, WorldState):
            raise TypeError("world must be a WorldState")
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        if (
            isinstance(max_estimated_tokens, bool)
            or not isinstance(max_estimated_tokens, int)
            or max_estimated_tokens <= 0
        ):
            raise ValueError("max_estimated_tokens must be a positive integer")
        if not isinstance(mandatory_entity_ids, (tuple, list)):
            raise TypeError("mandatory_entity_ids must be a tuple or list")

        normalized_query = query.strip()
        mandatory_ids: list[int] = []
        for entity_id in mandatory_entity_ids:
            if isinstance(entity_id, bool) or not isinstance(entity_id, int):
                raise TypeError("mandatory entity IDs must be integers")
            if entity_id not in mandatory_ids:
                mandatory_ids.append(entity_id)

        public_records = self.memory_search_service.export(world)
        record_lookup: dict[str, dict[int | str, dict[str, Any]]] = {}
        object_lookup: dict[str, dict[int | str, Any]] = {}

        for category in _RECORD_CATEGORIES:
            values = public_records.get(category, [])
            record_lookup[category] = {
                record["id"]: record
                for record in values
                if isinstance(record, dict) and record.get("id") is not None
            }
            object_lookup[category] = dict(getattr(world, category))

        search_result = self.memory_search_service.search(world, normalized_query)
        searched_entity_ids = {
            record.get("id")
            for record in search_result.get("entities", [])
            if isinstance(record, dict)
        }
        for entity_id in mandatory_ids:
            mandatory_record = record_lookup["entities"].get(entity_id)
            if mandatory_record is not None and entity_id not in searched_entity_ids:
                search_result.setdefault("entities", []).append(mandatory_record)

        expanded = self.context_expander.expand(
            world,
            search_result,
            max_depth=1,
        )

        candidates: dict[RecordKey, tuple[float, dict[str, Any]]] = {}
        for category in _RECORD_CATEGORIES:
            base_score = ContextRenderer.CATEGORY_BASE_SCORES[category]
            # ContextExpander replaces some collections with graph-related
            # records. Retain direct search hits as well, especially events
            # and relations whose own text matched but which have no selected
            # entity edge.
            category_records = [
                *search_result.get(category, []),
                *expanded.get(category, []),
            ]
            for record in category_records:
                if not isinstance(record, dict):
                    continue
                record_id = record.get("id")
                if (
                    record_id is None
                    or isinstance(record_id, bool)
                    or not isinstance(record_id, (int, str))
                    or record_id not in record_lookup[category]
                ):
                    continue
                if category == "events" and record.get("secret") is True:
                    continue
                key = (category, record_id)
                score = self.ranker.score_candidate(
                    data=record,
                    query=normalized_query,
                    base_score=base_score,
                )
                current = candidates.get(key)
                if current is None or score > current[0]:
                    candidates[key] = (score, record)

        for entity_id in mandatory_ids:
            if entity_id not in record_lookup["entities"]:
                continue
            record = record_lookup["entities"][entity_id]
            candidates[("entities", entity_id)] = (float("inf"), record)

        selected: set[RecordKey] = set()
        estimated_tokens = 0

        def dependency_keys(category: str, record: dict[str, Any]) -> list[RecordKey]:
            dependencies: list[RecordKey] = []

            def add(target_category: str, target_id: Any) -> None:
                if (
                    target_id is None
                    or isinstance(target_id, bool)
                    or not isinstance(target_id, (int, str))
                ):
                    return
                if target_id in record_lookup[target_category]:
                    dependencies.append((target_category, target_id))

            if category == "relations":
                add("entities", record.get("subject_id"))
                add("entities", record.get("target_id"))
            elif category == "events":
                metadata = record.get("metadata")
                related_ids = metadata.get("entity_ids", []) if isinstance(metadata, dict) else []
                if isinstance(related_ids, (list, tuple, set)):
                    for entity_id in related_ids:
                        add("entities", entity_id)
            elif category == "item_instances":
                add("items", record.get("item_id"))
                add("entities", record.get("owner_id"))
                add("entities", record.get("location_id"))
            elif category == "resource_balances":
                add("resources", record.get("resource_id"))
                add("entities", record.get("owner_id"))

            return dependencies

        def bundle_for(initial: RecordKey) -> set[RecordKey]:
            bundle: set[RecordKey] = set()
            pending = [initial]
            while pending:
                key = pending.pop()
                if key in bundle or key[1] not in record_lookup.get(key[0], {}):
                    continue
                bundle.add(key)
                record = record_lookup[key[0]][key[1]]
                pending.extend(dependency_keys(key[0], record))
            return bundle

        def bundle_cost(bundle: set[RecordKey]) -> int:
            total = 0
            for category, record_id in bundle - selected:
                record = record_lookup[category][record_id]
                payload = json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                    separators=(",", ":"),
                )
                # The fixed allowance covers category labels and prompt line
                # syntax that are not present in the serialized record.
                total += estimate_tokens(payload) + 16
            return total

        # The active player entity is mandatory context. It is admitted before
        # optional candidates, and the operation fails explicitly if it cannot fit.
        mandatory_keys = [
            ("entities", entity_id)
            for entity_id in mandatory_ids
            if entity_id in record_lookup["entities"]
        ]
        for key in mandatory_keys:
            bundle = bundle_for(key)
            cost = bundle_cost(bundle)
            if estimated_tokens + cost > max_estimated_tokens:
                raise ProposalContextBudgetError(
                    "mandatory player context exceeds the configured token budget"
                )
            selected.update(bundle)
            estimated_tokens += cost

        category_order = ContextRenderer.CATEGORY_PRIORITY
        ordered_candidates = sorted(
            candidates.items(),
            key=lambda item: (
                -item[1][0],
                category_order[item[0][0]],
                str(item[0][1]),
            ),
        )

        for key, _candidate in ordered_candidates:
            if key in selected:
                continue
            bundle = bundle_for(key)
            if not bundle:
                continue
            cost = bundle_cost(bundle)
            if estimated_tokens + cost > max_estimated_tokens:
                continue
            selected.update(bundle)
            estimated_tokens += cost

        selected_entities: dict[int, Entity] = {}
        selected_items: dict[int, Item] = {}
        selected_item_instances: dict[int, ItemInstance] = {}
        selected_resources: dict[int, Resource] = {}
        selected_resource_balances: dict[int, ResourceBalance] = {}
        selected_relations: dict[str, Relation] = {}
        selected_events: dict[str, Event] = {}

        def selected_record_sort_key(
            record_key: RecordKey,
        ) -> tuple[int, int, int | str]:
            category, record_id = record_key
            if isinstance(record_id, int):
                return category_order[category], 0, record_id
            return category_order[category], 1, str(record_id)

        for category, record_id in sorted(
            selected,
            key=selected_record_sort_key,
        ):
            original = object_lookup[category].get(record_id)
            if category == "entities" and isinstance(record_id, int) and isinstance(original, Entity):
                selected_entities[record_id] = deepcopy(original)
            elif category == "items" and isinstance(record_id, int) and isinstance(original, Item):
                selected_items[record_id] = deepcopy(original)
            elif category == "item_instances" and isinstance(record_id, int) and isinstance(original, ItemInstance):
                selected_item_instances[record_id] = deepcopy(original)
            elif category == "resources" and isinstance(record_id, int) and isinstance(original, Resource):
                selected_resources[record_id] = deepcopy(original)
            elif category == "resource_balances" and isinstance(record_id, int) and isinstance(original, ResourceBalance):
                selected_resource_balances[record_id] = deepcopy(original)
            elif category == "relations" and isinstance(record_id, str) and isinstance(original, Relation):
                selected_relations[record_id] = deepcopy(original)
            elif category == "events" and isinstance(record_id, str) and isinstance(original, Event):
                selected_events[record_id] = deepcopy(original)

        projected_world = WorldState(
            entities=selected_entities,
            items=selected_items,
            item_instances=selected_item_instances,
            resources=selected_resources,
            resource_balances=selected_resource_balances,
            relations=selected_relations,
            events=selected_events,
        )
        available_counts = tuple(
            (category, len(record_lookup[category]))
            for category in _RECORD_CATEGORIES
        )
        candidate_counts = tuple(
            (
                category,
                sum(1 for candidate_category, _ in candidates if candidate_category == category),
            )
            for category in _RECORD_CATEGORIES
        )
        selected_lookup = {
            "entities": selected_entities,
            "items": selected_items,
            "item_instances": selected_item_instances,
            "resources": selected_resources,
            "resource_balances": selected_resource_balances,
            "relations": selected_relations,
            "events": selected_events,
        }
        selected_counts = tuple(
            (category, len(selected_lookup[category]))
            for category in _RECORD_CATEGORIES
        )
        diagnostics = ContextProjectionDiagnostics(
            estimated_tokens=estimated_tokens,
            budget_tokens=max_estimated_tokens,
            available_counts=available_counts,
            candidate_counts=candidate_counts,
            selected_counts=selected_counts,
        )
        return WorldContextProjection(
            world=projected_world,
            diagnostics=diagnostics,
        )
