# Campaign services

## Responsibility
Campaign lifecycle, campaign state, campaign clock and per-campaign runtime composition.

## Package modules
- `campaign_state_service.py` — campaign/session state and turn-context assembly.
- `campaign_clock_service.py` — campaign clock reads, advancement and time-based effect expiry.
- `persistent_effect_service.py` — campaign-scoped effect lifecycle, duration deadlines and status transitions.
- `effective_condition_service.py` — derives D&D condition sets from active persistent effects; conditions are projections, not a second persisted source of truth.

## Related modules outside this package
- `bootstrap/campaign_runtime.py` — runtime composition root and cache. This is the composition boundary; the package itself does not own runtime construction.

## Dependency rules
- Compose repositories and application services at the bootstrap boundary, not inside campaign use cases.
- Do not depend on FastAPI routers or request objects.
- Keep runtime construction at the composition boundary.
- Campaign state may depend on the world state port, but does not own world mutation.
- Effect lifecycle and condition projection belong to campaign state; combat consumes the derived `ConditionSet` without owning effect persistence.

## Pending work
- [ ] Define runtime invalidation on campaign deletion and configuration changes.
- [ ] Specify shutdown behavior and assess whether the unbounded runtime cache needs safe eviction. Runtime state is process-local; the supported deployment remains one process/worker.
- [ ] Formalize typed composition contracts only where a real substitution boundary requires them; narrative, extraction and mechanics roles already have explicit model and timeout settings in LLMSettings.
- [ ] Add focused lifecycle and invalidation tests.
- [x] Migrate consumers to canonical campaign-package imports and retire the former flat compatibility paths.

## Session and conversation read API
- `GET /sessions?limit=50&offset=0` returns a campaign-scoped page with session metadata, turn count and last-turn timestamp.
- `GET /sessions/{session_id}` returns the same summary or 404 if the session is not part of the selected campaign.
- `GET /turns?session_id={id}&limit=50&offset=0` returns a stable, oldest-first transcript page. Omitting session_id lists campaign-wide turns.
- Transcript records expose version and status so the UI can distinguish active and superseded versions. Internal snapshots are never returned.
- Session notes are deliberately omitted from the read DTO; a separate GM-only policy is required before exposing them.
- All queries are campaign-scoped and do not mutate campaign state.
