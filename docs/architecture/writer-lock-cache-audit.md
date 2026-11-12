# Campaign writer, lock and cache-coherence audit (F-13)

**Scope:** all tracked FastAPI routes that mutate campaign-owned state, plus routes that lazily initialize it.
**Deployment assumption:** one application process and one worker. `TurnExecutionLock` is process-local; SQLite transactions and revision triggers protect persistence, but this is not a distributed lock.

## Findings and changes in PR #78

The audit found four missing synchronization boundaries in `api/routers/character.py`:

- `POST /characters` and `POST /campaign/bootstrap` persisted a new `entities` row and `character_states` row without taking the campaign lock. The `WorldService` cache was not reloaded after the committed entity write.
- `POST /characters/{character_entity_id}/equipment` and `DELETE /characters/{character_entity_id}/equipment/{slot}` had SQLite transactions but did not take the shared campaign lock.
- `GET /characters/{character_entity_id}/equipment` assembled its response from several independent reads and could mix equipment projections if a write interleaved.
- `GET /campaign/clock` called `CampaignClockService.get()`, which may insert the initial clock row. It was a write-capable GET without the campaign lock, and the service used a DEFERRED transaction for that lazy initialization.

PR #78 fixes these boundaries:
- Character creation/bootstrap now run under the campaign lock and reload `WorldService` after the character-creation transaction commits.
- Equipment writes and the multi-query equipment read run under the same campaign lock.
- Campaign clock GET now runs under the campaign lock, and `CampaignClockService.get()` uses `BEGIN IMMEDIATE` because `ensure()` can write.
- Tests verify that character creation/bootstrap refresh the in-memory world and that character/equipment/clock endpoints acquire the shared lock.

## Route-to-writer matrix

| Route(s) | Writer / transaction owner | Lock | Revision / cache behavior |
|---|---|---|---|
| `POST /campaigns` | `CampaignRepository.create_campaign()`; repository-owned SQLite connection | No selected campaign runtime exists yet | Creates a new campaign. Its runtime and world cache are built on first selection. |
| `PATCH /campaign`, `PATCH /campaign/session`, `PATCH /campaign/active-character`, `POST /sessions` | `CampaignRepository` / `CampaignStateService`; repository-owned connection(s) | Route acquires campaign lock | Campaign/session/active-character tables are covered by migration 021 revision triggers. No `WorldState` cache is modified. |
| `POST /characters`, `POST /campaign/bootstrap` | `CharacterCreationService.create_character()`; one `get_conn()` context owns the atomic entity + character + active-character writes | Route acquires campaign lock | Migration 021 triggers advance revision for entity/character/campaign writes. PR #78 reloads the runtime `WorldService` after commit. Failed creation rolls back all writes; the cache is not refreshed on failure. |
| `POST /characters/{id}/equipment`, `DELETE /characters/{id}/equipment/{slot}` | `WeaponEquipmentRepository`; `transaction("IMMEDIATE")` owns the slot replacement/removal | Route acquires campaign lock | Migration 026 installs revision triggers for `equipped_items`. Equipment is a DB projection, not part of `WorldState`. |
| `GET /characters/{id}/equipment` | Character/equipment repositories; multiple read queries | Route acquires campaign lock for a coherent projection | Read-only; no revision or cache change. |
| `GET /characters/{id}/inventory` | One inventory query | No lock required | Read-only, one query. |
| `GET /campaign/clock` | `CampaignClockService.get()`; `transaction("IMMEDIATE")` because `ensure()` may insert | Route acquires campaign lock | Migration 021 revision triggers cover `campaign_clocks`; lazy initialization is now serialized. |
| `POST /campaign/clock/advance` | `CampaignClockService.advance()`; `transaction("IMMEDIATE")` includes clock update and due-effect expiration | Route acquires campaign lock | Clock and persistent-effect revision triggers advance in the same transaction. |
| `POST /world/entities/bootstrap` | `WorldService.apply_operations_and_save()` and `WorldRepository.save_world()`; one repository-owned connection/commit for the multi-table save | Route acquires campaign lock | World tables are covered by migration 021 revision triggers. In-memory operation application is staged; save failure restores the original cache reference. |
| `POST /encounters`, `/start`, `/death-save`, `/advance`, `/complete`, `/attack`, `/opportunity-attack`, `/reaction`, `/move` | `CombatEncounterService` / `CombatAttackService`; `transaction("IMMEDIATE")` (all encounter mutations use `transaction("IMMEDIATE")`) | Every mutating combat route acquires campaign lock | Encounter, character HP, creature state and effects commit together where applicable. Migrations 021 and 024 cover the relevant campaign-owned tables; migration 024 adds creature-state revision triggers. New creatures trigger a post-commit `WorldService.load()`. |
| `POST /entities/{id}/effects`, `PATCH /effects/{id}/status`, `DELETE /effects/{id}` | `PersistentEffectService`; `transaction("IMMEDIATE")` | Route acquires campaign lock | Persistent effects/timers are transactionally persisted and revision-triggered. No `WorldState` cache is maintained for effect rows. |
| `POST /turn`, `POST /turn/roll`, `POST /turn/clarification` | `DurableNativeTurnService`; short explicit SQLite transactions, with `IMMEDIATE` for claims/commit | Service acquires shared campaign lock | Captures and validates campaign revision; consequences and durable resolution commit atomically. `WorldService` publishes the committed world state and restores its prior state on rollback. |
| `POST /integration/turn/resolve`, `/roll`, `/clarification`, `/complete` | `DurableNativeTurnService` plus context adapter | Route or durable service acquires shared campaign lock (completion acquires internally) | Same durable revision/commit contract as native turns. |
| Deprecated `POST /integration/turn` | `SillyTavernIntegrationService.process_turn()`; legacy transaction and snapshot reconciliation | Service acquires shared campaign lock | Legacy path retains snapshot rollback/reconciliation behavior; do not extend it. |
| `POST /integration/context`, integration state GETs, world/memory/export GETs | Read/context assembly | Route acquires lock where it reads shared in-memory world or multiple related projections | Read-only; lock provides a consistent in-process view. |

