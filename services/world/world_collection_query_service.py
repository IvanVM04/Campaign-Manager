import json
from dataclasses import asdict, is_dataclass
from typing import Any, ClassVar, cast

from pydantic import BaseModel

from models.world_collection_read_models import (
    WorldCollectionPage,
    WorldEventRead,
    WorldItemInstanceRead,
    WorldItemRead,
    WorldRelationRead,
    WorldResourceBalanceRead,
    WorldResourceRead,
)
from models.world_state import WorldState


class WorldCollectionQueryService:
    """Create detached projections for every browsable world collection."""

    _COLLECTIONS: ClassVar = {
        "items": ("items", WorldItemRead, ("name", "description", "significance", "notes")),
        "item-instances": ("item_instances", WorldItemInstanceRead, ("condition", "notes", "item_id", "owner_id", "location_id")),
        "resources": ("resources", WorldResourceRead, ("name", "resource_type", "unit", "notes")),
        "resource-balances": ("resource_balances", WorldResourceBalanceRead, ("notes", "resource_id", "owner_id")),
        "relations": ("relations", WorldRelationRead, ("relation_type", "subject_id", "target_id")),
        "events": ("events", WorldEventRead, ("event_type", "title", "description", "consequences")),
    }

    @staticmethod
    def _entity_name(world: WorldState, entity_id: int | None) -> str | None:
        if entity_id is None:
            return None
        entity = world.entities.get(entity_id)
        return entity.name if entity is not None else None

    def _related_names(self, world: WorldState, collection: str, value) -> dict[str, str | None]:
        if collection == "item-instances":
            item = world.items.get(value.item_id)
            return {
                "item_name": item.name if item is not None else None,
                "owner_name": self._entity_name(world, value.owner_id),
                "location_name": self._entity_name(world, value.location_id),
            }
        if collection == "resource-balances":
            resource = world.resources.get(value.resource_id)
            return {
                "resource_name": resource.name if resource is not None else None,
                "owner_name": self._entity_name(world, value.owner_id),
            }
        if collection == "relations":
            return {
                "subject_name": self._entity_name(world, value.subject_id),
                "target_name": self._entity_name(world, value.target_id),
            }
        return {}

    def list_collection(
        self,
        world: WorldState,
        collection: str,
        *,
        query: str | None = None,
        active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> WorldCollectionPage:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must not be negative")
        if collection not in self._COLLECTIONS:
            raise ValueError(f"unsupported world collection: {collection}")

        attribute, model, search_fields = self._COLLECTIONS[collection]
        ordered = sorted(
            getattr(world, attribute).values(),
            key=lambda value: (
                getattr(value, "id", None) is None,
                str(getattr(value, "id", "")),
            ),
        )
        needle = (query or "").strip().casefold()
        projected: list[BaseModel] = []
        for value in ordered:
            if active is not None and hasattr(value, "active") and value.active is not active:
                continue
            related_names = self._related_names(world, collection, value)
            searchable = " ".join(
                str(getattr(value, field, "")) for field in search_fields
            )
            searchable = f"{searchable} {' '.join(name or '' for name in related_names.values())}"
            if needle and needle not in searchable.casefold():
                continue
            data = (
                asdict(cast(Any, value))
                if is_dataclass(value) and not isinstance(value, type)
                else dict(vars(value))
            )
            data.update(related_names)
            if collection in {"relations", "events"}:
                metadata = data.pop("metadata", None)
                data["metadata_json"] = (
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True)
                    if metadata is not None or collection == "events"
                    else None
                )
            projected.append(model(**data))

        return WorldCollectionPage(
            items=tuple(projected[offset:offset + limit]),
            total=len(projected),
            limit=limit,
            offset=offset,
        )
