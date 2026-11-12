# SillyTavern adapter boundary

## Ownership

- `integrations/adapters/silly_tavern/context_adapter.py` owns context/history and external transcript-state read translation.
- `integrations/adapters/silly_tavern/service.py` is a thin read-oriented façade exposing `get_context()` and `get_external_turn_state()`.
- `bootstrap/campaign_runtime.py` constructs and wires the adapter into the campaign runtime.
- `api/routers/integration.py` owns transport validation and delegates state-changing operations to `DurableNativeTurnService`.

## Active request contracts

- Context retrieval: `POST /integration/context`.
- Player intent and durable consequence commit: `POST /integration/turn/resolve`.
- Clarification/manual dice continuation: dedicated `/clarification` and `/roll` routes.
- Narrative completion/version persistence: `POST /integration/turn/complete`.
- Transcript and challenge reads: dedicated GET routes under `/integration/turn/{external_turn_id}`.

The external client must use one stable `external_turn_id` for the logical player action, including retries, clarifications and narrative versions. Completion requires this identity.

## Removed behavior

The narrative-first `POST /integration/turn` route and `LegacySillyTavernTurnService` have been removed. The adapter has no `process_turn()` method and does not own world mutation, LLM extraction, snapshot repositories, campaign-state-version repositories or transactions.

Migration 029 archives former snapshot JSON before removing the runtime `turns.snapshot` column. The archive is not part of this adapter boundary.

## Invariants

- The durable service commits consequences once before narration.
- Narrative regeneration cannot replay world operations or mechanics.
- Context/transcript reads remain campaign-scoped.
- Clarification and manual-roll submissions resume the original durable resolution.
- Keep adapter imports inward; capability services must not depend on integration adapters.