## Revision-trigger coverage

The campaign revision is a persistence guard, not a substitute for the lock. Migration 021 installs INSERT/UPDATE/DELETE triggers on the campaign-owned tables that existed at that migration. Later campaign-owned tables require explicit triggers:

- Migration 022 `turn_resolutions`: durable execution records use lifecycle/commit-specific integrity triggers; they are not world-context state and do not use the general mutation counter for every lifecycle update.
- Migration 024 `creature_states`: explicit INSERT/UPDATE/DELETE revision triggers.
- Migration 026 `equipped_items`: explicit INSERT/UPDATE/DELETE revision triggers.
- Migration 027/028: no new campaign-owned tables; changes are guards/schema columns on existing tables.

Any future migration adding a campaign-owned table must decide explicitly whether its mutations affect turn context and install revision triggers accordingly.

## Canonical state and rollback rules

- SQLite is canonical for persisted campaign, character, equipment, combat, clock, effect and turn-resolution state.
- `WorldService.world` is a runtime cache of the world tables. Mutations that write world entities/items/resources/events outside `WorldService` must refresh that cache after commit while holding the campaign lock. Character creation was the missing tracked path fixed here; combat creature creation already reloads after commit.
- The lock serializes request workflows that share a runtime. It is an `RLock`, so route-level locking can safely call nested services that also acquire it.
- SQLite transaction contexts own commit/rollback. In-memory state must not be published as authoritative until persistence succeeds; `WorldService.apply_turn_operations()` preserves the original `WorldState` identity and restores it on rollback.
- Campaign revision triggers participate in the same SQLite transaction and roll back with it. Durable turn planning compares captured and current revisions before consequence application.
- Direct repository calls from tests/maintenance scripts are outside the HTTP lock contract; production writers must go through the campaign-scoped application/route path.

## Remaining deployment boundary

The process-local lock does not coordinate multiple Uvicorn workers or multiple backend processes. The supported deployment remains one process/one worker. SQLite transactions and optimistic revisions still protect database integrity, but they do not make the in-memory `WorldService` cache coherent across processes. Multi-worker support requires a separate cache invalidation/distributed coordination design and is not part of F-13.
