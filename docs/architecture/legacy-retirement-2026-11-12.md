# Legacy retirement — 2026-11-12

## Decision

Campaign Manager now has one supported turn pipeline. The parallel
narrative-first mutation path has been removed rather than kept as an
indefinite compatibility mode.

## Retired in this cleanup

- `LLMWorldExtractor.extract()` and its callable façade.
- The static legacy narrative prompt builder and `legacy_prompt_sections/`.
- The legacy extraction budgets and `build_relevant_world_projection()` callback path.
- The narrative-first `POST /integration/turn` endpoint.
- `LegacySillyTavernTurnService` and the adapter's `process_turn()` method.
- `WorldSnapshotRepository`, the `TurnRecord.snapshot` field and the runtime `turns.snapshot` column.
- Tests that exclusively exercised narrative-first mutation and snapshot restoration/regeneration.

## Retained active contracts

- Native durable turn execution through `DurableNativeTurnService`.
- SillyTavern context/history and external transcript-state reads.
- `POST /integration/turn/resolve`, challenge continuation and `POST /integration/turn/complete`.
- External turn identity, transcript versioning, idempotency, revision/lease fencing and restart recovery.
- One structured `propose()` path for world consequences, with deterministic validation and mutation downstream.

## Historical data preservation

Migration 029 creates `turn_snapshot_archive`, copies every non-null legacy
snapshot JSON value with its original turn and campaign IDs, then drops the
runtime `snapshot` column from `turns`. It is safe to rerun without
duplicating archived records. The archive is inert: runtime code does not read
it and must not use it to restore or mutate campaign state. Earlier migration
history is untouched.

## Verification still required outside deterministic CI

- Run the full GitHub Actions quality gate and do not merge unless every required check is green.
- Perform the documented live SillyTavern smoke test against a disposable campaign.
- Run structured proposal quality probes against the configured Ollama model(s). These remain separate from deterministic CI.

## Next architecture work

With the legacy paths removed, the next structural priorities are:
1. extract attack-profile selection from `CombatAttackService`;
2. decompose `DurableNativeTurnService` behind its stable public façade;
3. audit `CombatEncounterService` transaction integrity before splitting it;
4. review `WorldService` dispatch and connection ownership;
5. split transport schemas by bounded context without changing OpenAPI contracts.
