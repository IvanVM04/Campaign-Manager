# World services

## Responsibility
Apply validated typed world operations to in-memory campaign state, coordinate world application and serialize world state for supported consumers.

## Current modules (still in services/)
- world_service.py — world application facade.
- world_applier.py — operation dispatch.
- world_entity_applier.py
- world_item_applier.py
- world_relation_applier.py
- world_resource_applier.py
- world_serializer.py
- world_state_port.py — world-state abstraction.

## Dependency rules
- Apply typed operations; never accept arbitrary model-generated database writes.
- Keep persistence behind repositories and preserve caller-owned transaction semantics.
- Keep entity, item, relation and resource application boundaries explicit.
- Avoid coupling world mutation to HTTP or concrete LLM providers.

## Pending work
- [ ] Audit operation dispatch so each supported operation has explicit validation and a clear owner.
- [ ] Review atomicity when one proposal changes multiple world aggregates.
- [ ] Verify campaign scoping and stale-context/revision checks at the application boundary.
- [ ] Add architecture tests preventing prompt/extraction code from writing repositories directly.
- [ ] Ensure unsupported operations fail without partial inconsistent application.
- [ ] Review serializer consumers before changing its output contract.

## Migration status
This is a documented target boundary only. Source modules and imports remain in services/ until a separate migration preserves compatibility.
