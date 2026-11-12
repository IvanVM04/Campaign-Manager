> **Historical document — superseded by the 2026-11-12 legacy-retirement cleanup.**
> The narrative-first extractor, static legacy prompt builder, deprecated
> `POST /integration/turn`, legacy turn service and runtime snapshot
> reconciliation described below have been removed. Migration 029 archives
> existing non-null snapshot JSON in `turn_snapshot_archive`. Do not treat
> the recommendations in this historical report as current implementation
> instructions; see [the current architecture audit](architecture-audit-2026-11-12.md)
> and [turn pipeline contract](turn-pipeline-compatibility.md).

# Legacy SillyTavern retirement audit — 2026-11-11

**Repository:** IvanVM04/Campaign-Manager  
**Baseline:** `main` at `6aab67a58ff063ca1fa3f293628c3ddc6ab6b2b7` (merge of PR #157).  
**Scope:** deprecated narrative-first `POST /integration/turn`, its adapter/delegate, snapshot persistence and the active SillyTavern contract.  
**Method:** source and test search, route inspection, repository inspection and migration inspection. No live external-client usage logs or production deployment data were available.

## 1. Findings

### 1.1 The deprecated route is instrumented, but usage has not been proven to be zero

- `api/routers/integration.py` marks `POST /integration/turn` as deprecated in OpenAPI.
- Every request emits a structured warning with `campaign_id` and `external_turn_id`, directing clients to `/integration/turn/resolve` and `/integration/turn/complete`.
- `tests/test_silly_tavern_integration.py` verifies the OpenAPI deprecation flag and the structured warning fields.
- This is request-level usage telemetry in application logs. It is not an aggregate counter, retention system or proof that external clients have migrated.
- No production log window, release telemetry or external fork inventory was available during this repository audit.

**Decision:** keep the route. Removal requires an agreed observation window with zero matching log events and an explicit check of supported extension versions/forks.

### 1.2 The integration adapter is still active

`SillyTavernIntegrationService` has active responsibilities beyond the deprecated mutation endpoint:

- `get_context()` builds campaign context/history for the extension.
- `get_external_turn_state()` reads the persisted external transcript version.
- `process_turn()` delegates only the old narrative-first mutation workflow to `LegacySillyTavernTurnService`.

The current extension uses the durable resolve/complete lifecycle. Removing the entire adapter would therefore break active context and transcript-state reads even after the old POST route is retired.

**Decision:** if compatibility retirement becomes approved, remove only the legacy delegate/wiring from the adapter while retaining the adapter's active read/context methods.

### 1.3 Snapshot persistence is a column, not a set of snapshot tables

`WorldSnapshotRepository` serializes campaign state from these existing tables into one JSON string:

- `entities`
- `items`
- `item_instances`
- `resources`
- `resource_balances`
- `relations`
- `world_events`
- `character_states`

It also stores campaign pointer values in the JSON payload. The payload is persisted in the nullable `turns.snapshot` column added by migration 008. There are no dedicated snapshot tables.

The legacy turn service creates a snapshot before applying a legacy turn, loads it to build regeneration context, and restores it inside the regeneration transaction. The active durable turn narration path writes `snapshot=None`; it does not depend on snapshot restoration.

Repository search found:
- production construction of `WorldSnapshotRepository` in `SillyTavernIntegrationService`;
- production create/load/restore calls in `LegacySillyTavernTurnService`;
- direct repository tests in `tests/test_world_repository.py`;
- legacy integration/regeneration tests in `tests/test_silly_tavern_integration.py`.

**Decision:** retain the repository and `turns.snapshot` while the legacy route remains. Do not describe the persistence as historical snapshot tables. When retirement is approved, verify all snapshot field consumers again and handle existing JSON payloads and the column through an explicit migration/retention decision.

## 2. Consumer and ownership matrix

| Component | Current role | Retirement action |
|---|---|---|
| `POST /integration/turn` | Deprecated HTTP entry point; logs each request | Remove only after zero-usage observation and client sign-off |
| `SillyTavernIntegrationService.process_turn()` | Compatibility delegate | Remove with the route/delegate, not the whole adapter |
| `SillyTavernIntegrationService.get_context()` | Active context/history provider | Retain |
| `SillyTavernIntegrationService.get_external_turn_state()` | Active transcript-state read | Retain |
| `LegacySillyTavernTurnService` | Legacy narrative-first mutation and regeneration | Remove with deprecated route after sign-off |
| `WorldSnapshotRepository` | JSON snapshot encode/decode/restore | Remove only after no production callers remain |
| `turns.snapshot` | Nullable historical JSON payload | Preserve or explicitly migrate/clear; do not drop incidentally |
| Snapshot tests | Repository serialization and legacy regeneration contracts | Retire legacy-specific tests with implementation; retain generic repository tests only if the repository remains |

## 3. Required retirement gates

Before implementation of the removal:

1. Define and record the observation-window duration and the log query used to identify requests to the deprecated route.
2. Verify zero usage over that full window in deployed logs; repository CI cannot establish this.
3. Check supported SillyTavern extension releases, documented clients, forks and local scripts for calls to the old endpoint.
4. Confirm active clients use resolve/complete, context and external-turn-state endpoints as appropriate.
5. Re-run repository-wide searches for `process_turn`, `WorldSnapshotRepository`, `create_snapshot`, `restore_snapshot`, `load_snapshot_state` and reads/writes of `turns.snapshot`.
6. Remove the route and legacy delegate/service/tests in one focused PR, while retaining active adapter methods.
7. Make a separate, reviewed decision for existing snapshot JSON payloads and the nullable `turns.snapshot` column. Do not delete campaign history or rewrite historical turn records without an explicit retention/migration requirement.
8. Run Ruff, Python tests excluding live LLM tests, JavaScript tests and the architecture-boundary suite.

## 4. Non-goals

- No endpoint or service removal in this audit.
- No schema or data migration.
- No change to the durable native/SillyTavern turn contract.
- No change to request logging or telemetry semantics.
- No claim that production usage is currently zero.

## 5. Next step

Keep this compatibility surface isolated while the LLM prompt/context and operation-contract work proceeds. Revisit retirement only when the external usage gates above can be evidenced.
