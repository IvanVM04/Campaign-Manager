# World services

## Responsibility
Apply validated typed world operations to in-memory campaign state, coordinate persistence through repositories and expose serialization/state-port adapters.

## Modules
- `world_service.py` — campaign-scoped world facade and state publication.
- `world_turn_operation_coordinator.py` — ordered mixed world/character turn operations, reference resolution hand-off and caller-owned connection coordination.
- `world_query_service.py` — immutable, filtered and paginated entity read models.
- `world_collection_query_service.py` — detached read projections for items, instances, resources, balances, relations and events, including display names for related records.
- `world_visibility_policy.py` — the shared player-read policy for secret events.
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
- Player-facing reads must use `WorldVisibilityPolicy`; secret events are filtered before search and pagination so neither their fields nor their existence count is exposed.
- The current policy intentionally has no unauthenticated GM bypass. A future GM projection must be protected by a verified principal and campaign-scoped GM authorization, not by a query parameter or caller-controlled role header.

## Dependency rules
- Apply typed operations; never accept arbitrary model-generated database writes.
- Keep persistence behind repositories and preserve caller-owned transaction semantics.
- Keep entity, item, relation and resource application boundaries explicit.
- API read models must be detached from mutable domain state; metadata is serialized as JSON text.
- Avoid coupling world mutation to HTTP or concrete LLM providers.
- Model-generated proposals must pass parsing and validation before reaching this package.

## Pending work
- [x] Centralize secret-event filtering for world, collection, memory and export reads.
- [ ] Add authenticated GM/player principals and per-campaign authorization before remote or multi-user exposure.
- [x] Extract mixed turn-operation dispatch and preserve the shared caller-owned transaction; rollback tests cover operation failures.
- [ ] Verify campaign scoping and stale-context/revision checks at the application boundary.
- [ ] Add architecture tests preventing prompt/extraction code from writing repositories directly.
- [ ] Review serializer consumers before changing its output contract.
- [x] Remove former flat world compatibility shims after caller migration; canonical imports remain under `services.world`.

## Migration status
All eight modules now live in `services/world/`. The former flat world compatibility modules have been removed. The current `services/` root contains only the active SillyTavern integration adapter; no flat world shim remains.
