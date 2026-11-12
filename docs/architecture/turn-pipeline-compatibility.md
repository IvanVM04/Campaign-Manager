# Turn pipeline contract

**Status:** one supported turn-resolution contract. The narrative-first mutation path and runtime snapshot reconciliation have been retired.

## Route-to-use-case map

| Entry point | Owner | Status | Contract |
|---|---|---|---|
| `POST /turn` | `DurableNativeTurnService.play_turn()` | Active | Durable resolution, idempotency, atomic consequence commit and recoverable narration |
| `POST /integration/turn/resolve` | `DurableNativeTurnService.prepare_external_turn()` | Active | Commits consequences before SillyTavern generates prose |
| `POST /integration/turn/complete` | `DurableNativeTurnService.complete_external_narration()` | Active | Persists narrative/version against the committed resolution; never applies consequences |
| `POST /integration/turn/clarification`, `/roll` | `DurableNativeTurnService` | Active | Resumes a persisted challenge against the original resolution |
| `GET /integration/turn/{external_turn_id}` | `SillyTavernIntegrationService.get_external_turn_state()` | Active | Reads the active external transcript version |
| `GET /integration/turn/{external_turn_id}/clarification` and `/manual-roll` | `DurableNativeTurnService` | Active | Reads durable challenge state |
| `POST /integration/context` | `SillyTavernIntegrationService.get_context()` | Active | Builds campaign context/history for the external client |

`POST /integration/turn` is removed and returns 404. There is no fallback narrative-first mutation handler.

## Active lifecycle

1. Before generation, call `POST /integration/turn/resolve` with a stable `external_turn_id`, the player's intent and context query.
2. The backend selects bounded world context, resolves supported mechanics, proposes typed consequences, validates them and commits the durable resolution atomically.
3. Generate presentation prose only after the backend returns the committed resolution evidence (or a pending clarification/manual-roll challenge).
4. Call `POST /integration/turn/complete` with the same external turn ID, player input, narrative and version.
5. For clarification/manual rolls, use the dedicated durable challenge endpoints. Do not submit the answer as a new player action.
6. Retry with the same external turn identity after generation/completion failure. Consequences must never be applied twice.

## Regeneration and historical data

Swipes/regenerations create narrative versions against one committed resolution. They do not restore old world state, rerun mechanics or replay consequences.

Migration 029 moves all non-null values from the former `turns.snapshot` column to `turn_snapshot_archive`, then removes the runtime column. The archive is intentionally inert and not referenced by runtime services. Earlier migration functions remain unchanged.

## Guardrails

- Preserve external-turn idempotency, campaign revision fencing and lease fencing.
- Keep provider calls and narration outside write transactions.
- Require a stable external turn ID on completion.
- Keep model output untrusted and validate proposals independently of prompts.
- Do not reintroduce `process_turn()`, `LegacySillyTavernTurnService`, `WorldSnapshotRepository` or snapshot restoration.
- Manual live SillyTavern smoke tests remain separate from deterministic CI.
