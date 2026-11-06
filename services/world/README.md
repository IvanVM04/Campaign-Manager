# World services

## Responsibility
Apply validated typed world operations to in-memory campaign state, coordinate persistence through repositories and expose serialization/state-port adapters.

## Modules
- `world_service.py` — campaign-scoped world facade and transaction coordination.
- `world_query_service.py` — immutable, filtered and paginated entity read models.
- `world_collection_query_service.py` — detached read projections for items, instances, resources, balances, relations and events, including display names for related records.
- `world_applier.py` — typed operation dispatch.
- `world_entity_applier.py`, `world_item_applier.py`, `world_relation_applier.py`, `world_resource_applier.py` — operation-family application.
- `world_serializer.py` — domain dataclass serialization.
- `world_state_port.py` — minimal world-state protocol.

## Read-model contract
- Keep canonical IDs in every projection; related display names are additive and nullable.
- Item instances expose the item, owner and location names when those records exist.
- Resource balances expose resource and owner names; relations expose subject and target names.
- Missing related records do not hide the original IDs and produce a null display name.
- Search includes resolved display names as well as the collection's own fields.
- Projections remain frozen and detached from mutable domain state.
- Event visibility is not changed by these projections; secret-event filtering must be enforced by a separate authorization/visibility policy before player-facing exposure.

## Dependency rules
- Apply typed operations; never accept arbitrary model-generated database writes.
- Keep persistence behind repositories and preserve caller-owned transaction semantics.
- Keep entity, item, relation and resource application boundaries explicit.
- API read models must be detached from mutable domain state; metadata is serialized as JSON text.
- Avoid coupling world mutation to HTTP or concrete LLM providers.
- Model-generated proposals must pass parsing and validation before reaching this package.

## Pending work
- [ ] Add relation/event visibility policy before exposing secret campaign data to non-GM clients.
- [ ] Audit operation dispatch and multi-aggregate atomicity.
- [ ] Verify campaign scoping and stale-context/revision checks at the application boundary.
- [ ] Add architecture tests preventing prompt/extraction code from writing repositories directly.
- [ ] Review serializer consumers before changing its output contract.
- [ ] Remove compatibility shims only after all callers migrate.

## Migration status
All eight modules now live in `services/world/`. The former `services.world_*` and `services.world_state_port` paths remain compatibility re-exports until consumers migrate separately.
