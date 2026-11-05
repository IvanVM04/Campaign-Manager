# World services

## Responsibility
Apply validated typed world operations to in-memory campaign state, coordinate persistence through repositories and expose serialization/state-port adapters.

## Modules
- `world_service.py` — campaign-scoped world facade and transaction coordination.
- `world_applier.py` — typed operation dispatch.
- `world_entity_applier.py`, `world_item_applier.py`, `world_relation_applier.py`, `world_resource_applier.py` — operation-family application.
- `world_serializer.py` — domain dataclass serialization.
- `world_state_port.py` — minimal world-state protocol.

## Dependency rules
- Apply typed operations; never accept arbitrary model-generated database writes.
- Keep persistence behind repositories and preserve caller-owned transaction semantics.
- Keep entity, item, relation and resource application boundaries explicit.
- Avoid coupling world mutation to HTTP or concrete LLM providers.
- Model-generated proposals must pass parsing and validation before reaching this package.

## Pending work
- [ ] Audit operation dispatch so each supported operation has explicit validation and a clear owner.
- [ ] Review atomicity when one proposal changes multiple world aggregates.
- [ ] Verify campaign scoping and stale-context/revision checks at the application boundary.
- [ ] Add architecture tests preventing prompt/extraction code from writing repositories directly.
- [ ] Ensure unsupported operations fail without partial inconsistent application.
- [ ] Review serializer consumers before changing its output contract.
- [ ] Remove compatibility shims only after all callers migrate.

## Migration status
All eight modules now live in `services/world/`. The former `services.world_*` and `services.world_state_port` paths remain compatibility re-exports until consumers migrate separately.
