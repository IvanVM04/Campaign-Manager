# Turn pipeline compatibility boundaries

**Status:** compatibility boundaries documented and instrumented; legacy removal is intentionally gated on usage evidence.

This document is the source of truth for which turn pipeline owns each entry point. The application remains a single-process modular monolith. There is one supported turn-resolution contract: the durable lifecycle coordinated by `DurableNativeTurnService`.

## Route-to-use-case map

| Entry point | Owner | Status | Contract |
|---|---|---|---|
| `POST /turn` | `DurableNativeTurnService.play_turn()` | Active | Durable resolution, idempotency, atomic consequence commit, recoverable narration |
| `POST /integration/turn/resolve` | `DurableNativeTurnService.prepare_external_turn()` | Active | Commits consequences before SillyTavern generates prose |
| `POST /integration/turn/complete` | `DurableNativeTurnService.complete_external_narration()` | Active | Persists narrative/version against the committed resolution; never applies consequences |
| `POST /integration/turn/clarification`, `/roll` | `DurableNativeTurnService` | Active | Resumes a persisted challenge against the original resolution |
| `GET /integration/turn/{external_turn_id}` | `SillyTavernIntegrationService.get_external_turn_state()` | Active | Reads the active external transcript version |
| `GET /integration/turn/{external_turn_id}/clarification` and `/manual-roll` | `DurableNativeTurnService` | Active | Reads durable challenge state |
| `POST /integration/context` | `SillyTavernIntegrationService.get_context()` | Active | Builds campaign context/history for the external client |
| `POST /integration/turn` | `SillyTavernIntegrationService.process_turn()` | Deprecated compatibility | Legacy narrative-first extraction and snapshot reconciliation; weaker guarantees and a separate mutation path |
| In-process `CampaignTurnService.play_turn()` / `submit_manual_roll()` | `CampaignTurnService` | Compatibility-only | Not used by the native HTTP route; retained for older in-process callers and regression coverage |

## Active SillyTavern contract

The current extension calls `/integration/turn/resolve` before generation and `/integration/turn/complete` after generation. It does not call `POST /integration/turn`. Swipes/regenerations create narrative versions against the same committed resolution; they do not restore snapshots, rerun mechanics or replay consequences.

`SillyTavernIntegrationService` remains in the active runtime because it supplies campaign context/history and external transcript-state reads. Its `process_turn()` method is a compatibility delegate to `LegacySillyTavernTurnService`; that collaborator owns the deprecated narrative-first extraction, snapshot reconciliation and legacy version persistence. The presence of either service in the runtime graph does not make that method part of the active turn lifecycle.

## Compatibility and deprecation policy

- `POST /integration/turn` is marked deprecated in OpenAPI and emits a structured warning for each request, including campaign ID and external turn ID. This is usage telemetry, not a hard cutoff.
- `CampaignTurnService` remains in the runtime graph for compatibility, but its public turn-execution methods emit structured warnings. No new gameplay behavior should be implemented there.
- No removal date is set. Do not remove either compatibility surface until downstream/in-process callers have been checked and observed usage is zero for an agreed migration window.
- Keep the old snapshot repository and legacy reconciliation code while the legacy endpoint remains supported. Do not route the active durable flow through snapshot restoration.
- The compatibility endpoint must not be presented as equivalent to the durable flow. Its successful response does not prove that it has the same commit-before-narration, challenge-recovery or no-replay guarantees.

## Migration for old SillyTavern clients

1. Before generation, call `POST /integration/turn/resolve` with the stable `external_turn_id`, player input and context query.
2. Generate prose only after the backend returns the committed resolution evidence (or a pending clarification/manual-roll challenge).
3. After generation, call `POST /integration/turn/complete` with the original player input, narrative and version.
4. For clarification/manual rolls, use the dedicated durable challenge endpoints. Do not submit the answer as a new player action.
5. Keep the same external turn identity when retrying after a generation or completion failure.

## Removal prerequisites

Before deleting `POST /integration/turn`, `SillyTavernIntegrationService.process_turn()` or snapshot reconciliation:

- inspect release/deployment notes and any external extension forks or scripts;
- inspect structured warning logs over a documented migration window;
- confirm the current extension and any supported clients use only the durable endpoints;
- identify and migrate any in-process imports of `CampaignTurnService` and its compatibility proxy;
- preserve existing campaign history; do not run a destructive data migration as part of endpoint retirement;
- remove code and tests in a separate PR after explicit compatibility sign-off.

The `CampaignTurnService` compatibility implementation has since been removed after a repository-wide consumer audit. This document now tracks only the still-supported SillyTavern compatibility route and snapshot reconciliation.
