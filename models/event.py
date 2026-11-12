from dataclasses import dataclass, field
from typing import Any

EPISTEMIC_STATUSES = frozenset({"confirmed", "rumor", "inference"})
PROVENANCE_SOURCES = frozenset({
    "gm_authored",
    "direct_observation",
    "npc_statement",
    "discovered_document",
    "rules_result",
    "model_inference",
    "imported",
})
VISIBILITY_SCOPES = frozenset({"public", "character", "gm_only"})


@dataclass
class Event:
    """Append-oriented campaign event with typed epistemic and visibility metadata.

    Legacy events default to confirmed GM-authored public facts. The legacy
    secret flag is retained as a compatibility alias for gm_only.
    """

    id: str
    event_type: str
    title: str
    description: str = ""
    consequences: str = ""
    session_id: int | None = None
    secret: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    epistemic_status: str = "confirmed"
    provenance_source: str = "gm_authored"
    visibility_scope: str = "public"
    known_by_entity_ids: list[int] = field(default_factory=list)
    source_entity_id: int | None = None
    campaign_elapsed_minutes: int | None = None
    supersedes_event_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("event id must not be empty")
        if not isinstance(self.event_type, str) or not self.event_type.strip():
            raise ValueError("event_type must not be empty")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("event title must not be empty")
        if not isinstance(self.secret, bool):
            raise TypeError("secret must be a boolean")

        if not isinstance(self.epistemic_status, str) or self.epistemic_status not in EPISTEMIC_STATUSES:
            raise ValueError("epistemic_status must be confirmed, rumor or inference")
        if not isinstance(self.provenance_source, str) or self.provenance_source not in PROVENANCE_SOURCES:
            raise ValueError("unsupported provenance_source")
        if not isinstance(self.visibility_scope, str) or self.visibility_scope not in VISIBILITY_SCOPES:
            raise ValueError("visibility_scope must be public, character or gm_only")
        if self.provenance_source == "model_inference" and self.epistemic_status != "inference":
            raise ValueError("model_inference provenance must remain epistemically unconfirmed")

        if self.secret:
            self.visibility_scope = "gm_only"
        if self.visibility_scope == "gm_only":
            self.secret = True

        if not isinstance(self.known_by_entity_ids, (list, tuple)):
            raise TypeError("known_by_entity_ids must be a list or tuple of integers")
        known_by: list[int] = []
        for entity_id in self.known_by_entity_ids:
            if isinstance(entity_id, bool) or not isinstance(entity_id, int) or entity_id < 1:
                raise ValueError("known_by_entity_ids must contain positive integers")
            if entity_id not in known_by:
                known_by.append(entity_id)
        self.known_by_entity_ids = known_by
        if self.visibility_scope == "character" and not known_by:
            raise ValueError("character-scoped events require at least one known-by entity")
        if self.visibility_scope != "character" and known_by:
            raise ValueError("known_by_entity_ids are only valid for character-scoped events")

        if self.source_entity_id is not None and (
            isinstance(self.source_entity_id, bool)
            or not isinstance(self.source_entity_id, int)
            or self.source_entity_id < 1
        ):
            raise ValueError("source_entity_id must be a positive integer or None")
        if self.campaign_elapsed_minutes is not None and (
            isinstance(self.campaign_elapsed_minutes, bool)
            or not isinstance(self.campaign_elapsed_minutes, int)
            or self.campaign_elapsed_minutes < 0
        ):
            raise ValueError("campaign_elapsed_minutes must be a non-negative integer or None")
        if self.supersedes_event_id is not None:
            if not isinstance(self.supersedes_event_id, str) or not self.supersedes_event_id.strip():
                raise ValueError("supersedes_event_id must be a non-empty string or None")
            if self.supersedes_event_id == self.id:
                raise ValueError("an event cannot supersede itself")
