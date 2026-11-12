# Campaign services

## Responsibility
Campaign lifecycle, campaign state, campaign clock and per-campaign runtime composition.

## Package modules
- `campaign_state_service.py` — campaign/session state and turn-context assembly.
- `campaign_clock_service.py` — campaign clock reads, advancement and time-based effect expiry.
- Campaign clock advancement expires due campaign-time effects in the same `IMMEDIATE` transaction.
- Character short/long rest use cases live in `services/characters/character_rest_service.py`; they advance this clock and expire due effects atomically with character Hit Dice/HP changes.
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

## Runtime lifecycle status
- [x] Explicit per-campaign runtime invalidation via `CampaignRuntimeFactory.invalidate()`.
- [x] Idempotent factory shutdown via `CampaignRuntimeFactory.shutdown()`, wired to FastAPI shutdown.
- [x] Tests for selective invalidation, full shutdown, idempotent shutdown and runtime reconstruction (`tests/test_campaign_runtime_lifecycle.py`; PR #203).
- [ ] Automatic invalidation on campaign deletion/configuration changes is deferred until those lifecycle operations exist and need to invalidate a cached runtime.
- [ ] Bounded LRU/TTL eviction is deferred. The supported deployment is one process/worker; add an eviction policy only after measuring cache pressure and defining behavior for in-flight requests.
- [ ] Add a typed composition protocol only if a real substitution boundary appears; the three LLM roles already have explicit model and timeout settings.
- [x] Migrate consumers to canonical campaign-package imports and retire the former flat compatibility paths.

## Session and conversation read API
- `GET /sessions?limit=50&offset=0` returns a campaign-scoped page with session metadata, turn count and last-turn timestamp.
- `GET /sessions/{session_id}` returns the same summary or 404 if the session is not part of the selected campaign.
- `GET /turns?session_id={id}&limit=50&offset=0` returns a stable, oldest-first transcript page. Omitting session_id lists campaign-wide turns.
- Transcript records expose version and status so the UI can distinguish active and superseded versions. Internal snapshots are never returned.
- Session notes are deliberately omitted from the read DTO; a separate GM-only policy is required before exposing them.
- All queries are campaign-scoped and do not mutate campaign state.
