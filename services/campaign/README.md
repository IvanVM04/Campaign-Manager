# Campaign services

## Responsibility
Campaign lifecycle, campaign state, campaign clock and per-campaign runtime composition.

## Current modules (still in services/)
- campaign_runtime.py — composition root and runtime cache.
- campaign_state_service.py — campaign state use cases.
- campaign_clock_service.py — campaign clock use cases.
- identity_service.py — ownership still needs review.

## Dependency rules
- Compose repositories and application services here.
- Do not depend on FastAPI routers or request objects.
- Keep runtime construction at the composition boundary.

## Pending work
- [ ] Define runtime invalidation on campaign deletion and configuration changes.
- [ ] Specify shutdown behavior and assess whether the unbounded runtime cache needs safe eviction.
- [ ] Make provider construction and role-specific settings explicit at the composition root.
- [ ] Decide whether identity_service belongs here or in a separate identity capability.
- [ ] Add focused lifecycle and invalidation tests.

## Migration status
This is a documented target boundary only. Source modules and imports remain in services/ until a separate migration preserves compatibility.
