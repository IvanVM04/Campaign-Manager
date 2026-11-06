import json
from dataclasses import asdict, is_dataclass
from typing import Any

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
    """Create detached, immutable-friendly projections for world collections."""

    _COLLECTIONS = {
        "items": ("items", WorldItemRead, ("name", "description", "significance", "notes")),
        "item-instances": ("item_instances", WorldItemInstanceRead, ("condition", "notes")),
        "resources": ("resources", WorldResourceRead, ("name", "resource_type", "unit", "notes")),
        "resource-balances": ("resource_balances", WorldResourceBalanceRead, ("notes",)),
        "relations": ("relations", WorldRelationRead, ("relation_type",)),
        "events": ("events", WorldEventRead, ("event_type", "title", "description", "consequences")),
    }

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
        values = getattr(world, attribute)
        ordered = sorted(
            values.values(),
            key=lambda value: (
                getattr(value, "id", None) is None,
                str(getattr(value, "id", "")),
            ),
        )
        needle = (query or "").strip().casefold()
        projected = []
        for value in ordered:
            if active is not None and hasattr(value, "active") and value.active is not active:
                continue
            searchable = " ".join(str(getattr(value, field, "")) for field in search_fields)
            if needle and needle not in searchable.casefold():
                continue
            data = asdict(value) if is_dataclass(value) else dict(vars(value))
            if collection in {"relations", "events"}:
                metadata = data.pop("metadata", None)
                data["metadata_json"] = json.dumps(
                    metadata, ensure_ascii=False, sort_keys=True
                ) if collection == "relations" and metadata is not None else (
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
                    if collection == "events" else None
                )
            projected.append(model(**data).model_dump())
        return WorldCollectionPage(
            items=tuple(projected[offset:offset + limit]),
            total=len(projected),
            limit=limit,
            offset=offset,
        )
