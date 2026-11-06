# Campaign services

## Responsibility
Campaign lifecycle, campaign state, campaign clock and per-campaign runtime composition.

## Package modules
- `campaign_state_service.py` — campaign/session state and turn-context assembly.
- `campaign_clock_service.py` — campaign clock reads, advancement and time-based effect expiry.

## Related modules outside this package
- `bootstrap/campaign_runtime.py` — runtime composition root and cache.
- `services/campaign_turn_service.py` — compatibility-only native turn workflow; belongs to the turns boundary.
- `services/identity_service.py` — ownership still needs review.

## Dependency rules
- Compose repositories and application services here.
- Do not depend on FastAPI routers or request objects.
- Keep runtime construction at the composition boundary.
- Campaign state may depend on the world state port, but does not own world mutation.

## Pending work
- [ ] Define runtime invalidation on campaign deletion and configuration changes.
- [ ] Specify shutdown behavior and assess whether the unbounded runtime cache needs safe eviction. Runtime state is process-local; the supported deployment remains one process/worker.
- [ ] Formalize provider/runtime construction behind typed composition contracts where substitution is needed; narrative, extraction and mechanics roles already have explicit model and timeout settings in LLMSettings.
- [ ] Decide whether the currently unreferenced identity_service.py should be removed or promoted to a documented shared text utility; do not move it into campaign without a real campaign use case.
- [ ] Add focused lifecycle and invalidation tests.
- [ ] Migrate remaining consumers from compatibility imports and remove shims when safe.
